import hashlib

from apkit.models import CryptographicKey, Person
from apkit.server import SubRouter
from apkit.server.responses import ActivityResponse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from database import Database
from models import CreateUser, LoginRequest
from routes.auth import get_current_user, hash_password
from settings import get_settings

router = SubRouter(prefix="/users")
settings = get_settings()
users_db = Database("users.json")


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
        user_id = f"{settings.host}/users/{user_data.username}"
        public_key_id = f"{user_id}#main-key"

        public_key_obj = CryptographicKey(
            id=public_key_id,
            owner=user_id,
            publicKeyPem=public_pem.decode("utf-8"),
        )

        # Hash password with salt using the improved function
        password_hash, salt = hash_password(user_data.password)

        # Create ActivityPub User object
        actor = Person(
            id=user_id,
            type="Person",
            preferredUsername=user_data.username,
            name=user_data.display_name,
            summary=user_data.summary,
            inbox=f"{user_id}/inbox",
            outbox=f"{user_id}/outbox",
            followers=f"{user_id}/followers",
            following=f"{user_id}/following",
            publicKey=public_key_obj,
        )

        # Use to_json() to get proper ActivityPub JSON-LD format
        user_doc = actor.to_json()
        # Add authentication fields to the document
        user_doc["_auth"] = {
            "password_hash": password_hash,
            "salt": salt,
            "private_key": private_pem.decode("utf-8"),
        }

        users_db.insert_raw(user_doc)

        return JSONResponse(
            {"message": "User created successfully", "user_id": user_id},
            status_code=201,
        )

    except HTTPException:
        raise
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

        password_hash = hashlib.sha256(login_data.password.encode()).hexdigest()

        if user_doc["_auth"]["password_hash"] != password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return JSONResponse({"message": "Login successful", "user_id": user_doc["id"]})

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

        # Remove auth data before returning ActivityPub object
        if "_auth" in user_doc:
            user_doc = user_doc.copy()  # Don't modify the original
            del user_doc["_auth"]

        # Return as ActivityResponse for proper headers
        actor = Person(**user_doc)
        return ActivityResponse(actor)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/me")
async def get_current_user_profile(current_user: str = Depends(get_current_user)):
    """Get the authenticated user's profile"""
    try:
        user_doc = users_db.find_one_raw({"id": current_user})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        # Remove auth data before returning ActivityPub object
        if "_auth" in user_doc:
            user_doc = user_doc.copy()  # Don't modify the original
            del user_doc["_auth"]

        return user_doc

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting current user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
