#!/usr/bin/env python3
"""
Common utility functions for the digest system.

This module provides shared functionality for file operations,
API calls, and other common tasks used across the digest system.
"""

import json
import sys
import time
import hashlib
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.config import get_config_value, get_config_int


def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Load JSON data from a file.

    Args:
        file_path: Path to the JSON file

    Returns:
        List of dictionaries containing the JSON data

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    with open(path, "r") as f:
        data = json.load(f)

    # Ensure we return a list for consistency
    return data if isinstance(data, list) else [data]


def save_json_file(data: List[Dict[str, Any]], file_path: str, indent: int = 2) -> None:
    """
    Save data to a JSON file.

    Args:
        data: Data to save
        file_path: Path where to save the file
        indent: JSON indentation level
    """
    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)


def load_json_file_safe(file_path: str) -> List[Dict[str, Any]]:
    """
    Load JSON data from a file, returning empty list if file doesn't exist.

    Args:
        file_path: Path to the JSON file

    Returns:
        List of dictionaries containing the JSON data, or empty list if file doesn't exist
    """
    try:
        return load_json_file(file_path)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


def call_ollama(item: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """
    Call ollama with the prompt and return the response.

    Args:
        prompt: The prompt to send to ollama
        model: Model to use (defaults to env OLLAMA_MODEL or 'llama3.2')
        base_url: Base URL for ollama (defaults to env OLLAMA_BASE_URL or 'http://localhost:11434')

    Returns:
        Dictionary containing the parsed JSON response

    Raises:
        RuntimeError: If ollama fails to respond after max retries
        ValueError: If the response doesn't contain required fields
    """
    config_path = item["config_path"]
    ollama_base_url = get_config_value(
        "OLLAMA_BASE_URL", config_path, "http://localhost:11434"
    )
    ollama_model = get_config_value("eval_model", config_path, "llama3.2")
    max_retries = get_config_int("eval_model", config_path, 3)

    # Initialize the eval data
    eval_data = {
        "model": ollama_model,
        "prompt": prompt,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "eval_date": get_current_timestamp(),
    }

    # Set the reuired keys
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
                if not isinstance(response_json["importance_score"], int):
                    print(
                        f"Attempt {attempt + 1}: Importance score ({response_json['importance_score']}) should be a number",
                        file=sys.stderr,
                    )
                    continue
                if not isinstance(response_json["confidence_score"], int):
                    print(
                        f"Attempt {attempt + 1}: Confidence score ({response_json['confidence_score']}) should be a number",
                        file=sys.stderr,
                    )
                    continue

                # All keys are present and numbers are numbers
                eval_data["response"] = response_json
                return eval_data
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


def get_dedup_key(item: Dict[str, Any]) -> str:
    """
    Generate a deduplication key for an item.

    Args:
        item: Item dictionary containing 'source' and 'link' keys

    Returns:
        MD5 hash of the deduplication string
    """
    dedup_string = f"{item['source']}|{item['link']}"
    return hashlib.md5(dedup_string.encode("utf-8")).hexdigest()


def get_current_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        Current timestamp as ISO string
    """
    return datetime.now().isoformat()


def ensure_directory_exists(file_path: str) -> None:
    """
    Ensure the directory for a file path exists.

    Args:
        file_path: Path to a file
    """
    directory = Path(file_path).parent
    directory.mkdir(parents=True, exist_ok=True)


def run_subprocess_with_json_output(
    command: List[str], cwd: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Run a subprocess and parse its JSON output.

    Args:
        command: Command to run as a list of strings
        cwd: Working directory for the command

    Returns:
        List of dictionaries from the JSON output

    Raises:
        subprocess.CalledProcessError: If the command fails
        json.JSONDecodeError: If the output is not valid JSON
    """
    import subprocess

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )

        # Pass through stderr
        for line in result.stderr.splitlines():
            if line.strip():
                print(line, file=sys.stderr)

        # Parse JSON output from stdout
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else [data]

    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(command)}: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        raise
    except json.JSONDecodeError as e:
        print(
            f"Error parsing JSON from command {' '.join(command)}: {e}", file=sys.stderr
        )
        print(f"stdout: {result.stdout}", file=sys.stderr)
        raise
