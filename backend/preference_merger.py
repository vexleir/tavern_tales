"""Multiplayer preference merging with veto semantics.

Merges two `UserPreferenceProfile` objects into a single
`CampaignPreferenceContext` suitable for prompt injection. The merger applies
"most-restrictive wins" rules so that whichever player has the stricter
position dictates the session-wide guidance.

Rules (in plain language):
    - Filter by ContextType.MULTIPLAYER — only items both players have marked
      as relevant in a multiplayer setting are considered.
    - Hard veto: if either player has realWorldWillingness=hard_no OR
      textRoleplayWillingness=no → the item is dropped entirely.
    - Soft veto: if either has realWorldWillingness in {soft_no, discuss_only}
      OR textRoleplayWillingness=maybe → the item is kept but flagged as
      "approach with care" in the guidance text.
    - Intensity ceiling: min(host_intensity, guest_intensity).
    - Fantasy interest: min(host_interest, guest_interest); items where the
      minimum is `none` are excluded.
    - Overlap-only: if either player has partnerSharePermission=overlap_only,
      the item only survives if both players have interest ≥ low.
    - Global fadeToBlack: union — if either player has fadeToBlack=True the
      merged context is fade-to-black.

When one profile is None the merger still applies, with the present profile's
items filtered by MULTIPLAYER context. When both are None it returns a disabled
`CampaignPreferenceContext`.
"""

from __future__ import annotations

from typing import Any

from preference_logic import (
    FANTASY_RANK,
    INTENSITY_RANK,
    REAL_WORLD_RANK,
    TEXT_RANK,
    iter_items,
)
from preference_schema import (
    ContextType,
    FantasyInterest,
    IntensityPreference,
    PartnerSharePermission,
    PreferenceItem,
    RealWorldWillingness,
    TextRoleplayWillingness,
    UserPreferenceProfile,
)
from schema import CampaignPreferenceContext


_FANTASY_BY_RANK: dict[int, FantasyInterest] = {v: k for k, v in FANTASY_RANK.items()}
_INTENSITY_BY_RANK: dict[int, IntensityPreference] = {v: k for k, v in INTENSITY_RANK.items()}


def _hard_veto(item: PreferenceItem) -> bool:
    return (
        item.realWorldWillingness == RealWorldWillingness.HARD_NO
        or item.textRoleplayWillingness == TextRoleplayWillingness.NO
    )


def _soft_caution(item: PreferenceItem) -> bool:
    return (
        item.realWorldWillingness in (RealWorldWillingness.SOFT_NO, RealWorldWillingness.DISCUSS_ONLY)
        or item.textRoleplayWillingness == TextRoleplayWillingness.MAYBE
    )


def _ranked_min_fantasy(a: FantasyInterest, b: FantasyInterest) -> FantasyInterest:
    return _FANTASY_BY_RANK[min(FANTASY_RANK[a], FANTASY_RANK[b])]


def _ranked_min_intensity(a: IntensityPreference, b: IntensityPreference) -> IntensityPreference:
    return _INTENSITY_BY_RANK[min(INTENSITY_RANK[a], INTENSITY_RANK[b])]


def _filter_items_by_context(
    profile: UserPreferenceProfile | None,
    context: ContextType,
) -> dict[str, tuple[str, PreferenceItem]]:
    """Return {item_id: (category_id, item)} for items including the given context."""
    if profile is None:
        return {}
    out: dict[str, tuple[str, PreferenceItem]] = {}
    for category_id, item in iter_items(profile):
        if context in item.context:
            out[item.id] = (category_id, item)
    return out


def _global_context(
    host: UserPreferenceProfile | None,
    guest: UserPreferenceProfile | None,
    fade_to_black: bool,
) -> dict[str, Any]:
    """Build a small, safe global-context dict from both profiles."""
    profiles = [p for p in (host, guest) if p is not None]
    if not profiles:
        return {"fadeToBlack": fade_to_black, "context": "multiplayer"}

    # Use the most-restrictive consent style: explicit > negotiated > implied.
    consent_priority = {"explicit": 2, "negotiated": 1, "implied": 0}
    consent_styles = [p.globalPreferences.consentStyle.value for p in profiles]
    consent_style = max(consent_styles, key=lambda s: consent_priority.get(s, 0))

    pov_values = {p.globalPreferences.preferredPOV.value for p in profiles}
    preferred_pov = pov_values.pop() if len(pov_values) == 1 else "third"

    return {
        "fadeToBlack": fade_to_black,
        "consentStyle": consent_style,
        "preferredPOV": preferred_pov,
        "context": "multiplayer",
        "participants": [
            {
                "displayName": p.displayName,
                "rolePreference": p.globalPreferences.rolePreference.value,
            }
            for p in profiles
        ],
    }


