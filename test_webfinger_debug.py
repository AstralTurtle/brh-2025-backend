import requests


def test_webfinger():
    q = "nixCraft@mastodon.social"
    username, domain = q.split("@", 1)
    webfinger_url = f"https://{domain}/.well-known/webfinger?resource=acct:{q}"

    print(f"Testing webfinger URL: {webfinger_url}")

    try:
        # Test webfinger lookup
        response = requests.get(
            webfinger_url, headers={"Accept": "application/jrd+json"}, timeout=10
        )

        print(f"Webfinger response status: {response.status_code}")

        if response.status_code == 200:
            webfinger_data = response.json()
            print(f"Webfinger data: {webfinger_data}")

            # Find actor URL
            actor_url = None
            if "links" in webfinger_data:
                for link in webfinger_data["links"]:
                    if (
                        link.get("rel") == "self"
                        and link.get("type") == "application/activity+json"
                    ):
                        actor_url = link.get("href")
                        print(f"Found actor URL: {actor_url}")
                        break

            if actor_url:
                print("Testing actor fetch with manual HTTP...")
                actor_response = requests.get(
                    actor_url,
                    headers={
                        "Accept": "application/activity+json",
                        "User-Agent": "ActivityPub-Client/1.0",
                    },
                    timeout=10,
                )

                print(f"Actor response status: {actor_response.status_code}")

                if actor_response.status_code == 200:
                    actor_data = actor_response.json()
                    print(
                        f"Actor preferredUsername: {actor_data.get('preferredUsername')}"
                    )
                    print(f"Actor name: {actor_data.get('name')}")
                    print(f"Actor id: {actor_data.get('id')}")
                else:
                    print(f"Actor fetch failed: {actor_response.text}")
        else:
            print(f"Webfinger failed with status {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_webfinger()
