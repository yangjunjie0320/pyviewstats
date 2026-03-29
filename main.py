"""ViewStats Monitor — pipeline orchestration.

Single entrypoint. Only file that imports across service boundaries.
Do NOT wrap the pipeline in broad try/except.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# Ensure the app directory is on the path for Docker
sys.path.insert(0, "/app")

from config import load_settings
from models import RankingResult
from services.feishu import FeishuNotifier
from services.translator import GeminiTranslator, GoogleTranslator
from services.viewstats import ViewStatsClient
from services.youtube import YouTubeDurationFetcher
from utils.cache import get_cache
from utils.logging import configure_logging

logger = logging.getLogger(__name__)

# Category ID → display name
CATEGORIES: dict[int, str] = {
    0: "All Categories",
    1: "Film & Animation",
    2: "Autos & Vehicles",
    10: "Music",
    15: "Pets & Animals",
    17: "Sports",
    19: "Travel & Events",
    20: "Gaming",
    22: "People & Blogs",
    23: "Comedy",
    24: "Entertainment",
    25: "News & Politics",
    26: "Howto & Style",
    27: "Education",
    28: "Science & Technology",
    29: "Nonprofits & Activism",
}


async def main() -> None:
    """Run the full pipeline: fetch → enrich → translate → notify."""
    configure_logging()
    settings = load_settings()
    cache = get_cache()

    category_name = CATEGORIES.get(settings.category_id, "All Categories")

    logger.info(
        "Starting pipeline: category=%s country=%s interval=%s",
        category_name,
        settings.country,
        settings.interval,
    )

    # Step 1: Fetch rankings
    vs_client = ViewStatsClient(settings.vs_token, cache)
    entries = await vs_client.fetch_video_rankings(
        category_id=settings.category_id,
        country=settings.country,
        interval=settings.interval,
    )

    if not entries:
        logger.warning("No entries returned from ViewStats, exiting")
        return

    # Step 2: Enrich with durations
    yt_fetcher = YouTubeDurationFetcher(cache)
    entries = await yt_fetcher.enrich_durations(entries)

    # Step 3: Split by duration threshold
    threshold = settings.duration_threshold_secs
    long_videos = sorted(
        [e for e in entries if (e.duration_secs or 0) >= threshold],
        key=lambda e: e.views,
        reverse=True,
    )
    short_videos = sorted(
        [e for e in entries if 0 < (e.duration_secs or 0) < threshold],
        key=lambda e: e.views,
        reverse=True,
    )

    logger.info(
        "Split: %d long (≥%ds), %d short (<%ds)",
        len(long_videos),
        threshold,
        len(short_videos),
        threshold,
    )

    # Step 4: Translate top N from each category
    top_n = settings.translate_top_n

    if settings.translate_backend == "gemini":
        translator = GeminiTranslator(settings.gemini_api_key, cache)
    else:
        translator = GoogleTranslator(cache)

    long_top = long_videos[:top_n]
    short_top = short_videos[:top_n]

    if long_top:
        long_top = await translator.translate_entries(long_top)
    if short_top:
        short_top = await translator.translate_entries(short_top)

    # Step 5: Build result and send
    result = RankingResult(
        long_videos=tuple(long_top),
        short_videos=tuple(short_top),
    )

    total_views = sum(e.views for e in entries)
    dur_known = sum(1 for e in entries if (e.duration_secs or 0) > 0)

    # Build ViewStats source URL for reference
    source_url = (
        f"https://www.viewstats.com/top-list"
        f"?category={settings.category_id}"
        f"&country={settings.country}"
        f"&movies=true&tab=videos"
    )

    notifier = FeishuNotifier(settings.feishu_bot_url, cache)
    await notifier.send_ranking_card(
        result,
        category_name=category_name,
        country=settings.country,
        interval=settings.interval,
        total_count=len(entries),
        total_views=total_views,
        dur_known=dur_known,
        source_url=source_url,
    )

    logger.info("Pipeline completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
