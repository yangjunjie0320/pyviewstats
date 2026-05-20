"""Tests for services/video_registry.py — weekly buffer and dedup."""

import tempfile

import diskcache
import pytest

from models import VideoEntry
from src.video_registry import VideoRegistry


@pytest.fixture
def registry(tmp_path):
    """Create a VideoRegistry backed by a temporary diskcache."""
    cache = diskcache.Cache(str(tmp_path / "cache"))
    yield VideoRegistry(cache)
    cache.close()


def _entry(video_id: str, views: int = 100) -> VideoEntry:
    return VideoEntry(
        rank=1, video_id=video_id, title=f"Title {video_id}",
        channel="TestChannel", views=views,
    )


class TestAddToWeeklyBuffer:
    def test_adds_new_entries(self, registry: VideoRegistry) -> None:
        entries = [_entry("a"), _entry("b"), _entry("c")]
        new = registry.add_to_weekly_buffer(entries)
        assert len(new) == 3

    def test_deduplicates_within_buffer(self, registry: VideoRegistry) -> None:
        registry.add_to_weekly_buffer([_entry("a")])
        new = registry.add_to_weekly_buffer([_entry("a"), _entry("b")])
        # "a" already in buffer, only "b" is new
        assert len(new) == 1
        assert new[0].video_id == "b"

    def test_skips_archived_videos(self, registry: VideoRegistry) -> None:
        # Manually set archived set
        registry._cache.set("registry:archived", {"old_video"})
        new = registry.add_to_weekly_buffer([_entry("old_video"), _entry("new_video")])
        assert len(new) == 1
        assert new[0].video_id == "new_video"


class TestGetWeekBuffer:
    def test_returns_entries(self, registry: VideoRegistry) -> None:
        registry.add_to_weekly_buffer([_entry("x"), _entry("y")])
        week_key = registry.get_week_key()
        entries = registry.get_week_buffer(week_key)
        assert len(entries) == 2
        ids = {e.video_id for e in entries}
        assert ids == {"x", "y"}

    def test_empty_week(self, registry: VideoRegistry) -> None:
        entries = registry.get_week_buffer("1970-W01")
        assert entries == []


class TestArchiveWeek:
    def test_archive_marks_done(self, registry: VideoRegistry) -> None:
        registry.add_to_weekly_buffer([_entry("v1"), _entry("v2")])
        week_key = registry.get_week_key()
        registry.archive_week(week_key)
        assert registry.should_generate_doc(week_key) is False

    def test_archived_ids_persist(self, registry: VideoRegistry) -> None:
        registry.add_to_weekly_buffer([_entry("v1")])
        week_key = registry.get_week_key()
        registry.archive_week(week_key)
        # v1 is now archived; adding it again should skip
        new = registry.add_to_weekly_buffer([_entry("v1"), _entry("v3")])
        assert len(new) == 1
        assert new[0].video_id == "v3"


class TestShouldGenerateDoc:
    def test_default_true(self, registry: VideoRegistry) -> None:
        assert registry.should_generate_doc("2025-W01") is True

    def test_false_after_archive(self, registry: VideoRegistry) -> None:
        registry._cache.set("registry:doc_done:2025-W01", True)
        assert registry.should_generate_doc("2025-W01") is False


class TestUpdateEntries:
    def test_updates_existing(self, registry: VideoRegistry) -> None:
        from dataclasses import replace

        original = _entry("u1")
        registry.add_to_weekly_buffer([original])
        updated = replace(original, translated_title="翻译标题")
        registry.update_entries([updated])

        week_key = registry.get_week_key()
        entries = registry.get_week_buffer(week_key)
        assert len(entries) == 1
        assert entries[0].translated_title == "翻译标题"

    def test_ignores_unknown_entries(self, registry: VideoRegistry) -> None:
        # Updating a video not in buffer should not crash
        unknown = _entry("unknown")
        registry.update_entries([unknown])  # should not raise
