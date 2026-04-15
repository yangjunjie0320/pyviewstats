"""Feishu card builder and message sender via lark-oapi SDK.

Sends interactive ranking cards to Feishu chats using the IM v1 API.
All threshold/top-N values are dynamic — no hardcoded text.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from models import RankingResult, VideoEntry
from utils.formatters import (
    format_duration,
    format_outlier,
    format_views,
    strip_symbols,
)

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)


# ── Card builders ─────────────────────────────────────────────────────


def _render_list_md(entries: list[VideoEntry]) -> str:
    """Build lark_md ordered list for a set of video entries."""
    if not entries:
        return "*(无符合条件的视频)*"

    lines = []
    for i, entry in enumerate(entries, 1):
        link = f"https://youtu.be/{entry.video_id}"
        title = entry.translated_title or strip_symbols(entry.title)
        views = format_views(entry.views)
        dur = format_duration(entry.duration_secs)
        outlier = format_outlier(entry.outlier_score)

        lines.append(
            f"{i}. **{entry.channel}** — [{title}]({link})\n"
            f"      👁️ {views}　⏱ {dur}　🎯 {outlier}"
        )

    return "\n".join(lines)


def _build_card_content(
    result: RankingResult,
    *,
    category_name: str,
    country: str,
    interval: str,
    total_count: int,
    total_views: int,
    dur_known: int,
    source_url: str = "",
    threshold_secs: int = 300,
) -> str:
    """Construct Feishu interactive card content as JSON string.

    The card body is returned as JSON suitable for ``msg_type="interactive"``
    via the IM v1 message create API.
    """
    avg_views = total_views // total_count if total_count > 0 else 0
    threshold_mins = threshold_secs // 60

    summary = (
        f"**{category_name}** / {country} / {interval}\n"
        f"共 **{total_count}** 个视频  ·  总播放 **{format_views(total_views)}**"
        f"  ·  均播放 **{format_views(avg_views)}**\n"
        f"长视频(≥{threshold_mins}min): **{len(result.long_videos)}**  ·  "
        f"短视频(<{threshold_mins}min): **{len(result.short_videos)}**  ·  "
        f"时长已知: {dur_known}/{total_count}"
    )

    long_md = _render_list_md(list(result.long_videos))
    short_md = _render_list_md(list(result.short_videos))

    n_long = len(result.long_videos)
    n_short = len(result.short_videos)

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"🎬 **长视频 Top {n_long} "
                    f"(≥{threshold_mins}分钟)**\n{long_md}"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"🩳 **短视频 Top {n_short} "
                    f"(<{threshold_mins}分钟)**\n{short_md}"
                ),
            },
        },
    ]

    # Footer with source link and timestamp
    footer_parts: list[str] = []
    if source_url:
        footer_parts.append(f"🔗 [查看完整榜单]({source_url})")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer_parts.append(f"🕒 获取时间: {now_str}")

    elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "  ·  ".join(footer_parts)},
        }
    )

    card = {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📊 ViewStats {category_name} 日报",
            },
            "template": "blue",
        },
        "elements": elements,
    }
    return json.dumps(card, ensure_ascii=False)


# ── Notifier ──────────────────────────────────────────────────────────


class FeishuNotifier:
    """Sends ranking cards to a Feishu chat via lark-oapi IM API."""

    def __init__(self, settings: Settings) -> None:
        self._client = (
            lark.Client.builder()
            .app_id(settings.feishu_app_id)
            .app_secret(settings.feishu_app_secret)
            .build()
        )
        self._chat_id = settings.feishu_chat_id

    # Feishu error codes that are safe to retry (transient/rate-limit).
    _RETRYABLE_CODES: frozenset[int] = frozenset({
        11232,  # frequency limited
        11233,  # send frequency limited
        11234,  # bot send message: frequency limited
        99991400,  # request too fast
    })

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
        threshold_secs: int = 300,
    ) -> None:
        """Build and send the ranking card with retry on rate-limit errors."""
        content = _build_card_content(
            result,
            category_name=category_name,
            country=country,
            interval=interval,
            total_count=total_count,
            total_views=total_views,
            dur_known=dur_known,
            source_url=source_url,
            threshold_secs=threshold_secs,
        )

        logger.info("Sending Feishu card to chat %s", self._chat_id)

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(self._chat_id)
                .msg_type("interactive")
                .content(content)
                .build()
            )
            .build()
        )

        max_retries = 3
        base_delay = 10  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                response = await asyncio.to_thread(
                    self._client.im.v1.message.create, request
                )
            except Exception as exc:
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Feishu IM network error: %s. Retrying (%d/%d) in %ds...",
                        exc, attempt, max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            if response.success():
                logger.info("Feishu card sent successfully")
                return

            if response.code in self._RETRYABLE_CODES and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Feishu IM rate-limited: code=%d msg=%s. "
                    "Retrying (%d/%d) in %ds...",
                    response.code, response.msg,
                    attempt, max_retries, delay,
                )
                await asyncio.sleep(delay)
                continue

            # Non-retryable error or final attempt
            logger.error(
                "Feishu IM API error: code=%d msg=%s",
                response.code,
                response.msg,
            )
            raise RuntimeError(
                f"Feishu IM API error: code={response.code} msg={response.msg}"
            )
