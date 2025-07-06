# Downloads recent papers from Arxiv
# Formats the output correctly and prints to stdout

# Uses the Arxiv API, documented here:
# https://info.arxiv.org/help/api/index.html
# https://arxiv.org/category_taxonomy

import json
import requests
import feedparser
from datetime import datetime, timedelta, UTC
import re
import sys
from pathlib import Path

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config import get_config_int, get_config_list

config_path = Path("sources/arxiv/config.toml")


def get_recent_papers():
    """Downloads recent papers from Arxiv"""
    lookback_days = get_config_int("lookback_days", config_path, 7)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    # ArXiv categories to search (from config or env var)
    categories = get_config_list(
        "arxiv_categories",
        config_path,
        [
            "physics.app-ph",
            "physics.geo-ph",
            "econ.GN",
            "eess.ET",
            "econ.EM",
            "eess.IV",
            "q-bio.PE",
            "q-bio.QM",
            "stat.AP",
        ],
    )

    papers = []
    max_results_per_category = get_config_int(
        "max_results_per_category", config_path, 100
    )

    # Format date for ArXiv API (YYYYMMDD format)
    cutoff_date_str = cutoff_date.strftime("%Y%m%d")
    current_date_str = datetime.now(tz=UTC).strftime("%Y%m%d")

    for category in categories:
        if isinstance(category, str):
            category = category.strip()
        else:
            category = str(category).strip()

        # Build ArXiv API query
        # Search for papers submitted in the date range
        query = f"cat:{category} AND submittedDate:[{cutoff_date_str}* TO {current_date_str}*]"

        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results_per_category,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Parse the Atom feed
            feed = feedparser.parse(response.content)

            # Check if parsing was successful
            if hasattr(feed, "bozo") and feed.bozo:
                print(
                    f"Warning: Feed parsing issues for category {category}: {feed.bozo_exception}",
                    file=sys.stderr,
                )

            if not hasattr(feed, "entries") or len(feed.entries) == 0:
                print(f"No entries found for category {category}", file=sys.stderr)
                continue

            # print(f"Got {len(feed.entries)} entries for category {category}",file=sys.stderr)
            for entry in feed.entries:
                try:
                    # Parse the submission date
                    if not hasattr(entry, "published"):
                        print(
                            f"Warning: Entry missing publication date: {getattr(entry, 'title', 'Unknown')}",
                            file=sys.stderr,
                        )
                        continue

                    submitted_date = datetime.fromisoformat(
                        entry.published.replace("Z", "+00:00")
                    )

                    # Double-check the date filter (API might return slightly outside range)
                    if submitted_date < cutoff_date:
                        continue

                    # Extract authors
                    main_author = "Unknown"
                    authors = set()
                    if hasattr(entry, "author"):
                        authors.add(entry.author)
                        main_author = entry.author
                    if hasattr(entry, "authors"):
                        authors.update([author.name for author in entry.authors])
                    if main_author == "Unknown":
                        main_author = ",".join(authors)
                    authors = list(authors)

                    # Clean up title (remove newlines and extra spaces)
                    title = (
                        re.sub(r"\s+", " ", entry.title.strip())
                        if hasattr(entry, "title")
                        else "Unknown Title"
                    )

                    # Clean up abstract
                    abstract = (
                        re.sub(r"\s+", " ", entry.summary.strip())
                        if hasattr(entry, "summary")
                        else ""
                    )

                    # Extract ArXiv ID from the link
                    arxiv_id = entry.id.split("/")[-1] if hasattr(entry, "id") else ""

                    # Get categories
                    paper_categories = []
                    if hasattr(entry, "tags"):
                        paper_categories = [tag.term for tag in entry.tags]

                    paper = {
                        "title": title,
                        "author": main_author,
                        "all_authors": authors,
                        "url": entry.link if hasattr(entry, "link") else entry.id,
                        "abstract": abstract,
                        "arxiv_id": arxiv_id,
                        "submitted_date": submitted_date.isoformat(),
                        "categories": paper_categories,
                        "primary_category": category,
                        # "full_entry": entry,
                    }

                    papers.append(paper)

                except Exception as e:
                    print(f"Error processing entry: {e}", file=sys.stderr)
                    continue

        except requests.RequestException as e:
            print(
                f"Error fetching papers for category {category}: {e}", file=sys.stderr
            )
            continue
        except Exception as e:
            print(
                f"Error processing papers for category {category}: {e}", file=sys.stderr
            )
            continue

    # Remove duplicates based on ArXiv ID
    seen_ids = set()
    unique_papers = []
    for paper in papers:
        if paper["arxiv_id"] not in seen_ids:
            seen_ids.add(paper["arxiv_id"])
            unique_papers.append(paper)

    # Sort by submission date (newest first)
    unique_papers.sort(key=lambda x: x["submitted_date"], reverse=True)

    return unique_papers


if __name__ == "__main__":
    papers = get_recent_papers()

    result = [
        {
            "source": "Arxiv",
            "title": f"{paper['title']} by {paper['author']}",
            "link": paper["url"],
            "creation_date": paper["submitted_date"],
            "input": paper,
        }
        for paper in papers
    ]
    print(json.dumps(result, indent=4))
