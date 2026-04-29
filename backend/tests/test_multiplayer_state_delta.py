"""Slot-aware apply_state_delta + apply_reversal."""

from __future__ import annotations

import state_manager
from schema import (
    MultiplayerConfig,
    PlayerCharacter,
    PlayerSlot,
    SessionStatus,
    StateDelta,
)


def _make_multiplayer(state) -> None:
    state.multiplayer = MultiplayerConfig(
        room_code="ROOM01",
        host_character=PlayerCharacter(
            slot=PlayerSlot.HOST,
            name="Hostess",
            location="Tavern",
            stats={"Health": 100, "Gold": 50},
            inventory=["Sword"],
        ),
        guest_character=PlayerCharacter(
            slot=PlayerSlot.GUEST,
            name="Guest",
            location="Tavern",
            stats={"Health": 100, "Gold": 0},
            inventory=[],
        ),
        session_status=SessionStatus.HOST_TURN,
    )


def test_delta_routes_to_host_character(new_state):
    state = new_state("c1")
    _make_multiplayer(state)
    delta = StateDelta(
        stats_changes={"Gold": 10},
        inventory_added=["Map"],
    )
    reversal = state_manager.apply_state_delta(state, delta, PlayerSlot.HOST)

    assert state.multiplayer.host_character.stats["Gold"] == 60
    assert "Map" in state.multiplayer.host_character.inventory
    # Guest is untouched.
    assert state.multiplayer.guest_character.stats["Gold"] == 0
    assert state.multiplayer.guest_character.inventory == []
    # Legacy `state.player` is also untouched.
    assert state.player.stats.get("Gold") == 50

    assert reversal["player_slot"] == "host"

    # Apply reversal — host should be back to original.
    state_manager.apply_reversal(state, reversal)
    assert state.multiplayer.host_character.stats["Gold"] == 50
    assert "Map" not in state.multiplayer.host_character.inventory


def test_delta_routes_to_guest_character(new_state):
    state = new_state("c2")
    _make_multiplayer(state)
    delta = StateDelta(
        stats_changes={"Health": -20},
        location="Forest",
    )
    reversal = state_manager.apply_state_delta(state, delta, PlayerSlot.GUEST)

    assert state.multiplayer.guest_character.stats["Health"] == 80
    assert state.multiplayer.guest_character.location == "Forest"
    # Host untouched.
    assert state.multiplayer.host_character.stats["Health"] == 100
    assert state.multiplayer.host_character.location == "Tavern"

    state_manager.apply_reversal(state, reversal)
    assert state.multiplayer.guest_character.stats["Health"] == 100
    assert state.multiplayer.guest_character.location == "Tavern"


def test_single_player_delta_unchanged_by_slot_addition(new_state):
    state = new_state("c3")
    delta = StateDelta(stats_changes={"Health": -5}, inventory_added=["Apple"])
    reversal = state_manager.apply_state_delta(state, delta)

    assert state.player.stats["Health"] == 95
    assert "Apple" in state.player.inventory
    assert reversal["player_slot"] is None

    state_manager.apply_reversal(state, reversal)
    assert state.player.stats["Health"] == 100
    assert "Apple" not in state.player.inventory


def test_npc_updates_remain_global_under_slot_routing(new_state):
    state = new_state("c4")
    _make_multiplayer(state)
    from schema import NPCUpdate

    delta = StateDelta(
        npc_updates=[NPCUpdate(name="Elena", disposition_change="Hostile", secret_revealed="Has a curse")],
    )
    state_manager.apply_state_delta(state, delta, PlayerSlot.GUEST)

    elena = next(n for n in state.npcs if n.name == "Elena")
    assert elena.disposition.value == "Hostile"
    assert "Has a curse" in elena.secrets_known
