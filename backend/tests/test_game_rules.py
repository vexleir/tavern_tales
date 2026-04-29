from __future__ import annotations

from game_rules import render_resolution, resolve_action
from schema import (
    Condition,
    MultiplayerConfig,
    PlayerCharacter,
    PlayerSlot,
    Quest,
    QuestObjective,
    SessionStatus,
)
from prompt_builder import build_prompt


def test_resolve_risky_action_uses_matching_stat(new_state):
    state = new_state("rules", stats={"Dexterity": 70, "Health": 100})
    result = resolve_action(state, "I sneak past the guard.", roll=10)
    assert result is not None
    assert result.stat == "Dexterity"
    assert result.total == 12
    assert result.outcome == "success"


def test_resolve_risky_action_uses_multiplayer_slot_stats(new_state):
    state = new_state("rules_mp", stats={"Dexterity": 30})
    state.multiplayer = MultiplayerConfig(
        room_code="ABC123",
        host_character=PlayerCharacter(
            slot=PlayerSlot.HOST,
            name="Host",
            stats={"Dexterity": 40},
        ),
        guest_character=PlayerCharacter(
            slot=PlayerSlot.GUEST,
            name="Guest",
            stats={"Dexterity": 80},
        ),
        session_status=SessionStatus.GUEST_TURN,
    )

    result = resolve_action(state, "I sneak past the guard.", roll=10, player_slot=PlayerSlot.GUEST)

    assert result is not None
    assert result.stat == "Dexterity"
    assert result.stat_value == 80
    assert result.total == 13


def test_safe_action_has_no_roll(new_state):
    state = new_state("rules")
    assert resolve_action(state, "I greet the innkeeper politely.") is None


def test_action_resolution_is_injected_into_prompt(new_state):
    state = new_state("rules")
    resolution = resolve_action(state, "I attack the raider.", roll=1)
    built = build_prompt(state, "I attack the raider.", turn_context=render_resolution(resolution))
    assert "ACTION RESOLUTION" in built.system_prompt
    assert "critical failure" in built.system_prompt


def test_quests_and_conditions_are_injected(new_state):
    state = new_state("rules")
    state.quests = [
        Quest(title="Find the lost bell", objectives=[QuestObjective(text="Search the old chapel")])
    ]
    state.conditions = [Condition(name="Poisoned", severity="major", duration="3 turns")]
    built = build_prompt(state, "I press on.")
    assert "ACTIVE QUESTS" in built.system_prompt
    assert "Search the old chapel" in built.system_prompt
    assert "ACTIVE CONDITIONS" in built.system_prompt
    assert "Poisoned" in built.system_prompt
