"""
State-change extraction from the player/GM exchange.

Runs on the utility model (not the GM model) — configurable per campaign with
a fallback chain via model_resolver. Output is validated against StateDelta;
garbage input returns an empty delta rather than polluting state.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from model_resolver import resolve_utility_model
from ollama_client import complete_json
from schema import CampaignState, PlayerSlot, StateDelta

log = logging.getLogger(__name__)


def _build_prompt(user_action: str, gm_response: str, active_stats: list[str]) -> str:
    stats_example = ", ".join(f'"{s}": 0' for s in active_stats) if active_stats else '"Health": 0'
    return f"""You are a state-tracking assistant for a roleplay game. Analyze the exchange below and emit a JSON object describing the concrete game-state changes it implies.

RULES:
- Return INTEGER DELTAS for stat changes, not absolute values. +5 means "gained 5", -10 means "lost 10".
- If no change, omit the field or return 0 / [].
- New stats may be introduced (e.g. "Sanity", "Stamina") if the narrative clearly implies them.
- NPCs mentioned by name may have their disposition updated; acceptable values are "Friendly", "Neutral", "Suspicious", "Hostile".
- Treat the GM Narrative as authoritative for what actually happened.

Schema:
{{
    "stats_changes": {{ {stats_example} }},
    "location": "<string or empty>",
    "inventory_added": ["<item name>"],
    "inventory_removed": ["<item name>"],
    "npc_updates": [
        {{"name": "<npc name>", "disposition_change": "<enum or empty>", "secret_revealed": "<string or null>"}}
    ]
}}

Player Action:
{user_action}

GM Narrative:
{gm_response}

Return ONLY the JSON object. No prose."""


async def extract_state_changes(
    state: CampaignState,
    user_action: str,
    gm_response: str,
) -> StateDelta:
    utility_model = await resolve_utility_model(state.models.utility, state.models.gm)
    active_stats = list(state.player.stats.keys()) or ["Health", "Gold"]

    prompt = _build_prompt(user_action, gm_response, active_stats)
    raw = await complete_json(
        messages=[{"role": "user", "content": prompt}],
        model=utility_model,
    )
    if raw is None:
        log.info("Extraction returned no usable JSON; no delta applied.")
        return StateDelta()

    try:
        return StateDelta.model_validate(raw)
    except ValidationError as e:
        log.warning("Extraction JSON failed validation: %s; raw=%r", e, raw)
        return StateDelta()


async def extract_state_changes_for_slot(
    state: CampaignState,
    slot: PlayerSlot,
    user_action: str,
    gm_response: str,
) -> StateDelta:
    """Extract state changes for one character in a multiplayer round.

    Uses the slot's character stats as the hint set so the model has the right
    keys to choose from. Falls back gracefully when the multiplayer config or
    target character isn't populated.
    """
    if state.multiplayer is None:
        return await extract_state_changes(state, user_action, gm_response)

    if slot == PlayerSlot.HOST:
        character = state.multiplayer.host_character
    elif slot == PlayerSlot.GUEST and state.multiplayer.guest_character is not None:
        character = state.multiplayer.guest_character
    else:
        return StateDelta()

    utility_model = await resolve_utility_model(state.models.utility, state.models.gm)
    active_stats = list(character.stats.keys()) or ["Health", "Gold"]

    framing = (
        f"You are extracting state changes that apply ONLY to character "
        f"{character.name!r} in a two-player session. Ignore any changes that "
        f"clearly belong to the other character."
    )
    prompt = framing + "\n\n" + _build_prompt(user_action, gm_response, active_stats)
    raw = await complete_json(
        messages=[{"role": "user", "content": prompt}],
        model=utility_model,
    )
    if raw is None:
        return StateDelta()
    try:
        return StateDelta.model_validate(raw)
    except ValidationError as e:
        log.warning("Multiplayer extraction (%s) failed validation: %s; raw=%r", slot.value, e, raw)
        return StateDelta()
