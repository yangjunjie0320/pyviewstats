"""Video registry for weekly report deduplication.

Maintains a persistent set of archived video IDs and per-week buffers
to ensure weekly documents contain no duplicates across weeks.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from models import VideoEntry

if TYPE_CHECKING:
    import diskcache

logger = logging.getLogger(__name__)


class VideoRegistry:
    """Track which videos have been included in weekly reports."""

    def __init__(self, cache: diskcache.Cache) -> None:
        self._cache = cache

    @staticmethod
    def get_week_key() -> str:
        """Return current ISO week key, e.g. '2026-W15'."""
        iso = datetime.now().isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    @staticmethod
    def get_previous_week_key() -> str:
        """Return previous ISO week key."""
        last_week = datetime.now() - timedelta(weeks=1)
        iso = last_week.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def add_to_weekly_buffer(self, entries: list[VideoEntry]) -> list[VideoEntry]:
        """Add new entries to current week's buffer.

        Skips videos already archived in previous weeks' documents.
        Returns only truly new entries added this call.
        """
        archived: set[str] = self._cache.get("registry:archived") or set()
        week_key = self.get_week_key()
        buffer_key = f"registry:buffer:{week_key}"
        buffer: dict[str, dict] = self._cache.get(buffer_key) or {}

        new_entries: list[VideoEntry] = []
        for entry in entries:
            if entry.video_id not in archived and entry.video_id not in buffer:
                buffer[entry.video_id] = asdict(entry)
                new_entries.append(entry)

        self._cache.set(buffer_key, buffer)

        if new_entries:
            logger.info(
                "Added %d new videos to weekly buffer %s (total: %d)",
                len(new_entries),
                week_key,
                len(buffer),
            )
        return new_entries

    def get_week_buffer(self, week_key: str) -> list[VideoEntry]:
        """Get all entries accumulated during a specific week."""
        buffer: dict[str, dict] = (
            self._cache.get(f"registry:buffer:{week_key}") or {}
        )
        return [VideoEntry(**d) for d in buffer.values()]

    def should_generate_doc(self, week_key: str) -> bool:
        """Check if weekly document has NOT yet been generated."""
        return not self._cache.get(f"registry:doc_done:{week_key}", False)

    def archive_week(self, week_key: str) -> None:
        """Mark a week's videos as archived after document generation.

        Archived video IDs will be excluded from all future weekly documents.
        """
        buffer: dict[str, dict] = (
            self._cache.get(f"registry:buffer:{week_key}") or {}
        )
        archived: set[str] = self._cache.get("registry:archived") or set()
        archived |= set(buffer.keys())
        self._cache.set("registry:archived", archived)
        self._cache.set(f"registry:doc_done:{week_key}", True)
        logger.info(
            "Archived %d videos for week %s (total archived: %d)",
            len(buffer),
            week_key,
            len(archived),
        )

    def update_entries(self, entries: list[VideoEntry]) -> None:
        """Update buffer entries with enriched data (e.g. translated titles).

        Merges updated fields into existing buffer entries for the current week.
        """
        week_key = self.get_week_key()
        buffer_key = f"registry:buffer:{week_key}"
        buffer: dict[str, dict] = self._cache.get(buffer_key) or {}

        updated = 0
        for entry in entries:
            if entry.video_id in buffer:
                buffer[entry.video_id] = asdict(entry)
                updated += 1

        if updated:
            self._cache.set(buffer_key, buffer)
            logger.info(
                "Updated %d entries in buffer %s", updated, week_key
            )
