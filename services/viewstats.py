"""ViewStats API client with AES-GCM decryption.

Maps camelCase API response fields to snake_case VideoEntry instances.
No raw dicts leave this module.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from models import VideoEntry
from utils.crypto import decrypt_payload

if TYPE_CHECKING:
    import diskcache

logger = logging.getLogger(__name__)

API_BASE = "https://api.viewstats.com"

# interval string → numeric value (from ViewStats frontend source)
INTERVAL_MAP: dict[str, int] = {
    "daily": 1,
    "yesterday": 1,
    "weekly": 7,
    "monthly": 28,
    "quarterly": 90,
    "semiannually": 180,
    "annually": 365,
    "all_time": 0,
}

_HEADERS = {
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Referer": "https://www.viewstats.com/",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua-platform": '"macOS"',
    "Content-Type": "application/json",
}

_CACHE_TTL = 6 * 3600  # 6 hours


class ViewStatsClient:
    """Fetches video rankings from the ViewStats API."""

    def __init__(self, token: str, cache: diskcache.Cache) -> None:
        self._token = token
        self._cache = cache

    def _get_headers(self) -> dict[str, str]:
        headers = dict(_HEADERS)
        headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _post(self, endpoint: str, body: dict) -> dict:
        """POST to ViewStats API, auto-decrypt if response is not JSON."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_BASE}/{endpoint}",
                headers=self._get_headers(),
                json=body,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.json()
            return decrypt_payload(resp.content)

    async def fetch_video_rankings(
        self,
        *,
        category_id: int = 0,
        country: str = "all",
        interval: str = "weekly",
        include_kids: bool = False,
        include_music: bool = True,
    ) -> list[VideoEntry]:
        """Fetch video rankings and return mapped VideoEntry list."""
        cache_key = f"rankings:{category_id}:{country}:{interval}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for %s", cache_key)
            return cached

        body = {
            "interval": INTERVAL_MAP.get(interval, 7),
            "includeKids": include_kids,
            "includeMusic": include_music,
            "country": country or "all",
            "categoryId": category_id or 9999,
            "videoFormat": "all",
        }

        logger.info(
            "Fetching rankings: category=%s country=%s interval=%s",
            category_id,
            country,
            interval,
        )
        result = await self._post("rankings/videos", body)
        raw_list: list[dict] = result.get("data", result) if isinstance(result, dict) else result

        entries = []
        for item in raw_list:
            raw = item.get("video", item)
            channel_info = item.get("channel", {})
            upload_date_raw = raw.get("uploadDate")
            upload_date = (
                upload_date_raw[:10] if upload_date_raw else None
            )

            entries.append(
                VideoEntry(
                    rank=item.get("rank", 0),
                    video_id=raw["videoId"] if "videoId" in raw else raw.get("id", ""),
                    title=raw.get("title", ""),
                    channel=channel_info.get("displayName", channel_info.get("name", "")),
                    views=raw.get("viewCount", raw.get("views", 0)),
                    outlier_score=raw.get("outlierScore"),
                    duration_secs=None,
                    translated_title=None,
                    upload_date=upload_date,
                    like_count=raw.get("likeCount"),
                    comment_count=raw.get("commentCount"),
                )
            )

        logger.info("Fetched %d video entries", len(entries))
        self._cache.set(cache_key, entries, expire=_CACHE_TTL)
        return entries
