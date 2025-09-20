import uuid
from apkit.server import SubRouter
from apmodel import Person
from models import CreateUser
from settings import get_settings
from cryptography.hazmat.primitives import serialization as crypto_serialization
from pydantic_sqlite import DataBase

db: DataBase = DataBase("users.db")

router = SubRouter(prefix="/users")

settings = get_settings()

router.post("/create")
def create_user(user: CreateUser):
    user_id = str(uuid.uuid4())
    
    
    private_key = settings.private_key
    
    public_key_pem = private_key.public_key().public_bytes(
        encoding=crypto_serialization.Encoding.PEM,
        format=crypto_serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    host = settings.host
    
    actor = Person(
        id=f"https://{settings}/users/{user_id}",
        name=user.display_name,
        preferredUsername=user.username,
        summary=user.summary,
        inbox=f"https://{host}/users/{user_id}/inbox",
        outbox=f"https://{host}/users/{user_id}/outbox",
        publicKey=CryptographicKey(
            id=f"https://{host}/users/{user_id}#main-key",
            owner=f"https://{host}/users/{user_id}",
            publicKeyPem=public_key_pem
        )
    )
    
    db.save(actor)
    
    
    
    return actor