#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import sys
import time
import toml
from pathlib import Path
import requests
from typing import Dict, List, Any
from datetime import datetime


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


def needs_evaluation(item: Dict[str, Any]) -> bool:
    """Check if an item needs evaluation"""
    # Check if item has response
    if "response" not in item:
        return True

    # Check if response has required fields
    response = item["response"]
    if not isinstance(response, dict):
        return True

    required_keys = {"summary", "evaluation", "importance_score", "confidence_score"}
    if not required_keys.issubset(response.keys()):
        return True

    # Check if prompt has changed (if we have a stored prompt hash)
    if "prompt_hash" in item and "prompt" in item:
        current_prompt_hash = hashlib.sha256(item["prompt"].encode("utf-8")).hexdigest()
        if current_prompt_hash != item["prompt_hash"]:
            return True

    return False


def main():
    """Main function that evaluates items without evaluations"""
    parser = argparse.ArgumentParser(description="Evaluate items using LLM")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="raw_data.json",
        help="Input file with collected data (default: raw_data.json)",
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
        "--limit",
        "-l",
        type=int,
        help="Limit number of items to evaluate (useful for testing)",
    )
    args = parser.parse_args()

    print("Starting evaluation process...")

    try:
        # Load data
        print(f"Loading data from {args.input}...")
        all_items = load_data(args.input)
        print(f"Loaded {len(all_items)} items")

        # Find items that need evaluation
        if args.force:
            items_to_evaluate = all_items
            print("Force mode: evaluating all items")
        else:
            items_to_evaluate = [item for item in all_items if needs_evaluation(item)]
            print(f"Found {len(items_to_evaluate)} items needing evaluation")

        if not items_to_evaluate:
            print("No items need evaluation. Use --force to re-evaluate all items.")
            return

        # Apply limit if specified
        if args.limit:
            items_to_evaluate = items_to_evaluate[: args.limit]
            print(f"Limited to {len(items_to_evaluate)} items")

        # Get the base configuration
        base_config = load_base_config()

        # Process each item
        evaluated_count = 0
        for i, item in enumerate(items_to_evaluate):
            print(f"Evaluating item {i + 1}/{len(items_to_evaluate)}: {item['title']}")

            try:
                # Get the item's source configuration
                source_config = load_source_config(item["config_path"])

                # Merge the base config with the current item's config
                config = merge_configs(base_config, source_config)

                # Assemble the prompt
                prompt = assemble_prompt(config, item)
                item["prompt"] = prompt

                # Calculate and store prompt hash
                prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                item["prompt_hash"] = prompt_hash

                # Store evaluation timestamp
                item["eval_date"] = datetime.now().isoformat()

                # Run through ollama
                response = call_ollama(prompt)
                item["response"] = response
                evaluated_count += 1

                print(
                    f"  Score: {item['response']['importance_score']}, "
                    f"Confidence: {item['response']['confidence_score']}"
                )

            except Exception as e:
                print(f"  Error evaluating item: {e}", file=sys.stderr)
                # Continue with other items rather than failing completely
                continue

        print(f"\nSuccessfully evaluated {evaluated_count} items")

        # Save results
        print(f"Saving results to {args.output}...")
        with open(args.output, "w") as f:
            json.dump(all_items, f, indent=2)

        print("Evaluation completed successfully!")

    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
