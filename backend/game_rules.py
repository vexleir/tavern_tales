"""Lightweight action-resolution rules for Tavern Tales."""

from __future__ import annotations

import random

from schema import ActionResolution, CampaignState

RISK_KEYWORDS = (
    "attack", "fight", "strike", "stab", "shoot", "cast", "sneak", "hide",
    "steal", "pick", "force", "break", "climb", "jump", "run", "flee",
    "persuade", "lie", "deceive", "intimidate", "threaten", "resist",
    "search", "track", "disarm", "dodge",
)

STAT_HINTS = (
    (("sneak", "hide", "steal", "pick", "dodge"), ("Dexterity", "Agility", "Stealth")),
    (("persuade", "lie", "deceive"), ("Charisma", "Presence", "Charm")),
    (("intimidate", "threaten", "resist"), ("Willpower", "Presence", "Strength")),
    (("search", "track", "disarm"), ("Wisdom", "Perception", "Intelligence")),
    (("cast", "spell", "magic"), ("Magic", "Mana", "Willpower", "Sanity")),
    (("attack", "fight", "strike", "stab", "force", "break", "climb", "jump"), ("Strength", "Might", "Health")),
)


def _best_stat(state: CampaignState, action: str) -> tuple[str, int]:
    stats = state.player.stats or {}
    lowered = action.lower()
    for keywords, candidates in STAT_HINTS:
        if any(k in lowered for k in keywords):
            for candidate in candidates:
                if candidate in stats:
                    return candidate, stats[candidate]
    if stats:
        name = max(stats, key=lambda k: stats[k])
        return name, stats[name]
    return "Luck", 50


def _modifier(stat_value: int) -> int:
    # Tavern Tales stats are often broad 0-100 values. Compress them into a d20 modifier.
    return max(-5, min(10, round((stat_value - 50) / 10)))


def resolve_action(state: CampaignState, action: str, roll: int | None = None) -> ActionResolution | None:
    """Return an action check for risky actions, otherwise None."""
    if not state.rules.enabled:
        return None

    lowered = action.lower()
    if not any(k in lowered for k in RISK_KEYWORDS):
        return None

    stat, value = _best_stat(state, action)
    rolled = roll if roll is not None else random.randint(1, 20)
    modifier = _modifier(value)
    total = rolled + modifier
    dc = state.rules.default_dc

    if rolled == 20:
        outcome = "critical_success"
    elif rolled == 1:
        outcome = "critical_failure"
    elif total >= dc:
        outcome = "success"
    elif total >= dc - 3:
        outcome = "partial_success"
    else:
        outcome = "failure"

    summary = f"{state.rules.dice_mode}: rolled {rolled} + {modifier} {stat} = {total} vs DC {dc} ({outcome.replace('_', ' ')})"
    return ActionResolution(
        risky=True,
        stat=stat,
        stat_value=value,
        modifier=modifier,
        roll=rolled,
        total=total,
        dc=dc,
        outcome=outcome,
        summary=summary,
    )


def render_resolution(resolution: ActionResolution | None) -> str:
    if resolution is None or not resolution.risky:
        return ""
    return (
        "The player's action has already been resolved by the game rules. "
        f"Honor this result in the narration: {resolution.summary}. "
        "On success, grant clear progress. On partial success, grant progress with a cost or complication. "
        "On failure, introduce a fair consequence without negating player agency."
    )
