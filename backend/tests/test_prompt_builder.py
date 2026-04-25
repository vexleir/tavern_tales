"""
Prompt builder: the #1 coherence test.

If the WORLD / OPENING SCENE / PROTAGONIST / CAST / LOREBOOK blocks ever go
missing again from the system prompt, these tests fail. That's the precise
regression the whole refactor exists to prevent.
"""

from __future__ import annotations

from prompt_builder import build_prompt
from schema import (
    CampaignState,
    ChapterSummary,
    Disposition,
    Message,
    ModelConfig,
    NPC,
    Player,
    Role,
)


def _rich_state() -> CampaignState:
    s = CampaignState(
        campaign_id="demo",
        models=ModelConfig(gm="llama3.1:8b-instruct", utility="llama3.1:8b-instruct"),
        player=Player(
            name="Matt",
            location="Willowdale Market",
            stats={"Health": 100, "Gold": 50, "Sanity": 80},
            inventory=["Rusty Sword", "Torch"],
        ),
        npcs=[
            NPC(name="Elara", disposition=Disposition.NEUTRAL, secrets_known=["knows the tome location"]),
            NPC(name="Lord Ravenwood", disposition=Disposition.HOSTILE),
        ],
        lorebook={"Magic": "Magic is illegal and heavily punished.", "Crown": "The crown is missing."},
        world_description="In the realm of Arcadia, sorcerers rule with an iron fist.",
        starting_scene="You stand in a bustling market square at dusk.",
    )
    s.messages = [
        Message(role=Role.USER, content="I enter the tavern."),
        Message(role=Role.ASSISTANT, content="The door creaks open. Smoke curls."),
    ]
    s.summaries.short = "Matt arrived in Willowdale."
    s.summaries.arc = "A tale of forbidden magic and a stolen crown."
    s.summaries.chapters = [
        ChapterSummary(start_turn=1, end_turn=20, text="Chapter 1: early days in the village."),
    ]
    return s


def test_system_prompt_contains_every_required_block():
    """THE anchor test. Regression here = the coherence bug came back."""
    built = build_prompt(_rich_state(), user_message="I look around.")
    sp = built.system_prompt
    # World
    assert "WORLD" in sp and "Arcadia" in sp
    # Scene
    assert "OPENING SCENE" in sp and "market square" in sp
    # Protagonist
    assert "PROTAGONIST" in sp
    assert "Matt" in sp
    assert "Willowdale Market" in sp
    assert "Health: 100" in sp
    assert "Rusty Sword" in sp
    # Cast — including GM-only secrets tag
    assert "CAST" in sp
    assert "Elara" in sp
    assert "Lord Ravenwood" in sp
    assert "tome location" in sp
    assert "GM-only knowledge" in sp
    # Lorebook — ALL entries, not keyword-filtered
    assert "LOREBOOK" in sp
    assert "[Magic]" in sp
    assert "[Crown] The crown is missing." in sp
    # Summaries
    assert "CAMPAIGN ARC" in sp
    assert "RECENT CHAPTERS" in sp
    assert "RECENT EVENTS" in sp


def test_user_message_is_last_turn():
    built = build_prompt(_rich_state(), user_message="I draw my sword.")
    assert built.messages[0]["role"] == "system"
    last = built.messages[-1]
    assert last["role"] == "user"
    assert last["content"] == "I draw my sword."


def test_no_user_message_omits_final_user_turn():
    s = _rich_state()
    built = build_prompt(s, user_message=None)
    last = built.messages[-1]
    # Last message comes from state.messages history (an assistant line).
    assert last["role"] in ("assistant", "system")


def test_empty_world_and_scene_blocks_are_skipped():
    s = _rich_state()
    s.world_description = ""
    s.starting_scene = ""
    built = build_prompt(s, user_message="x")
    assert "[WORLD]" not in built.system_prompt
    assert "OPENING SCENE" not in built.system_prompt
    # But protagonist etc. must still be present.
    assert "PROTAGONIST" in built.system_prompt


def test_prompt_stats_populated():
    built = build_prompt(_rich_state(), user_message="x")
    stats = built.stats
    assert stats.system_tokens > 0
    assert stats.model_context_window > 0
    assert stats.total_used > 0
    assert stats.blocks.world > 0
    assert stats.blocks.protagonist > 0
    assert stats.blocks.cast > 0
    assert stats.blocks.lorebook > 0


def test_window_respects_budget():
    """Flood the history and verify we still keep some turns (not zero)."""
    s = _rich_state()
    for i in range(100):
        s.messages.append(Message(role=Role.USER, content=f"msg {i} " * 50))
        s.messages.append(Message(role=Role.ASSISTANT, content=f"reply {i} " * 50))
    built = build_prompt(s, user_message="final")
    # At least the user message + something, system + safety budget unviolated.
    assert built.messages[0]["role"] == "system"
    assert built.messages[-1]["content"] == "final"
    assert built.stats.total_used <= built.stats.model_context_window


def test_memories_deduped_against_window():
    s = _rich_state()
    window_msg = "You entered a dark cave and found a glowing crystal."
    s.messages.append(Message(role=Role.ASSISTANT, content=window_msg))
    memories = [
        {"document": "You entered a dark cave and found a glowing crystal.", "distance": 0.1},
        {"document": "A raven landed on your shoulder silently.", "distance": 0.2},
    ]
    built = build_prompt(s, user_message="x", retrieved_memories=memories)
    # The duplicate memory should be dropped from the injected RELEVANT PAST MEMORIES block.
    assert "raven landed" in built.system_prompt
    assert "glowing crystal" not in built.system_prompt
    # The window itself (passed as chat messages) still carries the original.
    window_contents = "\n".join(m["content"] for m in built.messages if m["role"] != "system")
    assert "glowing crystal" in window_contents


def test_large_lorebook_is_truncated():
    s = _rich_state()
    s.lorebook = {f"Lore{i}": ("very long rule " * 80) for i in range(80)}
    built = build_prompt(s, user_message="x")
    assert "LOREBOOK" in built.system_prompt
    assert "truncated to fit prompt budget" in built.system_prompt
    assert built.stats.total_used <= built.stats.model_context_window
