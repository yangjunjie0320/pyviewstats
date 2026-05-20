"""Tests for utils/formatters.py — view/duration/outlier formatting."""

import pytest

from utils.formatters import (
    format_count,
    format_duration,
    format_outlier,
    format_views,
    strip_symbols,
)


class TestFormatViews:
    def test_zero(self) -> None:
        assert format_views(0) == "0"

    def test_none(self) -> None:
        assert format_views(None) == "0"

    def test_negative(self) -> None:
        assert format_views(-100) == "0"

    def test_small_number(self) -> None:
        assert format_views(9999) == "9,999"

    def test_wan(self) -> None:
        assert format_views(12345) == "1.2万"

    def test_exact_wan(self) -> None:
        assert format_views(10000) == "1.0万"

    def test_yi(self) -> None:
        assert format_views(100000000) == "1.0亿"

    def test_large_yi(self) -> None:
        assert format_views(350000000) == "3.5亿"


class TestFormatCount:
    def test_none_returns_dash(self) -> None:
        assert format_count(None) == "-"

    def test_delegates_to_format_views(self) -> None:
        assert format_count(50000) == "5.0万"


class TestFormatDuration:
    def test_zero(self) -> None:
        assert format_duration(0) == "-"

    def test_none(self) -> None:
        assert format_duration(None) == "-"

    def test_negative(self) -> None:
        assert format_duration(-5) == "-"

    def test_seconds_only(self) -> None:
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self) -> None:
        assert format_duration(90) == "1:30"

    def test_exact_minute(self) -> None:
        assert format_duration(300) == "5:00"

    def test_hours(self) -> None:
        assert format_duration(3661) == "1:01:01"

    def test_large_hours(self) -> None:
        assert format_duration(36000) == "10:00:00"


class TestFormatOutlier:
    def test_none(self) -> None:
        assert format_outlier(None) == "暂无"

    def test_below_one(self) -> None:
        result = format_outlier(0.5)
        assert "普通" in result
        assert "0.5x" in result

    def test_good(self) -> None:
        result = format_outlier(2.0)
        assert "不错" in result

    def test_excellent(self) -> None:
        result = format_outlier(5.0)
        assert "优秀" in result

    def test_viral(self) -> None:
        result = format_outlier(50.0)
        assert "爆款" in result

    def test_phenomenal(self) -> None:
        result = format_outlier(100.0)
        assert "现象级" in result

    def test_boundary_at_1(self) -> None:
        result = format_outlier(1.0)
        assert "不错" in result

    def test_boundary_at_3(self) -> None:
        result = format_outlier(3.0)
        assert "优秀" in result

    def test_boundary_at_10(self) -> None:
        result = format_outlier(10.0)
        assert "爆款" in result


class TestStripSymbols:
    def test_empty(self) -> None:
        assert strip_symbols("") == ""

    def test_plain_text(self) -> None:
        assert strip_symbols("Hello World") == "Hello World"

    def test_removes_markdown(self) -> None:
        assert strip_symbols("**bold** _italic_") == "bold italic"

    def test_collapses_whitespace(self) -> None:
        assert strip_symbols("  too   many   spaces  ") == "too many spaces"

    def test_removes_common_emoji(self) -> None:
        result = strip_symbols("🔥 Hot Video 🎬")
        assert "🔥" not in result
        assert "🎬" not in result
        assert "Hot Video" in result
