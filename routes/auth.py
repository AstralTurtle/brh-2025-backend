import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from apkit.server import SubRouter
from cryptography.hazmat.primitives import serialization as crypto_serialization
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import Database
from models import LoginRequest
from settings import get_settings

# Use TinyDB instead of pydantic-sqlite
users_db = Database("users.json")
router = SubRouter(prefix="/auth")
security = HTTPBearer()
settings = get_settings()


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Hash password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    )
    return password_hash.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify password against hash"""
    password_hash, _ = hash_password(password, salt)
    return password_hash == hashed


def create_jwt_token(user_id: str) -> str:
    """Create JWT token for user"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }

    # Use the private key from settings for signing
    private_key = crypto_serialization.load_pem_private_key(
        settings.private_key.encode("utf-8"), password=None
    )

    return jwt.encode(payload, private_key, algorithm="RS256")


def verify_jwt_token(token: str) -> str:
    """Verify JWT token and return user_id"""
    try:
        private_key = crypto_serialization.load_pem_private_key(
            settings.private_key.encode("utf-8"), password=None
        )
        public_key = private_key.public_key()

        payload = jwt.decode(token, public_key, algorithms=["RS256"])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Dependency to get current authenticated user"""
    return verify_jwt_token(credentials.credentials)


@router.post("/login")
async def login(login_request: LoginRequest):
    """Login endpoint"""
    try:
        # Query user by username using TinyDB
        user_doc = users_db.find_one_raw({"preferredUsername": login_request.username})
        if not user_doc:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check if auth data exists in the user document
        if "_auth" not in user_doc:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        auth_data = user_doc["_auth"]

        # Verify password using the stored salt and hash
        if not verify_password(
            login_request.password,
            auth_data["password_hash"],
            auth_data.get("salt", ""),
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create JWT token
        token = create_jwt_token(user_doc["id"])

        return JSONResponse(
            {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user_doc["id"],
                    "username": user_doc["preferredUsername"],
                    "display_name": user_doc.get("name", ""),
                },
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/verify")
async def verify_token(current_user: str = Depends(get_current_user)):
    """Verify token endpoint"""
    try:
        user_doc = users_db.find_one_raw({"id": current_user})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        return JSONResponse(
            {
                "valid": True,
                "user": {
                    "id": user_doc["id"],
                    "username": user_doc["preferredUsername"],
                    "display_name": user_doc.get("name", ""),
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Verify error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
