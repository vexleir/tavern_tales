"""HTTP surface for multiplayer session infrastructure."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client(temp_state_dir, temp_chroma, mock_ollama):
    import main

    return TestClient(main.app)


def _init_campaign(client: TestClient, campaign_id: str = "camp_session") -> None:
    payload = {
        "campaign_id": campaign_id,
        "player_name": "Hero",
        "starting_location": "The Village",
        "player_gender": "NB",
        "player_appearance": "Ash-streaked cloak.",
        "player_description": "A wanderer.",
        "stats": {"Health": 100},
        "inventory": ["Sword"],
        "npcs": [],
        "lorebook": {},
        "story_summary": "",
        "world_description": "A misty valley.",
        "starting_scene": "You wake in a tavern.",
        "gm_model": "llama3",
        "utility_model": "llama3",
        "nsfw_world_gen": False,
    }
    response = client.post("/api/campaign/init", json=payload)
    assert response.status_code == 200, response.text


def test_create_session_and_state_auth(temp_state_dir, temp_chroma, mock_ollama):
    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client)

    response = client.post("/api/session/create", json={"campaign_id": "camp_session"})
    assert response.status_code == 200, response.text
    body = response.json()
    room_code = body["room_code"]
    assert len(room_code) == 6
    assert body["session_state"]["status"] == "lobby"
    assert body["multiplayer"]["host_character"]["name"] == "Hero"

    guest_state = client.get("/api/state/camp_session")
    assert guest_state.status_code == 403

    host_state = client.get("/api/state/camp_session", headers={"X-Player-Slot": "host"})
    assert host_state.status_code == 200
    assert host_state.json()["multiplayer"]["room_code"] == room_code


def test_archive_session_is_host_only(temp_state_dir, temp_chroma, mock_ollama):
    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_archive")
    created = client.post("/api/session/create", json={"campaign_id": "camp_archive"}).json()
    room_code = created["room_code"]

    forbidden = client.post(f"/api/session/{room_code}/archive")
    assert forbidden.status_code == 403

    archived = client.post(
        f"/api/session/{room_code}/archive",
        headers={"X-Player-Slot": "host"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["multiplayer"]["session_status"] == "archived"

    gone = client.get(f"/api/session/{room_code}/state")
    assert gone.status_code == 404
