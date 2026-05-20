"""Tests for models.py — frozen dataclasses."""

from dataclasses import FrozenInstanceError, replace

import pytest

from src.models import RankingResult, VideoEntry


class TestVideoEntry:
    def test_defaults(self) -> None:
        entry = VideoEntry(rank=1, video_id="abc", title="Test", channel="Ch", views=100)
        assert entry.outlier_score is None
        assert entry.duration_secs is None
        assert entry.translated_title is None
        assert entry.upload_date is None
        assert entry.like_count is None
        assert entry.comment_count is None

    def test_frozen_raises_on_mutation(self) -> None:
        entry = VideoEntry(rank=1, video_id="abc", title="Test", channel="Ch", views=100)
        with pytest.raises(FrozenInstanceError):
            entry.views = 999  # type: ignore[misc]

    def test_replace_returns_new_instance(self) -> None:
        entry = VideoEntry(rank=1, video_id="abc", title="Test", channel="Ch", views=100)
        updated = replace(entry, duration_secs=300, translated_title="测试")
        assert updated is not entry
        assert updated.duration_secs == 300
        assert updated.translated_title == "测试"
        # Original unchanged
        assert entry.duration_secs is None
        assert entry.translated_title is None

    def test_equality(self) -> None:
        a = VideoEntry(rank=1, video_id="abc", title="T", channel="C", views=1)
        b = VideoEntry(rank=1, video_id="abc", title="T", channel="C", views=1)
        assert a == b

    def test_all_fields(self) -> None:
        entry = VideoEntry(
            rank=1,
            video_id="abc",
            title="Title",
            channel="Channel",
            views=1000,
            outlier_score=5.5,
            duration_secs=120,
            translated_title="标题",
            upload_date="2025-01-01",
            like_count=50,
            comment_count=10,
        )
        assert entry.outlier_score == 5.5
        assert entry.like_count == 50


class TestRankingResult:
    def test_construction(self) -> None:
        e1 = VideoEntry(rank=1, video_id="a", title="Long", channel="C", views=1000)
        e2 = VideoEntry(rank=2, video_id="b", title="Short", channel="C", views=500)
        result = RankingResult(long_videos=(e1,), short_videos=(e2,))
        assert len(result.long_videos) == 1
        assert len(result.short_videos) == 1

    def test_empty(self) -> None:
        result = RankingResult(long_videos=(), short_videos=())
        assert len(result.long_videos) == 0
        assert len(result.short_videos) == 0

    def test_frozen(self) -> None:
        result = RankingResult(long_videos=(), short_videos=())
        with pytest.raises(FrozenInstanceError):
            result.long_videos = ()  # type: ignore[misc]
