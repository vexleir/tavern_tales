"""HTTP surface for multiplayer session infrastructure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


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


def _receive_until(ws, msg_type: str, limit: int = 8) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message.get("type") == msg_type:
            return message
    raise AssertionError(f"did not receive {msg_type!r}")


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


def test_session_exists_endpoint(temp_state_dir, temp_chroma, mock_ollama):
    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_exists")
    created = client.post("/api/session/create", json={"campaign_id": "camp_exists"}).json()
    room_code = created["room_code"]

    found = client.get(f"/api/session/{room_code}/exists")
    assert found.status_code == 200
    assert found.json() == {"exists": True, "status": "lobby"}

    missing = client.get("/api/session/NOPE42/exists")
    assert missing.status_code == 200
    assert missing.json() == {"exists": False, "status": None}


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
            role=Role.USER,
            content=(
                "Active player submission. Treat this as command text, not prose to continue in first person.\n"
                "Acting character: Host Hero\n"
                "Submitted action text (I/me/my/we refers to Host Hero): I raise my shield.\n"
                "Required response style: third-person present-tense story narration."
            ),
            player_slot="host",
        ))
        st.messages.append(Message(
            turn_id="turn_host",
            role=Role.ASSISTANT,
            content="Host-facing result.",
            player_slot="host",
        ))
        st.messages.append(Message(
            turn_id="turn_guest",
            role=Role.USER,
            content="I inspect the sigils.",
            player_slot="guest",
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
    assert [turn["gm_content"] for turn in body["turns"]] == [
        "Host-facing result.",
        "Guest-facing result.",
    ]
    assert body["turns"][0]["player_slot"] == "host"
    assert body["turns"][0]["actor_name"] == "Host Hero"
    assert body["turns"][0]["player_action"] == "I raise my shield."
    assert body["turns"][1]["player_slot"] == "guest"
    assert body["turns"][1]["actor_name"] == "Guest Hero"
    assert body["turns"][1]["player_action"] == "I inspect the sigils."


def test_multiplayer_kickoff_generates_once(temp_state_dir, temp_chroma, mock_ollama):
    import anyio
    import main
    import session_manager
    import state_manager
    from schema import PlayerSlot, Role

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_kickoff")
    created = client.post("/api/session/create", json={"campaign_id": "camp_kickoff"}).json()
    room_code = created["room_code"]
    mock_ollama.set_stream_text("The two heroes stand beneath a storm-lit arch.")

    async def _ready_and_kickoff():
        await session_manager.join_session(
            room_code,
            websocket=FakeWebSocket(),
            display_name="Host",
            character_name="Host Hero",
            desired_slot=PlayerSlot.HOST,
        )
        await session_manager.join_session(
            room_code,
            websocket=FakeWebSocket(),
            display_name="Guest",
            character_name="Guest Hero",
            desired_slot=PlayerSlot.GUEST,
        )
        await session_manager.set_ready(room_code, PlayerSlot.HOST, True)
        rt = await session_manager.set_ready(room_code, PlayerSlot.GUEST, True)
        assert rt.kickoff_needed is True

        await main._run_multiplayer_kickoff(room_code)
        state = await state_manager.load_state("camp_kickoff")
        kickoff_messages = [m for m in state.messages if m.is_kickoff and m.role == Role.ASSISTANT]
        assert len(kickoff_messages) == 1
        assert "storm-lit arch" in kickoff_messages[0].content

        rt.kickoff_needed = True
        await main._run_multiplayer_kickoff(room_code)
        state = await state_manager.load_state("camp_kickoff")
        kickoff_messages = [m for m in state.messages if m.is_kickoff and m.role == Role.ASSISTANT]
        assert len(kickoff_messages) == 1

    anyio.run(_ready_and_kickoff)


def test_ws_update_character_is_sender_slot_scoped(temp_state_dir, temp_chroma, mock_ollama):
    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_character_edit")
    created = client.post("/api/session/create", json={"campaign_id": "camp_character_edit"}).json()
    room_code = created["room_code"]

    with client.websocket_connect(f"/api/session/{room_code}/ws") as host_ws:
        host_ws.send_json({
            "type": "join",
            "display_name": "Host",
            "character_name": "Host Hero",
            "slot": "host",
            "client_id": "host-client",
        })
        assert host_ws.receive_json()["type"] == "slot_assigned"
        _receive_until(host_ws, "session_state")

        with client.websocket_connect(f"/api/session/{room_code}/ws") as guest_ws:
            guest_ws.send_json({
                "type": "join",
                "display_name": "Guest",
                "character_name": "Guest Hero",
                "slot": "guest",
                "client_id": "guest-client",
            })
            assigned = guest_ws.receive_json()
            assert assigned["type"] == "slot_assigned"
            assert assigned["slot"] == "guest"
            _receive_until(guest_ws, "session_state")

            guest_ws.send_json({
                "type": "update_character",
                "slot": "host",
                "stats": {"Health": 77, "Gold": 12},
                "inventory": ["Lockpick", "", "Lantern"],
                "appearance": "A silver cloak.",
                "location": "Old Cellar",
            })
            updated = _receive_until(guest_ws, "session_state")

    guest_character = updated["multiplayer"]["guest_character"]
    host_character = updated["multiplayer"]["host_character"]
    assert guest_character["stats"] == {"Health": 77, "Gold": 12}
    assert guest_character["inventory"] == ["Lockpick", "Lantern"]
    assert guest_character["appearance"] == "A silver cloak."
    assert guest_character["location"] == "Old Cellar"
    assert host_character["stats"] == {"Health": 100}
    assert host_character["inventory"] == ["Sword"]


def test_reconnect_after_window_expired_returns_session_expired(temp_state_dir, temp_chroma, mock_ollama):
    import anyio
    import session_manager
    from schema import PlayerSlot, SessionStatus

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_reconnect_expired")
    created = client.post("/api/session/create", json={"campaign_id": "camp_reconnect_expired"}).json()
    room_code = created["room_code"]

    async def _pause_past_window():
        rt, _ = await session_manager.join_session(
            room_code,
            websocket=FakeWebSocket(),
            display_name="Host",
            character_name="Host Hero",
            desired_slot=PlayerSlot.HOST,
            client_id="host-client",
        )
        rt, _ = await session_manager.join_session(
            room_code,
            websocket=FakeWebSocket(),
            display_name="Guest",
            character_name="Guest Hero",
            desired_slot=PlayerSlot.GUEST,
            client_id="guest-client",
        )
        async with rt.lock:
            rt.status = SessionStatus.PAUSED
            rt.paused_status_before = SessionStatus.HOST_TURN
            rt.paused_since = datetime.now(timezone.utc) - timedelta(seconds=31)
            rt.reconnect_window_seconds = 30
            rt.players[PlayerSlot.GUEST].is_connected = False
            rt.connections.pop(PlayerSlot.GUEST, None)

    anyio.run(_pause_past_window)

    with client.websocket_connect(f"/api/session/{room_code}/ws") as guest_ws:
        guest_ws.send_json({
            "type": "reconnect",
            "slot": "guest",
            "display_name": "Guest",
            "character_name": "Guest Hero",
            "client_id": "guest-client",
        })
        message = guest_ws.receive_json()

    assert message["type"] == "error"
    assert message["code"] == "session_expired"
    assert "reconnect window closed" in message["message"]


def test_ws_set_starting_slot_is_host_only_and_persists(temp_state_dir, temp_chroma, mock_ollama):
    import anyio
    import state_manager
    from schema import PlayerSlot

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_starting_slot_ws")
    created = client.post("/api/session/create", json={"campaign_id": "camp_starting_slot_ws"}).json()
    room_code = created["room_code"]

    with client.websocket_connect(f"/api/session/{room_code}/ws") as host_ws:
        host_ws.send_json({
            "type": "join",
            "display_name": "Host",
            "character_name": "Host Hero",
            "slot": "host",
            "client_id": "host-client",
        })
        assert host_ws.receive_json()["type"] == "slot_assigned"
        _receive_until(host_ws, "session_state")

        with client.websocket_connect(f"/api/session/{room_code}/ws") as guest_ws:
            guest_ws.send_json({
                "type": "join",
                "display_name": "Guest",
                "character_name": "Guest Hero",
                "slot": "guest",
                "client_id": "guest-client",
            })
            assert guest_ws.receive_json()["type"] == "slot_assigned"
            _receive_until(guest_ws, "session_state")
            _receive_until(host_ws, "session_state")

            guest_ws.send_json({"type": "set_starting_slot", "slot": "host"})
            guest_error = guest_ws.receive_json()
            assert guest_error["type"] == "error"
            assert guest_error["code"] == "host_only"

            host_ws.send_json({"type": "set_starting_slot", "slot": "guest"})
            updated = _receive_until(host_ws, "session_state")

    assert updated["session_state"]["starting_slot_this_round"] == "guest"
    state = anyio.run(state_manager.load_state, "camp_starting_slot_ws")
    assert state.multiplayer.starting_slot_this_round == PlayerSlot.GUEST


def test_ws_gift_turn_advances_floor_without_generation(temp_state_dir, temp_chroma, mock_ollama):
    import anyio
    import session_manager
    from schema import PlayerSlot, SessionStatus

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_gift_turn")
    created = client.post("/api/session/create", json={"campaign_id": "camp_gift_turn"}).json()
    room_code = created["room_code"]

    with client.websocket_connect(f"/api/session/{room_code}/ws") as host_ws:
        host_ws.send_json({
            "type": "join",
            "display_name": "Host",
            "character_name": "Host Hero",
            "slot": "host",
            "client_id": "host-client",
        })
        assert host_ws.receive_json()["type"] == "slot_assigned"
        _receive_until(host_ws, "session_state")

        with client.websocket_connect(f"/api/session/{room_code}/ws") as guest_ws:
            guest_ws.send_json({
                "type": "join",
                "display_name": "Guest",
                "character_name": "Guest Hero",
                "slot": "guest",
                "client_id": "guest-client",
            })
            assert guest_ws.receive_json()["type"] == "slot_assigned"
            _receive_until(guest_ws, "session_state")
            _receive_until(host_ws, "session_state")

            async def _force_host_turn():
                rt = await session_manager.get_session(room_code)
                async with rt.lock:
                    rt.status = SessionStatus.HOST_TURN
                    rt.starting_slot_this_round = PlayerSlot.HOST
                    rt.kickoff_needed = False
                    rt.kickoff_in_progress = False

            anyio.run(_force_host_turn)

            guest_ws.send_json({"type": "gift_turn"})
            guest_error = guest_ws.receive_json()
            assert guest_error["type"] == "error"
            assert guest_error["code"] == "host_only"

            host_ws.send_json({"type": "gift_turn"})
            updated = _receive_until(host_ws, "session_state")

    assert updated["session_state"]["status"] == "guest_turn"
    assert updated["session_state"]["active_slot"] == "guest"
    assert updated["session_state"]["turn_number"] == 1
    assert mock_ollama.stream_calls == []


def test_ws_request_continue_appends_to_last_multiplayer_message(temp_state_dir, temp_chroma, mock_ollama):
    import anyio
    import session_manager
    import state_manager
    from schema import Message, PlayerCharacter, PlayerSlot, Role, SessionStatus

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_mp_continue")
    created = client.post("/api/session/create", json={"campaign_id": "camp_mp_continue"}).json()
    room_code = created["room_code"]

    async def _seed_turn():
        state = await state_manager.load_state("camp_mp_continue")
        state.multiplayer.guest_character = PlayerCharacter(slot=PlayerSlot.GUEST, name="Guest Hero")
        user = Message(
            turn_id="turn_continue",
            role=Role.USER,
            content=(
                "Active player submission. Treat this as command text, not prose to continue in first person.\n"
                "Acting character: Host Hero\n"
                "Submitted action text (I test the door): I test the door.\n"
                "Required response style: third-person present-tense story narration."
            ),
            player_slot="host",
        )
        gm = Message(
            turn_id="turn_continue",
            role=Role.ASSISTANT,
            content="The hinges groan",
            player_slot="host",
        )
        state.messages.extend([user, gm])
        await state_manager.save_state(state)
        rt = await session_manager.get_session(room_code)
        async with rt.lock:
            rt.status = SessionStatus.HOST_TURN
            rt.starting_slot_this_round = PlayerSlot.HOST
        return gm.id

    target_id = anyio.run(_seed_turn)
    mock_ollama.set_stream_text(" and reveal a silver-lit room.")

    with client.websocket_connect(f"/api/session/{room_code}/ws") as host_ws:
        host_ws.send_json({
            "type": "join",
            "display_name": "Host",
            "character_name": "Host Hero",
            "slot": "host",
            "client_id": "host-client",
        })
        assert host_ws.receive_json()["type"] == "slot_assigned"
        _receive_until(host_ws, "session_state")

        host_ws.send_json({"type": "request_continue", "message_id": target_id})
        started = _receive_until(host_ws, "generation_start", limit=12)
        done = _receive_until(host_ws, "generation_done", limit=12)

    assert started["mode"] == "continue"
    assert started["target_message_id"] == target_id
    assert done["mode"] == "continue"
    assert done["target_message_id"] == target_id

    state = anyio.run(state_manager.load_state, "camp_mp_continue")
    gm_messages = [m for m in state.messages if m.role == Role.ASSISTANT]
    assert len(gm_messages) == 1
    assert gm_messages[0].id == target_id
    assert gm_messages[0].content == "The hinges groan and reveal a silver-lit room."
    assert state.multiplayer.session_status == SessionStatus.HOST_TURN


def test_ws_request_reroll_replaces_last_multiplayer_message_without_advancing(temp_state_dir, temp_chroma, mock_ollama):
    import anyio
    import session_manager
    import state_manager
    from schema import Message, PlayerCharacter, PlayerSlot, Role, SessionStatus

    client = _client(temp_state_dir, temp_chroma, mock_ollama)
    _init_campaign(client, "camp_mp_reroll")
    created = client.post("/api/session/create", json={"campaign_id": "camp_mp_reroll"}).json()
    room_code = created["room_code"]

    async def _seed_turn():
        state = await state_manager.load_state("camp_mp_reroll")
        state.multiplayer.guest_character = PlayerCharacter(slot=PlayerSlot.GUEST, name="Guest Hero")
        user = Message(
            turn_id="turn_reroll",
            role=Role.USER,
            content=(
                "Active player submission. Treat this as command text, not prose to continue in first person.\n"
                "Acting character: Guest Hero\n"
                "Submitted action text (I inspect the sigils): I inspect the sigils.\n"
                "Required response style: third-person present-tense story narration."
            ),
            player_slot="guest",
        )
        gm = Message(
            turn_id="turn_reroll",
            role=Role.ASSISTANT,
            content="Old sigil response.",
            player_slot="guest",
        )
        state.messages.extend([user, gm])
        await state_manager.save_state(state)
        rt = await session_manager.get_session(room_code)
        async with rt.lock:
            rt.status = SessionStatus.GUEST_TURN
            rt.starting_slot_this_round = PlayerSlot.GUEST
        return gm.id

    old_gm_id = anyio.run(_seed_turn)
    mock_ollama.set_stream_text("The sigils flare with new meaning.")

    with client.websocket_connect(f"/api/session/{room_code}/ws") as host_ws:
        host_ws.send_json({
            "type": "join",
            "display_name": "Host",
            "character_name": "Host Hero",
            "slot": "host",
            "client_id": "host-client",
        })
        assert host_ws.receive_json()["type"] == "slot_assigned"
        _receive_until(host_ws, "session_state")

        with client.websocket_connect(f"/api/session/{room_code}/ws") as guest_ws:
            guest_ws.send_json({
                "type": "join",
                "display_name": "Guest",
                "character_name": "Guest Hero",
                "slot": "guest",
                "client_id": "guest-client",
            })
            assert guest_ws.receive_json()["type"] == "slot_assigned"
            _receive_until(guest_ws, "session_state")
            _receive_until(host_ws, "session_state")

            guest_ws.send_json({"type": "request_reroll", "message_id": old_gm_id})
            started = _receive_until(guest_ws, "generation_start", limit=12)
            done = _receive_until(guest_ws, "generation_done", limit=12)

    assert started["mode"] == "reroll"
    assert started["target_message_id"] == old_gm_id
    assert done["mode"] == "reroll"
    assert done["target_message_id"] == old_gm_id
    assert done["next_active_slot"] == "guest"

    state = anyio.run(state_manager.load_state, "camp_mp_reroll")
    assert all(m.id != old_gm_id for m in state.messages)
    gm_messages = [m for m in state.messages if m.role == Role.ASSISTANT]
    assert len(gm_messages) == 1
    assert gm_messages[0].content == "The sigils flare with new meaning."
    assert gm_messages[0].player_slot == "guest"
    assert state.multiplayer.session_status == SessionStatus.GUEST_TURN
