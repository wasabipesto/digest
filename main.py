#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import toml
from pathlib import Path
import requests
from typing import Dict, List, Any


def load_base_config() -> Dict[str, Any]:
    """Load base configuration from sources/base.toml"""
    base_config_path = Path("sources/base.toml")
    if not base_config_path.exists():
        raise FileNotFoundError(f"Base config file not found: {base_config_path}")

    with open(base_config_path, "r") as f:
        return toml.load(f)


def find_source_configs() -> List[Path]:
    """Find all source config.toml files"""
    sources_dir = Path("sources")
    config_files = []

    for item in sources_dir.iterdir():
        if item.is_dir() and item.name != "__pycache__":
            config_path = item / "config.toml"
            if config_path.exists():
                config_files.append(config_path)

    return config_files


def load_source_config(config_path: Path) -> Dict[str, Any]:
    """Load a source's config.toml file"""
    with open(config_path, "r") as f:
        return toml.load(f)


def run_data_loader(loader_path: str) -> List[Dict[str, Any]]:
    """Run a source's data loader and return the JSON output"""
    try:
        # Make the loader path executable
        full_loader_path = Path(loader_path)
        if not full_loader_path.exists():
            raise FileNotFoundError(f"Data loader not found: {full_loader_path}")

        # Run the loader script
        result = subprocess.run(
            [str(full_loader_path)],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path.cwd(),
        )

        # Parse JSON output
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else [data]

    except subprocess.CalledProcessError as e:
        print(f"Error running data loader {loader_path}: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from {loader_path}: {e}", file=sys.stderr)
        print(f"stdout: {result.stdout}", file=sys.stderr)
        return []


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
    prompt_parts.append(item["input"])

    if "container_post" in config:
        prompt_parts.append(config["container_post"])

    if "criteria" in config:
        prompt_parts.append(config["criteria"])

    if "instructions" in config:
        prompt_parts.append(config["instructions"])

    return "\n\n".join(prompt_parts)


def call_ollama(prompt: str) -> str:
    """Call ollama with the prompt and return the response"""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")

    required_keys = {"summary", "evaluation", "importance_score", "confidence_score"}
    max_retries = 3

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
                timeout=300,
            )
            response.raise_for_status()

            result = response.json()
            response = result["response"]
            response_json = json.loads(response)

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
                    sys.exit(1)

        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1}: Error calling ollama: {e}", file=sys.stderr)
            if attempt == max_retries - 1:
                print(
                    f"Failed to get response from ollama after {max_retries} attempts - {str(e)}",
                    file=sys.stderr,
                )
                sys.exit(1)
        except json.JSONDecodeError as e:
            print(
                f"Attempt {attempt + 1}: Error parsing JSON response: {e}",
                file=sys.stderr,
            )
            if attempt == max_retries - 1:
                print(
                    f"Failed to parse JSON response after {max_retries} attempts - {str(e)}",
                    file=sys.stderr,
                )
                sys.exit(1)

    print("Unexpected error in call_ollama", file=sys.stderr)
    sys.exit(1)


def main():
    """Main function that orchestrates the entire process"""
    print("Starting digest processing...")

    try:
        # Step 1: Get base config from sources/base.toml
        print("Loading base configuration...")
        base_config = load_base_config()

        # Step 2: Find and load each source's config.toml file
        print("Finding source configurations...")
        source_config_paths = find_source_configs()

        if len(source_config_paths) > 0:
            source_names = [
                config_path.parent.name for config_path in source_config_paths
            ]
            print(f"Found source configurations {', '.join(source_names)}.")
        else:
            print("No source configurations found.")
            return

        all_results = []

        for config_path in source_config_paths:
            source_name = config_path.parent.name
            print(f"\nProcessing source: {source_name}")

            # Load source config
            source_config = load_source_config(config_path)

            # Merge configs (source takes precedence)
            merged_config = merge_configs(base_config, source_config)

            # Step 3: Fetch data by running the source's data loader
            loader_path = merged_config.get("loader")
            if not loader_path:
                print(f"No loader specified for source {source_name}")
                continue

            print(f"Running data loader: {loader_path}")
            data_items = run_data_loader(loader_path)

            if not data_items:
                print(f"No data returned from loader for source {source_name}")
                continue

            print(f"Processing {len(data_items)} items from {source_name}")

            # Step 4 & 5: Assemble prompt and run through ollama for each item
            for i, item in enumerate(data_items):
                print(
                    f"  Processing item {i + 1}/{len(data_items)}: {item['title']}",
                )

                # Assemble the final prompt
                prompt = assemble_prompt(merged_config, item)
                item["prompt"] = prompt

                # Run through ollama
                response = call_ollama(prompt)
                item["response"] = response
                print(
                    f"    Score: {item['response']['importance_score']}, Confidence: {item['response']['confidence_score']}"
                )

                # Save to final array
                all_results.append(item)

        # Output results
        print(f"\nCompleted processing {len(all_results)} total items")

        # Save results to file
        output_file = "digest_results.json"
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2)

        print(f"Results saved to {output_file}")

    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
