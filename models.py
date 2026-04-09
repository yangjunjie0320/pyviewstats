"""Frozen dataclasses for the ViewStats monitor pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoEntry:
    """A single video from the ViewStats rankings."""

    rank: int
    video_id: str
    title: str
    channel: str
    views: int
    outlier_score: float | None = None
    duration_secs: int | None = None
    translated_title: str | None = None
    upload_date: str | None = None
    like_count: int | None = None
    comment_count: int | None = None


@dataclass(frozen=True)
class RankingResult:
    """Processed ranking split into long and short videos."""

    long_videos: tuple[VideoEntry, ...]
    short_videos: tuple[VideoEntry, ...]
