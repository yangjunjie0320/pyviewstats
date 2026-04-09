"""YouTube HTML scraper for video duration and yt-dlp downloader.

Duration: parses ``"lengthSeconds":"123"`` from the YouTube watch page HTML.
Download: uses yt-dlp to download short videos for Feishu doc embedding.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
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
                async with httpx.AsyncClient(
                    timeout=_REQUEST_TIMEOUT, follow_redirects=True
                ) as client:
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


class YouTubeVideoDownloader:
    """Downloads YouTube videos using yt-dlp for Feishu doc embedding."""

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(3)

    async def download_video(self, video_id: str) -> str | None:
        """Download a YouTube video to a temp file. Returns file path or None."""
        async with self._sem:
            return await asyncio.to_thread(self._download_sync, video_id)

    @staticmethod
    def _download_sync(video_id: str) -> str | None:
        """Synchronous download using yt-dlp."""
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp not installed, cannot download videos")
            return None

        output_dir = tempfile.mkdtemp(prefix="viewstats_")
        output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")

        ydl_opts = {
            "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "socket_timeout": 30,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

            for fname in os.listdir(output_dir):
                fpath = os.path.join(output_dir, fname)
                if os.path.isfile(fpath):
                    logger.info(
                        "Downloaded video %s (%d bytes)",
                        video_id,
                        os.path.getsize(fpath),
                    )
                    return fpath

            logger.warning("No file found after download for %s", video_id)
            return None

        except Exception:
            logger.warning("Failed to download video %s", video_id, exc_info=True)
            return None