def _serialize_theme(
    item: PreferenceItem,
    *,
    fantasy_interest: FantasyInterest,
    intensity: IntensityPreference,
    fantasy_only: bool,
    soft_caution: bool,
) -> dict[str, Any]:
    """Render a merged theme entry safe for prompt inclusion."""
    return {
        "id": item.id,
        "label": item.label,
        "description": item.description,
        "fantasyInterest": fantasy_interest.value,
        "intensityPreference": intensity.value,
        "fantasyOnly": fantasy_only,
        "softCaution": soft_caution,
    }


def _single_profile_context(
    profile: UserPreferenceProfile,
    context: ContextType,
) -> CampaignPreferenceContext:
    """Build a multiplayer context from one present profile.

    Used when a guest skips preference sharing or the host has no profile. The
    present profile still gets context filtering and its own vetoes honored.
    """
    selected_themes: list[dict[str, Any]] = []
    fantasy_only_ids: list[str] = []
    hard_no_ids: list[str] = []
    soft_caution_ids: list[str] = []

    for item_id, (_, item) in sorted(_filter_items_by_context(profile, context).items()):
        if _hard_veto(item):
            hard_no_ids.append(item_id)
            continue
        if item.fantasyInterest == FantasyInterest.NONE:
            continue
        is_soft = _soft_caution(item)
        if is_soft:
            soft_caution_ids.append(item_id)
        if item.fantasyOnly:
            fantasy_only_ids.append(item_id)
        selected_themes.append(
            _serialize_theme(
                item,
                fantasy_interest=item.fantasyInterest,
                intensity=item.intensityPreference,
                fantasy_only=item.fantasyOnly,
                soft_caution=is_soft,
            )
        )

    safety_principle = "Fantasy interest is not real-world consent."
    if soft_caution_ids:
        safety_principle += " Items flagged with softCaution should be approached gently — at least one player marked them as soft-no, discuss-only, or maybe."

    return CampaignPreferenceContext(
        enabled=bool(selected_themes or hard_no_ids),
        source="multiplayer_merge",
        profile_id=profile.profileId,
        profile_version=profile.profileVersion,
        selected_themes=selected_themes,
        fantasy_only_theme_ids=fantasy_only_ids,
        real_world_hard_no_theme_ids=hard_no_ids,
        global_context=_global_context(profile, None, profile.globalPreferences.fadeToBlack),
        safety_principle=safety_principle,
    )


