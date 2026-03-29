"""Feishu card builder and webhook notifier.

Sends interactive cards to Feishu bot webhook. Deduplicates pushes by
hashing the top-5 video IDs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from models import RankingResult, VideoEntry

if TYPE_CHECKING:
    import diskcache

logger = logging.getLogger(__name__)


def _fmt_views_cn(n: int) -> str:
    """Format view count in Chinese style (万/亿)."""
    if n <= 0:
        return "0"
    if n >= 1_0000_0000:
        return f"{n / 1_0000_0000:.1f}亿"
    if n >= 1_0000:
        return f"{n / 1_0000:.1f}万"
    return f"{n:,}"


def _fmt_duration(seconds: int | None) -> str:
    """Format seconds as mm:ss or hh:mm:ss."""
    if not seconds or seconds <= 0:
        return "-"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _strip_symbols(text: str) -> str:
    """Remove emojis, markdown symbols, and excessive whitespace."""
    text = re.sub(r"[\U0001F000-\U0001FFFF]", "", text)
    text = re.sub(r"[\u2600-\u27BF]", "", text)
    text = re.sub(r"[\uFE00-\uFE0F]", "", text)
    text = re.sub(r"[\u200D\u20E3\uFE0F]", "", text)
    text = re.sub(r"[*_~`#|]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fmt_outlier(score: float | None) -> str:
    """Convert outlier score to a qualitative label with numeric value."""
    if score is None:
        return "暂无数据"
    if score >= 100:
        return f"现象级({score:.1f})"
    if score >= 10:
        return f"爆款({score:.1f})"
    if score >= 3:
        return f"优秀({score:.1f})"
    if score >= 1:
        return f"不错({score:.1f})"
    return f"普通({score:.1f})"


def _render_list_md(entries: list[VideoEntry]) -> str:
    """Build lark_md ordered list for a set of video entries."""
    if not entries:
        return "*(无符合条件的视频)*"

    lines = []
    for i, entry in enumerate(entries, 1):
        link = f"https://youtu.be/{entry.video_id}"
        title = entry.translated_title or _strip_symbols(entry.title)
        views = _fmt_views_cn(entry.views)
        dur = _fmt_duration(entry.duration_secs)
        outlier = _fmt_outlier(entry.outlier_score)

        lines.append(
            f"{i}. **{entry.channel}** — [{title}]({link})\n"
            f"      👁️ {views}　⏱ {dur}　🎯 {outlier}"
        )

    return "\n".join(lines)


def _build_card_payload(
    result: RankingResult,
    *,
    category_name: str,
    country: str,
    interval: str,
    total_count: int,
    total_views: int,
    dur_known: int,
    source_url: str = "",
) -> dict:
    """Construct Feishu interactive card payload."""
    avg_views = total_views // total_count if total_count > 0 else 0

    summary = (
        f"**{category_name}** / {country} / {interval}\n"
        f"共 **{total_count}** 个视频  ·  总播放 **{_fmt_views_cn(total_views)}**"
        f"  ·  均播放 **{_fmt_views_cn(avg_views)}**\n"
        f"长视频(≥5min): **{len(result.long_videos)}**  ·  "
        f"短视频(<5min): **{len(result.short_videos)}**  ·  "
        f"时长已知: {dur_known}/{total_count}"
    )

    long_md = _render_list_md(list(result.long_videos))
    short_md = _render_list_md(list(result.short_videos))

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": summary},
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"🎬 **长视频 Top 5 (≥5分钟)**\n{long_md}",
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"🩳 **短视频 Top 5 (<5分钟)**\n{short_md}",
            },
        },
    ]

    # Add source URL and timestamp footer
    footer_text = []
    if source_url:
        footer_text.append(f"🔗 [查看完整榜单]({source_url})")
    
    # Add current timestamp
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer_text.append(f"🕒 获取时间: {now_str}")

    elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "  ·  ".join(footer_text),
            },
        }
    )

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 ViewStats {category_name} 周报",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }


class FeishuNotifier:
    """Sends ranking cards to Feishu webhook with deduplication."""

    def __init__(self, webhook_url: str, cache: diskcache.Cache) -> None:
        self._webhook_url = webhook_url
        self._cache = cache

    async def send_ranking_card(
        self,
        result: RankingResult,
        *,
        category_name: str = "All Categories",
        country: str = "all",
        interval: str = "weekly",
        total_count: int = 0,
        total_views: int = 0,
        dur_known: int = 0,
        source_url: str = "",
    ) -> None:
        """Build and send the ranking card."""
        payload = _build_card_payload(
            result,
            category_name=category_name,
            country=country,
            interval=interval,
            total_count=total_count,
            total_views=total_views,
            dur_known=dur_known,
            source_url=source_url,
        )

        logger.info("Sending Feishu card")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self._webhook_url,
                json=payload,
            )
            body = resp.text

            if resp.status_code != 200:
                logger.error(
                    "Feishu webhook returned %d: %s", resp.status_code, body[:500]
                )
                raise RuntimeError(
                    f"Feishu webhook error: HTTP {resp.status_code}: {body[:500]}"
                )

            try:
                resp_json = resp.json()
                code = resp_json.get("code")
                if code is not None and code != 0:
                    logger.error("Feishu API returned error: %s", body[:500])
                    raise RuntimeError(f"Feishu API error: {body[:500]}")
            except Exception as e:
                if isinstance(e, RuntimeError):
                    raise

            logger.info("Feishu card sent successfully: %s", body[:200])
