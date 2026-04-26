"""
Build the system prompt + history window that gets sent to the GM model.

This module replaces the previous frontend-side assembly. Every turn, the full
world/protagonist/cast/lorebook is re-injected — so the model never forgets
the setting after the opening turn (audit §1.1, the #1 coherence bug).

Key design:
  - System blocks are assembled greedily in priority order.
  - Message-history window is chosen by token budget, not count.
  - Retrieved memories are deduped against the window so we don't double-feed.
"""

from __future__ import annotations

import logging

from prompt_templates import GM_ONLY_MARKER, ROLE_RULES
from schema import BlockTokens, BuiltPrompt, CampaignState, PromptStats, Role
from tokenizer import count_messages, count_tokens, lookup_context_window

log = logging.getLogger(__name__)


def _section(title: str, body: str) -> str:
    return f"[{title}]\n{body}\n[/{title}]"


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if count_tokens(text) <= max_tokens:
        return text
    max_chars = max(200, max_tokens * 4)
    clipped = text[:max_chars].rsplit("\n", 1)[0].strip() or text[:max_chars].strip()
    return f"{clipped}\n[truncated to fit prompt budget]"


def _render_protagonist(state: CampaignState) -> str:
    p = state.player
    stats = ", ".join(f"{k}: {v}" for k, v in p.stats.items()) or "(none)"
    inv = ", ".join(p.inventory) if p.inventory else "(empty)"
    return (
        f"Name: {p.name}\n"
        f"Location: {p.location}\n"
        f"Stats: {stats}\n"
        f"Inventory: {inv}"
    )


def _render_cast(state: CampaignState) -> str:
    if not state.npcs:
        return "(no named NPCs yet)"
    lines: list[str] = []
    for npc in state.npcs:
        line = f"- {npc.name} ({npc.disposition.value})"
        if npc.secrets_known:
            secrets = "; ".join(npc.secrets_known)
            line += f"\n    {GM_ONLY_MARKER} Secrets: {secrets}"
        lines.append(line)
    return "\n".join(lines)


def _render_lorebook(state: CampaignState) -> str:
    if not state.lorebook:
        return ""
    lines = [f"- [{k}] {v}" for k, v in state.lorebook.items()]
    return "\n".join(lines)


def _render_chapters(state: CampaignState, max_chapters: int = 3) -> str:
    if not state.summaries.chapters:
        return ""
    tail = state.summaries.chapters[-max_chapters:]
    return "\n\n".join(
        f"Chapter {c.start_turn}-{c.end_turn}: {c.text}" for c in tail
    )


def _render_quests(state: CampaignState) -> str:
    active = [q for q in state.quests if q.status == "active"]
    if not active:
        return ""
    lines: list[str] = []
    for quest in active:
        lines.append(f"- {quest.title}")
        for obj in quest.objectives:
            mark = "done" if obj.complete else "open"
            lines.append(f"    [{mark}] {obj.text}")
    return "\n".join(lines)


def _render_conditions(state: CampaignState) -> str:
    if not state.conditions:
        return ""
    return "\n".join(
        f"- {c.name} ({c.severity}, {c.duration})" + (f" from {c.source}" if c.source else "")
        for c in state.conditions
    )


def _render_memories(memories: list[dict]) -> str:
    if not memories:
        return ""
    lines: list[str] = []
    for m in memories:
        doc = m.get("document") or m.get("text") or ""
        if not doc:
            continue
        lines.append(f"- {doc}")
    return "\n".join(lines)


def _dedupe_memories_against_window(
    memories: list[dict],
    window_msg_contents: list[str],
) -> list[dict]:
    """Drop memories whose text substantially overlaps a message already in the window."""
    if not memories or not window_msg_contents:
        return memories

    def _norm(s: str) -> str:
        return " ".join(s.lower().split())[:200]

    window_snippets = {_norm(c) for c in window_msg_contents}
    out: list[dict] = []
    for m in memories:
        doc = m.get("document") or m.get("text") or ""
        snippet = _norm(doc)
        if snippet and not any(snippet[:100] in ws or ws[:100] in snippet for ws in window_snippets):
            out.append(m)
    return out


