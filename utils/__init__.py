"""
Utilities package for the digest system.

This package contains shared utilities for configuration management,
data processing, and other common functionality used across the digest system.
"""

from .config import (
    get_config_value,
    get_config,
    get_int_config,
    get_float_config,
    get_list_config,
    load_base_config,
    load_source_config,
)

from .common import (
    load_json_file,
    save_json_file,
    load_json_file_safe,
    call_ollama,
    get_dedup_key,
    get_current_timestamp,
    ensure_directory_exists,
    run_subprocess_with_json_output,
)

__all__ = [
    "get_config_value",
    "get_config",
    "get_int_config",
    "get_float_config",
    "get_list_config",
    "load_base_config",
    "load_source_config",
    "load_json_file",
    "save_json_file",
    "load_json_file_safe",
    "call_ollama",
    "get_dedup_key",
    "get_current_timestamp",
    "ensure_directory_exists",
    "run_subprocess_with_json_output",
]
