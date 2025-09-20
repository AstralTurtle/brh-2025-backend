import uuid

import uvicorn
from apkit.client.asyncio.client import ActivityPubClient
from apkit.client.models import Link, Resource, WebfingerResult
from apkit.models import (
    Actor as APKitActor,
)
from apkit.models import (
    CryptographicKey,
    Follow,
    Nodeinfo,
    NodeinfoProtocol,
    NodeinfoServices,
    NodeinfoSoftware,
    NodeinfoUsage,
    NodeinfoUsageUsers,
    Person,
)
from apkit.server import ActivityPubServer
from apkit.server.responses import ActivityResponse
from apkit.server.types import ActorKey, Context
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request, Response
from fastapi.responses import JSONResponse

import routes
import routes.user
from settings import get_settings

# --- Configuration ---
HOST = "4de70cf88f75.ngrok-free.app"
USER_ID = str(uuid.uuid4())

settings = get_settings()

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

# --- Server Initialization ---
app = ActivityPubServer()


# --- Key Retrieval Function ---
# This function provides the private key for signing outgoing activities.
async def get_keys_for_actor(identifier: str) -> list[ActorKey]:
    if identifier == USER_ID:
        return [ActorKey(key_id=actor.publicKey.id, private_key=private_key)]
    return []


# -- Routers ---
app.include_router(router=routes.user.router)


# --- Endpoints ---
app.inbox("/users/{identifier}/inbox")
app.outbox("/users/{identifier}/outbox")


# @app.get("/users/{identifier}")
# async def get_actor_endpoint(identifier: str):
#     if identifier == USER_ID:
#         return ActivityResponse(actor)
#     return JSONResponse({"error": "Not Found"}, status_code=404)


@app.webfinger()
async def webfinger_endpoint(request: Request, acct: Resource) -> Response:
    if acct.username == "demo" and acct.host == HOST:
        link = Link(
            rel="self",
            type="application/activity+json",
            href=f"https://{HOST}/users/{USER_ID}",
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
