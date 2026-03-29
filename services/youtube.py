"""YouTube HTML scraper for video duration.

Parses `"lengthSeconds":"123"` from the YouTube watch page HTML.
Uses asyncio.Semaphore(5) for concurrent fetching.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace
from typing import TYPE_CHECKING

import httpx

from models import VideoEntry

if TYPE_CHECKING:
    import diskcache

logger = logging.getLogger(__name__)

_CACHE_TTL = 30 * 24 * 3600  # 30 days
_SEMAPHORE_LIMIT = 5
_REQUEST_TIMEOUT = 15

_LENGTH_RE = re.compile(r'"lengthSeconds"\s*:\s*"(\d+)"')
_APPROX_RE = re.compile(r'"approxDurationMs"\s*:\s*"(\d+)"')

_YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class YouTubeDurationFetcher:
    """Scrapes YouTube pages to extract video durations."""

    def __init__(self, cache: diskcache.Cache) -> None:
        self._cache = cache
        self._sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    async def _fetch_duration(self, video_id: str) -> int:
        """Fetch duration for a single video. Returns 0 on failure."""
        cache_key = f"duration:{video_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with self._sem:
                async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
                    resp = await client.get(
                        f"https://www.youtube.com/watch?v={video_id}",
                        headers=_YT_HEADERS,
                    )
                    if resp.status_code != 200:
                        logger.warning(
                            "YouTube returned %d for %s", resp.status_code, video_id
                        )
                        return 0

                    html = resp.text

                    match = _LENGTH_RE.search(html)
                    if match:
                        duration = int(match.group(1))
                        self._cache.set(cache_key, duration, expire=_CACHE_TTL)
                        return duration

                    match2 = _APPROX_RE.search(html)
                    if match2:
                        duration = round(int(match2.group(1)) / 1000)
                        self._cache.set(cache_key, duration, expire=_CACHE_TTL)
                        return duration

                    logger.warning("No duration found in HTML for %s", video_id)
                    return 0

        except Exception:
            logger.warning("Failed to fetch duration for %s", video_id, exc_info=True)
            return 0

    async def enrich_durations(self, entries: list[VideoEntry]) -> list[VideoEntry]:
        """Return new VideoEntry list with duration_secs populated.

        Failed fetches get duration_secs=0 (never None after enrichment).
        """
        logger.info("Fetching durations for %d videos", len(entries))

        tasks = [self._fetch_duration(e.video_id) for e in entries]
        durations = await asyncio.gather(*tasks)

        enriched = [
            replace(entry, duration_secs=dur)
            for entry, dur in zip(entries, durations)
        ]

        known = sum(1 for d in durations if d > 0)
        logger.info("Durations fetched: %d/%d known", known, len(entries))
        return enriched
