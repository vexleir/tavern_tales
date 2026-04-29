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
    assert "[MULTIPLAYER NARRATION RULES]" in sp
    assert "override the single-player second-person POV guidance" in sp
    assert "Current acting character: Aragorn (host)." in sp
    assert "Next spotlight after your response: Legolas (guest)." in sp
    assert "third-person present tense" in sp
    assert "Do not use second person" in sp


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


def test_format_multiplayer_turn_message_attributes_single_actor():
    msg = prompt_builder.format_multiplayer_turn_message(
        "Legolas",
        " I study the tracks. ",
        next_actor_name="Aragorn",
    )
    assert "Acting character: Legolas" in msg
    assert "Player input (I/me/my refers to Legolas): I study the tracks." in msg
    assert "hand the spotlight to: Aragorn" in msg
