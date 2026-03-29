"""Application configuration from environment variables.

This is the sole reader of os.environ in the entire application.
Missing required vars will raise KeyError at startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    vs_token: str
    feishu_bot_url: str
    category_id: int
    country: str
    interval: str
    duration_threshold_secs: int
    translate_backend: str
    gemini_api_key: str | None
    translate_top_n: int


def load_settings() -> Settings:
    """Load settings from environment. Call once at startup."""
    load_dotenv()

    translate_backend = os.environ.get("TRANSLATE_BACKEND", "gemini")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")

    # Validate: if gemini backend is selected, key is required
    if translate_backend == "gemini" and not gemini_api_key:
        raise KeyError("GEMINI_API_KEY is required when TRANSLATE_BACKEND=gemini")

    return Settings(
        vs_token=os.environ["VS_TOKEN"],
        feishu_bot_url=os.environ["FEISHU_BOT_URL"],
        category_id=int(os.environ.get("CATEGORY_ID", "0")),
        country=os.environ.get("COUNTRY", "all"),
        interval=os.environ.get("INTERVAL", "weekly"),
        duration_threshold_secs=int(os.environ.get("DURATION_THRESHOLD_SECS", "300")),
        translate_backend=translate_backend,
        gemini_api_key=gemini_api_key,
        translate_top_n=int(os.environ.get("TRANSLATE_TOP_N", "5")),
    )
