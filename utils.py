from apkit.server.types import ActorKey
from cryptography.hazmat.primitives import serialization

from database import Database
from settings import get_settings

settings = get_settings()
users_db = Database("users.json")

# Load the server's private key from settings
server_private_key = serialization.load_pem_private_key(
    settings.private_key.encode("utf-8"),
    password=None,
)


async def get_keys_for_actor(identifier: str) -> list[ActorKey]:
    print(f"[DEBUG] Getting keys for actor: {identifier}")

    # Try to find user by ID first
    user_doc = users_db.find_one_raw({"id": identifier})
    print(f"[DEBUG] Found user by ID: {user_doc is not None}")

    # If not found by ID, try by preferredUsername
    if not user_doc:
        # Extract username from identifier if it's a URL
        if "/" in identifier:
            username = identifier.split("/")[-1]
            user_doc = users_db.find_one_raw({"preferredUsername": username})
            print(
                f"[DEBUG] Found user by username '{username}': {user_doc is not None}"
            )

    if user_doc:
        print(f"[DEBUG] User found: {user_doc.get('preferredUsername')}")
        if user_doc.get("_auth") and user_doc["_auth"].get("private_key"):
            try:
                # Use the user's private key for signing
                user_private_key = serialization.load_pem_private_key(
                    user_doc["_auth"]["private_key"].encode("utf-8"),
                    password=None,
                )

                public_key_id = user_doc["publicKey"]["id"]
                print(
                    f"[DEBUG] Successfully loaded keys for {identifier}, public key ID: {public_key_id}"
                )

                return [ActorKey(key_id=public_key_id, private_key=user_private_key)]
            except Exception as e:
                print(f"[DEBUG] Error loading private key: {e}")
        else:
            print("[DEBUG] No _auth or private_key found in user doc")
    else:
        print(f"[DEBUG] No user found for identifier: {identifier}")

    print(f"[DEBUG] No keys found for actor: {identifier}")
    return []
