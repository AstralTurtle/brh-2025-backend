import asyncio
import json

import steamspypi

from database import Database
from models import CreateUser
from routes.user import create_user
from settings import get_settings

tag_db: Database = Database("steam_tags.json")
# Yooo steam db  :kekw:
steam_db: Database = Database("steam_data.json")


settings = get_settings()


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


async def update_info(tag: str):
    data_request = dict()
    data_request["request"] = "tag"
    data_request["tag"] = tag
    data = steamspypi.download(data_request)
    return data[10]


if __name__ == "__main__":
    asyncio.run(create_genre_users())
