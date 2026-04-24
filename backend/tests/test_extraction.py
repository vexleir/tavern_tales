"""
Extraction: JSON validation, fallback on bad input, NPC normalization at the
delta level (integration happens in test_state_manager).
"""

from __future__ import annotations

import pytest

import extraction


@pytest.mark.asyncio
async def test_valid_json_parsed_into_delta(new_state, mock_ollama):
    mock_ollama.set_json({
        "stats_changes": {"Health": -10},
        "location": "A Dark Forest",
        "inventory_added": ["Torch"],
        "inventory_removed": [],
        "npc_updates": [{"name": "Owen", "disposition_change": "Hostile", "secret_revealed": None}],
    })
    state = new_state()
    delta = await extraction.extract_state_changes(state, "I fall", "You lose 10 HP.")
    assert delta.stats_changes == {"Health": -10}
    assert delta.location == "A Dark Forest"
    assert delta.inventory_added == ["Torch"]
    assert len(delta.npc_updates) == 1
    assert delta.npc_updates[0].name == "Owen"


@pytest.mark.asyncio
async def test_none_response_returns_empty_delta(new_state, mock_ollama):
    mock_ollama.set_json(None)
    state = new_state()
    delta = await extraction.extract_state_changes(state, "x", "y")
    assert delta.stats_changes == {}
    assert delta.location is None
    assert delta.inventory_added == []


@pytest.mark.asyncio
async def test_garbled_json_returns_empty_delta(new_state, mock_ollama):
    # Values that can't validate against StateDelta.
    mock_ollama.set_json({"stats_changes": "not a dict", "npc_updates": "also wrong"})
    state = new_state()
    delta = await extraction.extract_state_changes(state, "x", "y")
    assert delta.stats_changes == {}
    assert delta.npc_updates == []


@pytest.mark.asyncio
async def test_unknown_fields_tolerated(new_state, mock_ollama):
    mock_ollama.set_json({
        "stats_changes": {"Gold": 5},
        "inexplicable_field": [1, 2, 3],
    })
    state = new_state()
    delta = await extraction.extract_state_changes(state, "x", "y")
    assert delta.stats_changes == {"Gold": 5}
