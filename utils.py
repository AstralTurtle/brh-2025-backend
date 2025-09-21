import logging
from typing import Any, Dict, List

from apkit.server.types import ActorKey

from database import Database
from settings import get_settings

# Add logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

settings = get_settings()
users_db = Database("users.json")


def paginate_data(
    data: List[Dict[str, Any]], page: int = 1, limit: int = 10
) -> Dict[str, Any]:
    """
    Simple pagination utility for lists of data

    Args:
        data: List of items to paginate
        page: Page number (starts from 1)
        limit: Items per page

    Returns:
        Dictionary with paginated data and metadata
    """
    # Validate inputs
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10
    if limit > 100:  # Max limit to prevent abuse
        limit = 100

    # Calculate pagination
    total_items = len(data)
    total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
    start_index = (page - 1) * limit
    end_index = start_index + limit

    # Get paginated items
    paginated_items = data[start_index:end_index]

    return {
        "data": paginated_items,
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total_items,
            "items_per_page": limit,
            "has_next": page < total_pages,
            "has_previous": page > 1,
            "start_item": start_index + 1 if total_items > 0 else 0,
            "end_item": min(end_index, total_items),
        },
    }


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
