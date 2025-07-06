#!/usr/bin/env python3

import json
from typing import Dict, Any
from datetime import datetime, timedelta, timezone

from utils.config import get_int_config, get_config_value, get_float_config


def assemble_prompt(item: Dict[str, Any]) -> str:
    """Assemble the final prompt for an item using the config"""
    prompt_parts = []
    config_path = item["config_path"]

    # Add components in the specified order
    prompt_parts = [
        get_config_value("prompt_header", config_path),
        get_config_value("prompt_introduction", config_path),
        get_config_value("prompt_container_pre", config_path),
        item["title"],
        json.dumps(item["input"]),
        get_config_value("prompt_container_post", config_path),
        get_config_value("prompt_criteria", config_path),
        get_config_value("prompt_instructions", config_path),
    ]

    return "\n\n".join(prompt_parts)


def is_item_important(item: Dict[str, Any]) -> bool:
    """Check if an item meets the importance score cutoff"""
    min_score = get_float_config("min_email_score", item["config_path"], 70.0)
    return (item.get("weighted_score") or 0) >= min_score


def is_item_recent(item: Dict[str, Any]) -> bool:
    """Check if an item was created within the lookback period"""
    lookback_days = get_int_config("lookback_days", item["config_path"], 7)
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


def needs_evaluation(item: Dict[str, Any], eval_round_num: int) -> bool:
    """Check if an item needs evaluation for the current pass"""
    num_evals_passed = item["num_evals"]
    queued_to_reevaluate = num_evals_passed < eval_round_num
    been_evaluated_a_lot = num_evals_passed > 5
    high_confidence = item["median_confidence"] and item["median_confidence"] > 80
    obviously_good = item["weighted_score"] and item["weighted_score"] > 80
    obviously_bad = item["weighted_score"] and item["weighted_score"] < 20

    # Big brain time: If we're confident that the item is good or bad, don't evaluate it again
    if (
        queued_to_reevaluate
        and been_evaluated_a_lot
        and high_confidence
        and (obviously_good or obviously_bad)
    ):
        print(f"Skipping: {item['title']} (bigbrain)")
        return False

    # Standard mode: Only if queued
    return queued_to_reevaluate
