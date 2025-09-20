import json

import steamspypi

from database import Database
from models import CreateUser
from routes.user import create_user
from settings import get_settings

tag_db: Database = Database("steam_tags.json")
# Yooo steam db  :kekw:
steam_db: Database = Database("steam_data.json")

data_request = dict()
data_request["request"] = "genre"
data_request["page"] = "0"

data = steamspypi.download(data_request)

settings = get_settings()


def create_tag_users():
    with open("steam_tags.json", "r") as f:
        thingy = json.load(f)
        for tag in thingy["tag"]:
            create_user(
                CreateUser(
                    icon=f"https://api.dicebear.com/9.x/pixel-art/svg?seed={tag}",
                    username=f"{tag.replace(' ', '').lower()}tracker",
                    display_name=f"{tag.title()} Tracker",
                    summary=f"A page that tracks trends {tag}",
                    password="420" * 69,
                )
            )


async def update_info(genre: str):
    data_request["genre"] = genre
    data = steamspypi.download(data_request)
    return data[10]