def _build_system_prompt(
    state: CampaignState,
    memories: list[dict],
    window_msg_contents: list[str],
    turn_context: str = "",
) -> tuple[str, BlockTokens]:
    tokens = BlockTokens()
    parts: list[str] = []

    # 1. Role rules (always present)
    length_note = f"Campaign pacing preference: {state.rules.response_length} responses."
    role_rules = f"{ROLE_RULES}\n{length_note}"
    parts.append(role_rules)
    tokens.role_rules = count_tokens(role_rules)

    # 2. World
    if state.world_description.strip():
        body = state.world_description.strip()
        s = _section("WORLD", body)
        parts.append(s)
        tokens.world = count_tokens(s)

    # 3. Opening scene
    if state.starting_scene.strip():
        body = state.starting_scene.strip()
        s = _section("OPENING SCENE", body)
        parts.append(s)
        tokens.scene = count_tokens(s)

    # 4. Protagonist
    body = _render_protagonist(state)
    s = _section("PROTAGONIST", body)
    parts.append(s)
    tokens.protagonist = count_tokens(s)

    # 5. Cast
    body = _truncate_to_tokens(_render_cast(state), 900)
    s = _section("CAST", body)
    parts.append(s)
    tokens.cast = count_tokens(s)

    # 6. Lorebook — ALL entries, not keyword-filtered (audit §1.6)
    lb = _render_lorebook(state)
    if lb:
        lb = _truncate_to_tokens(lb, 1200)
        s = _section("LOREBOOK (absolute rules — honor them)", lb)
        parts.append(s)
        tokens.lorebook = count_tokens(s)

    # 7. Arc summary
    if state.summaries.arc.strip():
        s = _section("CAMPAIGN ARC SO FAR", state.summaries.arc.strip())
        parts.append(s)
        tokens.arc_summary = count_tokens(s)

    # 8. Chapter summaries
    chapters = _render_chapters(state)
    if chapters:
        s = _section("RECENT CHAPTERS", chapters)
        parts.append(s)
        tokens.chapter_summaries = count_tokens(s)

    # 9. Short summary
    if state.summaries.short.strip():
        s = _section("RECENT EVENTS", state.summaries.short.strip())
        parts.append(s)
        tokens.short_summary = count_tokens(s)

    # Active game systems
    quests = _render_quests(state)
    if quests:
        s = _section("ACTIVE QUESTS", quests)
        parts.append(s)
        tokens.quests = count_tokens(s)

    conditions = _render_conditions(state)
    if conditions:
        s = _section("ACTIVE CONDITIONS", conditions)
        parts.append(s)
        tokens.conditions = count_tokens(s)

    if turn_context.strip():
        s = _section("ACTION RESOLUTION (binding)", turn_context.strip())
        parts.append(s)
        tokens.action_resolution = count_tokens(s)

    # 10. Retrieved memories (deduped)
    filtered = _dedupe_memories_against_window(memories, window_msg_contents)
    mem = _render_memories(filtered)
    if mem:
        mem = _truncate_to_tokens(mem, 1200)
        s = _section("RELEVANT PAST MEMORIES", mem)
        parts.append(s)
        tokens.memories = count_tokens(s)

    return "\n\n".join(parts), tokens


def _select_window(
    state: CampaignState,
    budget_tokens: int,
) -> list[dict[str, str]]:
    """
    Walk messages newest→oldest, including each until the budget is exhausted.
    Returns oldest-first list of {role, content}.
    """
    selected: list[dict[str, str]] = []
    used = 0
    for msg in reversed(state.messages):
        if msg.role == Role.SYSTEM:
            continue
        role_api = "user" if msg.role == Role.USER else "assistant"
        content = msg.content
        cost = count_tokens(content) + count_tokens(role_api) + 4
        if used + cost > budget_tokens and selected:
            break
        selected.append({"role": role_api, "content": content})
        used += cost
    selected.reverse()
    return selected


def build_prompt(
    state: CampaignState,
    user_message: str | None,
    retrieved_memories: list[dict] | None = None,
    turn_context: str = "",
    response_budget: int = 512,
    system_reserve: int = 1500,
) -> BuiltPrompt:
    """
    Construct the full list of messages to send to the GM model.

    `user_message` — if provided, is appended as the final user turn. If None,
    the caller is responsible for having already appended a user message to
    state.messages (e.g. kickoff flow).
    """
    retrieved_memories = retrieved_memories or []
    model_window = lookup_context_window(state.models.gm)
    # Leave ~500 tokens of safety margin at the very end.
    total_budget = max(2048, model_window - 500)
    window_budget = max(512, total_budget - system_reserve - response_budget)

    # Choose window first so the dedupe step has message contents to compare against.
    window = _select_window(state, window_budget)
    window_contents = [m["content"] for m in window]

    system_text, block_tokens = _build_system_prompt(
        state,
        retrieved_memories,
        window_contents,
        turn_context=turn_context,
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_text}]
    messages.extend(window)

    if user_message is not None:
        messages.append({"role": "user", "content": user_message})

    system_tokens = count_tokens(system_text) + 4
    history_tokens = count_messages(messages) - system_tokens
    stats = PromptStats(
        blocks=block_tokens,
        system_tokens=system_tokens,
        history_tokens=history_tokens,
        response_budget=response_budget,
        model_context_window=model_window,
        total_used=system_tokens + history_tokens + response_budget,
    )

    return BuiltPrompt(
        messages=messages,
        stats=stats,
        system_prompt=system_text,
        retrieved_memories=retrieved_memories,
    )
