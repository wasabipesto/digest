#!/usr/bin/env python3

import matplotlib
import matplotlib.pyplot as plt
import base64
import io
from collections import defaultdict
from typing import Dict, List

matplotlib.use("Agg")  # Use non-interactive backend


def aggregate_data(digest_results):
    """Extract and process items from digest results."""
    all_items = []

    for item in digest_results:
        # Skip those without evals
        if item["weighted_score"] is None:
            continue

        evals = [
            {
                "prompt_hash": e["prompt_hash"],
                "model": e["model"],
                "score": e["response"]["importance_score"],
                "confidence": e["response"]["confidence_score"],
            }
            for e in item["evals"]
        ]
        item_data = {
            "source": item["source"],
            "title": item["title"],
            "dedup_key": item["dedup_key"],
            "weighted_score": item["weighted_score"],
            "evals": evals,
        }
        all_items.append(item_data)

    all_items.sort(key=lambda x: x["weighted_score"])
    return all_items


def plot_to_base64(fig):
    """Convert matplotlib figure to base64 string."""
    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format="png", dpi=150, bbox_inches="tight")
    img_buffer.seek(0)
    img_str = base64.b64encode(img_buffer.getvalue()).decode()
    plt.close(fig)
    return img_str


def create_importance_eventplot(all_items, max_items_to_show=50, max_title_len=50):
    """Create importance score event plot."""
    print("Generating importance event plot...")
    titles, importance_scores_lists, weighted_scores = [], [], []
    for item in all_items[-max_items_to_show:]:
        short_title = (
            item["title"][:max_title_len] + "..."
            if len(item["title"]) > max_title_len
            else item["title"]
        )
        titles.append(f"{item['source']}: {short_title}")
        importance_scores_lists.append([e["score"] for e in item["evals"]])
        weighted_scores.append(item["weighted_score"])

    y_positions = range(len(titles))
    fig_height = max(6, len(titles) * 0.25)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    ax.eventplot(
        importance_scores_lists,
        orientation="horizontal",
        lineoffsets=y_positions,
        linelengths=0.8,
        alpha=0.5,
    )
    ax.scatter(weighted_scores, y_positions, s=100, alpha=0.8, marker=".", zorder=10)
    ax.set_xlim(0, 100)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(titles, fontsize=8)
    ax.set_xlabel("Importance Score")
    ax.set_ylabel("Items")
    ax.set_title("Distribution of Importance Scores by Item")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    return plot_to_base64(fig)


def create_scatter_plot(all_items):
    """Create scatter plot of scores vs confidence by source."""
    print("Generating scatter plot of scores...")
    scores_by_source = defaultdict(list)
    confidences_by_source = defaultdict(list)

    for item in all_items:
        for e in item["evals"]:
            scores_by_source[item["source"]].append(e["score"])
            confidences_by_source[item["source"]].append(e["confidence"])

    fig, ax = plt.subplots(figsize=(10, 8))
    colormap = plt.get_cmap("tab10")
    for i, source in enumerate(scores_by_source):
        ax.scatter(
            scores_by_source[source],
            confidences_by_source[source],
            alpha=0.3,
            s=40,
            label=source,
            color=colormap(i % 10),
        )

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Importance Score")
    ax.set_ylabel("Confidence Score")
    ax.set_title("Scores vs Confidence (All Items, Colored by Source)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    return plot_to_base64(fig)


def all_plots(data) -> List[Dict[str, str]]:
    agg_data = aggregate_data(data)
    return [
        {
            "title": "Importance Score Distribution",
            "body": create_importance_eventplot(agg_data),
        },
        {
            "title": "Confidence vs Importance Scores",
            "body": create_scatter_plot(agg_data),
        },
    ]
