#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "toml",
#     "requests",
#     "bs4",
# ]
# ///

# Downloads unread feed items from the FreshRSS Fever API
# Formats the output correctly and prints to stdout

# Uses the Fever API, documented here:
# https://freshrss.github.io/FreshRSS/en/developers/06_Fever_API.html

import json
import requests
from datetime import datetime, timedelta, UTC
import itertools
from bs4 import BeautifulSoup
from pathlib import Path
import sys

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config import get_config_value, get_int_config

config_path = Path("sources/freshrss/config.toml")


def get_date(item):
    """Get the item's creation date."""
    return datetime.fromtimestamp(item["created_on_time"], UTC)


def filter_by_date(item):
    """Keep items that are unread and newer than the cutoff date."""
    lookback_days = get_int_config("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    return get_date(item) > cutoff_date and item["is_read"] == 0


def get_recent_unread_feed_items():
    fever_base_url = get_config_value("FEVER_API_BASE", config_path)
    fever_api_key = get_config_value("FEVER_API_KEY", config_path)

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
    batch_size = get_int_config("batch_size", config_path, 50)
    for chunk in itertools.batched(unread_item_ids, batch_size):
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

    return [i for i in all_items if filter_by_date(i)]


def clean_html(input):
    """Strips HTML formatting and returns plain text"""
    soup = BeautifulSoup(input, "html.parser")
    return soup.get_text()


if __name__ == "__main__":
    feed_items = get_recent_unread_feed_items()

    result = []
    for item in feed_items:
        item["html"] = clean_html(item["html"])
        result.append(
            {
                "source": "FreshRSS",
                "title": f"{item['title']} by {item['author']}",
                "link": item["url"],
                "creation_date": get_date(item).isoformat(),
                "input": item,
            }
        )
    print(json.dumps(result, indent=4))
