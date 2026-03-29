"""Translation service with dual backend: Gemini API and Google Translate.

Both share the same cache key pattern so switching backends still serves
previously cached translations.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

import httpx

from models import VideoEntry

if TYPE_CHECKING:
    import diskcache

logger = logging.getLogger(__name__)

_CACHE_TTL = 30 * 24 * 3600  # 30 days
_TARGET_LANG = "zh"


def _cache_key(text: str) -> str:
    """Generate cache key for a translation."""
    md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"translation:{_TARGET_LANG}:{md5}"


class TranslatorProtocol(Protocol):
    """Common interface for translation backends."""

    async def translate_entries(self, entries: list[VideoEntry]) -> list[VideoEntry]:
        ...


class GeminiTranslator:
    """Batch translation using Google Gemini API (gemini-2.0-flash)."""

    def __init__(self, api_key: str, cache: diskcache.Cache) -> None:
        self._api_key = api_key
        self._cache = cache

    async def translate_entries(self, entries: list[VideoEntry]) -> list[VideoEntry]:
        """Translate titles in a single batch Gemini request."""
        if not entries:
            return []

        # Check cache first, collect uncached
        cached_translations: dict[int, str] = {}
        uncached_indices: list[int] = []
        uncached_titles: list[str] = []

        for i, entry in enumerate(entries):
            key = _cache_key(entry.title)
            cached = self._cache.get(key)
            if cached is not None:
                cached_translations[i] = cached
            else:
                uncached_indices.append(i)
                uncached_titles.append(entry.title)

        if cached_translations:
            logger.info("Translation cache hits: %d/%d", len(cached_translations), len(entries))

        # Batch translate uncached titles via Gemini
        if uncached_titles:
            try:
                translations = await self._batch_translate(uncached_titles)
                for idx, translation in zip(uncached_indices, translations):
                    cached_translations[idx] = translation
                    self._cache.set(
                        _cache_key(entries[idx].title), translation, expire=_CACHE_TTL
                    )
            except Exception:
                logger.warning(
                    "Gemini translation failed, falling back to Google Translate",
                    exc_info=True,
                )
                # Fall back to GoogleTranslator for remaining
                fallback = GoogleTranslator(self._cache)
                fallback_entries = [entries[i] for i in uncached_indices]
                translated = await fallback.translate_entries(fallback_entries)
                for idx, entry in zip(uncached_indices, translated):
                    if entry.translated_title:
                        cached_translations[idx] = entry.translated_title

        # Build result
        result = []
        for i, entry in enumerate(entries):
            translated_title = cached_translations.get(i)
            result.append(replace(entry, translated_title=translated_title))
        return result

    async def _batch_translate(self, titles: list[str]) -> list[str]:
        """Send all titles in one Gemini API call."""
        from google import genai

        client = genai.Client(api_key=self._api_key)

        numbered_titles = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
        prompt = (
            "将以下YouTube视频标题翻译成简洁的中文。"
            "要求：1) 译文尽量精简，去掉冗余修饰词；"
            "2) 保持编号，每行一个翻译；3) 不要解释。\n\n"
            f"{numbered_titles}"
        )

        logger.info("Gemini batch translating %d titles", len(titles))

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
        )

        text = response.text.strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # Strip numbering prefix (e.g., "1. ")
        import re

        translations = []
        for line in lines:
            cleaned = re.sub(r"^\d+\.\s*", "", line)
            translations.append(cleaned)

        # Ensure we have enough translations
        if len(translations) < len(titles):
            logger.warning(
                "Gemini returned %d translations for %d titles",
                len(translations),
                len(titles),
            )
            translations.extend([""] * (len(titles) - len(translations)))

        return translations[: len(titles)]


class GoogleTranslator:
    """Unofficial Google Translate endpoint via httpx.

    Sequential with asyncio.sleep(0.5) between calls (rate limit guard).
    Do NOT remove the sleep.
    """

    _BASE_URL = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, cache: diskcache.Cache) -> None:
        self._cache = cache

    async def translate_entries(self, entries: list[VideoEntry]) -> list[VideoEntry]:
        """Translate titles sequentially with rate limiting."""
        result = []
        for entry in entries:
            key = _cache_key(entry.title)
            cached = self._cache.get(key)
            if cached is not None:
                result.append(replace(entry, translated_title=cached))
                continue

            translated = await self._translate_single(entry.title)
            if translated:
                self._cache.set(key, translated, expire=_CACHE_TTL)
                result.append(replace(entry, translated_title=translated))
            else:
                logger.warning("Translation failed for: %s", entry.title[:50])
                result.append(entry)

            await asyncio.sleep(0.5)  # Rate limit guard — do NOT remove

        return result

    async def _translate_single(self, text: str) -> str | None:
        """Translate a single text via unofficial Google endpoint."""
        clean = text.replace("#", " ").replace("@", " ").replace("\n", " ").strip()
        if not clean:
            return None

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    self._BASE_URL,
                    params={
                        "client": "gtx",
                        "sl": "auto",
                        "tl": "zh-CN",
                        "dt": "t",
                        "q": clean,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Google Translate returned %d for: %s",
                        resp.status_code,
                        clean[:50],
                    )
                    return None
                data = resp.json()
                return "".join(segment[0] for segment in data[0] if segment[0])
        except Exception:
            logger.warning("Google Translate request failed", exc_info=True)
            return None

