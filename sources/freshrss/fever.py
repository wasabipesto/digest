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
import re
from readability import Document

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


def count_words(text):
    """Count words in text"""
    return len(re.findall(r"\b\w+\b", text))


def extract_main_content(html_content):
    """Extract main content from HTML using multiple strategies"""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove unwanted elements
    for element in soup.find_all(
        ["script", "style", "nav", "footer", "header", "aside"]
    ):
        element.decompose()

    # Try semantic HTML tags first
    for tag in ["article", "main", '[role="main"]']:
        content = soup.select_one(tag)
        if content:
            return content.get_text(strip=True, separator=" ")

    # Try common content class names
    for selector in [
        ".content",
        ".post-content",
        ".entry-content",
        ".article-content",
        ".main-content",
    ]:
        content = soup.select_one(selector)
        if content:
            return content.get_text(strip=True, separator=" ")

    # Fall back to body content
    body = soup.find("body")
    if body:
        return body.get_text(strip=True, separator=" ")

    return soup.get_text(strip=True, separator=" ")


def fetch_full_content(url):
    """Fetch full page content and extract main text"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # First try readability
        try:
            doc = Document(response.text)
            content = doc.summary()
            extracted_text = clean_html(content)
            if count_words(extracted_text) >= 50:
                return extracted_text
        except Exception as e:
            print(f"Non-critical error parsing {url}: {str(e)}", file=sys.stderr)
            pass

        # Fall back to manual extraction
        extracted_text = extract_main_content(response.text)
        return extracted_text

    except Exception as e:
        print(f"Error fetching content from {url}: {str(e)}", file=sys.stderr)
        return None


if __name__ == "__main__":
    feed_items = get_recent_unread_feed_items()
    min_word_count = get_int_config("min_word_count", config_path, 50)

    result = []
    for item in feed_items:
        cleaned_content = clean_html(item["html"])

        # Check if content is too short and fetch full page if needed
        if count_words(cleaned_content) < min_word_count and item.get("url"):
            print(
                f"Content too short ({count_words(cleaned_content)} words), fetching full page: {item['url']}",
                file=sys.stderr,
            )
            full_content = fetch_full_content(item["url"])
            if full_content and count_words(full_content) > count_words(
                cleaned_content
            ):
                cleaned_content = full_content
                print(
                    f"Successfully fetched full content ({count_words(full_content)} words)",
                    file=sys.stderr,
                )

        item["html"] = cleaned_content
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
