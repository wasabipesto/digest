#!/usr/bin/env python3

import argparse
import sys
import json
import numpy as np
from typing import Dict, List, Any
from utils import (
    get_config_value,
    get_config_int,
    assemble_prompt,
    is_item_recent,
    needs_evaluation,
    load_json_file,
    save_json_file,
    call_ollama,
)


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
        help="Number of evaluation rounds (default from config 'eval_rounds', use 'infinite' for continuous evaluation)",
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
        max_rounds = get_config_int("eval_rounds", "base.toml", 1)

        print(
            f"Starting evaluation process with {max_rounds if max_rounds != float('inf') else 'infinite'} rounds..."
        )

    try:
        # Load data
        print(f"Loading data from {args.input}...")
        all_items = load_json_file(args.input)
        print(f"Loaded {len(all_items)} items")

        # Filter items by recency
        recent_items = [item for item in all_items if is_item_recent(item)]
        print(f"Filtered to {len(recent_items)} items based on source criteria")

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
                    # Assemble the prompt
                    prompt = assemble_prompt(item)

                    # Run through ollama
                    eval_provider = get_config_value(
                        "eval_provider", item["config_path"], "ollama"
                    )
                    if eval_provider == "ollama":
                        eval_data = call_ollama(item, prompt)
                    else:
                        raise ValueError(f"Unknown eval provider: {eval_provider}")

                    round_evaluated += 1
                    total_evaluated += 1

                    # Save and aggregate evals so far
                    eval_data["round"] = round_num
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
                    save_json_file(all_items, args.output)

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
