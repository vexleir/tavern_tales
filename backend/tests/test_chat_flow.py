"""
Chat-flow integration test.

Exercises the backend HTTP surface end-to-end with the mocked Ollama. Verifies
the regression path for the #1 coherence bug: after kickoff, the *next* chat
call must assemble a prompt that contains the world description — i.e., the
frontend no longer owns the system prompt and the backend re-injects state
every turn.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_state_dir, temp_chroma, mock_ollama):
    """FastAPI TestClient with all external side-effects mocked/redirected."""
    import main
    return TestClient(main.app), mock_ollama


def _init_campaign(client, campaign_id: str = "camp_flow"):
    payload = {
        "campaign_id": campaign_id,
        "player_name": "Hero",
        "starting_location": "The Village",
        "stats": {"Health": 100, "Gold": 50},
        "inventory": ["Sword"],
        "npcs": [{"name": "Elena", "disposition": "Neutral", "secrets_known": []}],
        "lorebook": {"Magic": "Magic is rare."},
        "story_summary": "",
        "world_description": "A misty valley of ancient runes.",
        "starting_scene": "You wake in a cold tavern.",
        "gm_model": "llama3",
        "utility_model": "llama3",
        "nsfw_world_gen": False,
    }
    r = client.post("/api/campaign/init", json=payload)
    assert r.status_code == 200, r.text


def _consume_stream(resp):
    """Return list of parsed JSON events from an ndjson StreamingResponse."""
    events = []
    for line in resp.iter_lines():
        if not line:
            continue
        events.append(json.loads(line))
    return events


def test_init_and_list(client):
    c, _ = client
    _init_campaign(c)
    r = c.get("/api/campaigns")
    assert r.status_code == 200
    listing = r.json()
    assert any(x["id"] == "camp_flow" for x in listing)


def test_kickoff_stream_produces_narrative(client):
    c, mo = client
    _init_campaign(c)
    mo.set_stream_text("The hearth is warm. Smoke curls toward the beams.")

    r = c.post("/api/campaign/camp_flow/kickoff")
    assert r.status_code == 200
    events = _consume_stream(r)
    tokens = "".join(e["data"] for e in events if e.get("type") == "token")
    assert "hearth is warm" in tokens
    assert any(e.get("type") == "done" for e in events)


def test_second_turn_prompt_contains_world(client):
    """The regression-catcher: after kickoff, a new chat call's prompt still has the world/scene blocks."""
    c, mo = client
    _init_campaign(c)

    # First, a kickoff so the campaign has an assistant message.
    mo.set_stream_text("Opening narration.")
    _consume_stream(c.post("/api/campaign/camp_flow/kickoff"))

    # Now a real player turn — check the messages handed to the (mocked) model.
    mo.stream_calls.clear()
    mo.set_stream_text("Your sword rings as you draw it.")
    r = c.post("/api/chat/stream", json={"campaign_id": "camp_flow", "user_message": "I draw my sword."})
    assert r.status_code == 200
    _consume_stream(r)

    assert len(mo.stream_calls) == 1
    prompt = mo.stream_calls[0]["messages"]
    system_content = prompt[0]["content"]
    assert prompt[0]["role"] == "system"
    assert "misty valley" in system_content, "world_description must survive into turn-2 system prompt"
    assert "You wake in a cold tavern" in system_content
    assert "Hero" in system_content  # protagonist
    assert "Elena" in system_content  # cast
    assert "Magic" in system_content  # lorebook


def test_message_ids_assigned_and_saved(client, temp_state_dir):
    c, mo = client
    _init_campaign(c)
    mo.set_stream_text("Opening.")
    _consume_stream(c.post("/api/campaign/camp_flow/kickoff"))

    r = c.get("/api/state/camp_flow")
    assert r.status_code == 200
    data = r.json()
    # Kickoff writes a user message ("Begin the scene.") and a GM message.
    assert len(data["messages"]) == 2
    for m in data["messages"]:
        assert m["id"].startswith("msg_")
        assert len(m["id"]) > 6


def test_stream_error_does_not_save_message(client):
    c, mo = client
    _init_campaign(c)
    mo.set_stream_error("Mock connect failure")
    r = c.post("/api/chat/stream", json={"campaign_id": "camp_flow", "user_message": "hello"})
    assert r.status_code == 200
    events = _consume_stream(r)
    assert any(e.get("type") == "error" for e in events)

    state = c.get("/api/state/camp_flow").json()
    # No message should have been saved (error with no content).
    assert len(state["messages"]) == 0


