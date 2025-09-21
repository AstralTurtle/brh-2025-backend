import logging
import uuid

from apkit.models import CryptographicKey, Person
from apkit.server import SubRouter
from apkit.server.responses import ActivityResponse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pyld import jsonld

from database import Database
from follow_activity import follow_wrapper
from models import CreateUser, LoginRequest
from routes.auth import get_current_user, hash_password
from settings import get_settings

# Use the routes.user logger that's configured in main.py
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

        # return JSONResponse(
        #     {"message": "User created successfully", "user_id": user_id},
        #     status_code=201,
        # )

        # Create JWT token
        from routes.auth import create_jwt_token

        token = create_jwt_token(user_id)

        return JSONResponse(
            {"access_token": token, "token_type": "bearer", "user_id": user_id}
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


@router.get("/search")
async def search_users(q: str, limit: int = 20):
    """
    Search for users by name.
    - If query contains '@', performs webfinger lookup for external users
    - Otherwise searches local users by preferredUsername or name
    - limit: Maximum number of results to return (default: 20)
    """
    try:
        results = []
        logger.info(f"Starting search for query: {q}, limit: {limit}")

        # If query contains '@', treat as webfinger lookup
        if "@" in q:
            logger.info(f"Performing webfinger lookup for: {q}")
            try:
                import requests

                # Parse the webfinger address (user@domain)
                username, domain = q.split("@", 1)
                webfinger_url = (
                    f"https://{domain}/.well-known/webfinger?resource=acct:{q}"
                )

                logger.info(f"Webfinger URL: {webfinger_url}")

                # Perform webfinger lookup using requests
                response = requests.get(
                    webfinger_url,
                    headers={"Accept": "application/jrd+json"},
                    timeout=10,
                )

                if response.status_code == 200:
                    webfinger_data = response.json()
                    logger.info("Webfinger response received")

                    # Find the ActivityPub actor link
                    actor_url = None
                    if "links" in webfinger_data:
                        for link in webfinger_data["links"]:
                            if (
                                link.get("rel") == "self"
                                and link.get("type") == "application/activity+json"
                            ):
                                actor_url = link.get("href")
                                logger.info(f"Found actor URL: {actor_url}")
                                break

                    if actor_url:
                        # Fetch the actor profile using manual HTTP request
                        actor_response = requests.get(
                            actor_url,
                            headers={
                                "Accept": "application/activity+json",
                                "User-Agent": "ActivityPub-Client/1.0",
                            },
                            timeout=10,
                        )

                        if actor_response.status_code == 200:
                            actor_data = actor_response.json()
                            logger.info(
                                f"Actor data received for: {actor_data.get('preferredUsername')}"
                            )

                            # Extract icon/avatar information
                            icon = None
                            if "icon" in actor_data:
                                icon_data = actor_data["icon"]
                                # Handle both single icon and array of icons
                                if isinstance(icon_data, list) and len(icon_data) > 0:
                                    icon = icon_data[0].get("url")
                                elif isinstance(icon_data, dict):
                                    icon = icon_data.get("url")

                            # Clean up the response to match our format
                            user_result = {
                                "id": actor_data.get("id"),
                                "type": actor_data.get("type", "Person"),
                                "preferredUsername": actor_data.get("preferredUsername"),
                                "name": actor_data.get("name", ""),
                                "summary": actor_data.get("summary", ""),
                                "inbox": actor_data.get("inbox"),
                                "outbox": actor_data.get("outbox"),
                                "followers": actor_data.get("followers"),
                                "following": actor_data.get("following"),
                                "is_local": False,
                            }
                            
                            # Add icon if it exists
                            if icon:
                                user_result["icon"] = icon
                                logger.info(f"Added icon for user: {icon}")

                            results.append(user_result)
                            logger.info(
                                f"Added webfinger user to results: {user_result.get('preferredUsername')}"
                            )
                        else:
                            logger.warning(
                                f"Failed to fetch actor profile, status: {actor_response.status_code}"
                            )
                    else:
                        logger.warning(
                            "No ActivityPub actor URL found in webfinger links"
                        )
                else:
                    logger.warning(
                        f"Webfinger lookup failed with status: {response.status_code}"
                    )

            except Exception as webfinger_error:
                logger.warning(f"Webfinger lookup failed for {q}: {webfinger_error}")
                # Continue to search local users if webfinger fails

        # Search local users (always search local, even if webfinger was attempted)
        logger.info("Starting local user search")
        local_query = q.lower()

        try:
            all_users = users_db.find_raw({})
            logger.info("Retrieved users from database")

            for i, user_doc in enumerate(all_users):
                # Skip if we've reached the limit
                if len(results) >= limit:
                    logger.info(f"Reached limit of {limit} results, breaking")
                    break

                # Skip if no preferredUsername (invalid user)
                if "preferredUsername" not in user_doc:
                    continue

                username = user_doc.get("preferredUsername", "").lower()
                display_name = user_doc.get("name", "").lower()

                # Match by preferredUsername or display name
                if local_query in username or local_query in display_name:
                    # Clean the user data (remove auth info)
                    clean_doc = user_doc.copy()
                    if "_auth" in clean_doc:
                        del clean_doc["_auth"]

                    # Add is_local flag
                    clean_doc["is_local"] = True

                    # Ensure proper context
                    if "@context" not in clean_doc:
                        clean_doc["@context"] = ACTIVITYPUB_CONTEXT["@context"]

                    results.append(clean_doc)

        except Exception as local_search_error:
            logger.error(f"Error in local search: {local_search_error}")
            raise

        # Trim results to limit if necessary
        results = results[:limit]
        logger.info(f"Returning {len(results)} results")

        return JSONResponse(
            {
                "query": q,
                "limit": limit,
                "results_count": len(results),
                "results": results,
            },
            headers={"Content-Type": "application/json"},
        )

    except Exception as e:
        logger.error(f"Error searching users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/me")
async def get_current_user_profile(current_user: str = Depends(get_current_user)):
    """Get the authenticated user's profile"""

    try:
        user_doc = users_db.find_one_raw({"id": current_user})
        if not user_doc:
            raise HTTPException(status_code=404, detail="user not found")

        # Convert to Person object and return as ActivityResponse
        actor = json_to_person(user_doc)
        return ActivityResponse(actor)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{username}")
async def get_user(username: str):
    try:
        # First try to find user locally
        user_doc = users_db.find_one_raw({"preferredUsername": username})

        if user_doc:
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

        # If not found locally, try webfinger lookup for external users
        # Check if username contains @ (indicating external user)
        if "@" in username:
            try:
                import requests

                # Parse the webfinger address (user@domain)
                username, domain = username.split("@", 1)
                webfinger_url = (
                    f"https://{domain}/.well-known/webfinger?resource=acct:{username}"
                )

                logger.info(f"Webfinger URL: {webfinger_url}")

                # Perform webfinger lookup using requests
                response = requests.get(
                    webfinger_url,
                    headers={"Accept": "application/jrd+json"},
                    timeout=10,
                )

                if response.status_code == 200:
                    webfinger_data = response.json()
                    logger.info("Webfinger response received")

                    # Find the ActivityPub actor link
                    actor_url = None
                    if "links" in webfinger_data:
                        for link in webfinger_data["links"]:
                            if (
                                link.get("rel") == "self"
                                and link.get("type") == "application/activity+json"
                            ):
                                actor_url = link.get("href")
                                logger.info(f"Found actor URL: {actor_url}")
                                break

                    if actor_url:
                        # Fetch the actor profile using manual HTTP request
                        actor_response = requests.get(
                            actor_url,
                            headers={
                                "Accept": "application/activity+json",
                                "User-Agent": "ActivityPub-Client/1.0",
                            },
                            timeout=10,
                        )

                        if actor_response.status_code == 200:
                            actor_data = actor_response.json()
                            logger.info(
                                f"Actor data received for: {actor_data.get('preferredUsername')}"
                            )

                            # Return raw JSON-LD with proper headers
                            return JSONResponse(
                                content=actor_data,
                                headers={"Content-Type": "application/activity+json"},
                            )
                        else:
                            logger.warning(
                                f"Failed to fetch actor profile, status: {actor_response.status_code}"
                            )
                    else:
                        logger.warning(
                            "No ActivityPub actor URL found in webfinger links"
                        )
                else:
                    logger.warning(
                        f"Webfinger lookup failed with status: {response.status_code}"
                    )

            except Exception as webfinger_error:
                logger.warning(
                    f"Webfinger lookup failed for {username}: {webfinger_error}"
                )
                # Fall through to 404

        # If we get here, user not found locally or via webfinger
        raise HTTPException(status_code=404, detail="User not found")

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


@router.get("/{username}/followers")
async def get_user_followers(username: str):
    """Get followers for a user"""
    try:
        user_doc = users_db.find_one_raw({"preferredUsername": username})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        followers = await follow_wrapper.get_followers(user_doc["id"])

        return JSONResponse(
            {
                "user": user_doc["id"],
                "followers_count": len(followers),
                "followers": followers,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting followers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{username}/following")
async def get_user_following(username: str):
    """Get users that a user is following"""
    try:
        user_doc = users_db.find_one_raw({"preferredUsername": username})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        following = await follow_wrapper.get_following(user_doc["id"])

        return JSONResponse(
            {
                "user": user_doc["id"],
                "following_count": len(following),
                "following": following,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting following: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{username}/follow")
async def follow_user(username: str, current_user: str = Depends(get_current_user)):
    """Follow a user"""
    try:
        target_user = users_db.find_one_raw({"preferredUsername": username})
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if already following
        is_already_following = await follow_wrapper.is_following(
            current_user, target_user["id"]
        )
        if is_already_following:
            return JSONResponse(
                {"message": "Already following this user"}, status_code=200
            )

        # Store the follow relationship
        activity_id = f"https://{settings.host}/activities/follow-{uuid.uuid4()}"
        await follow_wrapper.store_follow_relationship(
            current_user,
            target_user["id"],
            activity_id,
            "accepted",  # For local follows, auto-accept
        )

        return JSONResponse(
            {
                "message": "Successfully followed user",
                "follower": current_user,
                "following": target_user["id"],
            },
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error following user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{username}/follow")
async def unfollow_user(username: str, current_user: str = Depends(get_current_user)):
    """Unfollow a user"""
    try:
        target_user = users_db.find_one_raw({"preferredUsername": username})
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Remove the follow relationship
        follow_wrapper.follows_db.delete(
            {"follower": current_user, "following": target_user["id"]}
        )

        return JSONResponse(
            {
                "message": "Successfully unfollowed user",
                "follower": current_user,
                "following": target_user["id"],
            },
            status_code=200,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error unfollowing user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{username}/follow-status/{target_username}")
async def check_follow_status(username: str, target_username: str):
    """Check if one user is following another"""
    try:
        user_doc = users_db.find_one_raw({"preferredUsername": username})
        target_doc = users_db.find_one_raw({"preferredUsername": target_username})

        if not user_doc or not target_doc:
            raise HTTPException(status_code=404, detail="User not found")

        is_following = await follow_wrapper.is_following(
            user_doc["id"], target_doc["id"]
        )

        return JSONResponse(
            {
                "follower": user_doc["id"],
                "following": target_doc["id"],
                "is_following": is_following,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error checking follow status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
