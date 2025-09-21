import asyncio
import json

import steamspypi

from database import Database
from models import CreatePost, CreateUser
from routes.posts import create_post
from routes.user import create_user
from settings import get_settings

tag_db: Database = Database("steam_tags.json")
# Yooo steam db  :kekw:
steam_db: Database = Database("steam_data.json")

settings = get_settings()
update_tags = []
with open("steam_tags.json", "r") as f:
    thingy = json.load(f)
    update_tags = thingy["tags"]


async def create_tag_users():
    with open("steam_tags.json", "r") as f:
        thingy = json.load(f)
        for tag in thingy["tags"]:
            try:
                print(tag)
                await create_user(
                    CreateUser(
                        icon=f"https://api.dicebear.com/9.x/pixel-art/svg?seed={tag}",
                        username=f"{tag.replace(' ', '').lower()}tracker",
                        display_name=f"{tag.title()} Tracker",
                        summary=f"A page that tracks trends {tag}",
                        password="420" * 69,
                    )
                )
            except:
                print(tag, "failed")


async def create_genre_users():
    with open("steam_tags.json", "r") as f:
        thingy = json.load(f)
        for genre in thingy["genres"]:
            try:
                print(genre)
                await create_user(
                    CreateUser(
                        icon=f"https://api.dicebear.com/9.x/pixel-art/svg?seed={genre}",
                        username=f"{genre.replace(' ', '').lower()}tracker",
                        display_name=f"{genre.title()} Tracker",
                        summary=f"A page that tracks trends the {genre} genre",
                        password="420" * 69,
                    )
                )
            except:
                print(genre, "failed")


async def update_info():
    global update_tags
    data_request = dict()
    data_request["request"] = "tag"
    current_tag: str = update_tags.pop()
    data_request["tag"] = current_tag
    update_tags.insert(0, current_tag)
    data = steamspypi.download(data_request)
    await create_post(
        CreatePost(
            content=f"Top 10 trending games for {current_tag} on steam: {data}",
            to=["https://www.w3.org/ns/activitystreams#Public"],
            cc=[
                f"https://{settings.host}/users/{current_tag.replace(' ', '').lower()}tracker/followers"
            ],
        ),
        current_user=f"https://{settings.host}/users/{current_tag.replace(' ', '').lower()}tracker",
    )


if __name__ == "__main__":
    asyncio.run(create_genre_users())
