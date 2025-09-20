import uuid

import uvicorn
from apkit.client.asyncio.client import ActivityPubClient
from apkit.client.models import Link, Resource, WebfingerResult
from apkit.config import AppConfig
from apkit.models import (
    Actor as APKitActor,
)
from apkit.models import (
    Create,
    CryptographicKey,
    Follow,
    Like,
    Nodeinfo,
    NodeinfoProtocol,
    NodeinfoServices,
    NodeinfoSoftware,
    NodeinfoUsage,
    NodeinfoUsageUsers,
    Note,
    Person,
)
from apkit.server import ActivityPubServer
from apkit.server.responses import ActivityResponse
from apkit.server.types import Context
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request, Response
from fastapi.responses import JSONResponse

import routes
import routes.posts
import routes.user
from database import Database
from settings import get_settings
from utils import get_keys_for_actor

# --- Configuration ---
HOST = get_settings().host
USER_ID = str(uuid.uuid4())

settings = get_settings()

posts_db = Database("posts.json")
users_db = Database("users.json")

# --- Key Generation (for demonstration) ---
# In a real application, you would load a persistent key from a secure storage.
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key_pem = (
    private_key.public_key()
    .public_bytes(
        encoding=crypto_serialization.Encoding.PEM,
        format=crypto_serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode("utf-8")
)

# --- Actor Definition ---
actor = Person(
    id=f"https://{HOST}/users/{USER_ID}",
    name="apkit Demo",
    preferredUsername="demo",
    summary="This is a demo actor powered by apkit!",
    inbox=f"https://{HOST}/users/{USER_ID}/inbox",
    outbox=f"https://{HOST}/users/{USER_ID}/outbox",
    publicKey=CryptographicKey(
        id=f"https://{HOST}/users/{USER_ID}#main-key",
        owner=f"https://{HOST}/users/{USER_ID}",
        publicKeyPem=public_key_pem,
    ),
)

config = AppConfig(
    actor_keys=get_keys_for_actor,  # This is where you pass the key loader
)

# --- Server Initialization ---
app = ActivityPubServer(apkit_config=config)

app.setup()


# --- Key Retrieval Function ---


# -- Routers ---
app.include_router(router=routes.user.router)
app.include_router(router=routes.posts.router)


# --- Endpoints ---
app.inbox("/users/{identifier}/inbox")
app.outbox("/users/{identifier}/outbox")


@app.webfinger()
async def webfinger_endpoint(request: Request, acct: Resource) -> Response:
    print(f"[DEBUG] Webfinger request for: {acct.username}@{acct.host}")

    # Handle demo user
    if acct.username == "demo" and acct.host == HOST:
        link = Link(
            rel="self",
            type="application/activity+json",
            href=f"https://{HOST}/users/{USER_ID}",
        )
        wf_result = WebfingerResult(subject=acct, links=[link])
        return JSONResponse(wf_result.to_json(), media_type="application/jrd+json")

    # Handle your database users - THIS IS THE KEY FIX
    if acct.host == HOST or acct.host == settings.host:
        user_doc = users_db.find_one_raw({"preferredUsername": acct.username})
        if user_doc:
            link = Link(
                rel="self",
                type="application/activity+json",
                href=user_doc["id"],  # This points to the actor endpoint
            )
            wf_result = WebfingerResult(subject=acct, links=[link])
            return JSONResponse(wf_result.to_json(), media_type="application/jrd+json")

    return JSONResponse({"message": "Not Found"}, status_code=404)


@app.nodeinfo("/nodeinfo/2.1", "2.1")
async def nodeinfo_endpoint():
    return ActivityResponse(
        Nodeinfo(
            version="2.1",
            software=NodeinfoSoftware(name="apkit-demo", version="0.1.0"),
            protocols=[NodeinfoProtocol.ACTIVITYPUB],
            services=NodeinfoServices(inbound=[], outbound=[]),
            openRegistrations=False,
            usage=NodeinfoUsage(users=NodeinfoUsageUsers(total=1)),
            metadata={},
        )
    )


# --- Activity Handlers ---
@app.on(Follow)
async def on_follow_activity(ctx: Context):
    activity = ctx.activity
    if not isinstance(activity, Follow):
        return JSONResponse({"error": "Invalid activity type"}, status_code=400)

    # Resolve the actor who sent the Follow request
    follower_actor = None
    if isinstance(activity.actor, str):
        async with ActivityPubClient() as client:
            follower_actor = await client.actor.fetch(activity.actor)
    elif isinstance(activity.actor, APKitActor):
        follower_actor = activity.actor

    if not follower_actor:
        return JSONResponse(
            {"error": "Could not resolve follower actor"}, status_code=400
        )

    # Automatically accept the follow request
    accept_activity = activity.accept()

    # Send the signed Accept activity back to the follower's inbox
    await ctx.send(get_keys_for_actor, follower_actor, accept_activity)
    return Response(status_code=202)


@app.on(Create)
async def create_post(ctx: Context):
    try:
        print("[DEBUG] Create activity received")
        print(f"[DEBUG] Activity: {ctx.activity}")
        print(f"[DEBUG] Actor: {ctx.activity.actor}")
        print(f"[DEBUG] Actor type: {type(ctx.activity.actor)}")

        # Fix: Handle actor as string (which is the normal case)
        actor_id = str(ctx.activity.actor)  # Convert to string if it's not already

        print(f"[DEBUG] Looking for user with id: {actor_id}")

        # Find user by actor ID
        user_doc = users_db.find_one_raw({"id": actor_id})
        if user_doc:
            print(f"[DEBUG] Found user: {user_doc.get('preferredUsername')}")

            if isinstance(ctx.activity.object, Note):
                new_post = ctx.activity.object
                print(f"[DEBUG] Post content: {new_post.content}")

                # Use the built-in to_json() method to serialize the ActivityPub Note
                post_data = new_post.to_json()

                # Store the ActivityPub JSON-LD format directly in TinyDB
                posts_db.insert_raw(post_data)
                print("[DEBUG] Post stored successfully!")

                return Response(status_code=202)
        else:
            print(f"[DEBUG] User not found with id: {actor_id}")

    except Exception as e:
        print(f"[DEBUG] Error in create_post: {e}")
        import traceback

        traceback.print_exc()

    return JSONResponse({"error": "User not found"}, status_code=404)


@app.on(Like)
async def on_like_activity(ctx: Context):
    try:
        activity = ctx.activity
        if not isinstance(activity, Like):
            return JSONResponse({"error": "Invalid activity type"}, status_code=400)

        print("[DEBUG] Like activity received")
        print(f"[DEBUG] Actor: {activity.actor}")
        print(f"[DEBUG] Object: {activity.object}")

        # Get the actor who liked the post
        actor_id = str(activity.actor)
        liker_user = users_db.find_one_raw({"id": actor_id})

        if not liker_user:
            print(f"[DEBUG] Liker not found: {actor_id}")
            return JSONResponse({"error": "Actor not found"}, status_code=404)

        # Get the object being liked (could be a post ID or full object)
        liked_object_id = str(activity.object)

        # Find the post being liked
        liked_post = posts_db.find_one_raw({"id": liked_object_id})

        if not liked_post:
            print(f"[DEBUG] Post not found: {liked_object_id}")
            return JSONResponse({"error": "Post not found"}, status_code=404)

        # Store the like activity
        like_data = {
            "id": activity.id,
            "type": "Like",
            "actor": actor_id,
            "object": liked_object_id,
            "published": activity.published or datetime.utcnow().isoformat() + "Z",
        }

        # Create a likes database if you don't have one
        likes_db = Database("likes.json")
        likes_db.insert_raw(like_data)

        print(
            f"[DEBUG] Like stored: {liker_user['preferredUsername']} liked post {liked_object_id}"
        )

        return Response(status_code=202)

    except Exception as e:
        print(f"[DEBUG] Error in on_like_activity: {e}")
        import traceback

        traceback.print_exc()
        return JSONResponse({"error": "Internal server error"}, status_code=500)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
