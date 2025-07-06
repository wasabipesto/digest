#!/usr/bin/env python3
"""
Configuration utility module for digest data loaders.

This module provides functions to load configuration from TOML files,
with fallback to base configuration and environment variables for secrets.
"""

import os
import toml
from pathlib import Path
from typing import Dict, Any, Optional


def load_base_config() -> Dict[str, Any]:
    """Load base configuration from sources/base.toml"""
    base_config_path = Path("sources/base.toml")
    if not base_config_path.exists():
        raise FileNotFoundError(f"Base config file not found: {base_config_path}")

    with open(base_config_path, "r") as f:
        return toml.load(f)


def load_source_config(config_path: str) -> Dict[str, Any]:
    """Load a source's config.toml file"""
    if config_path == "" or config_path is None:
        raise ValueError("Config path cannot be empty or null")

    if not config_path.exists():
        raise FileNotFoundError(f"Source config file not found: {config_path}")

    with open(config_path, "r") as f:
        return toml.load(f)


def get_config_value(key: str, config_path: str, default: Any = None) -> Any:
    """
    Get a configuration value with fallback priority:
    1. Environment variable (for secrets)
    2. Source-specific config.toml
    3. Base config.toml
    4. Default value
    """
    # Always check environment first for secrets
    env_value = os.getenv(key)
    if env_value is not None:
        return env_value

    try:
        # Load source config
        source_config = load_source_config(config_path)
        if key in source_config:
            return source_config[key]
    except FileNotFoundError:
        pass

    try:
        # Load base config
        base_config = load_base_config()
        if key in base_config:
            return base_config[key]
    except FileNotFoundError:
        pass

    if default is not None:
        return default
    raise ValueError(f"Configuration key '{key}' not found and no default provided")

def get_config(config_path: str) -> Dict[str, Any]:
    """
    Get merged configuration for a source.
    Base config is loaded first, then source config overrides it.
    Environment variables are not included here - use get_config_value for those.
    """
    try:
        base_config = load_base_config()
    except FileNotFoundError:
        base_config = {}

    try:
        source_config = load_source_config(config_path)
    except FileNotFoundError:
        source_config = {}

    # Merge configs (source overrides base)
    merged_config = base_config.copy()
    merged_config.update(source_config)

    return merged_config


def get_int_config(key: str, config_path: str, default: int = 0) -> int:
    """Get an integer configuration value with type conversion"""
    value = get_config_value(key, config_path, default)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return int(value) if value is not None else default


def get_float_config(key: str, config_path: str, default: float = 0.0) -> float:
    """Get a float configuration value with type conversion"""
    value = get_config_value(key, config_path, default)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return float(value) if value is not None else default


def get_list_config(key: str, config_path: str, default: list = None, separator: str = ",") -> list:
    """Get a list configuration value, handling both TOML arrays and comma-separated strings"""
    if default is None:
        default = []

    value = get_config_value(key, config_path, default)

    if isinstance(value, list):
        return value
    elif isinstance(value, str):
        return [item.strip() for item in value.split(separator) if item.strip()]
    else:
        return default
