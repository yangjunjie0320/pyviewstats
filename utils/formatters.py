"""Shared formatting utilities for view counts, durations, and text cleanup."""

import re

def format_views(n: int | None) -> str:
    """Format large numbers into Chinese scale (万/亿)."""
    if n is None or n <= 0:
        return "0"
    if n >= 1_0000_0000:
        return f"{n / 1_0000_0000:.1f}亿"
    if n >= 1_0000:
        return f"{n / 1_0000:.1f}万"
    return f"{n:,}"

def format_count(n: int | None) -> str:
    """Format counts with fallback for None."""
    if n is None:
        return "-"
    return format_views(n)

def format_duration(seconds: int | None) -> str:
    """Format seconds as mm:ss or hh:mm:ss."""
    if not seconds or seconds <= 0:
        return "-"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def format_outlier(score: float | None) -> str:
    """Format standard outlier score string."""
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

def strip_symbols(text: str) -> str:
    """Remove emojis, markdown symbols, and excessive whitespace."""
    text = re.sub(r"[\U0001F000-\U0001FFFF]", "", text)
    text = re.sub(r"[\u2600-\u27BF]", "", text)
    text = re.sub(r"[\uFE00-\uFE0F]", "", text)
    text = re.sub(r"[\u200D\u20E3\uFE0F]", "", text)
    text = re.sub(r"[*_~`#|]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
