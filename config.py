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


def load_settings() -> Settings:
    """Load settings from environment. Call once at startup."""
    load_dotenv()

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise KeyError("GEMINI_API_KEY is legally required for translation")

    return Settings(
        vs_token=os.environ["VS_TOKEN"],
        category_id=int(os.environ.get("CATEGORY_ID", "0")),
        country=os.environ.get("COUNTRY", "all"),
        interval=os.environ.get("INTERVAL", "weekly"),
        duration_threshold_secs=int(os.environ.get("DURATION_THRESHOLD_SECS", "300")),
        gemini_api_key=gemini_api_key,
        translate_top_n=int(os.environ.get("TRANSLATE_TOP_N", "5")),
        feishu_app_id=os.environ["FEISHU_APP_ID"],
        feishu_app_secret=os.environ["FEISHU_APP_SECRET"],
        feishu_chat_id=os.environ["FEISHU_CHAT_ID"],
        feishu_folder_token=os.environ.get("FEISHU_FOLDER_TOKEN"),
    )
