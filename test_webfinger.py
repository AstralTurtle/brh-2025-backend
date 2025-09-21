#!/usr/bin/env python3
"""
Test script to debug webfinger lookup for nixCraft@mastodon.social
"""

import asyncio
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_webfinger():
    try:
        from apkit.client.asyncio.client import ActivityPubClient

        logger.info("Starting webfinger test for nixCraft@mastodon.social")

        async with ActivityPubClient() as client:
            # Test webfinger lookup
            logger.info("Performing webfinger lookup...")
            webfinger_result = await client.webfinger.fetch("nixCraft@mastodon.social")

            logger.info(f"Webfinger result: {webfinger_result}")
            logger.info(f"Webfinger result type: {type(webfinger_result)}")

            if webfinger_result:
                logger.info(
                    f"Has links attribute: {hasattr(webfinger_result, 'links')}"
                )
                if hasattr(webfinger_result, "links"):
                    logger.info(f"Links: {webfinger_result.links}")
                    logger.info(f"Number of links: {len(webfinger_result.links)}")

                    # Find ActivityPub actor link
                    actor_url = None
                    for i, link in enumerate(webfinger_result.links):
                        logger.info(f"Link {i}: {link}")
                        logger.info(f"Link type: {type(link)}")
                        logger.info(f"Link attributes: {dir(link)}")

                        if (
                            hasattr(link, "rel")
                            and hasattr(link, "type")
                            and hasattr(link, "href")
                        ):
                            logger.info(f"Link rel: {link.rel}")
                            logger.info(f"Link type: {link.type}")
                            logger.info(f"Link href: {link.href}")

                            if (
                                link.rel == "self"
                                and link.type == "application/activity+json"
                            ):
                                actor_url = link.href
                                logger.info(f"Found ActivityPub actor URL: {actor_url}")
                                break

                    if actor_url:
                        # Test actor fetch
                        logger.info(f"Fetching actor from: {actor_url}")
                        actor = await client.actor.fetch(actor_url)

                        if actor:
                            logger.info(f"Actor fetched successfully: {type(actor)}")
                            actor_data = actor.to_json()
                            logger.info(f"Actor name: {actor_data.get('name')}")
                            logger.info(
                                f"Actor preferredUsername: {actor_data.get('preferredUsername')}"
                            )
                        else:
                            logger.error("Failed to fetch actor")
                    else:
                        logger.error(
                            "No ActivityPub actor URL found in webfinger links"
                        )
            else:
                logger.error("Webfinger lookup returned None")

    except Exception as e:
        logger.error(f"Error in webfinger test: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(test_webfinger())
