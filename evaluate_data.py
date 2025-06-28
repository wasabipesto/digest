#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import sys
import time
import toml
import numpy as np
from pathlib import Path
import requests
from typing import Dict, List, Any
from datetime import datetime, timedelta, UTC


def load_data(data_file: str) -> List[Dict[str, Any]]:
    """Load data from the specified file"""
    data_path = Path(data_file)
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    with open(data_path, "r") as f:
        return json.load(f)


def load_base_config() -> Dict[str, Any]:
    """Load base configuration from sources/base.toml"""
    base_config_path = Path("sources/base.toml")
    if not base_config_path.exists():
        raise FileNotFoundError(f"Base config file not found: {base_config_path}")

    with open(base_config_path, "r") as f:
        return toml.load(f)


def load_source_config(config_path: Path) -> Dict[str, Any]:
    """Load a source's config.toml file"""
    with open(config_path, "r") as f:
        return toml.load(f)


def merge_configs(
    base_config: Dict[str, Any], source_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge base config with source config, source config takes precedence"""
    merged = base_config.copy()
    merged.update(source_config)
    return merged


def assemble_prompt(config: Dict[str, Any], item: Dict[str, Any]) -> str:
    """Assemble the final prompt for an item using the config"""
    prompt_parts = []

    # Add components in the specified order
    if "header" in config:
        prompt_parts.append(config["header"])

    if "introduction" in config:
        prompt_parts.append(config["introduction"])

    # Input container with the actual content
    if "container_pre" in config:
        prompt_parts.append(config["container_pre"])

    # Add the actual input content
    prompt_parts.append(item["title"])
    prompt_parts.append(json.dumps(item["input"]))

    if "container_post" in config:
        prompt_parts.append(config["container_post"])

    if "criteria" in config:
        prompt_parts.append(config["criteria"])

    if "instructions" in config:
        prompt_parts.append(config["instructions"])

    return "\n\n".join(prompt_parts)


def call_ollama(prompt: str) -> Dict[str, Any]:
    """Call ollama with the prompt and return the response"""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
    max_retries = int(os.getenv("OLLAMA_RETRIES", 3))

    required_keys = {"summary", "evaluation", "importance_score", "confidence_score"}

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{ollama_base_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
                timeout=60,
            )
            response.raise_for_status()
            response_text = response.json().get("response")
            response_json = json.loads(response_text)

            # Check if response has all required keys
            if isinstance(response_json, dict) and required_keys.issubset(
                response_json.keys()
            ):
                return response_json
            else:
                missing_keys = required_keys - set(
                    response_json.keys() if isinstance(response_json, dict) else []
                )
                print(
                    f"Attempt {attempt + 1}: Missing required keys in response: {missing_keys}",
                    file=sys.stderr,
                )
                if attempt == max_retries - 1:
                    print(
                        f"Failed to get valid response after {max_retries} attempts",
                        file=sys.stderr,
                    )
                    raise ValueError("Failed to get valid response from ollama")

        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1}: Error calling ollama: {e}", file=sys.stderr)
            time.sleep(1)
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Failed to get response from ollama after {max_retries} attempts: {str(e)}"
                )
        except json.JSONDecodeError as e:
            print(
                f"Attempt {attempt + 1}: Error parsing JSON response: {e}",
                file=sys.stderr,
            )
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to parse JSON response after {max_retries} attempts: {str(e)}"
                )

    raise RuntimeError("Unexpected error in call_ollama")


def needs_evaluation(item: Dict[str, Any], max_evals_for_pass: int) -> bool:
    """Check if an item needs evaluation for the current pass"""
    return item["num_evals"] < max_evals_for_pass


def weighted_score(evals: List[Dict[str, Any]]) -> float:
    """Aggregate a weighted score from evaluations"""
    total_score = 0
    total_weight = 0
    for eval in evals:
        i_score = eval["response"]["importance_score"]
        i_weight = eval["response"]["confidence_score"] + 100
        total_score += i_score * i_weight
        total_weight += i_weight
    return int(total_score / total_weight) if total_weight > 0 else 0


def median_confidence(evals: List[Dict[str, Any]]) -> float:
    """Aggregate a median confidence score from evaluations"""
    return int(np.median([e["response"]["confidence_score"] for e in evals]))


def is_item_recent(item: Dict[str, Any], lookback_days: int) -> bool:
    """Check if an item was created within the lookback period"""
    if lookback_days <= 0:
        return True  # No date filtering

    try:
        # Assuming item has a 'date' or 'created_date' field
        item_date_str = item.get("creation_date")
        if not item_date_str:
            return True  # If no date info, include it

        item_date = datetime.fromisoformat(item_date_str)
        cutoff_date = datetime.now(tz=UTC) - timedelta(days=lookback_days)

        return item_date >= cutoff_date
    except (ValueError, AttributeError):
        # If we can't parse the date, include the item
        return True


def main():
    """Main function that evaluates items with multiple evaluation passes"""
    parser = argparse.ArgumentParser(description="Evaluate items using LLM")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="digest_results.json",
        help="Input file with collected data (default: digest_results.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="digest_results.json",
        help="Output file for evaluated data (default: digest_results.json)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-evaluation of all items",
    )
    parser.add_argument(
        "--rounds",
        "-r",
        type=str,
        help="Number of evaluation rounds (default from env EVAL_ROUNDS, use 'infinite' for continuous evaluation)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        help="Only evaluate items created within this many days (default from env LOOKBACK_DAYS, use 0 for no limit)",
    )
    args = parser.parse_args()

    # Get configuration from environment or arguments
    if args.rounds:
        if args.rounds.lower() == "infinite" or args.rounds.lower() == "inf":
            max_rounds = float("inf")
            print("Running in infinite evaluation mode")
        else:
            max_rounds = int(args.rounds)
    else:
        max_rounds = int(os.getenv("EVAL_ROUNDS", "3"))

    lookback_days = (
        args.lookback_days
        if args.lookback_days is not None
        else int(os.getenv("LOOKBACK_DAYS", "7"))
    )

    print(
        f"Starting evaluation process with {max_rounds if max_rounds != float('inf') else 'infinite'} rounds..."
    )
    print(
        f"Lookback period: {'No limit' if lookback_days <= 0 else f'{lookback_days} days'}"
    )

    try:
        # Load data
        print(f"Loading data from {args.input}...")
        all_items = load_data(args.input)
        print(f"Loaded {len(all_items)} items")

        # Filter items by date if lookback_days is specified
        if not args.force and lookback_days > 0:
            recent_items = [
                item for item in all_items if is_item_recent(item, lookback_days)
            ]
            print(
                f"Filtered to {len(recent_items)} items created within the last {lookback_days} days"
            )
        else:
            recent_items = all_items

        # Get the base configuration
        base_config = load_base_config()

        # Run multiple evaluation rounds
        total_evaluated = 0
        round_num = 1

        while round_num <= max_rounds:
            print(f"\n--- Evaluation Round {round_num} of {max_rounds} ---")

            # Find items that need evaluation for this round
            if args.force:
                # In force mode, re-evaluate everything in every round
                items_to_evaluate = recent_items
                print("Force mode: evaluating all items")
            else:
                # Normal mode: evaluate items with fewer than round_num evaluations
                items_to_evaluate = [
                    item for item in recent_items if needs_evaluation(item, round_num)
                ]
                print(
                    f"Found {len(items_to_evaluate)} items needing evaluation (round {round_num})"
                )

            # Process each item in this round
            round_evaluated = 0
            for i, item in enumerate(items_to_evaluate):
                print(
                    f"Evaluating item {i + 1}/{len(items_to_evaluate)}: {item['title']}"
                )

                try:
                    # Initialize the eval data
                    eval_data = {}

                    # Get the item's source configuration
                    source_config = load_source_config(item["config_path"])

                    # Merge the base config with the current item's config
                    config = merge_configs(base_config, source_config)

                    # Assemble the prompt
                    prompt = assemble_prompt(config, item)
                    eval_data["prompt"] = prompt

                    # Calculate and store some eval data
                    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                    eval_data["model"] = os.getenv("OLLAMA_MODEL", "llama3.2")
                    eval_data["prompt_hash"] = prompt_hash
                    eval_data["eval_date"] = datetime.now().isoformat()
                    eval_data["round"] = round_num

                    # Run through ollama
                    response = call_ollama(prompt)
                    eval_data["response"] = response
                    round_evaluated += 1
                    total_evaluated += 1

                    # Save and aggregate evals so far
                    item["evals"].append(eval_data)
                    item["num_evals"] += 1
                    item["weighted_score"] = weighted_score(item["evals"])
                    item["median_confidence"] = median_confidence(item["evals"])
                    item["last_eval"] = eval_data["eval_date"]

                    # Print results and save
                    print(
                        f" Score: {eval_data['response']['importance_score']},"
                        f" Confidence: {eval_data['response']['confidence_score']},"
                        f" Cumulative Score: {item['weighted_score']}"
                    )

                    # Save after each evaluation to prevent data loss
                    with open(args.output, "w") as f:
                        json.dump(all_items, f, indent=2)

                except Exception as e:
                    print(f"  Error evaluating item: {e}", file=sys.stderr)
                    # Continue with other items rather than failing completely
                    continue

            print(f"Round {round_num} completed: evaluated {round_evaluated} items")
            round_num += 1

    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        sys.exit(1)

    # Final save
    print(f"Saving final results to {args.output}...")
    with open(args.output, "w") as f:
        json.dump(all_items, f, indent=2)

    print("\nEvaluation process completed!")
    print(f"Total evaluations across all rounds: {total_evaluated}")


if __name__ == "__main__":
    main()
