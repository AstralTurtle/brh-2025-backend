import base64
import hashlib
import json
from datetime import datetime
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# User data from your JSON
PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC38v8B6bkDVksD
XYOYNNI/D/D5/ymg6gXTQ6XTc/2CieUUhiq7St4Ra2ueCjv+31r+dshBHH0OXD/F
fLdr875wQ+ykzIIiLXGpiEBSj5xRiN+lDD8P0lkt+qPhW/4Bx+EdjIdypKYtebGn
XO5qmJPgk5j5AycXmY4zAlrkmjRHpqkaAi6CLEXuIrjMa4mnJGkPkvWp7trZnJN/
d7mDglsAstBnzmgMqPb3BXgi3atv1AagRsjcDfwMeEQSvxq9HvL8SVKLkD4qwvot
9qKXTz6fE+QZjoXLKZIz3Eh2l/k0+l4VGMkabGtUY9VdY0ijgD6RYM4/EzulQKa2
fbdUAsjtAgMBAAECggEACHb/rM8HFbQPtqNug1S8RMJPNLSSbgERlzkP3/erTP8F
0i3MY0WyNhCrPqC6Rbkcia+Io+po3NN6QcnCnQ6gjwT+gPpCQMq2O3bK0vcghTtX
Df7OxhkdbnllYjZRWDP3qYbxKAw9824cB+zFsepnNQNFxlZn+Eo3hM8RGgpN6UAa
GKxjL42YTombWOIRQwvsakCz3uxPxTfqEq6j6nksLcl/mTryI2zyCZAk6G/RcY72
ovTO8KcmS2u98VUHj0GdJhiMI5OcTAJ28op2zPQB7biOQ/Us5xv6rhZkhzopQcM1
TIDPdgEIXamgx1Ihpq+CSom04R25F9ENaBc9+7YPFwKBgQD6vAlKxgpAfc8SMHDr
L5m34NR3XyeNuR2VMWWxNxxdV/sq5H2aU10HzX8rG51qI/96F+U3jGRCxPlcpgiS
KBB0IuiZ80sSrLh3JUTOQ0v/qafD8ED+GnQrzo4VNy+1O0+5L+7/+KLgPPIxVTgh
NS9Yzbs1O1eepeL+GLD0d5dc+wKBgQC7z+sCNrnWHjxfrJ+uLNrwt+xHSjYWqAOS
3DiavoiKWIOUP2dS0h5TXl1NwdLrNGVKSVvDA8vS5P9RnCNSwT0l5lk+0Pdwl8uz
SnIi7MQWTrkah4tzmtizrZuBumd5gH7oqH0+waB76KiRCTy959uzfncsJmn6cFJd
NkFjKCI9NwKBgDIrF4zfjUOUKK+SA7X7Iz24faqY3ngr9vBYHunThhhjNz1A1KTh
UzbxdiVw9BE9vKt4RoPT0mfNs7tG+WYNICWsqm/LT1UgPBSS326J5pX0Iz5APzDY
qC/vt1wlW6VehbgfEColXKmTaD5Yt89lLeEN4QxooEJ9HKsM07NGjoGrAoGAJZWP
JwtClznHxTGrZtStH7z+uKl+N3x58prFbRoyAtWBx1oE2EsaLH7W1yexiMYcewhB
J76LvHF9Mpy3aOkoznvRYkO5MLv/1KpSOvD8sKYiXs+/NWxIb3SPiR9/c44mV3LY
VYW0EvfVO+kIUcyjZ8EoIhqx3J87rFGeNjSi3XMCgYEAn1SYKssbff4U240emiy1
7wGh+791wJZYyP8g7f8iG+/d06/RSQBQfJj7MGDMr0l4qvuiiAXWLDlNpts1SvTY
G1kRjAn8qVYc+hGxzgkSEhUZBsZUQEn9X+xJLdqz62qhsHGim17G3JlLlZZqEAYy
3q/vYJiABSnPkZIr/9fyQOU=
-----END PRIVATE KEY-----"""

KEY_ID = "0.0.0.0/users/techno#main-key"  # This should match your users.json
ACTOR_ID = "0.0.0.0/users/techno"  # This should match your users.json


def make_signed_request():
    # Load private key
    private_key = serialization.load_pem_private_key(
        PRIVATE_KEY_PEM.encode("utf-8"), password=None
    )

    # Create the activity
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": "0.0.0.0/activities/create-example-1",
        "type": "Create",
        "actor": ACTOR_ID,
        "published": "2025-09-20T12:00:00Z",
        "to": ["https://www.w3.org/ns/activitystreams#Public"],
        "cc": ["0.0.0.0/users/techno/followers"],
        "object": {
            "id": "0.0.0.0/posts/example-post-1",
            "type": "Note",
            "content": "Hello, ActivityPub world! This is my first signed post.",
            "attributedTo": ACTOR_ID,
            "published": "2025-09-20T12:00:00Z",
            "to": ["https://www.w3.org/ns/activitystreams#Public"],
            "cc": ["0.0.0.0/users/techno/followers"],
        },
    }

    # Request details
    method = "POST"
    url = "http://localhost:8000/users/techno/inbox"
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    path = parsed_url.path

    # Create date
    date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    # Create body and digest
    body_json = json.dumps(activity, separators=(",", ":"))
    body_bytes = body_json.encode("utf-8")
    digest_hash = hashlib.sha256(body_bytes).digest()
    digest = f"SHA-256={base64.b64encode(digest_hash).decode('utf-8')}"

    # Create signing string
    signing_string_parts = [
        f"(request-target): {method.lower()} {path}",
        f"host: {host}",
        f"date: {date}",
        f"digest: {digest}",
    ]
    signing_string = "\n".join(signing_string_parts)

    # Sign the string
    signature_bytes = private_key.sign(
        signing_string.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")

    # Create signature header
    signature_header = f'keyId="{KEY_ID}",algorithm="rsa-sha256",headers="(request-target) host date digest",signature="{signature_b64}"'

    # Prepare headers
    headers = {
        "Content-Type": "application/activity+json",
        "Host": host,  # Add this line
        "Date": date,
        "Digest": digest,
        "Signature": signature_header,
    }

    print(f"Making request to: {url}")
    print(f"Headers: {headers}")
    print(f"Body: {body_json}")
    print("\n" + "=" * 50 + "\n")

    # Make the request
    try:
        response = requests.post(url, data=body_json, headers=headers)
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        return response
    except Exception as e:
        print(f"Error making request: {e}")
        return None


if __name__ == "__main__":
    make_signed_request()
