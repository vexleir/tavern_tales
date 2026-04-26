"""
Memory (ChromaDB): add, retrieve, per-message deletion, full-campaign deletion,
per-campaign isolation.
"""

from __future__ import annotations

import memory


def test_add_and_retrieve_roundtrip(temp_chroma):
    memory.add_memory("camp_a", msg_id="msg_1", content="The raven circled overhead.", turn=1, kind="event", location="Tower")
    memory.add_memory("camp_a", msg_id="msg_2", content="Dragons sleep in the mountain.", turn=2)
    results = memory.retrieve_relevant_memories("camp_a", query="raven", n_results=2)
    docs = [r["document"] for r in results]
    assert any("raven" in d for d in docs)
    raven = next(r for r in results if "raven" in r["document"])
    assert raven["metadata"]["kind"] == "event"
    assert raven["metadata"]["location"] == "Tower"


def test_campaigns_are_isolated(temp_chroma):
    memory.add_memory("camp_x", msg_id="m1", content="Alice met Bob.", turn=1)
    memory.add_memory("camp_y", msg_id="m2", content="Carol found a key.", turn=1)
    x_docs = [r["document"] for r in memory.retrieve_relevant_memories("camp_x", "Alice")]
    y_docs = [r["document"] for r in memory.retrieve_relevant_memories("camp_y", "Alice")]
    assert any("Alice" in d for d in x_docs)
    assert not any("Alice" in d for d in y_docs)


def test_per_message_deletion(temp_chroma):
    mid1 = memory.add_memory("camp_z", msg_id="mA", content="Alpha.", turn=1)
    mid2 = memory.add_memory("camp_z", msg_id="mB", content="Beta.", turn=2)
    memory.delete_memories_for_message("camp_z", [mid1])
    docs = [r["document"] for r in memory.retrieve_relevant_memories("camp_z", "Alpha Beta", n_results=5)]
    assert "Beta." in docs
    assert "Alpha." not in docs
    _ = mid2  # used implicitly — second memory should survive


def test_delete_campaign_drops_collection(temp_chroma):
    memory.add_memory("camp_del", msg_id="m", content="Something.", turn=1)
    memory.delete_campaign_memory("camp_del")
    # Querying a dropped collection returns empty rather than raising.
    assert memory.retrieve_relevant_memories("camp_del", "Something") == []


def test_retrieve_on_empty_campaign_returns_empty(temp_chroma):
    assert memory.retrieve_relevant_memories("new_camp", "query") == []
