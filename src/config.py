"""Application configuration from config.yaml.

This is the sole configuration reader in the entire application.
Supports config.yaml with environment variable overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    vs_token: str
    category_id: int
    country: str
    interval: str
    duration_threshold_secs: int
    gemini_api_key: str
    translate_top_n: int
    # Feishu SDK credentials (required)
    feishu_app_id: str
    feishu_app_secret: str
    feishu_chat_id: str
    # Feishu doc archival (optional)
    feishu_folder_token: str | None
    # Feishu tenant domain for document URLs
    feishu_domain: str


def load_settings(config_path: str | Path = "config.yaml") -> Settings:
    """Load settings from YAML file with env var overrides.

    Priority: environment variable > config.yaml > default value.
    """
    path = Path(config_path)
    data: dict[str, Any] = {}

    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    def get(key: str, default: Any = None) -> Any:
        """Read from env var (uppercase) first, then YAML, then default."""
        return os.environ.get(key.upper(), data.get(key, default))

    def require(key: str) -> str:
        """Read a required value; raise if missing from both sources."""
        val = get(key)
        if not val:
            raise KeyError(f"Missing required config: {key}")
        return str(val)

    return Settings(
        vs_token=require("vs_token"),
        category_id=int(get("category_id", 0)),
        country=str(get("country", "all")),
        interval=str(get("interval", "weekly")),
        duration_threshold_secs=int(get("duration_threshold_secs", 300)),
        gemini_api_key=require("gemini_api_key"),
        translate_top_n=int(get("translate_top_n", 5)),
        feishu_app_id=require("feishu_app_id"),
        feishu_app_secret=require("feishu_app_secret"),
        feishu_chat_id=require("feishu_chat_id"),
        feishu_folder_token=get("feishu_folder_token"),
        feishu_domain=str(get("feishu_domain", "skyland2020.feishu.cn")),
    )
