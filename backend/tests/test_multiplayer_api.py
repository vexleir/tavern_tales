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

    response = client.post(
        "/api/session/create",
        json={"campaign_id": "camp_session"},
        headers={"Origin": "http://192.168.1.50:5173"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    room_code = body["room_code"]
    assert len(room_code) == 6
    assert body["join_url"].startswith("http://")
    assert ":5173/" in body["join_url"]
    assert ":8000/" not in body["join_url"]
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


def test_export_session_includes_persisted_multiplayer_turns(temp_state_dir, temp_chroma, mock_ollama):
    import state_manager
    from schema import Message, PlayerCharacter, PlayerSlot, Role

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_export")
    created = client.post(
        "/api/session/create",
        json={
            "campaign_id": "camp_export",
            "host_character": {
                "name": "Host Hero",
                "location": "The Village",
                "stats": {"Health": 100},
            },
        },
    ).json()
    room_code = created["room_code"]

    async def _add_messages(st):
        st.multiplayer.guest_character = PlayerCharacter(
            slot=PlayerSlot.GUEST,
            name="Guest Hero",
        )
        st.messages.append(Message(
            turn_id="turn_host",
            role=Role.ASSISTANT,
            content="Host-facing result.",
            player_slot="host",
        ))
        st.messages.append(Message(
            turn_id="turn_guest",
            role=Role.ASSISTANT,
            content="Guest-facing result.",
            player_slot="guest",
        ))
        return st

    import anyio
    anyio.run(state_manager.mutate_state, "camp_export", _add_messages)

    exported = client.post(f"/api/session/{room_code}/export")
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert [turn["content"] for turn in body["turns"]] == [
        "Host-facing result.",
        "Guest-facing result.",
    ]
    assert body["turns"][0]["player_slot"] == "host"
    assert body["turns"][0]["actor_name"] == "Host Hero"
    assert body["turns"][1]["player_slot"] == "guest"
    assert body["turns"][1]["actor_name"] == "Guest Hero"
