"""Multiplayer-aware prompt builder behavior."""

from __future__ import annotations

import prompt_builder
from schema import (
    MultiplayerConfig,
    PlayerCharacter,
    PlayerSlot,
    SessionStatus,
)


def _attach_multiplayer(state, *, with_guest: bool = True) -> None:
    state.multiplayer = MultiplayerConfig(
        room_code="ABC234",
        host_character=PlayerCharacter(
            slot=PlayerSlot.HOST,
            name="Aragorn",
            location="The Prancing Pony",
            gender="M",
            appearance="Weathered ranger, dark cloak.",
            stats={"Health": 100, "Sword": 12},
            inventory=["Sword", "Pipe"],
        ),
        guest_character=(
            PlayerCharacter(
                slot=PlayerSlot.GUEST,
                name="Legolas",
                location="The Prancing Pony",
                gender="M",
                appearance="Elven archer with pale features.",
                stats={"Health": 90, "Bow": 18},
                inventory=["Bow", "Quiver"],
            ) if with_guest else None
        ),
        session_status=SessionStatus.HOST_TURN,
    )


def test_multiplayer_prompt_includes_party_block(new_state):
    state = new_state("camp_party")
    _attach_multiplayer(state)

    built = prompt_builder.build_prompt(state, user_message="[Aragorn]: I open the door.")
    sp = built.system_prompt

    # PARTY block replaces PROTAGONIST in multiplayer mode.
    assert "[PARTY]" in sp
    assert "[PROTAGONIST]" not in sp
    assert "Aragorn" in sp
    assert "Legolas" in sp
    # Per-character details should appear.
    assert "Pipe" in sp     # host inventory
    assert "Quiver" in sp   # guest inventory
    assert "Sword: 12" in sp
    assert "Bow: 18" in sp


def test_multiplayer_prompt_handles_missing_guest(new_state):
    state = new_state("camp_solo_party")
    _attach_multiplayer(state, with_guest=False)

    built = prompt_builder.build_prompt(state, user_message="[Aragorn]: I wait.")
    assert "[PARTY]" in built.system_prompt
    assert "guest character not yet joined" in built.system_prompt


def test_single_player_still_uses_protagonist_block(new_state):
    state = new_state("camp_solo")
    built = prompt_builder.build_prompt(state, user_message="I wait by the fire.")
    assert "[PROTAGONIST]" in built.system_prompt
    assert "[PARTY]" not in built.system_prompt


def test_format_multiplayer_user_message_orders_by_starter():
    # Host starts → host action first.
    msg = prompt_builder.format_multiplayer_user_message(
        host_name="Aragorn",
        host_action="I draw my sword.",
        guest_name="Legolas",
        guest_action="I knock an arrow.",
        starter_slot="host",
    )
    assert msg.startswith("[Aragorn]:")
    assert msg.index("[Aragorn]") < msg.index("[Legolas]")

    # Guest starts → guest action first.
    msg = prompt_builder.format_multiplayer_user_message(
        host_name="Aragorn",
        host_action="I draw my sword.",
        guest_name="Legolas",
        guest_action="I knock an arrow.",
        starter_slot="guest",
    )
    assert msg.startswith("[Legolas]:")
    assert msg.index("[Legolas]") < msg.index("[Aragorn]")
