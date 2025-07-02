import json
import os
import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
import requests
from collections import defaultdict
import subprocess


def is_item_important(item: Dict[str, Any], min_score: float) -> bool:
    """Check if an item meets the importance score cutoff"""
    return (item.get("weighted_score", 0) or 0) >= min_score


def is_item_recent(item: Dict[str, Any], lookback_days: int) -> bool:
    """Check if an item was created within the lookback period"""
    if lookback_days <= 0:
        return True  # No date filtering

    try:
        item_date_str = item.get("creation_date")
        if not item_date_str:
            return True  # If no date info, include it

        # Parse ISO format datetime
        if item_date_str.endswith("Z"):
            item_date_str = item_date_str[:-1] + "+00:00"

        item_date = datetime.fromisoformat(item_date_str)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        return item_date >= cutoff_date
    except (ValueError, AttributeError):
        print(f"Failed to parse date: {item_date_str}")
        return True  # If we can't parse the date, include it


def get_item_summary(item: Dict[str, Any]) -> str:
    """Extract summary from first item evaluation"""
    if not item.get("evals"):
        return "No summary available."

    for eval_data in item["evals"]:
        if isinstance(eval_data.get("response"), dict):
            summary = eval_data["response"].get("summary", "")
            if summary:
                return summary

    return "No summary available."


def filter_and_sort_items(
    items: List[Dict[str, Any]], lookback_days: int, min_score: float
) -> List[Dict[str, Any]]:
    """Filter items by date and score, then sort by weighted score"""
    filtered_items = [
        i
        for i in items
        if is_item_important(i, min_score) and is_item_recent(i, lookback_days)
    ]

    # Sort by weighted score (highest first)
    return sorted(filtered_items, key=lambda x: x["weighted_score"], reverse=True)


