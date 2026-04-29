"""Multiplayer session manager state-machine tests."""

from __future__ import annotations

import pytest

import session_manager
import state_manager
from schema import MultiplayerConfig, PlayerCharacter, PlayerSlot, SessionStatus


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def _host_character(name: str = "Host Hero") -> PlayerCharacter:
    return PlayerCharacter(
        slot=PlayerSlot.HOST,
        name=name,
        location="The Tavern",
        stats={"Health": 100},
        inventory=["Sword"],
    )


@pytest.mark.asyncio
async def test_create_join_ready_and_submit_flow(temp_state_dir, new_state):
    await state_manager.save_state(new_state("camp_multi", player_name="Host Hero"))

    rt = await session_manager.create_session("camp_multi", _host_character())
    assert rt.room_code
    assert rt.status == SessionStatus.LOBBY

    _, host = await session_manager.join_session(
        rt.room_code,
        websocket=FakeWebSocket(),
        display_name="Host",
        character_name="Host Hero",
    )
    _, guest = await session_manager.join_session(
        rt.room_code,
        websocket=FakeWebSocket(),
        display_name="Guest",
        character_name="Guest Hero",
    )
    assert host.slot == PlayerSlot.HOST
    assert guest.slot == PlayerSlot.GUEST

    await session_manager.set_ready(rt.room_code, PlayerSlot.HOST, True)
    rt = await session_manager.set_ready(rt.room_code, PlayerSlot.GUEST, True)
    assert rt.status == SessionStatus.HOST_TURN

    with pytest.raises(ValueError, match="not your turn"):
        await session_manager.submit_action(rt.room_code, PlayerSlot.GUEST, "I go first.")

    rt, result = await session_manager.submit_action(rt.room_code, PlayerSlot.HOST, "I open the door.")
    assert result == "stored"
    assert rt.status == SessionStatus.GUEST_TURN

    rt, result = await session_manager.submit_action(rt.room_code, PlayerSlot.GUEST, "I hold the lantern.")
    assert result == "ready_to_generate"
    assert rt.status == SessionStatus.GENERATING
    assert set(rt.pending_actions) == {PlayerSlot.HOST, PlayerSlot.GUEST}

    actions = await session_manager.consume_pending_actions(rt.room_code)
    assert actions[PlayerSlot.HOST] == "I open the door."
    assert actions[PlayerSlot.GUEST] == "I hold the lantern."

    rt = await session_manager.begin_next_round(rt.room_code)
    assert rt.turn_number == 1
    assert rt.starting_slot_this_round == PlayerSlot.GUEST
    assert rt.status == SessionStatus.GUEST_TURN

    rt, result = await session_manager.submit_action(rt.room_code, PlayerSlot.GUEST, "I lead this round.")
    assert result == "stored"
    assert rt.status == SessionStatus.HOST_TURN

    rt, result = await session_manager.submit_action(rt.room_code, PlayerSlot.HOST, "I follow up.")
    assert result == "ready_to_generate"
    assert rt.status == SessionStatus.GENERATING


@pytest.mark.asyncio
async def test_disconnect_pauses_and_reconnect_restores(temp_state_dir, new_state):
    await state_manager.save_state(new_state("camp_pause", player_name="Host Hero"))
    rt = await session_manager.create_session("camp_pause", _host_character())
    await session_manager.join_session(
        rt.room_code,
        websocket=FakeWebSocket(),
        display_name="Host",
        character_name="Host Hero",
    )
    await session_manager.join_session(
        rt.room_code,
        websocket=FakeWebSocket(),
        display_name="Guest",
        character_name="Guest Hero",
    )
    await session_manager.set_ready(rt.room_code, PlayerSlot.HOST, True)
    rt = await session_manager.set_ready(rt.room_code, PlayerSlot.GUEST, True)
    assert rt.status == SessionStatus.HOST_TURN

    rt = await session_manager.mark_disconnected(rt.room_code, PlayerSlot.GUEST)
    assert rt is not None
    assert rt.status == SessionStatus.PAUSED
    assert rt.paused_status_before == SessionStatus.HOST_TURN

    rt, guest = await session_manager.join_session(
        rt.room_code,
        websocket=FakeWebSocket(),
        display_name="Guest",
        character_name="Guest Hero",
        desired_slot=PlayerSlot.GUEST,
    )
    assert guest.slot == PlayerSlot.GUEST
    assert rt.status == SessionStatus.HOST_TURN
    assert rt.paused_status_before is None


@pytest.mark.asyncio
async def test_restart_rebuild_stays_paused_until_both_players_reconnect(temp_state_dir, new_state):
    state = new_state("camp_rebuild", player_name="Host Hero")
    state.multiplayer = MultiplayerConfig(
        room_code="ABC234",
        host_character=_host_character(),
        guest_character=PlayerCharacter(slot=PlayerSlot.GUEST, name="Guest Hero"),
        session_status=SessionStatus.GUEST_TURN,
    )
    await state_manager.save_state(state)

    await session_manager.initialize()
    rt = await session_manager.get_session("ABC234")
    assert rt is not None
    assert rt.status == SessionStatus.PAUSED
    assert rt.paused_status_before == SessionStatus.GUEST_TURN

    rt, _ = await session_manager.join_session(
        "ABC234",
        websocket=FakeWebSocket(),
        display_name="Host",
        character_name="Host Hero",
        desired_slot=PlayerSlot.HOST,
    )
    assert rt.status == SessionStatus.PAUSED

    rt, _ = await session_manager.join_session(
        "ABC234",
        websocket=FakeWebSocket(),
        display_name="Guest",
        character_name="Guest Hero",
        desired_slot=PlayerSlot.GUEST,
    )
    assert rt.status == SessionStatus.GUEST_TURN
