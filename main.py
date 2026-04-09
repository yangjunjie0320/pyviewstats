"""ViewStats Monitor — pipeline orchestration.

Single entrypoint. Only file that imports across service boundaries.
Do NOT wrap the pipeline in broad try/except.

Daily flow:  fetch → enrich → split → translate top-N → send card → buffer for weekly doc
Weekly flow: translate all → download short videos → create Feishu document
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
from services.feishu_doc import FeishuDocArchiver
from services.translator import GeminiTranslator, GoogleTranslator
from services.video_registry import VideoRegistry
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


def _make_translator(settings, cache):
    """Select translation backend based on settings."""
    if settings.translate_backend == "gemini":
        return GeminiTranslator(settings.gemini_api_key, cache)
    return GoogleTranslator(cache)


async def main() -> None:
    """Run the full pipeline: fetch → enrich → card → weekly doc."""
    configure_logging()
    settings = load_settings()
    cache = get_cache()

    category_name = CATEGORIES.get(settings.category_id, "All Categories")
    threshold = settings.duration_threshold_secs
    top_n = settings.translate_top_n

    logger.info(
        "Starting pipeline: category=%s country=%s interval=%s",
        category_name,
        settings.country,
        settings.interval,
    )

    # ── Step 1: Fetch rankings ────────────────────────────────────────
    vs_client = ViewStatsClient(settings.vs_token, cache)
    entries = await vs_client.fetch_video_rankings(
        category_id=settings.category_id,
        country=settings.country,
        interval=settings.interval,
    )

    if not entries:
        logger.warning("No entries returned from ViewStats, exiting")
        return

    # ── Step 2: Enrich all with durations ─────────────────────────────
    yt_fetcher = YouTubeDurationFetcher(cache)
    entries = await yt_fetcher.enrich_durations(entries)

    # ── Step 3: Add to weekly buffer (for doc dedup) ──────────────────
    registry = VideoRegistry(cache)
    new_videos = registry.add_to_weekly_buffer(entries)
    logger.info(
        "Video registry: %d new this run, %d total fetched",
        len(new_videos),
        len(entries),
    )

    # ── Step 4: Split by duration threshold ───────────────────────────
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
        "Split: %d long (>=%ds), %d short (<%ds)",
        len(long_videos),
        threshold,
        len(short_videos),
        threshold,
    )

    # ── Step 5: Translate top N for daily card ────────────────────────
    translator = _make_translator(settings, cache)

    long_top = long_videos[:top_n]
    short_top = short_videos[:top_n]

    if long_top:
        long_top = await translator.translate_entries(long_top)
    if short_top:
        short_top = await translator.translate_entries(short_top)

    # ── Step 6: Send daily card ───────────────────────────────────────
    result = RankingResult(
        long_videos=tuple(long_top),
        short_videos=tuple(short_top),
    )

    total_views = sum(e.views for e in entries)
    dur_known = sum(1 for e in entries if (e.duration_secs or 0) > 0)

    source_url = (
        f"https://www.viewstats.com/top-list"
        f"?category={settings.category_id}"
        f"&country={settings.country}"
        f"&movies=true&tab=videos"
    )

    notifier = FeishuNotifier(settings)
    await notifier.send_ranking_card(
        result,
        category_name=category_name,
        country=settings.country,
        interval=settings.interval,
        total_count=len(entries),
        total_views=total_views,
        dur_known=dur_known,
        source_url=source_url,
        threshold_secs=threshold,
    )

    # ── Step 7: Weekly document generation ────────────────────────────
    if settings.feishu_folder_token:
        prev_week = registry.get_previous_week_key()

        if registry.should_generate_doc(prev_week):
            week_entries = registry.get_week_buffer(prev_week)

            if week_entries:
                logger.info(
                    "Generating weekly doc for %s with %d videos",
                    prev_week,
                    len(week_entries),
                )

                # Re-enrich durations (most will be cached)
                week_entries = await yt_fetcher.enrich_durations(week_entries)

                # Split
                week_long = sorted(
                    [e for e in week_entries if (e.duration_secs or 0) >= threshold],
                    key=lambda e: e.views,
                    reverse=True,
                )
                week_short = sorted(
                    [e for e in week_entries if 0 < (e.duration_secs or 0) < threshold],
                    key=lambda e: e.views,
                    reverse=True,
                )

                # Translate ALL titles for the document
                if week_long:
                    week_long = await translator.translate_entries(week_long)
                if week_short:
                    week_short = await translator.translate_entries(week_short)

                # Create the document (downloads + embeds short videos)
                archiver = FeishuDocArchiver(settings, cache)
                await archiver.archive_weekly_report(
                    week_long,
                    week_short,
                    category_name=category_name,
                    week_key=prev_week,
                    threshold_secs=threshold,
                )

                # Mark week as archived
                registry.archive_week(prev_week)
                logger.info("Weekly document for %s completed", prev_week)
            else:
                logger.info("No videos in buffer for week %s", prev_week)

    logger.info("Pipeline completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
