"""Persistent admin overrides on top of the static kink catalog.

Stored as a single JSON file at `backend/kink_catalog_overrides.json` so admin
edits survive across runs. The shape is:

    {
      "deletedIds": ["klib_..."],
      "addedItems": [
        {
          "id": "klib_admin_<slug>",
          "category": "<existing category id>",
          "label": "...",
          "description": "..."
        }
      ]
    }

This module owns reading/writing that file and applying the overrides on top
of the in-memory catalog produced by `kink_catalog.categorized_kinks()`.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
OVERRIDES_FILE = _BACKEND_DIR / "kink_catalog_overrides.json"

# Local-trust admin gate. Anyone with read access to the source can see this
# string — it gates accidental destructive edits on the local machine, not
# attackers with code access.
ADMIN_PASSWORD = "primus"

_lock = threading.Lock()


def verify_admin_password(provided: str) -> bool:
    """Constant-time comparison so we don't leak length via timing."""
    if not isinstance(provided, str) or not provided:
        return False
    return hmac.compare_digest(provided, ADMIN_PASSWORD)


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or "kink"


def _empty() -> dict[str, list]:
    return {"deletedIds": [], "addedItems": []}


def load_overrides() -> dict[str, list]:
    if not OVERRIDES_FILE.exists():
        return _empty()
    try:
        raw = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("kink_catalog_overrides: could not parse %s: %s", OVERRIDES_FILE, e)
        return _empty()
    if not isinstance(raw, dict):
        return _empty()
    return {
        "deletedIds": [str(x) for x in raw.get("deletedIds", []) if isinstance(x, str)],
        "addedItems": [
            {
                "id": str(item.get("id", "")),
                "category": str(item.get("category", "")),
                "label": str(item.get("label", "")),
                "description": str(item.get("description", "")),
            }
            for item in raw.get("addedItems", [])
            if isinstance(item, dict) and item.get("label")
        ],
    }


def _atomic_write(payload: dict[str, list]) -> None:
    tmp = OVERRIDES_FILE.with_suffix(OVERRIDES_FILE.suffix + ".tmp")
    data = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    try:
        os.replace(tmp, OVERRIDES_FILE)
    except PermissionError:
        # Same Windows-sandbox fallback used in preference_store.
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            f.write(data)


def save_overrides(payload: dict[str, list]) -> None:
    with _lock:
        _atomic_write(payload)


def mark_deleted(ids: list[str]) -> dict[str, list]:
    """Add the given ids to the deletedIds list. Returns the updated overrides."""
    if not ids:
        return load_overrides()
    cleaned = [str(i) for i in ids if isinstance(i, str) and i.strip()]
    with _lock:
        current = load_overrides()
        merged = list(dict.fromkeys([*current["deletedIds"], *cleaned]))  # de-dup, preserve order
        # Also drop these ids from addedItems if any were admin-added; deleting
        # an admin-added item simply removes it from the overlay.
        added = [a for a in current["addedItems"] if a["id"] not in set(merged)]
        payload = {"deletedIds": merged, "addedItems": added}
        _atomic_write(payload)
    return payload


def restore_deleted(ids: list[str]) -> dict[str, list]:
    """Undo a deletion (admin-only convenience). Returns the updated overrides."""
    if not ids:
        return load_overrides()
    drop = set(str(i) for i in ids if isinstance(i, str))
    with _lock:
        current = load_overrides()
        kept = [d for d in current["deletedIds"] if d not in drop]
        payload = {"deletedIds": kept, "addedItems": current["addedItems"]}
        _atomic_write(payload)
    return payload


def add_item(category_id: str, label: str, description: str = "") -> dict[str, Any]:
    """Add a new item to the given category. Returns the entry that was added."""
    label = (label or "").strip()
    if not label:
        raise ValueError("label is required")
    category_id = (category_id or "").strip()
    if not category_id:
        raise ValueError("category is required")

    with _lock:
        current = load_overrides()
        used_ids = {a["id"] for a in current["addedItems"]} | set(current["deletedIds"])
        base = f"klib_admin_{_slugify(label)}"
        candidate = base
        suffix = 2
        while candidate in used_ids:
            candidate = f"{base}_{suffix}"
            suffix += 1
        entry = {
            "id": candidate,
            "category": category_id,
            "label": label,
            "description": (description or "").strip(),
        }
        payload = {
            "deletedIds": current["deletedIds"],
            "addedItems": [*current["addedItems"], entry],
        }
        _atomic_write(payload)
    return entry


def apply_overrides_to_categorized(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter deleted ids out of the categorized output and append admin-added
    items into their target categories. Categories whose ids are unknown are
    silently dropped (admin can't add items to a non-existent category)."""
    overrides = load_overrides()
    deleted = set(overrides["deletedIds"])
    added_by_category: dict[str, list[dict[str, str]]] = {}
    for entry in overrides["addedItems"]:
        added_by_category.setdefault(entry["category"], []).append(entry)

    out: list[dict[str, Any]] = []
    for category in categories:
        new_cat = deepcopy(category)
        new_cat["items"] = [
            item for item in new_cat["items"] if item["id"] not in deleted
        ]
        for added in added_by_category.get(new_cat["id"], []):
            new_cat["items"].append({
                "id": added["id"],
                "label": added["label"],
                "description": added.get("description", ""),
            })
        out.append(new_cat)
    return out


def apply_overrides_to_flat(flat: list[dict[str, str]]) -> list[dict[str, str]]:
    overrides = load_overrides()
    deleted = set(overrides["deletedIds"])
    out = [entry for entry in flat if entry["id"] not in deleted]
    # Build a category-id -> category-label map from the flat list itself.
    cat_labels: dict[str, str] = {}
    for entry in flat:
        cat_labels.setdefault(entry["category"], entry["categoryLabel"])
    for added in overrides["addedItems"]:
        if added["category"] not in cat_labels:
            continue
        out.append({
            "id": added["id"],
            "label": added["label"],
            "category": added["category"],
            "categoryLabel": cat_labels[added["category"]],
            "description": added.get("description", ""),
        })
    return out