def group_items_by_source(
    items: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by their source"""
    grouped = defaultdict(list)
    for item in items:
        source = item.get("source", "Unknown")
        grouped[source].append(item)

    return grouped


def generate_email_subject(items: List[Dict[str, Any]]) -> str:
    """Generates a subject line based on the number of items"""
    return f"{len(items)} items in your weekly digest"


def generate_html_email(
    items: List[Dict[str, Any]], lookback_days: int, min_score: float
) -> str:
    """Generate HTML email content"""
    if not items:
        return """
        <html>
        <body>
        <h1>Weekly Digest</h1>
        <p>No items found matching the criteria.</p>
        </body>
        </html>
        """

    # Get top 3 items
    top_items = items[:3]

    # Group remaining items by source
    grouped_items = group_items_by_source(items)

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #333; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
            h2 {{ color: #555; margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
            h3 {{ color: #666; margin-top: 20px; }}
            .top-items {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #007cba; margin: 20px 0; }}
            .item {{ margin: 15px 0; padding: 10px; border-left: 3px solid #ddd; }}
            .item-title {{ font-weight: bold; color: #007cba; }}
            .item-score {{ color: #888; font-size: 0.9em; }}
            .item-summary {{ margin-top: 5px; color: #555; }}
            a {{ color: #007cba; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #888; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <h1>Weekly Digest</h1>
        <p><strong>Criteria:</strong> Items from last {lookback_days} days with score ≥ {min_score}</p>
        <p><strong>Total items:</strong> {len(items)}</p>

        <div class="top-items00">
            <h2>🏆 Top Items</h2>
    """

    for item in top_items:
        score = item.get("weighted_score", 0) or 0
        confidence = item.get("median_confidence", 0) or 0
        html += f"""
            <div class="item">
                <div class="item-title">
                    <a href="{item.get("link", "#")}" target="_blank">{item.get("title", "Untitled")}</a>
                </div>
                <div class="item-score">Score: {score} ({confidence}%) | Source: {item.get("source", "Unknown")}</div>
            </div>
        """

    html += """
        </div>

        <h2>📚 All Items by Source</h2>
    """

    for source, source_items in grouped_items.items():
        html += f"""
        <h3>{source} ({len(source_items)} items)</h3>
        """

        for item in source_items:
            score = item.get("weighted_score", 0) or 0
            confidence = item.get("median_confidence", 0) or 0
            summary = get_item_summary(item)

            html += f"""
            <div class="item">
                <div class="item-title">
                    <a href="{item.get("link", "#")}" target="_blank">{item.get("title", "Untitled")}</a>
                </div>
                <div class="item-score">Score: {score}, Confidence: {confidence}</div>
                <div class="item-summary">{summary}</div>
            </div>
            """

    html += f"""
        <div class="footer">
            <p>This digest was generated at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}.</p>
        </div>
    </body>
    </html>
    """

    return html


def save_html_to_file(html_content: str, filename: str = "digest_email.html") -> str:
    """Save HTML content to file and return the file path"""
    filepath = os.path.join(os.getcwd(), filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def open_in_browser(html_content: str):
    """Save HTML to temp file and open in browser"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html_content)
        temp_path = f.name

    subprocess.call(["xdg-open", temp_path])
    print(f"Opened in browser: {temp_path}")


def send_via_mailgun(html_content: str, subject: str, recipient_email: str):
    """Send email via Mailgun API"""
    mailgun_api_key = os.getenv("MAILGUN_API_KEY")
    mailgun_domain = os.getenv("MAILGUN_DOMAIN")
    sender_email = os.getenv("SENDER_EMAIL", f"digest@{mailgun_domain}")

    if not mailgun_api_key:
        raise ValueError("MAILGUN_API_KEY environment variable is required")
    if not mailgun_domain:
        raise ValueError("MAILGUN_DOMAIN environment variable is required")

    url = f"https://api.mailgun.net/v3/{mailgun_domain}/messages"

    data = {
        "from": sender_email,
        "to": recipient_email,
        "subject": subject,
        "html": html_content,
    }

    response = requests.post(url, auth=("api", mailgun_api_key), data=data)

    if response.status_code == 200:
        print(f"Email sent successfully to {recipient_email}")
        return True
    else:
        print(f"Failed to send email: {response.status_code} - {response.text}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate and send digest email")
    parser.add_argument(
        "action",
        choices=["save", "preview", "send"],
        help="Action to take: save to file, open preview, or send email",
    )
    parser.add_argument(
        "--input",
        default="digest_results.json",
        help="Input JSON file (default: digest_results.json)",
    )
    parser.add_argument(
        "--output",
        default="digest_email.html",
        help="Output HTML file name when using 'save' action (default: digest_email.html)",
    )
    parser.add_argument(
        "--recipient", help="Email recipient (overrides RECIPIENT_EMAIL env var)"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        help="Days to look back (overrides LOOKBACK_DAYS env var)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        help="Minimum importance score (overrides MIN_EMAIL_SCORE env var)",
    )

    args = parser.parse_args()

    # Get configuration from environment variables or arguments
    lookback_days = (
        args.lookback_days
        if args.lookback_days is not None
        else int(os.getenv("LOOKBACK_DAYS", "7"))
    )
    min_score = (
        args.min_score
        if args.min_score is not None
        else float(os.getenv("MIN_EMAIL_SCORE", 70))
    )
    recipient_email = args.recipient or os.getenv("RECIPIENT_EMAIL")

    # Validate email action requirements
    if args.action == "send" and not recipient_email:
        parser.error(
            "Email recipient is required. Use --recipient or set RECIPIENT_EMAIL environment variable."
        )

    # Load and process data
    print(f"Loading data from {args.input}...")
    try:
        with open(args.input, "r") as f:
            digest_results = json.load(f)
    except FileNotFoundError:
        print(f"Error: File {args.input} not found")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.input}: {e}")
        return 1

    print(f"Loaded {len(digest_results)} total items")

    # Filter and sort items
    print(f"Filtering items: last {lookback_days} days, score >= {min_score}")
    filtered_items = filter_and_sort_items(digest_results, lookback_days, min_score)
    print(f"Found {len(filtered_items)} items matching criteria")

    if not filtered_items:
        print("No items found matching the criteria")
        if args.action == "send":
            print("Skipping email send - no content to send")
        return 0

    # Generate HTML content
    print("Generating HTML content...")
    html_content = generate_html_email(filtered_items, lookback_days, min_score)
    subject = generate_email_subject(filtered_items)

    # Execute the requested action
    if args.action == "save":
        filepath = save_html_to_file(html_content, args.output)
        print(f"HTML saved to: {filepath}")

    elif args.action == "preview":
        open_in_browser(html_content)

    elif args.action == "send":
        print(f"Sending email to {recipient_email}...")
        success = send_via_mailgun(html_content, subject, recipient_email)
        if not success:
            return 1

    return 0


if __name__ == "__main__":
    exit(main())
