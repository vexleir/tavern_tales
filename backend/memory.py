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
import uuid
from typing import Any

import chromadb

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")

_client = chromadb.PersistentClient(path=DB_PATH)


def _collection_name(campaign_id: str) -> str:
    safe = _SAFE_ID.sub("_", campaign_id)
    # Chroma collection names must be 3-63 chars, start+end alnum, may contain _- and .
    if len(safe) < 3:
        safe = safe + "___"
    return f"tt_camp_{safe}"[:63]


def get_collection(campaign_id: str):
    name = _collection_name(campaign_id)
    try:
        return _client.get_collection(name=name)
    except Exception:
        return _client.create_collection(name=name, metadata={"hnsw:space": "cosine"})


def add_memory(campaign_id: str, msg_id: str, content: str, turn: int) -> str:
    coll = get_collection(campaign_id)
    mem_id = f"mem_{uuid.uuid4().hex[:12]}"
    coll.add(
        documents=[content],
        metadatas=[{"campaign": campaign_id, "msg_id": msg_id, "turn": turn}],
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
        res = coll.query(query_texts=[query], n_results=min(n_results, coll.count()))
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
    return out


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
    try:
        _client.delete_collection(name=name)
    except Exception as e:
        log.info("Collection %s not present (or delete failed): %s", name, e)


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
            metadatas=new_metas,
            ids=new_ids,
        )
    except Exception as e:
        log.warning("Failed to duplicate collection %s -> %s: %s", src_id, dest_id, e)
