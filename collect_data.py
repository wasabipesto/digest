#!/usr/bin/env python3

import argparse
import json
import sys
import toml
from pathlib import Path
from typing import Dict, List, Any, Set
from datetime import datetime
import hashlib


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
    import subprocess

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


def get_dedup_key(item: Dict[str, Any]) -> str:
    """Generate a deduplication key for this item"""
    dedup_string = f"{item['title']}|{item['creation_date']}"
    return hashlib.md5(dedup_string.encode("utf-8")).hexdigest()


def deduplicate_items(all_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate items based on title and link"""
    seen_keys: Set[str] = set()
    unique_items = []
    duplicates_removed = 0

    for item in all_items:
        dedup_key = get_dedup_key(item)

        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            item["dedup_key"] = dedup_key
            unique_items.append(item)
        else:
            duplicates_removed += 1

    if duplicates_removed > 0:
        print(f"Removed {duplicates_removed} duplicate items")

    return unique_items


def load_existing_data(data_file: str) -> List[Dict[str, Any]]:
    """Load existing data from file if it exists"""
    data_path = Path(data_file)
    if data_path.exists():
        try:
            with open(data_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return []


def merge_new_with_existing(
    existing_items: List[Dict[str, Any]], new_items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge new items with existing ones, preserving evaluations"""
    # Create a map of existing items by dedup_key
    existing_map = {}
    for item in existing_items:
        if "dedup_key" in item:
            existing_map[item["dedup_key"]] = item

    merged_items = []
    new_count = 0
    updated_count = 0

    # Process new items
    for new_item in new_items:
        dedup_key = new_item["dedup_key"]

        if dedup_key in existing_map:
            # Item exists - preserve evaluation data but update other fields
            existing_item = existing_map[dedup_key]

            # Update data fields but preserve evaluation fields
            for key, value in new_item.items():
                if key not in ["response", "prompt", "prompt_hash", "eval_date"]:
                    existing_item[key] = value

            # Update collection timestamp
            existing_item["last_collected"] = datetime.now().isoformat()
            merged_items.append(existing_item)
            updated_count += 1
        else:
            # New item
            new_item["first_collected"] = datetime.now().isoformat()
            new_item["last_collected"] = datetime.now().isoformat()
            merged_items.append(new_item)
            new_count += 1

    # Add any existing items that weren't in the new batch
    for existing_item in existing_items:
        if "dedup_key" in existing_item and existing_item["dedup_key"] not in {
            item["dedup_key"] for item in new_items
        }:
            merged_items.append(existing_item)

    print(f"Added {new_count} new items, updated {updated_count} existing items")
    return merged_items


def main():
    """Main function that collects data from all sources"""
    parser = argparse.ArgumentParser(description="Collect data from digest sources")
    parser.add_argument(
        "--source",
        "-s",
        type=str,
        help="Process only the specified source (optional)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="raw_data.json",
        help="Output file for collected data (default: raw_data.json)",
    )
    args = parser.parse_args()

    print("Starting data collection...")

    try:
        # Find and load each source's config.toml file
        print("Finding source configurations...")
        source_config_paths = find_source_configs()

        # Filter by specified source if provided
        if args.source:
            source_config_paths = [
                path for path in source_config_paths if path.parent.name == args.source
            ]
            if not source_config_paths:
                print(f"Source '{args.source}' not found.")
                print("Available sources:")
                all_source_names = [
                    config_path.parent.name for config_path in find_source_configs()
                ]
                for source_name in all_source_names:
                    print(f"  {source_name}")
                return

        if len(source_config_paths) > 0:
            source_names = [
                config_path.parent.name for config_path in source_config_paths
            ]
            if args.source:
                print(f"Processing specified source: {args.source}")
            else:
                print(f"Found source configurations: {', '.join(source_names)}")
        else:
            print("No source configurations found.")
            return

        # Load existing data
        existing_data = load_existing_data(args.output)
        print(f"Loaded {len(existing_data)} existing items")

        all_new_items = []

        for config_path in source_config_paths:
            source_name = config_path.parent.name
            print(f"\nProcessing source: {source_name}")

            # Fetch data by running the source's data loader
            loader_path = load_source_config(config_path).get("loader")
            if not loader_path:
                print(f"No loader specified for source {source_name}")
                continue

            print(f"Running data loader: {loader_path}")
            data_items = run_data_loader(loader_path)

            if not data_items:
                print(f"No data returned from loader for source {source_name}")
                continue

            # Set config path so evaluator knows where to find the source config
            for i in data_items:
                i["config_path"] = str(config_path)

            print(f"Collected {len(data_items)} items from {source_name}")
            all_new_items.extend(data_items)

        if not all_new_items:
            print("No new data collected.")
            return

        print(f"\nTotal items collected: {len(all_new_items)}")

        # Deduplicate new items
        print("Deduplicating items...")
        unique_new_items = deduplicate_items(all_new_items)
        print(f"Unique items after deduplication: {len(unique_new_items)}")

        # Merge with existing data
        print("Merging with existing data...")
        final_items = merge_new_with_existing(existing_data, unique_new_items)

        # Save results to file
        print(f"\nSaving {len(final_items)} total items to {args.output}")
        with open(args.output, "w") as f:
            json.dump(final_items, f, indent=2)

        print("Data collection completed successfully!")

    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
