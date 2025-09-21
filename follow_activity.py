from datetime import datetime
from typing import Optional

from apkit.client.asyncio.client import ActivityPubClient
from apkit.models import Actor as APKitActor
from apkit.models import Follow, Reject
from apkit.server.types import Context
from fastapi import Response
from fastapi.responses import JSONResponse

from database import Database
from settings import get_settings

settings = get_settings()
follows_db = Database("follows.json")
users_db = Database("users.json")


class FollowActivityWrapper:
    """Wrapper class for handling Follow activities"""

    def __init__(self):
        self.follows_db = follows_db
        self.users_db = users_db

    async def resolve_actor(self, actor_ref) -> Optional[APKitActor]:
        """Resolve an actor reference to an Actor object"""
        try:
            if isinstance(actor_ref, str):
                async with ActivityPubClient() as client:
                    return await client.actor.fetch(actor_ref)
            elif isinstance(actor_ref, APKitActor):
                return actor_ref
            return None
        except Exception as e:
            print(f"Error resolving actor: {e}")
            return None

    async def store_follow_relationship(
        self,
        follower_id: str,
        following_id: str,
        activity_id: str,
        status: str = "pending",
    ):
        """Store a follow relationship in the database"""
        try:
            follow_record = {
                "id": activity_id,
                "follower": follower_id,
                "following": following_id,
                "status": status,  # pending, accepted, rejected
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }

            # Check if relationship already exists
            existing = self.follows_db.find_one_raw(
                {"follower": follower_id, "following": following_id}
            )

            if existing:
                # Update existing relationship
                self.follows_db.update(
                    {"follower": follower_id, "following": following_id},
                    {"status": status, "updated_at": follow_record["updated_at"]},
                )
            else:
                # Create new relationship
                self.follows_db.insert_raw(follow_record)

            print(
                f"[DEBUG] Follow relationship stored: {follower_id} -> {following_id} ({status})"
            )

        except Exception as e:
            print(f"Error storing follow relationship: {e}")

    async def check_follow_policy(self, follower_id: str, following_id: str) -> str:
        """Check if a follow request should be auto-accepted, auto-rejected, or require manual approval"""
        try:
            # Get the target user's settings
            target_user = self.users_db.find_one_raw({"id": following_id})
            if not target_user:
                return "reject"  # Can't follow non-existent user

            # Check for blocked users (if you implement blocking)
            # blocked_users = target_user.get("blocked_users", [])
            # if follower_id in blocked_users:
            #     return "reject"

            # For now, auto-accept all follow requests
            # You can customize this logic based on your needs
            return "accept"

        except Exception as e:
            print(f"Error checking follow policy: {e}")
            return "reject"

    async def handle_follow_request(
        self, ctx: Context, follow_activity: Follow
    ) -> Response:
        """Handle an incoming follow request"""
        try:
            print(
                f"[DEBUG] Follow request received: {follow_activity.actor} -> {follow_activity.object}"
            )

            # Resolve the follower actor
            follower_actor = await self.resolve_actor(follow_activity.actor)
            if not follower_actor:
                return JSONResponse(
                    {"error": "Could not resolve follower actor"}, status_code=400
                )

            follower_id = str(follow_activity.actor)
            following_id = str(follow_activity.object)

            # Check if the target user exists in our system
            target_user = self.users_db.find_one_raw({"id": following_id})
            if not target_user:
                return JSONResponse({"error": "Target user not found"}, status_code=404)

            # Store the follow relationship as pending
            await self.store_follow_relationship(
                follower_id, following_id, follow_activity.id, "pending"
            )

            # Check follow policy
            policy_decision = await self.check_follow_policy(follower_id, following_id)

            if policy_decision == "accept":
                return await self.accept_follow_request(
                    ctx, follow_activity, follower_actor
                )
            elif policy_decision == "reject":
                return await self.reject_follow_request(
                    ctx, follow_activity, follower_actor
                )
            else:
                # Manual approval required - for now we'll auto-accept
                return await self.accept_follow_request(
                    ctx, follow_activity, follower_actor
                )

        except Exception as e:
            print(f"Error handling follow request: {e}")
            import traceback

            traceback.print_exc()
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    async def accept_follow_request(
        self, ctx: Context, follow_activity: Follow, follower_actor: APKitActor
    ) -> Response:
        """Accept a follow request"""
        try:
            # Create Accept activity
            accept_activity = follow_activity.accept()

            # Update follow relationship status
            await self.store_follow_relationship(
                str(follow_activity.actor),
                str(follow_activity.object),
                follow_activity.id,
                "accepted",
            )

            # Send the Accept activity back to the follower
            from utils import get_keys_for_actor

            await ctx.send(get_keys_for_actor, follower_actor, accept_activity)

            print(
                f"[DEBUG] Follow request accepted: {follow_activity.actor} -> {follow_activity.object}"
            )
            return Response(status_code=202)

        except Exception as e:
            print(f"Error accepting follow request: {e}")
            return JSONResponse({"error": "Failed to accept follow"}, status_code=500)

    async def reject_follow_request(
        self, ctx: Context, follow_activity: Follow, follower_actor: APKitActor
    ) -> Response:
        """Reject a follow request"""
        try:
            # Create Reject activity
            reject_activity = Reject(
                id=f"https://{settings.host}/activities/{datetime.utcnow().timestamp()}",
                actor=follow_activity.object,  # The person being followed
                object=follow_activity,  # The original follow activity
                published=datetime.utcnow().isoformat() + "Z",
            )

            # Update follow relationship status
            await self.store_follow_relationship(
                str(follow_activity.actor),
                str(follow_activity.object),
                follow_activity.id,
                "rejected",
            )

            # Send the Reject activity back to the follower
            from utils import get_keys_for_actor

            await ctx.send(get_keys_for_actor, follower_actor, reject_activity)

            print(
                f"[DEBUG] Follow request rejected: {follow_activity.actor} -> {follow_activity.object}"
            )
            return Response(status_code=202)

        except Exception as e:
            print(f"Error rejecting follow request: {e}")
            return JSONResponse({"error": "Failed to reject follow"}, status_code=500)

    async def get_followers(self, user_id: str) -> list:
        """Get all followers for a user"""
        try:
            followers = self.follows_db.find_raw(
                {"following": user_id, "status": "accepted"}
            )
            return [follow["follower"] for follow in followers]
        except Exception as e:
            print(f"Error getting followers: {e}")
            return []

    async def get_following(self, user_id: str) -> list:
        """Get all users that a user is following"""
        try:
            following = self.follows_db.find_raw(
                {"follower": user_id, "status": "accepted"}
            )
            return [follow["following"] for follow in following]
        except Exception as e:
            print(f"Error getting following: {e}")
            return []

    async def is_following(self, follower_id: str, following_id: str) -> bool:
        """Check if one user is following another"""
        try:
            relationship = self.follows_db.find_one_raw(
                {
                    "follower": follower_id,
                    "following": following_id,
                    "status": "accepted",
                }
            )
            return relationship is not None
        except Exception as e:
            print(f"Error checking follow status: {e}")
            return False


# Create a global instance
follow_wrapper = FollowActivityWrapper()
