#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "toml",
#     "dotenv",
#     "requests",
#     "jinja2",
#     "tiptapy",
#     "bs4",
# ]
# ///

# Downloads a list of comments from Manifold Markets
# Filters based on likes and length
# Formats the output correctly and prints to stdout

# Partially uses the Manifold public API, documented here:
# https://docs.manifold.markets/api

import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, UTC
import tiptapy
from bs4 import BeautifulSoup
from pathlib import Path
import sys

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config import get_config_value, get_int_config
config_path = Path(f"sources/manifold-comment/config.toml")


def get_date(item):
    """Get the item's creation date."""
    if "created_time" in item:
        return datetime.fromisoformat(item["created_time"]).replace(tzinfo=UTC)
    elif "createdTime" in item:
        return datetime.fromtimestamp(item["createdTime"] // 1000).replace(tzinfo=UTC)
    else:
        print("No date found")


def get_comments():
    """
    Get comments from Manifold's database with a minimum number of likes.
    Manifold comments API doesn't allow filtering by likes so we use the Supabase connection instead.
    """
    min_likes = get_int_config("min_likes", config_path, 15)
    max_comments = get_int_config("max_comments", config_path, 200)
    lookback_days = get_int_config("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    supabase_anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB4aWRyZ2thdHVtbHZmcWF4Y2xsIiwicm9sZSI6ImFub24iLCJpYXQiOjE2Njg5OTUzOTgsImV4cCI6MTk4NDU3MTM5OH0.d_yYtASLzAoIIGdXUBIgRAGLBnNow7JG2SoaNMQ8ySg"
    comments = requests.get(
        "https://pxidrgkatumlvfqaxcll.supabase.co/rest/v1/contract_comments",
        params={"likes": f"gte.{min_likes}", "created_time": f"gte.{cutoff_date.isoformat()}", "limit": max_comments},
        headers={"apikey": supabase_anon_key},
    ).json()
    return comments


def get_link(comment):
    """Get the link to the comment on the market page."""
    market = requests.get(
        f"https://api.manifold.markets/v0/market/{comment['contractId']}"
    ).json()
    return f"{market['url']}#{comment['id']}"


def convert_mentions_to_text(content):
    """Recursively convert mention objects to text objects in Tiptap content."""
    if isinstance(content, dict):
        if (
            content.get("type") == "mention"
            or content.get("type") == "contract-mention"
        ) and "attrs" in content:
            # Convert mention to text object using the label
            label = content["attrs"].get("label", "")
            return {"type": "text", "text": label}
        else:
            # Recursively process other dict objects
            result = {}
            for key, value in content.items():
                result[key] = convert_mentions_to_text(value)
            return result
    elif isinstance(content, list):
        # Recursively process list items
        return [convert_mentions_to_text(item) for item in content]
    else:
        # Return primitive values as-is
        return content


def convert_images_to_text(content):
    """Recursively convert image objects to text objects in Tiptap content."""
    if isinstance(content, dict):
        if content.get("type") == "image":
            # Convert image to text object using alt text or placeholder
            alt_text = ""
            if "attrs" in content and content["attrs"]:
                alt_text = content["attrs"].get("alt", "") or ""
            return {"type": "text", "text": alt_text or "[image]"}
        else:
            # Recursively process other dict objects
            result = {}
            for key, value in content.items():
                result[key] = convert_images_to_text(value)
            return result
    elif isinstance(content, list):
        # Recursively process list items
        return [convert_images_to_text(item) for item in content]
    else:
        # Return primitive values as-is
        return content


def clean_tiptap(comment):
    """Extract the comment text from Tiptap formatting."""
    content = comment["content"]

    # Convert mentions and images to text objects before rendering
    content = convert_mentions_to_text(content)
    content = convert_images_to_text(content)

    # Convert Tiptap to HTML
    class config:
        DOMAIN = "python.org"

    renderer = tiptapy.BaseDoc(config)
    rendered = renderer.render(content)

    # Convert HTML to text
    soup = BeautifulSoup(rendered, "html.parser")
    return soup.get_text()


def clean_comments(comments):
    """Clean comment text and then remove short ones."""
    cleaned_comments = []
    for comment in comments:
        cleaned_comment = comment["data"]
        cleaned_comment["content"] = clean_tiptap(cleaned_comment)
        if len(cleaned_comment["content"]) > 500:
            cleaned_comments.append(cleaned_comment)
    return cleaned_comments


if __name__ == "__main__":
    load_dotenv()
    comments = get_comments()
    comments = clean_comments(comments)

    result = [
        {
            "source": "Manifold Comments",
            "title": f"Comment by {comment['userName']} on {comment['contractQuestion']}",
            "link": get_link(comment),
            "creation_date": get_date(comment).isoformat(),
            "input": comment,
        }
        for comment in comments
    ]
    print(json.dumps(result, indent=4))
