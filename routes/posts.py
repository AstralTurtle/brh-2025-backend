import uuid
from datetime import datetime
from typing import Optional

import httpx
from apkit.server import SubRouter
from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from database import Database
from models import CreatePost
from routes.auth import get_current_user
from settings import get_settings
from utils import paginate_data

router = SubRouter(prefix="/posts")

settings = get_settings()
posts_db = Database("posts.json")
users_db = Database("users.json")
likes_db = Database("likes.json")


@router.get("/")
async def get_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    in_reply_to: Optional[str] = Query(
        None, description="Filter posts that are replies to this post ID"
    ),
):
    """Get posts with pagination and optional reply filtering"""
    try:
        # Get all posts
        posts = posts_db.all_raw()

        # Filter by replies if specified
        if in_reply_to:
            posts = [post for post in posts if post.get("inReplyTo") == in_reply_to]
        else:
            # If not filtering by replies, exclude replies from main feed (optional)
            posts = [post for post in posts if not post.get("inReplyTo")]

        # Sort by date (newest first)
        posts.sort(key=lambda x: x.get("published", ""), reverse=True)

        # Apply pagination
        result = paginate_data(posts, page, limit)

        return {
            "success": True,
            "posts": result["data"],
            "pagination": result["pagination"],
        }

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
            "embed": post_data.embed,
            "attributedTo": current_user,
            "published": datetime.utcnow().isoformat() + "Z",
            "to": post_data.to or ["https://www.w3.org/ns/activitystreams#Public"],
            "cc": post_data.cc or [f"{current_user}/followers"],
        }

        # Add inReplyTo field if this is a reply
        if post_data.in_reply_to:
            note["inReplyTo"] = post_data.in_reply_to

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
        # Decode the post_id if it's URL encoded
        import urllib.parse

        decoded_post_id = urllib.parse.unquote(post_id)

        # Check if post exists - try multiple formats
        post = posts_db.find_one_raw({"id": decoded_post_id})
        if not post:
            post = posts_db.find_one_raw({"id": post_id})
        # Try to find by UUID if it's just a UUID
        if not post and not post_id.startswith("http"):
            full_url = f"https://{settings.host}/posts/{post_id}"
            post = posts_db.find_one_raw({"id": full_url})
            # Also try with 0.0.0.0 (from your existing posts)
            if not post:
                full_url_alt = f"https://0.0.0.0/posts/{post_id}"
                post = posts_db.find_one_raw({"id": full_url_alt})

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Use the actual post ID from the found post
        actual_post_id = post["id"]

        # Check if user already liked this post BEFORE doing anything else
        existing_like = likes_db.find_one_raw(
            {"actor": current_user, "object": actual_post_id}
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
            "object": actual_post_id,
            "published": datetime.utcnow().isoformat() + "Z",
        }

        # Store the like locally
        likes_db.insert_raw(
            {
                "id": like_activity["id"],
                "type": "Like",
                "actor": current_user,
                "object": actual_post_id,
                "published": like_activity["published"],
            }
        )

        # Try to send to user's outbox for federation (but don't fail if this doesn't work)
        try:
            username = user_doc["preferredUsername"]
            outbox_url = f"http://localhost:8000/users/{username}/outbox"

            async with httpx.AsyncClient(timeout=5.0) as client:
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
                    print(f"Outbox warning: {response.status_code} - {response.text}")
                    # Don't raise error here - the like is already stored locally

        except Exception as outbox_error:
            print(f"Outbox federation failed (non-critical): {outbox_error}")
            # Continue anyway - local like storage succeeded

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
        # Decode the post_id if it's URL encoded
        import urllib.parse

        decoded_post_id = urllib.parse.unquote(post_id)

        # Check if post exists - try multiple formats
        post = posts_db.find_one_raw({"id": decoded_post_id})
        if not post:
            post = posts_db.find_one_raw({"id": post_id})
        # Try to find by UUID if it's just a UUID
        if not post and not post_id.startswith("http"):
            full_url = f"https://{settings.host}/posts/{post_id}"
            post = posts_db.find_one_raw({"id": full_url})
            # Also try with 0.0.0.0 (from your existing posts)
            if not post:
                full_url_alt = f"https://0.0.0.0/posts/{post_id}"
                post = posts_db.find_one_raw({"id": full_url_alt})

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Use the actual post ID from the found post
        actual_post_id = post["id"]

        # Get all likes for this post
        likes = likes_db.find_raw({"object": actual_post_id})

        return JSONResponse(
            {"post_id": actual_post_id, "likes_count": len(likes), "likes": likes}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting likes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/replies/{post_id}")
async def get_post_replies(
    post_id: str, page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=100)
):
    """Get all replies to a specific post"""
    try:
        # Decode the post_id if it's URL encoded
        import urllib.parse

        decoded_post_id = urllib.parse.unquote(post_id)

        # Check if the original post exists - try both versions
        original_post = posts_db.find_one_raw({"id": decoded_post_id})
        if not original_post:
            original_post = posts_db.find_one_raw({"id": post_id})
        if not original_post:
            raise HTTPException(status_code=404, detail="Original post not found")

        # Use the actual post ID from the found post
        actual_post_id = original_post["id"]

        # Get all replies to this post
        replies = [
            post
            for post in posts_db.all_raw()
            if post.get("inReplyTo") == actual_post_id
        ]

        # Sort by date (oldest first for replies)
        replies.sort(key=lambda x: x.get("published", ""))

        # Apply pagination
        result = paginate_data(replies, page, limit)

        return {
            "success": True,
            "original_post": original_post,
            "replies": result["data"],
            "pagination": result["pagination"],
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching replies: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
