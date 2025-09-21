import uuid
from datetime import datetime

import httpx
from apkit.server import SubRouter
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from database import Database
from models import CreatePost
from routes.auth import get_current_user
from settings import get_settings

router = SubRouter(prefix="/posts")

settings = get_settings()
posts_db = Database("posts.json")
users_db = Database("users.json")
likes_db = Database("likes.json")


@router.get("/")
async def get_posts():
    try:
        posts = posts_db.all_raw()
        return {"posts": posts}

    except Exception as e:
        print(f"Error fetching posts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/create")
async def create_post(
    post_data: CreatePost, current_user: str = Depends(get_current_user)
):
    """Create a new post and send it to the user's outbox"""
    try:
        # Get user data
        user_doc = users_db.find_one_raw({"id": current_user})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        # Create unique post ID
        post_id = f"https://{settings.host}/posts/{uuid.uuid4()}"

        # Create the Note object
        note = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": post_id,
            "type": "Note",
            "content": post_data.content,
            "attributedTo": current_user,
            "published": datetime.utcnow().isoformat() + "Z",
            "to": post_data.to or ["https://www.w3.org/ns/activitystreams#Public"],
            "cc": post_data.cc or [f"{current_user}/followers"],
        }

        # Create the Create activity
        create_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{settings.host}/activities/{uuid.uuid4()}",
            "type": "Create",
            "actor": current_user,
            "published": datetime.utcnow().isoformat() + "Z",
            "to": note["to"],
            "cc": note["cc"],
            "object": note,
        }

        # Store the post locally
        posts_db.insert_raw(note)

        # Send to user's outbox with proper ActivityPub headers
        # username = user_doc["preferredUsername"]
        # outbox_url = f"http://localhost:8000/users/{username}/outbox"

        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         outbox_url,
        #         json=create_activity,
        #         headers={
        #             "Content-Type": "application/activity+json",  # ActivityPub content type
        #             "Accept": "application/activity+json",  # Accept ActivityPub responses
        #             "User-Agent": "brh-2025-backend/0.1.0",  # Identify your server
        #         },
        #     )

        #     if response.status_code not in [200, 201, 202]:
        #         print(f"Outbox error: {response.status_code} - {response.text}")
        #         raise HTTPException(status_code=500, detail="Failed to send to outbox")

        return JSONResponse(
            {
                "message": "Post created successfully",
                "post_id": post_id,
                "activity_id": create_activity["id"],
            },
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{post_id}/like")
async def like_post(post_id: str, current_user: str = Depends(get_current_user)):
    """Like a post and send Like activity to the outbox"""
    try:
        # Check if post exists
        post = posts_db.find_one_raw({"id": post_id})
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Check if user already liked this post
        existing_like = likes_db.find_one_raw(
            {"actor": current_user, "object": post_id}
        )
        if existing_like:
            raise HTTPException(status_code=400, detail="Already liked this post")

        # Get user data
        user_doc = users_db.find_one_raw({"id": current_user})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        # Create the Like activity
        like_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{settings.host}/activities/{uuid.uuid4()}",
            "type": "Like",
            "actor": current_user,
            "object": post_id,
            "published": datetime.utcnow().isoformat() + "Z",
        }

        # Store the like locally
        likes_db.insert_raw(
            {
                "id": like_activity["id"],
                "type": "Like",
                "actor": current_user,
                "object": post_id,
                "published": like_activity["published"],
            }
        )

        # Send to user's outbox for federation
        username = user_doc["preferredUsername"]
        outbox_url = f"http://localhost:8000/users/{username}/outbox"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                outbox_url,
                json=like_activity,
                headers={
                    "Content-Type": "application/activity+json",
                    "Accept": "application/activity+json",
                    "User-Agent": "brh-2025-backend/0.1.0",
                },
            )

            if response.status_code not in [200, 201, 202]:
                print(f"Outbox error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail="Failed to send to outbox")

        return JSONResponse(
            {"message": "Post liked successfully", "like_id": like_activity["id"]},
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error liking post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{post_id}/likes")
async def get_post_likes(post_id: str):
    """Get all likes for a post"""
    try:
        # Check if post exists
        post = posts_db.find_one_raw({"id": post_id})
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Get all likes for this post
        likes = likes_db.find_raw({"object": post_id})

        return JSONResponse(
            {"post_id": post_id, "likes_count": len(likes), "likes": likes}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting likes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
