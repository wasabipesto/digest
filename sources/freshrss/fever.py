#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "dotenv",
#     "requests",
#     "bs4",
# ]
# ///

# Downloads unread feed items from the FreshRSS Fever API
# Formats the output correctly and prints to stdout

import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, UTC
import itertools
from bs4 import BeautifulSoup


def keep_item(item, cutoff_date):
    """Keep items that are unread and newer than the cutoff date."""
    return (
        datetime.fromtimestamp(item["created_on_time"], UTC) > cutoff_date
        and item["is_read"] == 0
    )


def get_recent_unread_feed_items():
    fever_base_url = os.getenv("FEVER_API_BASE")
    fever_api_key = os.getenv("FEVER_API_KEY")
    lookback_days = int(os.getenv("LOOKBACK_DAYS", 7))
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    unread_item_ids = (
        requests.post(
            fever_base_url + "&unread_item_ids",
            data={
                "api_key": fever_api_key,
            },
        )
        .json()
        .get("unread_item_ids", "")
        .split(",")
    )

    all_items = []
    for chunk in itertools.batched(unread_item_ids, 50):
        items = (
            requests.post(
                fever_base_url + "&items",
                data={
                    "api_key": fever_api_key,
                    "with_ids": ",".join(chunk),
                },
            )
            .json()
            .get("items", [])
        )
        all_items.extend(items)

    return [i for i in all_items if keep_item(i, cutoff_date)]


def clean_html(input):
    """Strips HTML formatting and returns plain text"""
    soup = BeautifulSoup(input, "html.parser")
    return soup.get_text()


if __name__ == "__main__":
    load_dotenv()
    feed_items = get_recent_unread_feed_items()

    result = []
    for item in feed_items:
        item["html"] = clean_html(item["html"])
        result.append(
            {
                "source": "FreshRSS",
                "title": f"{item['title']} by {item['author']}",
                "link": item["url"],
                "input": item,
            }
        )
    print(json.dumps(result, indent=4))
