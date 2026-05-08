"""Kink library — curated, categorized catalog with admin overrides applied.

Source of truth is `kink_catalog.py` (CATEGORIES). Admin deletions and
additions are stored in `kink_catalog_overrides.json` and applied on every
read so future profiles automatically pick up the changes.

The legacy `Kinks.csv` at the project root is no longer read; it remains in
the repo only as a reference document.
"""

from __future__ import annotations

import logging
import threading

import kink_catalog
import kink_catalog_overrides

log = logging.getLogger(__name__)

_categories_cache: list[dict[str, object]] | None = None
_flat_cache: list[dict[str, str]] | None = None
_cache_lock = threading.Lock()


def _ensure_cache() -> None:
    global _categories_cache, _flat_cache
    if _categories_cache is not None and _flat_cache is not None:
        return
    with _cache_lock:
        if _categories_cache is None:
            base = kink_catalog.categorized_kinks()
            _categories_cache = kink_catalog_overrides.apply_overrides_to_categorized(base)
            log.info("kink_library: loaded %d categories (with overrides)", len(_categories_cache))
        if _flat_cache is None:
            base_flat = kink_catalog.flat_kinks()
            _flat_cache = kink_catalog_overrides.apply_overrides_to_flat(base_flat)


def list_categories() -> list[dict[str, object]]:
    """Return the curated categories in display order, with admin overrides applied."""
    _ensure_cache()
    return _categories_cache or []


def list_kinks() -> list[dict[str, str]]:
    """Flat list across all categories, with admin overrides applied."""
    _ensure_cache()
    return _flat_cache or []


def reload_kinks() -> list[dict[str, str]]:
    """Force a re-read of the catalog and overrides."""
    global _categories_cache, _flat_cache
    with _cache_lock:
        base = kink_catalog.categorized_kinks()
        _categories_cache = kink_catalog_overrides.apply_overrides_to_categorized(base)
        base_flat = kink_catalog.flat_kinks()
        _flat_cache = kink_catalog_overrides.apply_overrides_to_flat(base_flat)
    return _flat_cache


def find_kink(kink_id: str) -> dict[str, str] | None:
    for entry in list_kinks():
        if entry["id"] == kink_id:
            return entry
    return None
