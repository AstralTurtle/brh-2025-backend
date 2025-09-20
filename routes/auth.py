import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from apkit.server import SubRouter
from cryptography.hazmat.primitives import serialization as crypto_serialization
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic_sqlite import DataBase

from models import LoginRequest, User
from settings import get_settings

db: DataBase = DataBase("auth.db")
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
        # Query user by username
        users = db.select(User, where={"preferredUsername": login_request.username})
        if not users:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user = users[0]

        # Get stored password hash and salt from database
        # You'll need to store these when creating users
        auth_records = db.select("auth_data", where={"user_id": user.id})
        if not auth_records:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        auth_data = auth_records[0]

        # Verify password
        if not verify_password(
            login_request.password, auth_data["password_hash"], auth_data["salt"]
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create JWT token
        token = create_jwt_token(user.id)

        return JSONResponse(
            {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user.id,
                    "username": user.preferredUsername,
                    "display_name": user.name,
                },
            }
        )

    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/verify")
async def verify_token(current_user: str = Depends(get_current_user)):
    """Verify token endpoint"""
    try:
        users = db.select(User, where={"id": current_user})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")

        user = users[0]
        return JSONResponse(
            {
                "valid": True,
                "user": {
                    "id": user.id,
                    "username": user.preferredUsername,
                    "display_name": user.name,
                },
            }
        )
    except Exception as e:
        print(f"Verify error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