def merge_preferences(
    host_profile: UserPreferenceProfile | None,
    guest_profile: UserPreferenceProfile | None,
    context: ContextType = ContextType.MULTIPLAYER,
) -> CampaignPreferenceContext:
    """Merge two preference profiles into a single CampaignPreferenceContext.

    Either profile may be None. When both are None, returns a disabled context.
    """
    if host_profile is None and guest_profile is None:
        return CampaignPreferenceContext()
    if guest_profile is None and host_profile is not None:
        return _single_profile_context(host_profile, context)
    if host_profile is None and guest_profile is not None:
        return _single_profile_context(guest_profile, context)

    host_items = _filter_items_by_context(host_profile, context)
    guest_items = _filter_items_by_context(guest_profile, context)

    selected_themes: list[dict[str, Any]] = []
    fantasy_only_ids: list[str] = []
    hard_no_ids: list[str] = []
    soft_caution_ids: list[str] = []

    # Iterate over the union of item IDs. Items present in only one profile are
    # treated as if the missing side defaulted to "no interest, hard_no" — the
    # standard veto rules then exclude them naturally.
    all_ids = set(host_items) | set(guest_items)

    for item_id in sorted(all_ids):
        host_pair = host_items.get(item_id)
        guest_pair = guest_items.get(item_id)

        # If only one player marked this item as multiplayer-relevant, treat
        # the other player's stance as "no interest" — this conservatively
        # excludes solo-only items from the shared session.
        if host_pair is None or guest_pair is None:
            present = host_pair or guest_pair
            assert present is not None  # at least one side present
            _, present_item = present
            if _hard_veto(present_item):
                hard_no_ids.append(item_id)
            continue

        _, a = host_pair
        _, b = guest_pair

        # Hard vetoes always exclude.
        if _hard_veto(a) or _hard_veto(b):
            hard_no_ids.append(item_id)
            continue

        # Fantasy interest is the more conservative of the two.
        merged_interest = _ranked_min_fantasy(a.fantasyInterest, b.fantasyInterest)
        if merged_interest == FantasyInterest.NONE:
            continue

        # Overlap-only requirement: if either side restricts to overlap-only,
        # both must have at least LOW interest for the item to survive.
        either_overlap = (
            a.partnerSharePermission == PartnerSharePermission.OVERLAP_ONLY
            or b.partnerSharePermission == PartnerSharePermission.OVERLAP_ONLY
        )
        if either_overlap and (
            FANTASY_RANK[a.fantasyInterest] < FANTASY_RANK[FantasyInterest.LOW]
            or FANTASY_RANK[b.fantasyInterest] < FANTASY_RANK[FantasyInterest.LOW]
        ):
            continue

        merged_intensity = _ranked_min_intensity(a.intensityPreference, b.intensityPreference)
        fantasy_only = a.fantasyOnly or b.fantasyOnly
        is_soft = _soft_caution(a) or _soft_caution(b)
        if is_soft:
            soft_caution_ids.append(item_id)
        if fantasy_only:
            fantasy_only_ids.append(item_id)

        # Use the host's label/description as canonical; fall back to guest's
        # if the host left them blank. They reference the same item id, so
        # labels should normally agree.
        canonical = a if (a.label or not b.label) else b
        selected_themes.append(
            _serialize_theme(
                canonical,
                fantasy_interest=merged_interest,
                intensity=merged_intensity,
                fantasy_only=fantasy_only,
                soft_caution=is_soft,
            )
        )

    fade_to_black = bool(
        (host_profile and host_profile.globalPreferences.fadeToBlack)
        or (guest_profile and guest_profile.globalPreferences.fadeToBlack)
    )

    safety_principle = "Fantasy interest is not real-world consent."
    if soft_caution_ids:
        safety_principle += " Items flagged with softCaution should be approached gently — at least one player marked them as soft-no, discuss-only, or maybe."

    profile_ids = [p.profileId for p in (host_profile, guest_profile) if p is not None]
    primary_profile_id = profile_ids[0] if profile_ids else ""
    primary_profile_version = (
        host_profile.profileVersion
        if host_profile is not None
        else (guest_profile.profileVersion if guest_profile is not None else None)
    )

    return CampaignPreferenceContext(
        enabled=bool(selected_themes or hard_no_ids),
        source="multiplayer_merge",
        profile_id=primary_profile_id,
        profile_version=primary_profile_version,
        selected_themes=selected_themes,
        fantasy_only_theme_ids=fantasy_only_ids,
        real_world_hard_no_theme_ids=hard_no_ids,
        global_context=_global_context(host_profile, guest_profile, fade_to_black),
        safety_principle=safety_principle,
    )


def merge_summary(context: CampaignPreferenceContext) -> dict[str, Any]:
    """Compact, lobby-friendly summary for both players to review before Ready."""
    soft_count = sum(1 for t in context.selected_themes if t.get("softCaution"))
    return {
        "enabled": context.enabled,
        "selected_count": len(context.selected_themes),
        "soft_caution_count": soft_count,
        "hard_no_count": len(context.real_world_hard_no_theme_ids),
        "fade_to_black": context.global_context.get("fadeToBlack", False),
        "consent_style": context.global_context.get("consentStyle", "explicit"),
        "preferred_pov": context.global_context.get("preferredPOV", "third"),
        "themes": [
            {
                "id": t["id"],
                "label": t.get("label", ""),
                "fantasyInterest": t.get("fantasyInterest"),
                "intensityPreference": t.get("intensityPreference"),
                "softCaution": bool(t.get("softCaution")),
            }
            for t in context.selected_themes
        ],
    }
