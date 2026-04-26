"""
Hierarchical progressive summarization.

Three tiers — none overwrite the others:
  short     — rolling summary of the most recent ~20 turns, refreshed every 5.
  chapters  — immutable summaries of older 20-turn blocks, produced at rollup.
  arc       — long-term narrative, compresses older chapters when they exceed 5.

The cadence is driven off message counts, not a floating "turn" counter. The
handler calls `maybe_summarize(state)` after each assistant turn; all decisions
are local.
"""

from __future__ import annotations

import logging

from model_resolver import resolve_utility_model
from ollama_client import complete_text
from schema import CampaignState, ChapterSummary, Role

log = logging.getLogger(__name__)

SHORT_UPDATE_EVERY = 5           # re-run short summary every N assistant turns
CHAPTER_ROLLUP_EVERY = 20        # start a new chapter every 20 assistant turns
MAX_CHAPTERS_BEFORE_ARC = 5      # fold oldest chapters into arc past this


def _assistant_turn_count(state: CampaignState) -> int:
    return sum(1 for m in state.messages if m.role == Role.ASSISTANT)


def _render_window(state: CampaignState, since_turn: int) -> str:
    parts: list[str] = []
    count = 0
    for m in state.messages:
        if m.role == Role.SYSTEM or m.is_kickoff:
            continue
        if m.role == Role.ASSISTANT:
            count += 1
        if count <= since_turn:
            continue
        prefix = "Player" if m.role == Role.USER else "GM"
        parts.append(f"({prefix}): {m.content}")
    return "\n".join(parts)


async def _summarize(utility_model: str, instruction: str, body: str, num_predict: int = 400) -> str:
    prompt = f"{instruction}\n\n{body}"
    result = await complete_text(
        messages=[{"role": "user", "content": prompt}],
        model=utility_model,
        num_predict=num_predict,
    )
    return (result or "").strip()


async def _update_short(state: CampaignState, utility_model: str) -> None:
    since = state.summaries.last_chapter_rollup_turn
    window_text = _render_window(state, since)
    if not window_text:
        return

    prior = state.summaries.short
    prior_block = f"Prior summary:\n{prior}\n\n" if prior else ""
    body = f"{prior_block}New events:\n{window_text}"

    instruction = (
        "Produce a factual 4-6 sentence summary of the roleplay events below. "
        "Retain all major events, decisions, objectives, and named NPCs. "
        "Do NOT invent new facts. Do NOT narrate in-character; describe in the past tense."
    )

    result = await _summarize(utility_model, instruction, body)
    if result:
        state.summaries.short = result
        state.summaries.last_short_update_turn = _assistant_turn_count(state)


async def _rollup_chapter(state: CampaignState, utility_model: str) -> None:
    since = state.summaries.last_chapter_rollup_turn
    end = _assistant_turn_count(state)
    if end - since < CHAPTER_ROLLUP_EVERY:
        return

    window_text = _render_window(state, since)
    instruction = (
        "Compress the events below into a 'chapter' summary of 6-10 sentences. "
        "Preserve plot beats, character developments, and unresolved threads. "
        "Past tense, third person. No in-character narration."
    )
    chapter_text = await _summarize(utility_model, instruction, window_text, num_predict=600)
    if not chapter_text:
        return

    state.summaries.chapters.append(
        ChapterSummary(start_turn=since + 1, end_turn=end, text=chapter_text)
    )
    state.summaries.last_chapter_rollup_turn = end
    # Short summary is now superseded by the chapter; clear it so the next cadence starts fresh.
    state.summaries.short = ""
    state.summaries.last_short_update_turn = end


async def _update_arc(state: CampaignState, utility_model: str) -> None:
    if len(state.summaries.chapters) <= MAX_CHAPTERS_BEFORE_ARC:
        return

    # Fold the oldest chapter into arc; keep the newer MAX_CHAPTERS_BEFORE_ARC chapters.
    oldest = state.summaries.chapters[0]
    current_arc = state.summaries.arc

    instruction = (
        "Combine the existing long-term arc summary with the new chapter. "
        "Produce a single 6-10 sentence summary of the overall campaign so far. "
        "Prioritize retention of major characters, pivotal decisions, and unresolved arcs. "
        "Past tense, third person."
    )
    body = f"Existing arc:\n{current_arc or '(none)'}\n\nNew chapter (turns {oldest.start_turn}-{oldest.end_turn}):\n{oldest.text}"

    result = await _summarize(utility_model, instruction, body, num_predict=500)
    if result:
        state.summaries.arc = result
        state.summaries.chapters = state.summaries.chapters[1:]


async def maybe_summarize(state: CampaignState) -> CampaignState:
    """Run whichever summarization passes are due for this turn. Mutates state in place."""
    turns = _assistant_turn_count(state)
    if turns == 0:
        return state

    utility_model = await resolve_utility_model(state.models.utility, state.models.gm)

    try:
        since_short = turns - state.summaries.last_short_update_turn
        if since_short >= SHORT_UPDATE_EVERY:
            await _update_short(state, utility_model)

        if turns - state.summaries.last_chapter_rollup_turn >= CHAPTER_ROLLUP_EVERY:
            await _rollup_chapter(state, utility_model)

        if len(state.summaries.chapters) > MAX_CHAPTERS_BEFORE_ARC:
            await _update_arc(state, utility_model)
    except Exception:
        log.exception("Summarizer pass failed; state left unchanged")

    return state
