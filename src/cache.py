"""Shared diskcache.Cache factory.

Cache directory defaults to /app/.cache (Docker volume mount point).
"""

import logging
import os

import diskcache

logger = logging.getLogger(__name__)

_DEFAULT_DIR = os.getenv("CACHE_DIR", "/app/.cache")
_instance: diskcache.Cache | None = None


def get_cache(directory: str | None = None) -> diskcache.Cache:
    """Return a singleton diskcache.Cache instance."""
    global _instance
    if _instance is None:
        cache_dir = directory or _DEFAULT_DIR
        _instance = diskcache.Cache(cache_dir)
        logger.info("Cache initialized at %s", cache_dir)
    return _instance
