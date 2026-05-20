"""Integration tests for Feishu API.

These tests send real messages to Feishu and are DISABLED by default.
To run: set FEISHU_INTEGRATION_SEND=1 in environment, ensure .env has valid credentials.
"""

import os

import pytest


def _integration_enabled() -> bool:
    return os.getenv("FEISHU_INTEGRATION_SEND") == "1"


@pytest.mark.integration
@pytest.mark.skipif(
    not _integration_enabled(),
    reason="set FEISHU_INTEGRATION_SEND=1 to send a real Feishu card",
)
async def test_send_real_card() -> None:
    """Smoke test: send a minimal card to the configured Feishu chat.

    This test requires:
    - Valid .env with FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_CHAT_ID
    - FEISHU_INTEGRATION_SEND=1 in environment
    """
    from src.config import load_settings
    from src.models import RankingResult, VideoEntry
    from src.feishu import FeishuNotifier

    settings = load_settings()
    entry = VideoEntry(
        rank=1, video_id="test123", title="Integration Test Video",
        channel="pytest", views=42, outlier_score=1.0, duration_secs=60,
        translated_title="集成测试视频",
    )
    result = RankingResult(long_videos=(entry,), short_videos=())
    notifier = FeishuNotifier(settings)

    # Should not raise
    await notifier.send_ranking_card(
        result,
        category_name="Integration Test",
        total_count=1,
        total_views=42,
        dur_known=1,
        threshold_secs=300,
    )
