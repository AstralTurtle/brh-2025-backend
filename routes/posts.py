from apkit.server import SubRouter
from fastapi import HTTPException

from database import Database
from settings import get_settings

router = SubRouter(prefix="/posts")

settings = get_settings()
posts_db = Database("posts.json")
users_db = Database("users.json")


@router.get("/")
async def get_posts():
    try:
        posts = posts_db.all_raw()
        return {"posts": posts}

    except Exception as e:
        print(f"Error fetching posts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
