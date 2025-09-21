import logging

from apkit.models import CryptographicKey, Person
from apkit.server import SubRouter
from apkit.server.responses import ActivityResponse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pyld import jsonld

from database import Database
from models import CreateUser, LoginRequest
from routes.auth import get_current_user, hash_password
from settings import get_settings

logger = logging.getLogger(__name__)

router = SubRouter(prefix="/users")
settings = get_settings()
users_db = Database("users.json")

# ActivityPub JSON-LD context
ACTIVITYPUB_CONTEXT = {
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1",
    ]
}


def json_to_person(user_doc: dict) -> Person:
    """Convert JSON-LD document to Person object using pyld"""
    # Remove auth data if present
    clean_doc = user_doc.copy()
    if "_auth" in clean_doc:
        del clean_doc["_auth"]

    # Expand JSON-LD to handle compact forms
    try:
        expanded = jsonld.expand(clean_doc)
        if expanded:
            expanded_doc = expanded[0]
        else:
            expanded_doc = clean_doc
    except:  # noqa: E722
        expanded_doc = clean_doc

    # Handle publicKey reconstruction
    public_key = None
    if "publicKey" in clean_doc:
        pk_data = clean_doc["publicKey"]
        public_key = CryptographicKey(
            id=pk_data["id"],
            owner=pk_data["owner"],
            publicKeyPem=pk_data["publicKeyPem"],
        )

    return Person(
        id=clean_doc["id"],
        type=clean_doc.get("type", "Person"),
        preferredUsername=clean_doc["preferredUsername"],
        name=clean_doc.get("name", ""),
        summary=clean_doc.get("summary", ""),
        inbox=clean_doc["inbox"],
        outbox=clean_doc["outbox"],
        followers=clean_doc.get("followers"),
        following=clean_doc.get("following"),
        publicKey=public_key,
    )


@router.post("/create")
async def create_user(user_data: CreateUser):
    try:
        # Check if user exists
        existing_user = users_db.find_one_raw({"preferredUsername": user_data.username})
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")

        # Generate key pair
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Create user ID and public key
        user_id = f"https://{settings.host}/users/{user_data.username}"
        public_key_id = f"{user_id}#main-key"

        # Hash password with salt
        password_hash, salt = hash_password(user_data.password)

        # Create proper ActivityPub JSON-LD document
        user_doc = {
            "@context": ACTIVITYPUB_CONTEXT["@context"],
            "id": user_id,
            "type": "Person",
            "preferredUsername": user_data.username,
            "name": user_data.display_name,
            "summary": user_data.summary,
            "inbox": f"{user_id}/inbox",
            "outbox": f"{user_id}/outbox",
            "followers": f"{user_id}/followers",
            "following": f"{user_id}/following",
            "publicKey": {
                "id": public_key_id,
                "owner": user_id,
                "publicKeyPem": public_pem.decode("utf-8"),
            },
            "_auth": {
                "password_hash": password_hash,
                "salt": salt,
                "private_key": private_pem.decode("utf-8"),
            },
        }

        # Compact the JSON-LD for storage (optional)
        try:
            compacted = jsonld.compact(user_doc, ACTIVITYPUB_CONTEXT)
            users_db.insert_raw(compacted)
        except:
            users_db.insert_raw(user_doc)

        return JSONResponse(
            {"message": "User created successfully", "user_id": user_id},
            status_code=201,
        )

    except HTTPException:
        raise HTTPException(status_code=502, detail="Service Unavailable")

    except Exception as e:
        print(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/login")
async def login_user(login_data: LoginRequest):
    try:
        # Find user document
        user_doc = users_db.find_one_raw({"preferredUsername": login_data.username})

        if not user_doc or "_auth" not in user_doc:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Use the proper hash_password function with salt
        auth_data = user_doc["_auth"]
        from routes.auth import verify_password

        if not verify_password(
            login_data.password, auth_data["password_hash"], auth_data["salt"]
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create JWT token
        from routes.auth import create_jwt_token

        token = create_jwt_token(user_doc["id"])

        return JSONResponse(
            {"access_token": token, "token_type": "bearer", "user_id": user_doc["id"]}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during login: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{username}")
async def get_user(username: str):
    try:
        user_doc = users_db.find_one_raw({"preferredUsername": username})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        # Remove auth data and ensure proper JSON-LD context
        clean_doc = user_doc.copy()
        if "_auth" in clean_doc:
            del clean_doc["_auth"]

        # Ensure proper ActivityPub context
        if "@context" not in clean_doc:
            clean_doc["@context"] = ACTIVITYPUB_CONTEXT["@context"]

        # Return raw JSON-LD with proper headers
        return JSONResponse(
            content=clean_doc, headers={"Content-Type": "application/activity+json"}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{host}/users/{name}")
async def get_user_by_id(host: str, name: str):
    id = f"https://{host}/users/{name}"
    logger.info(f"[DEBUG] Looking for user with ID: {id}")

    try:
        user_doc = users_db.find_one_raw({"id": id})
        if not user_doc:
            logger.warning(f"[DEBUG] User not found with ID: {id}")
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(
            f"[DEBUG] Found user: {user_doc.get('preferredUsername', 'unknown')} with ID: {id}"
        )

        clean_doc = user_doc.copy()
        if "_auth" in clean_doc:
            del clean_doc["_auth"]

        # Ensure proper ActivityPub context
        if "@context" not in clean_doc:
            clean_doc["@context"] = ACTIVITYPUB_CONTEXT["@context"]

        # Return raw JSON-LD with proper headers
        return JSONResponse(
            content=clean_doc, headers={"Content-Type": "application/activity+json"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DEBUG] Error fetching user with ID {id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/me")
async def get_current_user_profile(current_user: str = Depends(get_current_user)):
    """Get the authenticated user's profile"""
    try:
        user_doc = users_db.find_one_raw({"id": current_user})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        # Convert to Person object and return as ActivityResponse
        actor = json_to_person(user_doc)
        return ActivityResponse(actor)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting current user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
