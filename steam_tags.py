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


def parse_steam_data_to_text(data, tag_name):
    """Parse Steam API data into readable text format"""
    try:
        if not data or not isinstance(data, dict):
            return f"No trending games found for {tag_name} 😔"

        # Convert dict values to list and sort by positive reviews
        games_list = list(data.values()) if isinstance(data, dict) else data

        # Filter valid games and sort by positive reviews
        valid_games = [
            game
            for game in games_list
            if isinstance(game, dict) and "name" in game and "positive" in game
        ]

        if not valid_games:
            return f"No valid game data found for {tag_name} 😔"

        # Sort by positive reviews (descending) and take top 10
        top_games = sorted(
            valid_games, key=lambda x: x.get("positive", 0), reverse=True
        )[:10]

        # Create simple numbered list
        text_lines = [f"Top 10 trending {tag_name} games on Steam:\n"]

        for i, game in enumerate(top_games, 1):
            name = game.get("name", "Unknown Game")
            text_lines.append(f"{i}. {name}")

        return "\n".join(text_lines)

    except Exception as e:
        print(f"Error parsing steam data: {e}")
        return f"Error getting trending games for {tag_name} 😔"


def format_game_summary(games_data, tag_name):
    """Create a shorter summary format for posts"""
    try:
        if not games_data or not isinstance(games_data, dict):
            return f"No data available for {tag_name}"

        games_list = (
            list(games_data.values()) if isinstance(games_data, dict) else games_data
        )
        valid_games = [
            g
            for g in games_list
            if isinstance(g, dict) and "name" in g and "positive" in g
        ]

        if not valid_games:
            return f"No games found for {tag_name}"

        # Get top 5 games for summary
        top_games = sorted(
            valid_games, key=lambda x: x.get("positive", 0), reverse=True
        )[:5]

        text_lines = [f"Top 5 trending {tag_name} games:\n"]
        for i, game in enumerate(top_games, 1):
            name = game.get("name", "Unknown")
            text_lines.append(f"{i}. {name} by {game['developer']}")

        return ";".join(text_lines)

    except Exception:
        return f"Error getting {tag_name} trends"


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

    # Use the formatted text function instead of raw array data
    formatted_content = parse_steam_data_to_text(data, current_tag)

    await create_post(
        CreatePost(
            content=formatted_content,
            to=["https://www.w3.org/ns/activitystreams#Public"],
            cc=[
                f"https://{settings.host}/users/{current_tag.replace(' ', '').lower()}tracker/followers"
            ],
        ),
        current_user=f"https://{settings.host}/users/{current_tag.replace(' ', '').lower()}tracker",
    )


if __name__ == "__main__":
    asyncio.run(create_genre_users())
