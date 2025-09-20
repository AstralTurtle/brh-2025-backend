import logging
from typing import List

from apkit.server.types import ActorKey

from database import Database
from settings import get_settings

# Add logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

settings = get_settings()
users_db = Database("users.json")


async def get_keys_for_actor(actor_id: str) -> List[ActorKey]:
    """Get cryptographic keys for an actor - required by APKit"""
    try:
        logger.debug(f"[DEBUG] get_keys_for_actor called with: {actor_id}")

        # Find the user in your database
        user_doc = users_db.find_one_raw({"id": actor_id})
        logger.debug(f"[DEBUG] Found user_doc: {bool(user_doc)}")

        if not user_doc or "_auth" not in user_doc:
            logger.debug(f"[DEBUG] No user or auth data found for {actor_id}")
            # Let's also try searching by different formats
            logger.debug(
                "[DEBUG] Trying to find user with different actor_id formats..."
            )

            # Try without protocol
            if actor_id.startswith("http://") or actor_id.startswith("https://"):
                alt_id = actor_id.replace("http://", "").replace("https://", "")
                user_doc = users_db.find_one_raw({"id": alt_id})
                logger.debug(f"[DEBUG] Trying alt_id {alt_id}: found={bool(user_doc)}")

            if not user_doc:
                return []

        # Extract the private key from auth data
        private_key_pem = user_doc["_auth"]["private_key"]
        key_id = user_doc["publicKey"]["id"]

        logger.debug(f"[DEBUG] Returning key with id: {key_id}")

        # Return as ActorKey format expected by APKit
        return [
            ActorKey(
                id=key_id,  # The key ID
                private_key_pem=private_key_pem,
            )
        ]

    except Exception as e:
        logger.error(f"[DEBUG] Error getting keys for actor {actor_id}: {e}")
        import traceback

        traceback.print_exc()
        return []
