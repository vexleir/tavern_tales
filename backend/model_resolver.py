"""
Model availability resolution for Ollama.

Given a preferred model name, check whether it's currently pulled locally.
For utility-task models (extraction, summarization), fall back through a chain.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

import httpx

log = logging.getLogger(__name__)

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

# Default fallback chain for utility models (JSON-oriented, adult-content tolerant
# for analytical tasks). Tried in order; first pulled wins. GM model is the last
# resort (it'll work but costs context quality on narration turns).
DEFAULT_UTILITY_FALLBACKS: tuple[str, ...] = (
    "llama3.1:8b-instruct",
    "llama3.1:8b",
    "qwen2.5:7b-instruct",
    "qwen2.5:7b",
    "llama3:8b",
    "llama3",
)

# Default creative model for world generation when NSFW toggle is OFF.
DEFAULT_CREATIVE_MODEL = "llama3.1:8b-instruct"
# NSFW opt-in model for world generation.
NSFW_CREATIVE_MODEL = "fluffy/l3-8b-stheno-v3.2:latest"


_TAG_CACHE: dict[str, object] = {"tags": None, "ts": 0.0}
_TAG_TTL_SECONDS = 60.0


async def _list_pulled_tags() -> set[str]:
    now = time.time()
    cached_ts = float(_TAG_CACHE["ts"])  # type: ignore[arg-type]
    cached = _TAG_CACHE["tags"]
    if cached is not None and (now - cached_ts) < _TAG_TTL_SECONDS:
        return cached  # type: ignore[return-value]

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(OLLAMA_TAGS_URL, timeout=5.0)
            res.raise_for_status()
            data = res.json()
            tags = {m["name"] for m in data.get("models", []) if "name" in m}
    except Exception as e:
        log.warning("Could not fetch Ollama tag list: %s", e)
        # Return empty set so callers fall through to the last resort.
        tags = set()

    _TAG_CACHE["tags"] = tags
    _TAG_CACHE["ts"] = now
    return tags


def _match(pulled: set[str], name: str) -> str | None:
    """Match a name against the pulled set, accepting the bare name or a `:latest` alias."""
    if not name:
        return None
    if name in pulled:
        return name
    if f"{name}:latest" in pulled:
        return f"{name}:latest"
    # Some users pin exact versions; accept any tag whose bare name matches.
    bare = name.split(":", 1)[0]
    for tag in pulled:
        if tag.split(":", 1)[0] == bare:
            return tag
    return None


def invalidate_cache() -> None:
    _TAG_CACHE["tags"] = None
    _TAG_CACHE["ts"] = 0.0


async def resolve_utility_model(preferred: str | None, gm_fallback: str) -> str:
    """Return the first model in (preferred, *DEFAULT_UTILITY_FALLBACKS, gm_fallback) that's pulled."""
    chain: list[str] = []
    if preferred:
        chain.append(preferred)
    chain.extend(DEFAULT_UTILITY_FALLBACKS)
    if gm_fallback and gm_fallback not in chain:
        chain.append(gm_fallback)

    pulled = await _list_pulled_tags()
    if not pulled:
        # Tag list unavailable — trust the preferred/gm fallback and let the call fail loudly downstream.
        return preferred or gm_fallback

    for candidate in chain:
        resolved = _match(pulled, candidate)
        if resolved:
            if preferred and resolved != preferred and resolved != f"{preferred}:latest":
                log.warning(
                    "Preferred utility model %r not pulled; falling back to %r", preferred, resolved
                )
            return resolved

    log.warning("No utility model in fallback chain is pulled; using GM model %r", gm_fallback)
    return gm_fallback


async def is_model_available(name: str) -> bool:
    pulled = await _list_pulled_tags()
    return _match(pulled, name) is not None


async def list_available(preferred: Iterable[str]) -> list[str]:
    pulled = await _list_pulled_tags()
    return [m for m in preferred if _match(pulled, m)]
