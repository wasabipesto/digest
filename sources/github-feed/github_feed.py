# Downloads recent GitHub feed data (trending repos and friends' activity)
# Looks for repos that the user hasn't starred and fetches their README
# Formats the output correctly and prints to stdout

import json
import requests
import base64
from datetime import datetime, timedelta, UTC
import sys
from pathlib import Path
import time

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config import get_config_value, get_int_config

config_path = Path("sources/github-feed/config.toml")


def get_github_headers(token):
    """Get headers for GitHub API requests"""
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "digest-github-feed-loader",
    }


def make_github_request(url, headers, params=None):
    """Make a GitHub API request with error handling and rate limiting"""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        # Check rate limiting
        if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers:
            remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            if remaining == 0:
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                wait_time = reset_time - int(time.time())
                print(
                    f"Rate limit exceeded. Need to wait {wait_time} seconds",
                    file=sys.stderr,
                )
                sys.exit(1)

        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error making GitHub API request to {url}: {e}", file=sys.stderr)
        return None


def get_user_starred_repos(token, username):
    """Get list of repositories the user has starred"""
    headers = get_github_headers(token)
    starred_repos = set()
    page = 1

    while True:
        url = f"https://api.github.com/users/{username}/starred"
        params = {"page": page, "per_page": 100}

        data = make_github_request(url, headers, params)
        if not data:
            break

        if not data:  # Empty response means no more pages
            break

        for repo in data:
            starred_repos.add(repo["full_name"])

        # If we got less than 100 results, we're done
        if len(data) < 100:
            break

        page += 1

        # Safety limit to prevent infinite loops
        if page > 100:
            print(
                "Warning: Hit safety limit for starred repos pagination",
                file=sys.stderr,
            )
            break

    print(f"Found {len(starred_repos)} starred repositories", file=sys.stderr)
    return starred_repos


def get_trending_repos(token, lookback_days=7, min_stars=10):
    """Get trending repositories from the last week"""
    headers = get_github_headers(token)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")

    # Search for recently created or updated repositories with good engagement
    url = "https://api.github.com/search/repositories"
    params = {
        "q": f"created:>{cutoff_date_str} OR pushed:>{cutoff_date_str} stars:>={min_stars}",
        "sort": "stars",
        "order": "desc",
        "per_page": 50,
    }

    data = make_github_request(url, headers, params)
    return data.get("items", []) if data else []


def get_following_activity(token, username, lookback_days=7):
    """Get activity from users the authenticated user follows"""
    headers = get_github_headers(token)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    # Get list of users the authenticated user follows
    following_url = f"https://api.github.com/users/{username}/following"
    following_data = make_github_request(following_url, headers)
    if not following_data:
        return []

    # Limit to prevent too many API calls
    following_users = following_data[:20]  # Limit to first 20 following users

    interesting_repos = []

    for user in following_users:
        # Get recent events for this user
        events_url = f"https://api.github.com/users/{user['login']}/events"
        events_data = make_github_request(events_url, headers)

        if not events_data:
            continue

        for event in events_data:
            # Only look at star events (WatchEvent) and fork events
            if event.get("type") not in ["WatchEvent", "ForkEvent"]:
                continue

            # Check if event is recent
            event_date = datetime.fromisoformat(
                event["created_at"].replace("Z", "+00:00")
            )
            if event_date < cutoff_date:
                continue

            # Extract repository information
            repo_data = event.get("repo")
            if not repo_data:
                continue

            # Get full repository details
            repo_url = f"https://api.github.com/repos/{repo_data['name']}"
            repo_details = make_github_request(repo_url, headers)

            if repo_details:
                interesting_repos.append(repo_details)

    return interesting_repos


def get_readme_content(token, repo_full_name):
    """Get README content for a repository"""
    headers = get_github_headers(token)
    url = f"https://api.github.com/repos/{repo_full_name}/readme"

    data = make_github_request(url, headers)
    if not data:
        return None

    try:
        # README content is base64 encoded
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content
    except Exception as e:
        print(f"Error decoding README for {repo_full_name}: {e}", file=sys.stderr)
        return None


def get_authenticated_user(token):
    """Get the authenticated user's information"""
    headers = get_github_headers(token)
    url = "https://api.github.com/user"

    data = make_github_request(url, headers)
    if not data:
        print("Error: Could not get authenticated user information", file=sys.stderr)
        sys.exit(1)

    return data


def get_recent_feed_items():
    """Get recent items from GitHub feed"""
    # Get GitHub token from config/environment
    token = get_config_value("GITHUB_TOKEN", config_path)
    if not token:
        print("Error: GITHUB_TOKEN not found in config or environment", file=sys.stderr)
        sys.exit(1)

    lookback_days = get_int_config("lookback_days", config_path, 7)
    max_repos = get_int_config("max_repos", config_path, 30)
    min_stars = get_int_config("min_stars", config_path, 10)

    # Get authenticated user info
    user_info = get_authenticated_user(token)
    username = user_info["login"]

    print(f"Fetching GitHub feed for user: {username}", file=sys.stderr)

    # Get user's starred repositories to filter them out
    starred_repos = get_user_starred_repos(token, username)

    # Get trending repositories
    print("Fetching trending repositories...", file=sys.stderr)
    trending_repos = get_trending_repos(token, lookback_days, min_stars)

    # Get activity from followed users
    print("Fetching activity from followed users...", file=sys.stderr)
    following_activity = get_following_activity(token, username, lookback_days)

    # Combine and deduplicate repositories
    all_repos = {}

    # Add trending repos
    for repo in trending_repos:
        if repo["full_name"] not in starred_repos:
            all_repos[repo["full_name"]] = repo

    # Add repos from following activity
    for repo in following_activity:
        if repo["full_name"] not in starred_repos:
            all_repos[repo["full_name"]] = repo

    # Limit the number of repos to process
    repo_list = list(all_repos.values())[:max_repos]

    print(f"Processing {len(repo_list)} unstarred repositories...", file=sys.stderr)

    # Get README content for each repository
    results = []
    for repo in repo_list:
        try:
            print(f"Processing {repo['full_name']}...", file=sys.stderr)

            # Get README content
            readme_content = get_readme_content(token, repo["full_name"])

            # Add README to repo data
            repo_data = repo.copy()
            repo_data["readme_content"] = readme_content

            # Create the result item
            result_item = {
                "source": "GitHub Feed",
                "title": f"{repo['name']} - {repo.get('description', 'No description')}",
                "link": repo["html_url"],
                # creation date isn't what we're interested in here, so we use the scrape date instead
                "creation_date": datetime.now(tz=UTC).isoformat(),
                "input": repo_data,
            }

            results.append(result_item)

            # Small delay to be respectful to the API
            time.sleep(0.1)

        except Exception as e:
            print(
                f"Error processing repository {repo.get('full_name', 'unknown')}: {e}",
                file=sys.stderr,
            )
            continue

    return results


if __name__ == "__main__":
    try:
        feed_items = get_recent_feed_items()
        print(json.dumps(feed_items, indent=4))
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
