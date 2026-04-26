"""
Vector memory (ChromaDB) — one collection per campaign.

Per-campaign isolation means deleting a campaign also cleanly drops its
collection (audit §2.10 / task B3). Each inserted document is tagged with its
source `msg_id` so individual messages can have their memory side-effects
rolled back (B1/B2).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import uuid
from contextlib import suppress
from hashlib import blake2b
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_']+")
_EMBED_DIM = 384

_client: Any | None = None


def get_client():
    """Return the Chroma client, creating it lazily on first real memory use."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def set_client_for_tests(client) -> None:
    """Inject a test Chroma client without touching the runtime DB at import time."""
    global _client
    _client = client


def close_client() -> None:
    """Release Chroma file handles so deleted vector segment files can be removed."""
    global _client
    if _client is not None:
        close = getattr(_client, "close", None)
        if callable(close):
            with suppress(Exception):
                close()
        _client = None


def _collection_name(campaign_id: str) -> str:
    safe = _SAFE_ID.sub("_", campaign_id)
    # Chroma collection names must be 3-63 chars, start+end alnum, may contain _- and .
    if len(safe) < 3:
        safe = safe + "___"
    return f"tt_camp_{safe}"[:63]


def get_collection(campaign_id: str):
    client = get_client()
    name = _collection_name(campaign_id)
    try:
        return client.get_collection(name=name)
    except Exception:
        return client.create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )


def _local_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Deterministic local-only lexical embeddings.

    This avoids Chroma's default embedding function, which can download/cache an
    external model. Retrieval is less semantic than a transformer, but it never
    leaves the machine and stores no extra model artifacts.
    """
    vectors: list[list[float]] = []
    for text in texts:
        vec = [0.0] * _EMBED_DIM
        for token in _TOKEN_RE.findall(text.lower()):
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % _EMBED_DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        vectors.append(vec)
    return vectors


def add_memory(
    campaign_id: str,
    msg_id: str,
    content: str,
    turn: int,
    kind: str = "turn",
    location: str | None = None,
) -> str:
    coll = get_collection(campaign_id)
    mem_id = f"mem_{uuid.uuid4().hex[:12]}"
    metadata = {"campaign": campaign_id, "msg_id": msg_id, "turn": turn, "kind": kind}
    if location:
        metadata["location"] = location
    coll.add(
        documents=[content],
        embeddings=_local_embeddings([content]),
        metadatas=[metadata],
        ids=[mem_id],
    )
    return mem_id


def retrieve_relevant_memories(
    campaign_id: str,
    query: str,
    n_results: int = 4,
) -> list[dict[str, Any]]:
    try:
        coll = get_collection(campaign_id)
        if coll.count() == 0:
            return []
        count = coll.count()
        if count == 0:
            return []
        res = coll.query(
            query_embeddings=_local_embeddings([query]),
            n_results=min(max(n_results * 3, n_results), count),
        )
    except Exception as e:
        log.warning("Vector search failed for %s: %s", campaign_id, e)
        return []

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    ids = (res.get("ids") or [[]])[0]

    out: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        out.append({
            "id": ids[i] if i < len(ids) else None,
            "document": doc,
            "metadata": metas[i] if i < len(metas) else {},
            "distance": dists[i] if i < len(dists) else None,
        })
    return sorted(out, key=_hybrid_score)[:n_results]


def _hybrid_score(memory_item: dict[str, Any]) -> float:
    """Lower is better. Blend semantic distance with a small recency preference."""
    distance = memory_item.get("distance")
    if distance is None:
        distance = 1.0
    meta = memory_item.get("metadata") or {}
    try:
        turn = int(meta.get("turn", 0))
    except (TypeError, ValueError):
        turn = 0
    recency_bonus = min(turn / 1000.0, 0.2)
    return float(distance) - recency_bonus


def delete_memories_for_message(campaign_id: str, mem_ids: list[str]) -> None:
    if not mem_ids:
        return
    try:
        coll = get_collection(campaign_id)
        coll.delete(ids=mem_ids)
    except Exception as e:
        log.warning("Failed to delete memory ids for %s: %s", campaign_id, e)


def delete_campaign_memory(campaign_id: str) -> None:
    name = _collection_name(campaign_id)
    segment_dirs = _segment_dirs_for_collection(name)
    try:
        get_client().delete_collection(name=name)
    except Exception as e:
        log.info("Collection %s not present (or delete failed): %s", name, e)
    close_client()
    for path in segment_dirs:
        _remove_tree(path)
    _purge_orphaned_segment_dirs()


def purge_deleted_memory_artifacts() -> None:
    """Remove Chroma segment directories no longer referenced by the metadata DB."""
    _purge_orphaned_segment_dirs()


def _segment_dirs_for_collection(collection_name: str) -> list[Path]:
    db = Path(DB_PATH) / "chroma.sqlite3"
    if not db.exists():
        return []
    try:
        with sqlite3.connect(db) as con:
            rows = con.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN collections c ON s.collection = c.id
                WHERE c.name = ?
                """,
                (collection_name,),
            ).fetchall()
    except Exception as e:
        log.warning("Could not inspect Chroma segment dirs for %s: %s", collection_name, e)
        return []
    root = Path(DB_PATH).resolve()
    return [root / row[0] for row in rows if row and row[0]]


def _active_segment_ids() -> set[str]:
    db = Path(DB_PATH) / "chroma.sqlite3"
    if not db.exists():
        return set()
    try:
        with sqlite3.connect(db) as con:
            return {row[0] for row in con.execute("SELECT id FROM segments").fetchall()}
    except Exception as e:
        log.warning("Could not inspect active Chroma segments: %s", e)
        return set()


def _purge_orphaned_segment_dirs() -> None:
    root = Path(DB_PATH).resolve()
    if not root.exists():
        return
    active = _active_segment_ids()
    for child in root.iterdir():
        if child.is_dir() and child.name not in active:
            _remove_tree(child)


def _remove_tree(path: Path) -> None:
    root = Path(DB_PATH).resolve()
    try:
        resolved = path.resolve()
        if root not in (resolved, *resolved.parents):
            log.warning("Refusing to delete path outside Chroma DB: %s", resolved)
            return
        if resolved.exists():
            shutil.rmtree(resolved)
    except Exception as e:
        log.warning("Failed to remove Chroma artifact %s: %s", path, e)


def duplicate_campaign_memory(src_id: str, dest_id: str) -> None:
    try:
        src = get_collection(src_id)
        data = src.get()
        if not data or not data.get("ids"):
            return
        dest = get_collection(dest_id)
        new_ids = [f"mem_{uuid.uuid4().hex[:12]}" for _ in data["ids"]]
        new_metas = []
        for meta in data.get("metadatas", []):
            m = dict(meta or {})
            m["campaign"] = dest_id
            new_metas.append(m)
        dest.add(
            documents=data["documents"],
            embeddings=_local_embeddings(data["documents"]),
            metadatas=new_metas,
            ids=new_ids,
        )
    except Exception as e:
        log.warning("Failed to duplicate collection %s -> %s: %s", src_id, dest_id, e)
