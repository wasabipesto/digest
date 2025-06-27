#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///

# Downloads recently-added projects from Manifund API
# Downloads comments and appends them to the project data
# Formats the output correctly and prints to stdout

import json
import requests
from datetime import datetime, timedelta


def interpret_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")


# Get projects from Manifund API created within the last n days
def get_recent_projects(lookback_days):
    recent_projects = []
    before_param = None
    cutoff_date = datetime.now() - timedelta(days=lookback_days)

    while True:
        # Build URL with optional before parameter
        url = "https://manifund.org/api/v0/projects"
        if before_param:
            url += f"?before={before_param}"

        response = requests.get(url)
        response.raise_for_status()
        batch_projects = response.json()

        # If no projects returned, we're done
        if not batch_projects:
            break

        # Filter projects to only include those within our date range
        filtered_projects = []
        oldest_project_date = None

        for project in batch_projects:
            project_date = interpret_date(project.get("created_at"))
            if project_date > cutoff_date:
                filtered_projects.append(project)
            # Track the oldest project date for pagination
            if oldest_project_date is None or project_date < oldest_project_date:
                oldest_project_date = project_date

        recent_projects.extend(filtered_projects)

        # If the oldest project in this batch is older than our cutoff,
        # we've gotten all projects we need
        if oldest_project_date and oldest_project_date <= cutoff_date:
            break

        # Set up next pagination using the oldest project's created_at
        before_param = batch_projects[-1]["created_at"]

    return recent_projects


# Get comments from Manifund API created within the last n days
def get_recent_comments(lookback_days):
    recent_comments = []
    before_param = None
    cutoff_date = datetime.now() - timedelta(days=lookback_days)

    while True:
        # Build URL with optional before parameter
        url = "https://manifund.org/api/v0/comments"
        if before_param:
            url += f"?before={before_param}"

        response = requests.get(url)
        response.raise_for_status()
        batch_comments = response.json()

        # If no comments returned, we're done
        if not batch_comments:
            break

        # Filter comments to only include those within our date range
        filtered_comments = []
        oldest_project_date = None

        for project in batch_comments:
            project_date = interpret_date(project.get("created_at"))
            if project_date > cutoff_date:
                filtered_comments.append(project)
            # Track the oldest project date for pagination
            if oldest_project_date is None or project_date < oldest_project_date:
                oldest_project_date = project_date

        recent_comments.extend(filtered_comments)

        # If the oldest project in this batch is older than our cutoff,
        # we've gotten all comments we need
        if oldest_project_date and oldest_project_date <= cutoff_date:
            break

        # Set up next pagination using the oldest project's created_at
        before_param = batch_comments[-1]["created_at"]

    return recent_comments


def link_comments(projects, comments):
    for project in projects:
        project["comments"] = [
            f"{c['profiles']['full_name']} says: {c['content']}"
            for c in comments
            if c["projects"]["slug"] == project["slug"]
        ]
        project["comments"].reverse()
    return projects


if __name__ == "__main__":
    lookback_days = 7
    projects = get_recent_projects(lookback_days)
    comments = get_recent_comments(lookback_days)
    projects = link_comments(projects, comments)

    result = []
    for project in projects:
        result.append(
            {
                "source": "Manifund",
                "title": f"{project['title']} by {project['profiles']['full_name']}",
                "link": f"https://manifund.org/projects/{project['slug']}",
                "input": project,
            }
        )
    print(json.dumps(result, indent=4))
