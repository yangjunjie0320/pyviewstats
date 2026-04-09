"""Feishu document archiver for weekly reports.

Creates Feishu Docx documents containing video rankings with embedded
short videos, using the lark-oapi SDK for all Feishu operations.

Video embed flow (4 steps):
  1. Create empty file block (block_type=23, token="") → API returns View(33)
  2. Extract File block_id from View.children[0]
  3. Upload video via Drive API with parent_node=file_block_id
  4. Patch the file block with replace_file(token=upload_token)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING

import lark_oapi as lark
from lark_oapi.api.docx.v1 import (
    Block,
    CreateDocumentBlockChildrenRequest,
    CreateDocumentBlockChildrenRequestBody,
    CreateDocumentRequest,
    CreateDocumentRequestBody,
    Divider,
    File,
    PatchDocumentBlockRequest,
    ReplaceFileRequest,
    Table,
    TableProperty,
    Text,
    TextElement,
    TextRun,
    UpdateBlockRequest,
)
from lark_oapi.api.drive.v1 import (
    UploadAllMediaRequest,
    UploadAllMediaRequestBody,
)
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from models import VideoEntry

if TYPE_CHECKING:
    import diskcache
    from config import Settings

logger = logging.getLogger(__name__)


# ── Formatters ────────────────────────────────────────────────────────


def _fmt_views(n: int) -> str:
    if n <= 0:
        return "0"
    if n >= 1_0000_0000:
        return f"{n / 1_0000_0000:.1f}亿"
    if n >= 1_0000:
        return f"{n / 1_0000:.1f}万"
    return f"{n:,}"


def _fmt_count(n: int | None) -> str:
    """Format like/comment counts."""
    if n is None:
        return "-"
    return _fmt_views(n)


def _fmt_duration(seconds: int | None) -> str:
    if not seconds or seconds <= 0:
        return "-"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"


def _fmt_outlier(score: float | None) -> str:
    if score is None:
        return "暂无"
    if score >= 100:
        return f"🔥🔥 现象级 ({score:.1f}x)"
    if score >= 10:
        return f"🔥 爆款 ({score:.1f}x)"
    if score >= 3:
        return f"⭐ 优秀 ({score:.1f}x)"
    if score >= 1:
        return f"👍 不错 ({score:.1f}x)"
    return f"普通 ({score:.1f}x)"


# ── Block builders ────────────────────────────────────────────────────
# block_type: 2=Text, 3=Heading1, 4=Heading2, 22=Divider, 23=File


def _make_text(content: str) -> Text:
    return (
        Text.builder()
        .elements([
            TextElement.builder()
            .text_run(TextRun.builder().content(content).build())
            .build()
        ])
        .build()
    )


def _heading1_block(content: str) -> Block:
    return Block.builder().block_type(3).heading1(_make_text(content)).build()


def _heading2_block(content: str) -> Block:
    return Block.builder().block_type(4).heading2(_make_text(content)).build()


def _text_block(content: str) -> Block:
    return Block.builder().block_type(2).text(_make_text(content)).build()


def _divider_block() -> Block:
    return Block.builder().block_type(22).divider(Divider.builder().build()).build()


def _empty_file_block() -> Block:
    """Create an empty file block in preview mode (view_type=2)."""
    return Block.builder().block_type(23).file(
        File.builder().token("").view_type(2).build()
    ).build()


def _empty_1x2_table_block() -> Block:
    """Create a 1x2 Table block for side-by-side layout, setting explicit wider columns."""
    # Setting an explicit wider column width (e.g. 450 for text, 350 for video)
    prop = TableProperty.builder().column_size(2).row_size(1).column_width([450, 350]).build()
    table = Table.builder().property(prop).cells(['', '']).build()
    return Block.builder().block_type(31).table(table).build()


# ── Archiver ──────────────────────────────────────────────────────────


class FeishuDocArchiver:
    """Creates weekly Feishu documents with video rankings."""

    def __init__(self, settings: Settings, cache: diskcache.Cache) -> None:
        self._client = (
            lark.Client.builder()
            .app_id(settings.feishu_app_id)
            .app_secret(settings.feishu_app_secret)
            .build()
        )
        self._folder_token = settings.feishu_folder_token
        self._chat_id = settings.feishu_chat_id
        self._cache = cache

    async def archive_weekly_report(
        self,
        long_videos: list[VideoEntry],
        short_videos: list[VideoEntry],
        *,
        category_name: str,
        week_key: str,
        threshold_secs: int = 300,
    ) -> str | None:
        if not self._folder_token:
            logger.warning("FEISHU_FOLDER_TOKEN not set, skipping")
            return None

        title = f"ViewStats 周报 — {category_name} — {week_key}"
        threshold_mins = threshold_secs // 60

        doc_id = await self._create_document(title)
        logger.info("Created document %s: %s", doc_id, title)

        total = len(long_videos) + len(short_videos)
        total_views = sum(e.views for e in long_videos) + sum(
            e.views for e in short_videos
        )

        # Overview
        await self._insert_blocks(doc_id, [
            _heading1_block("📊 概览"),
            _text_block(
                f"📂 分类: {category_name}\n"
                f"📅 周期: {week_key}\n"
                f"🎯 总视频数: {total}  |  总播放量: {_fmt_views(total_views)}\n"
                f"🎬 长视频 (>={threshold_mins}min): {len(long_videos)}\n"
                f"🩳 短视频 (<{threshold_mins}min): {len(short_videos)}"
            ),
            _divider_block(),
        ])

        # Long videos — each separated by divider
        long_sorted = sorted(long_videos, key=lambda e: e.views, reverse=True)
        long_blocks: list[Block] = [
            _heading1_block(f"🎬 长视频 (>={threshold_mins}分钟)")
        ]
        if not long_sorted:
            long_blocks.append(_text_block("(无符合条件的视频)"))
        for i, entry in enumerate(long_sorted, 1):
            long_blocks.extend(self._video_blocks(i, entry))
            long_blocks.append(_divider_block())
        await self._insert_blocks(doc_id, long_blocks)

        # Short videos — info + embedded video + divider per entry
        short_sorted = sorted(short_videos, key=lambda e: e.views, reverse=True)
        await self._insert_blocks(doc_id, [
            _heading1_block(f"🩳 短视频 (<{threshold_mins}分钟)")
        ])
        if not short_sorted:
            await self._insert_blocks(doc_id, [_text_block("(无符合条件的视频)")])

        await self._embed_short_videos_inline(doc_id, short_sorted)

        # Send document link to chat
        await self._send_doc_link(doc_id, title, category_name, week_key,
                                  len(long_videos), len(short_videos))

        logger.info("Weekly report document completed: %s", doc_id)
        return doc_id

    # ── Document operations ───────────────────────────────────────────

    async def _create_document(self, title: str) -> str:
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .title(title)
                .folder_token(self._folder_token)
                .build()
            )
            .build()
        )
        response = await asyncio.to_thread(
            self._client.docx.v1.document.create, request
        )
        if not response.success():
            raise RuntimeError(
                f"Failed to create doc: {response.code} {response.msg}"
            )
        return response.data.document.document_id

    async def _insert_blocks(
        self, doc_id: str, blocks: list[Block], *, parent_id: str | None = None, return_raw: bool = False
    ) -> list:
        """Insert blocks as children of the document root or a specified parent.

        If return_raw=True, returns the full Block objects from the response
        (needed to extract View→File block hierarchy or Table block hierarchy).
        """
        if not blocks:
            return []

        parent_node = parent_id or doc_id
        results: list = []
        batch_size = 50
        for start in range(0, len(blocks), batch_size):
            batch = blocks[start : start + batch_size]
            request = (
                CreateDocumentBlockChildrenRequest.builder()
                .document_id(doc_id)
                .block_id(parent_node)
                .request_body(
                    CreateDocumentBlockChildrenRequestBody.builder()
                    .children(batch)
                    .index(-1)
                    .build()
                )
                .build()
            )
            response = await asyncio.to_thread(
                self._client.docx.v1.document_block_children.create, request
            )
            if not response.success():
                logger.error(
                    "Insert blocks failed: code=%d msg=%s",
                    response.code, response.msg,
                )
                raise RuntimeError(
                    f"Insert blocks failed: {response.code} {response.msg}"
                )
            if return_raw and response.data and response.data.children:
                results.extend(response.data.children)

        logger.info("Inserted %d blocks into %s", len(blocks), doc_id)
        return results

    # ── Video embedding (4-step flow) ─────────────────────────────────

    async def _embed_short_videos_inline(
        self, doc_id: str, short_videos: list[VideoEntry]
    ) -> None:
        """Insert info + embedded video + divider per short video entry.

        Each video gets its own section in a side-by-side Table layout:
          Left cell: H2 title → channel/link → stats
          Right cell: video preview
        Then a divider below the table.
        """
        from services.youtube import YouTubeVideoDownloader
        downloader = YouTubeVideoDownloader()

        for i, entry in enumerate(short_videos, 1):
            file_path: str | None = None
            try:
                # 1. Create a 1x2 Table block
                created_table = await self._insert_blocks(
                    doc_id, [_empty_1x2_table_block()], return_raw=True
                )
                if not created_table or not created_table[0].children or len(created_table[0].children) < 2:
                    logger.warning("Failed to create table for %s", entry.video_id)
                    await self._insert_blocks(doc_id, [_divider_block()])
                    continue

                cell0_id = created_table[0].children[0]
                cell1_id = created_table[0].children[1]

                # 2. Insert info blocks into Left Cell (Cell 0)
                info_blocks = self._video_blocks(i, entry)
                await self._insert_blocks(doc_id, info_blocks, parent_id=cell0_id)

                # 3. Insert empty file block into Right Cell (Cell 1)
                created_file_block = await self._insert_blocks(
                    doc_id, [_empty_file_block()], parent_id=cell1_id, return_raw=True
                )

                # Find the View block (type 33) in the response
                file_block_id = None
                for blk in (created_file_block or []):
                    if blk.block_type == 33 and blk.children:
                        file_block_id = blk.children[0]
                        break
                    elif blk.block_type == 23:
                        file_block_id = blk.block_id
                        break

                if not file_block_id:
                    logger.warning("No file block for %s", entry.video_id)
                    await self._insert_blocks(doc_id, [_divider_block()])
                    continue

                # Download video
                file_path = await downloader.download_video(entry.video_id)
                if not file_path:
                    logger.warning("Download failed for %s", entry.video_id)
                    await self._insert_blocks(doc_id, [_divider_block()])
                    continue

                # Upload + patch
                file_token = await self._upload_media(
                    file_block_id, file_path, entry.video_id
                )
                if file_token:
                    await self._replace_file_token(doc_id, file_block_id, file_token)
                    logger.info("Embedded video %s", entry.video_id)

                # Divider after each video's table
                await self._insert_blocks(doc_id, [_divider_block()])

            except Exception:
                logger.warning("Failed to embed %s", entry.video_id, exc_info=True)
            finally:
                if file_path and os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                        parent = os.path.dirname(file_path)
                        if parent and not os.listdir(parent):
                            os.rmdir(parent)
                    except OSError:
                        pass

    async def _upload_media(
        self, parent_block_id: str, file_path: str, video_id: str
    ) -> str | None:
        """Upload a video file to a file block."""
        file_size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            request = (
                UploadAllMediaRequest.builder()
                .request_body(
                    UploadAllMediaRequestBody.builder()
                    .file_name(f"{video_id}.mp4")
                    .parent_type("docx_file")
                    .parent_node(parent_block_id)
                    .size(file_size)
                    .file(f)
                    .build()
                )
                .build()
            )
            response = await asyncio.to_thread(
                self._client.drive.v1.media.upload_all, request
            )
        if not response.success():
            logger.error(
                "Upload failed %s: code=%d msg=%s",
                video_id, response.code, response.msg,
            )
            return None
        logger.info("Uploaded %s (%d bytes), token=%s",
                     video_id, file_size, response.data.file_token)
        return response.data.file_token

    async def _replace_file_token(
        self, doc_id: str, file_block_id: str, file_token: str
    ) -> None:
        """Patch a file block to associate the uploaded media token."""
        request = (
            PatchDocumentBlockRequest.builder()
            .document_id(doc_id)
            .block_id(file_block_id)
            .request_body(
                UpdateBlockRequest.builder()
                .replace_file(
                    ReplaceFileRequest.builder().token(file_token).build()
                )
                .build()
            )
            .build()
        )
        response = await asyncio.to_thread(
            self._client.docx.v1.document_block.patch, request
        )
        if not response.success():
            logger.error(
                "Patch failed %s: code=%d msg=%s",
                file_block_id, response.code, response.msg,
            )

    # ── Send doc link to chat ─────────────────────────────────────────

    async def _send_doc_link(
        self,
        doc_id: str,
        title: str,
        category_name: str,
        week_key: str,
        n_long: int,
        n_short: int,
    ) -> None:
        """Send the document link as a message to the chat."""
        doc_url = f"https://skyland2020.feishu.cn/docx/{doc_id}"
        content = json.dumps({
            "text": (
                f"📄 {title}\n"
                f"长视频: {n_long} | 短视频: {n_short}\n"
                f"点击查看: {doc_url}"
            ),
        }, ensure_ascii=False)

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(self._chat_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = await asyncio.to_thread(
            self._client.im.v1.message.create, request
        )
        if not response.success():
            logger.error(
                "Failed to send doc link: code=%d msg=%s",
                response.code, response.msg,
            )
        else:
            logger.info("Sent doc link to chat: %s", doc_url)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _video_blocks(index: int, entry: VideoEntry) -> list[Block]:
        """Build multiple blocks for one video entry with rich formatting."""
        title = entry.translated_title or entry.title
        link = f"https://youtu.be/{entry.video_id}"

        blocks: list[Block] = [
            # H2: rank + title
            _heading2_block(f"#{index}  {title}"),
            # Info line 1: channel + link
            _text_block(
                f"📺 频道: {entry.channel}\n"
                f"🔗 链接: {link}"
            ),
            # Info line 2: stats
            _text_block(
                f"▶️ 播放: {_fmt_views(entry.views)}  |  "
                f"⏱ 时长: {_fmt_duration(entry.duration_secs)}  |  "
                f"📊 离群值: {_fmt_outlier(entry.outlier_score)}\n"
                f"👍 点赞: {_fmt_count(entry.like_count)}  |  "
                f"💬 评论: {_fmt_count(entry.comment_count)}"
                + (f"  |  📅 上传: {entry.upload_date[:10]}" if entry.upload_date else "")
            ),
        ]
        return blocks
