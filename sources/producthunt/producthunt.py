# Downloads recent products from ProductHunt
# Formats the output correctly and prints to stdout

# Uses the ProductHunt GraphQL API v2
# Documentation: https://api.producthunt.com/v2/docs

import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, UTC
import sys
from pathlib import Path

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config import get_config_value, get_config_int

config_path = Path("sources/producthunt/config.toml")


def get_date(item):
    """Extract the creation date from a ProductHunt post."""
    return datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00"))


def filter_by_date(item):
    """Keep items that are newer than the cutoff date."""
    lookback_days = get_config_int("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    return get_date(item) > cutoff_date


def get_recent_posts():
    """Downloads recent posts from ProductHunt using GraphQL API"""
    api_token = get_config_value("PRODUCTHUNT_API_TOKEN", config_path)
    lookback_days = get_config_int("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    # Get minimum vote threshold from config
    min_votes = get_config_int("min_votes", config_path, 200)

    # GraphQL API endpoint
    url = "https://api.producthunt.com/v2/api/graphql"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}",
        "Host": "api.producthunt.com",
    }

    posts = []
    after_cursor = None
    max_pages = 20  # Safety limit to prevent infinite loops
    page_count = 0

    while page_count < max_pages:
        # Build GraphQL query
        cursor_param = f', after: "{after_cursor}"' if after_cursor else ""

        query = {
            "query": f"""
            query getRecentPosts {{
                posts(first: 50, order: NEWEST{cursor_param}) {{
                    edges {{
                        node {{
                            id
                            name
                            tagline
                            description
                            url
                            votesCount
                            createdAt
                            user {{
                                name
                                username
                            }}
                        }}
                        cursor
                    }}
                    pageInfo {{
                        hasNextPage
                        endCursor
                    }}
                }}
            }}
            """
        }

        try:
            response = requests.post(url, headers=headers, json=query, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Check for GraphQL errors
            if "errors" in data:
                print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
                break

            if "data" not in data or "posts" not in data["data"]:
                print("No posts data in response", file=sys.stderr)
                break

            posts_data = data["data"]["posts"]
            edges = posts_data.get("edges", [])

            if not edges:
                print("No posts found in current page", file=sys.stderr)
                break

            # Process posts from this page
            page_posts = []
            oldest_post_date = None

            for edge in edges:
                post = edge["node"]

                try:
                    # Parse creation date
                    post_date = get_date(post)

                    # Track oldest post date for stopping condition
                    if oldest_post_date is None or post_date < oldest_post_date:
                        oldest_post_date = post_date

                    # Only include posts within our date range and minimum vote threshold
                    if filter_by_date(post) and post.get("votesCount", 0) >= min_votes:
                        # Clean up the post data with minimal fields
                        cleaned_post = {
                            "id": post["id"],
                            "name": post["name"],
                            "tagline": post.get("tagline", ""),
                            "description": post.get("description", ""),
                            "url": post["url"],
                            "votes_count": post.get("votesCount", 0),
                            "created_at": post["createdAt"],
                        }

                        page_posts.append(cleaned_post)

                except Exception as e:
                    print(
                        f"Error processing post {post.get('id', 'unknown')}: {e}",
                        file=sys.stderr,
                    )
                    continue

            posts.extend(page_posts)

            # Check if we should continue pagination
            page_info = posts_data.get("pageInfo", {})
            has_next_page = page_info.get("hasNextPage", False)

            # Stop if no more pages or if oldest post is beyond our cutoff
            if not has_next_page or (
                oldest_post_date and oldest_post_date <= cutoff_date
            ):
                break

            # Set up next page
            after_cursor = page_info.get("endCursor")
            if not after_cursor:
                break

            page_count += 1

        except requests.RequestException as e:
            print(f"Error fetching posts: {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"Error processing posts: {e}", file=sys.stderr)
            break

    # Sort by creation date (newest first)
    posts.sort(key=lambda x: x["created_at"], reverse=True)
    return posts


if __name__ == "__main__":
    load_dotenv()

    posts = get_recent_posts()

    # Format for digest system
    result = [
        {
            "source": "ProductHunt",
            "title": post["name"],
            "link": post["url"],
            "creation_date": post["created_at"],
            "input": post,
        }
        for post in posts
    ]
    print(json.dumps(result, indent=4))
