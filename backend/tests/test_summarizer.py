"""
Summarizer: cadence (short @ 5 turns, chapter @ 20, arc @ >5 chapters), non-overwriting.
"""

from __future__ import annotations

import pytest

import summarizer
from schema import Message, Role


async def _assistant_turn(state, n=1):
    """Helper: inject N fake player+GM pairs, running maybe_summarize after each so the cadence fires naturally."""
    base = len([m for m in state.messages if m.role == Role.ASSISTANT])
    for i in range(n):
        idx = base + i
        state.messages.append(Message(role=Role.USER, content=f"User action {idx}"))
        state.messages.append(Message(role=Role.ASSISTANT, content=f"GM narration {idx}"))
        await summarizer.maybe_summarize(state)


@pytest.mark.asyncio
async def test_short_not_fired_before_cadence(new_state, mock_ollama):
    mock_ollama.set_text("short summary goes here.")
    state = new_state()
    await _assistant_turn(state, n=3)
    assert state.summaries.short == ""  # cadence not yet hit
    assert len(mock_ollama.text_calls) == 0


@pytest.mark.asyncio
async def test_short_fires_at_cadence(new_state, mock_ollama):
    mock_ollama.set_text("short summary goes here.")
    state = new_state()
    await _assistant_turn(state, n=5)
    assert state.summaries.short == "short summary goes here."
    assert state.summaries.last_short_update_turn == 5


@pytest.mark.asyncio
async def test_chapter_rollup_clears_short(new_state, mock_ollama):
    # Every call returns whatever is set; test doesn't need distinct outputs.
    mock_ollama.set_text("compressed.")
    state = new_state()
    # 20 turns triggers a chapter rollup.
    await _assistant_turn(state, n=20)
    assert len(state.summaries.chapters) == 1
    assert state.summaries.chapters[0].end_turn == 20
    assert state.summaries.short == ""  # cleared per design
    assert state.summaries.last_chapter_rollup_turn == 20


@pytest.mark.asyncio
async def test_arc_fires_when_chapters_exceed_limit(new_state, mock_ollama):
    mock_ollama.set_text("x.")
    state = new_state()
    # Six chapters' worth (120 turns).
    await _assistant_turn(state, n=120)
    # At 120 turns we have 6 chapters, arc fires (threshold is >5), oldest folded.
    assert state.summaries.arc != ""
    assert len(state.summaries.chapters) <= 5
