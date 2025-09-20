import uuid

from apkit.models import CryptographicKey
from apkit.server import SubRouter
from apkit.server.responses import ActivityResponse
from cryptography.hazmat.primitives import serialization as crypto_serialization
from fastapi import Depends
from fastapi.responses import JSONResponse
from pydantic_sqlite import DataBase

from models import CreateUser, User
from routes.auth import get_current_user, hash_password
from settings import get_settings

db: DataBase = DataBase("users.db")
auth_db: DataBase = DataBase("auth.db")
router = SubRouter(prefix="/users")

settings = get_settings()


@router.post("/create")
def create_user(user: CreateUser):
    user_id = str(uuid.uuid4())

    password_hash, salt = hash_password(user.password)

    private_key_str = settings.private_key

    private_key = crypto_serialization.load_pem_private_key(
        private_key_str.encode("utf-8"), password=None
    )

    public_key_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=crypto_serialization.Encoding.PEM,
            format=crypto_serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    host = settings.host

    actor = User(
        id=f"https://{host}/users/{user_id}",
        name=user.display_name,
        preferredUsername=user.username,
        summary=user.summary,
        inbox=f"https://{host}/users/{user_id}/inbox",
        outbox=f"https://{host}/users/{user_id}/outbox",
        publicKey=CryptographicKey(
            id=f"https://{host}/users/{user_id}#main-key",
            owner=f"https://{host}/users/{user_id}",
            publicKeyPem=public_key_pem,
        ),
    )

    db.save(actor)

    auth_data = {
        "user_id": actor.id,
        "password_hash": password_hash,
        "salt": salt,
        "created_at": str(uuid.uuid4()),
    }
    auth_db.save("auth_data", auth_data)

    return actor


@router.get("/{identifier}")
async def get_actor_endpoint(identifier: str):
    host = settings.host
    actor_id = f"https://{host}/users/{identifier}"
    try:
        actor = db.select(User, where={"id": actor_id})
        if actor:
            return ActivityResponse(actor[0])
    except Exception as e:
        print(f"Error querying database: {e}")

    return JSONResponse({"error": "Not Found"}, status_code=404)


@router.get("/named/{name}")
async def get_actor_named(name: str):
    try:
        actors = db.select(User, where={"preferredUsername": name})
        if actors:
            return ActivityResponse(actors[0])
    except Exception as e:
        print(f"Error querying database: {e}")

    return JSONResponse({"error": "User not found"}, status_code=404)


@router.get("/me")
async def get_current_user_profile(current_user: str = Depends(get_current_user)):
    """Get the authenticated user's profile"""
    try:
        actors = db.select(User, where={"id": current_user})
        if actors:
            return ActivityResponse(actors[0])
    except Exception as e:
        print(f"Error getting current user: {e}")

    return JSONResponse({"error": "User not found"}, status_code=404)