def test_delete_message_reverses_state(client):
    """Side-effect rollback: deleting a message rolls back stat changes it caused."""
    c, mo = client
    _init_campaign(c)

    # Kickoff first so we have a valid campaign with assistant messages.
    mo.set_stream_text("Open.")
    _consume_stream(c.post("/api/campaign/camp_flow/kickoff"))

    # Send a turn whose extraction (mocked) says player loses 30 HP + gains Potion.
    mo.set_stream_text("You are wounded.")
    mo.set_json({
        "stats_changes": {"Health": -30},
        "location": "",
        "inventory_added": ["Potion"],
        "inventory_removed": [],
        "npc_updates": [],
    })
    _consume_stream(c.post("/api/chat/stream", json={"campaign_id": "camp_flow", "user_message": "I fight."}))

    # Wait a tick — background task runs extraction; in TestClient, asyncio
    # tasks scheduled via create_task don't always complete before the response.
    # Use mutate_state directly to synchronously apply the delta for this test.
    # Simpler: just trigger another mutation pass and poll.
    import time
    for _ in range(20):
        state = c.get("/api/state/camp_flow").json()
        if state["player"]["stats"].get("Health") != 100:
            break
        time.sleep(0.05)

    state = c.get("/api/state/camp_flow").json()
    assert state["player"]["stats"]["Health"] == 70
    assert "Potion" in state["player"]["inventory"]

    # Find the most recent assistant message id.
    gm_msg = [m for m in state["messages"] if m["role"] == "assistant"][-1]
    r = c.delete(f"/api/campaign/camp_flow/message/{gm_msg['id']}")
    assert r.status_code == 200

    state = c.get("/api/state/camp_flow").json()
    assert state["player"]["stats"]["Health"] == 100
    assert "Potion" not in state["player"]["inventory"]


def test_delete_assistant_message_removes_whole_turn(client):
    """Normal deletion is turn-level: the player action and GM response disappear together."""
    c, mo = client
    _init_campaign(c)

    mo.set_stream_text("Open.")
    _consume_stream(c.post("/api/campaign/camp_flow/kickoff"))

    mo.set_stream_text("You step into the rain.")
    _consume_stream(c.post("/api/chat/stream", json={"campaign_id": "camp_flow", "user_message": "I go outside."}))
    state = c.get("/api/state/camp_flow").json()
    assert any(m["content"] == "I go outside." for m in state["messages"])

    gm_msg = [m for m in state["messages"] if m["role"] == "assistant"][-1]
    r = c.delete(f"/api/campaign/camp_flow/message/{gm_msg['id']}")
    assert r.status_code == 200

    state = c.get("/api/state/camp_flow").json()
    contents = [m["content"] for m in state["messages"]]
    assert "I go outside." not in contents
    assert "You step into the rain." not in contents


def test_continue_appends_to_existing_assistant_message(client):
    c, mo = client
    _init_campaign(c)

    mo.set_stream_text("Opening line")
    _consume_stream(c.post("/api/campaign/camp_flow/kickoff"))
    before = c.get("/api/state/camp_flow").json()
    assistant_count = len([m for m in before["messages"] if m["role"] == "assistant"])

    mo.set_stream_text(" and continuation.")
    r = c.post("/api/campaign/camp_flow/continue")
    assert r.status_code == 200
    _consume_stream(r)

    after = c.get("/api/state/camp_flow").json()
    assistants = [m for m in after["messages"] if m["role"] == "assistant"]
    assert len(assistants) == assistant_count
    assert "Opening line and continuation." in assistants[-1]["content"]


def test_director_patch_revision_conflict(client):
    c, _ = client
    _init_campaign(c)

    state = c.get("/api/state/camp_flow").json()
    revision = state["revision"]

    ok = c.patch("/api/state/camp_flow", json={
        "expected_revision": revision,
        "player": {"location": "The Old Road"},
    })
    assert ok.status_code == 200
    updated = ok.json()["state"]
    assert updated["player"]["location"] == "The Old Road"
    assert updated["revision"] > revision

    stale = c.patch("/api/state/camp_flow", json={
        "expected_revision": revision,
        "player": {"location": "Stale Road"},
    })
    assert stale.status_code == 409


def test_debug_bundle_contains_state_prompt_and_events(client):
    c, mo = client
    _init_campaign(c)

    mo.set_stream_text("Opening narration.")
    _consume_stream(c.post("/api/campaign/camp_flow/kickoff"))

    r = c.get("/api/campaign/camp_flow/debug")
    assert r.status_code == 200
    bundle = r.json()
    assert bundle["campaign_id"] == "camp_flow"
    assert bundle["state"]["campaign_id"] == "camp_flow"
    assert bundle["last_prompt"]["system_prompt"]
    assert isinstance(bundle["memory_count"], int)
    event_types = [e["type"] for e in bundle["recent_events"]]
    assert "campaign.init" in event_types
    assert "turn.stream.complete" in event_types


def test_input_size_limit_enforced(client):
    c, _ = client
    _init_campaign(c)
    long_msg = "x" * 5000
    r = c.post("/api/chat/stream", json={"campaign_id": "camp_flow", "user_message": long_msg})
    assert r.status_code == 422  # Pydantic validation failure
