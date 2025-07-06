# Downloads recently-added projects from Manifund API
# Downloads comments and appends them to the project data
# Formats the output correctly and prints to stdout

# Uses the Manifund API, documented here:
# https://manifund.org/docs

import json
import requests
from datetime import datetime, timedelta, UTC
from pathlib import Path
import sys

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config import get_config_int

config_path = Path("sources/manifund/config.toml")


def get_date(item):
    """Get the item's creation date."""
    return datetime.strptime(item["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=UTC
    )


def filter_by_date(item):
    lookback_days = get_config_int("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    item_date = get_date(item)
    return item_date > cutoff_date


# Generic function to get recent items from Manifund API
def get_recent_items(endpoint):
    """
    Fetch items from a Manifund API endpoint created within the last n days.

    Args:
        endpoint: API endpoint name (e.g., 'projects', 'comments')

    Returns:
        List of items matching the date criteria
    """
    recent_items = []
    before_param = None
    lookback_days = get_config_int("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    max_projects = get_config_int("max_projects", config_path, 100)

    # Track how many items we've processed to avoid infinite loops
    items_processed = 0

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

        # Check if we've processed enough items (safety limit)
        items_processed += len(batch_items)
        if items_processed > max_projects:
            break

        # Filter items to only include those within our date range
        filtered_items = []
        oldest_item_date = None

        for item in batch_items:
            if filter_by_date(item):
                filtered_items.append(item)
            # Track the oldest item date for pagination
            item_date = get_date(item)
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
            "creation_date": get_date(project).isoformat(),
            "input": project,
        }
        for project in projects
    ]

    print(json.dumps(result, indent=4))
