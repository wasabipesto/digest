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
    input_content = item.get("input", item)
    prompt_parts.append(json.dumps(input_content))

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
        return response_json

    except requests.exceptions.RequestException as e:
        print(f"Error calling ollama: {e}", file=sys.stderr)
        return f"Error: Failed to get response from ollama - {str(e)}"


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

        if not source_config_paths:
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
                    f"  Processing item {i + 1}/{len(data_items)}: {item.get('title', 'Untitled')}"
                )

                # Assemble the final prompt
                prompt = assemble_prompt(merged_config, item)
                item["prompt"] = prompt

                # Run through ollama
                response = call_ollama(prompt)
                item["response"] = response

                # Save to final array
                all_results.append(item)

        # Output results
        print(f"\nCompleted processing {len(all_results)} total items")

        # Save results to file
        output_file = "digest_results.json"
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2)

        print(f"Results saved to {output_file}")

        # Print summary
        print("\nSummary:")
        for item in all_results:
            print(f"- [{item['source']}] {item.get('title', 'Untitled')}")
            if "link" in item:
                print(f"  Link: {item['link']}")
            print(
                f"  Score: {item['response'].get('importance_score', 'ERR')}, Confidence {item['response'].get('confidence_score', 'ERR')}"
            )
            print()

    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
