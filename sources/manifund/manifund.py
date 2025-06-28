#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "dotenv",
#     "requests",
# ]
# ///

# Downloads recently-added projects from Manifund API
# Downloads comments and appends them to the project data
# Formats the output correctly and prints to stdout

# Uses the Manifund API, documented here:
# https://manifund.org/docs

import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, UTC


def interpret_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


# Generic function to get recent items from Manifund API
def get_recent_items(endpoint):
    """
    Fetch items from a Manifund API endpoint created within the last n days.

    Args:
        endpoint: API endpoint name (e.g., 'projects', 'comments')
        lookback_days: Number of days to look back

    Returns:
        List of items matching the date criteria
    """
    recent_items = []
    before_param = None
    lookback_days = int(os.getenv("LOOKBACK_DAYS", 7))
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    while True:
        # Build URL with optional before parameter
        url = f"https://manifund.org/api/v0/{endpoint}"
        if before_param:
            url += f"?before={before_param}"

        response = requests.get(url)
        response.raise_for_status()
        batch_items = response.json()

        # If no items returned, we're done
        if not batch_items:
            break

        # Filter items to only include those within our date range
        filtered_items = []
        oldest_item_date = None

        for item in batch_items:
            item_date = interpret_date(item.get("created_at"))
            if item_date > cutoff_date:
                filtered_items.append(item)
            # Track the oldest item date for pagination
            if oldest_item_date is None or item_date < oldest_item_date:
                oldest_item_date = item_date

        recent_items.extend(filtered_items)

        # If the oldest item in this batch is older than our cutoff,
        # we've gotten all items we need
        if oldest_item_date and oldest_item_date <= cutoff_date:
            break

        # Set up next pagination using the oldest item's created_at
        before_param = batch_items[-1]["created_at"]

    return recent_items


def link_comments(projects, comments):
    """Add relevant comments to each project."""
    for project in projects:
        project["comments"] = [
            f"{c['profiles']['full_name']} says: {c['content']}"
            for c in comments
            if c["projects"]["slug"] == project["slug"]
        ]
        # Reverse to show oldest comments first
        project["comments"].reverse()
    return projects


if __name__ == "__main__":
    # Get config
    load_dotenv()

    # Fetch recent projects and comments
    projects = get_recent_items("projects")
    comments = get_recent_items("comments")

    # Link comments to their respective projects
    projects = link_comments(projects, comments)

    # Format output for digest system
    result = [
        {
            "source": "Manifund",
            "title": f"{project['title']} by {project['profiles']['full_name']}",
            "link": f"https://manifund.org/projects/{project['slug']}",
            "input": project,
        }
        for project in projects
    ]

    print(json.dumps(result, indent=4))
