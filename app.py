#!/usr/bin/env python3
"""
Flask web application for viewing digest results.

This app serves the digest results data through a web interface,
replacing the static HTML file with server-side data loading.
"""

from flask import Flask, render_template, jsonify
from pathlib import Path
from utils import load_json_file_safe

app = Flask(__name__)

# Configuration
DATA_FILE = "digest_results.json"
DEBUG = True


@app.route("/")
def index():
    """Serve the main digest results viewer page."""
    return render_template("index.html")


@app.route("/api/data")
def get_data():
    """API endpoint to get digest results data."""
    try:
        data = load_json_file_safe(DATA_FILE)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
def get_stats():
    """API endpoint to get summary statistics."""
    try:
        data = load_json_file_safe(DATA_FILE)

        if not data:
            return jsonify(
                {
                    "total_items": 0,
                    "sources": [],
                    "score_ranges": {"high": 0, "medium": 0, "low": 0},
                }
            )

        # Calculate statistics
        total_items = len(data)
        sources = list(set(item.get("source", "Unknown") for item in data))

        # Score ranges
        high_score = sum(1 for item in data if item.get("weighted_score", 0) >= 70)
        medium_score = sum(
            1 for item in data if 30 <= item.get("weighted_score", 0) < 70
        )
        low_score = sum(1 for item in data if item.get("weighted_score", 0) < 30)

        return jsonify(
            {
                "total_items": total_items,
                "sources": sorted(sources),
                "score_ranges": {
                    "high": high_score,
                    "medium": medium_score,
                    "low": low_score,
                },
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/item/<item_id>")
def get_item_details(item_id):
    """API endpoint to get detailed information about a specific item."""
    try:
        data = load_json_file_safe(DATA_FILE)

        # Find item by dedup_key
        item = None
        for d in data:
            if d.get("dedup_key") == item_id:
                item = d
                break

        if not item:
            return jsonify({"error": "Item not found"}), 404

        return jsonify(item)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "data_file_exists": Path(DATA_FILE).exists(),
            "data_file_size": Path(DATA_FILE).stat().st_size
            if Path(DATA_FILE).exists()
            else 0,
        }
    )


if __name__ == "__main__":
    app.run(debug=DEBUG, host="0.0.0.0", port=5000)
