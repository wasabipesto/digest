import json
import matplotlib.pyplot as plt
import os
from collections import defaultdict

PLOTS_DIR = "plots"
TARGET_ITEM_KEY = "dcac426447620e3ee276475df208f58d"


def load_digest_results(path):
    with open(path, "r") as f:
        return json.load(f)


def extract_items(digest_results):
    all_items = []

    for item in digest_results:
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


def plot_target_scatter(all_items):
    target_item = [i for i in all_items if i["dedup_key"] == TARGET_ITEM_KEY][0]

    fig, ax = plt.subplots(figsize=(10, 8))

    scores = [e["score"] for e in target_item["evals"]]
    confidences = [e["confidence"] for e in target_item["evals"]]
    ax.scatter(scores, confidences, alpha=0.6, s=50)
    ax.set_title(f"Scores vs Confidence for\n{target_item['title']}")

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Importance Score")
    ax.set_ylabel("Confidence Score")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{PLOTS_DIR}/target_scatterplot.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_importance_eventplot(all_items, max_items_to_show=20, max_title_len=50):
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
    plt.savefig(f"{PLOTS_DIR}/importance_eventplot.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_all_scatter(all_items):
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
    plt.savefig(f"{PLOTS_DIR}/all_scatterplot.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(PLOTS_DIR, exist_ok=True)
    digest_results = load_digest_results("digest_results.json")
    all_items = extract_items(digest_results)

    plot_target_scatter(all_items)
    plot_importance_eventplot(all_items)
    plot_all_scatter(all_items)

    print(f"Analysis complete. Processed {len(all_items)} items.")
