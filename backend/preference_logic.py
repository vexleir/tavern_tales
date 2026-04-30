"""Privacy, matching, and generation helpers for preference profiles."""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from preference_schema import (
    CampaignSeed,
    ContextType,
    FantasyInterest,
    GeneratedFantasy,
    GiverReceiverRole,
    IntensityPreference,
    PartnerSharePermission,
    PreferenceItem,
    PreferenceSnapshot,
    RealWorldWillingness,
    SharingMode,
    TextRoleplayWillingness,
    UserPreferenceProfile,
    now_iso,
)


FANTASY_RANK = {
    FantasyInterest.NONE: 0,
    FantasyInterest.LOW: 1,
    FantasyInterest.MEDIUM: 2,
    FantasyInterest.HIGH: 3,
    FantasyInterest.FAVORITE: 4,
}

INTENSITY_RANK = {
    IntensityPreference.LIGHT: 0,
    IntensityPreference.MODERATE: 1,
    IntensityPreference.INTENSE: 2,
}

REAL_WORLD_RANK = {
    RealWorldWillingness.HARD_NO: 0,
    RealWorldWillingness.SOFT_NO: 1,
    RealWorldWillingness.DISCUSS_ONLY: 2,
    RealWorldWillingness.MAYBE: 3,
    RealWorldWillingness.YES: 4,
}

TEXT_RANK = {
    TextRoleplayWillingness.NO: 0,
    TextRoleplayWillingness.MAYBE: 1,
    TextRoleplayWillingness.YES: 2,
}

SHARE_RANK = {
    PartnerSharePermission.PRIVATE: 0,
    PartnerSharePermission.OVERLAP_ONLY: 1,
    PartnerSharePermission.SUMMARY: 2,
    PartnerSharePermission.FULL: 3,
}

ROLE_DIRECTION_LABELS = {
    GiverReceiverRole.GIVER: "profile wants to initiate, guide, direct, set rules, or lead this theme",
    GiverReceiverRole.RECEIVER: "profile wants to follow, yield, be guided, respond, or experience this theme",
    GiverReceiverRole.BOTH: "profile is open to either role in this theme",
}


def _roles_compatible(a: GiverReceiverRole, b: GiverReceiverRole) -> bool:
    if a == GiverReceiverRole.BOTH or b == GiverReceiverRole.BOTH:
        return True
    return a != b


def _shared_role(a: GiverReceiverRole, b: GiverReceiverRole) -> str:
    if a == GiverReceiverRole.BOTH and b == GiverReceiverRole.BOTH:
        return GiverReceiverRole.BOTH.value
    if a == GiverReceiverRole.BOTH:
        return b.value
    if b == GiverReceiverRole.BOTH:
        return a.value
    return f"first_{a.value}_second_{b.value}"


def iter_items(profile: UserPreferenceProfile) -> list[tuple[str, PreferenceItem]]:
    out: list[tuple[str, PreferenceItem]] = []
    for category in profile.categories:
        for item in category.items:
            out.append((category.id, item))
    return out


def redact_profile(profile: UserPreferenceProfile, include_private: bool = False) -> dict[str, Any]:
    data = deepcopy(profile).model_dump(mode="json")
    if include_private:
        return data

    for category in data.get("categories", []):
        for item in category.get("items", []):
            item["commentsPrivate"] = ""
            if item.get("partnerSharePermission") == PartnerSharePermission.PRIVATE.value:
                item["commentsShareable"] = ""

    for custom in data.get("customPreferences", []):
        custom["commentsPrivate"] = ""
        if custom.get("partnerSharePermission") == PartnerSharePermission.PRIVATE.value:
            custom["commentsShareable"] = ""

    data["realityBridge"] = {
        "enabled": False,
        "intent": "discussion_only",
        "comfortLevel": "curious",
        "nonNegotiables": [],
        "conditions": [],
        "shareWithPartner": False,
    }
    return data


def _lowest_intensity(a: IntensityPreference, b: IntensityPreference) -> IntensityPreference:
    return min((a, b), key=lambda x: INTENSITY_RANK[x])


def _stricter_real_world(a: RealWorldWillingness, b: RealWorldWillingness) -> RealWorldWillingness:
    return min((a, b), key=lambda x: REAL_WORLD_RANK[x])


def _least_permissive_share(a: PartnerSharePermission, b: PartnerSharePermission) -> PartnerSharePermission:
    return min((a, b), key=lambda x: SHARE_RANK[x])


def compare_profiles(
    first: UserPreferenceProfile,
    second: UserPreferenceProfile,
    context: ContextType = ContextType.AI,
) -> dict[str, Any]:
    first_by_id = {item.id: (cat_id, item) for cat_id, item in iter_items(first)}
    second_by_id = {item.id: (cat_id, item) for cat_id, item in iter_items(second)}

    matches: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    reality_bridge_excluded: list[str] = []

    for item_id, (cat_id, a) in first_by_id.items():
        pair = second_by_id.get(item_id)
        if pair is None:
            continue
        _, b = pair

        share_permission = _least_permissive_share(a.partnerSharePermission, b.partnerSharePermission)
        lowest_interest = min(FANTASY_RANK[a.fantasyInterest], FANTASY_RANK[b.fantasyInterest])
        lowest_text = min(TEXT_RANK[a.textRoleplayWillingness], TEXT_RANK[b.textRoleplayWillingness])
        fantasy_only = a.fantasyOnly or b.fantasyOnly
        real_world = _stricter_real_world(a.realWorldWillingness, b.realWorldWillingness)

        reasons: list[str] = []
        if context not in a.context or context not in b.context:
            reasons.append("context_not_shared")
        if lowest_interest == 0:
            reasons.append("fantasy_interest_not_mutual")
        if lowest_text == 0:
            reasons.append("text_roleplay_not_mutual")
        if not _roles_compatible(a.giverReceiverRole, b.giverReceiverRole):
            reasons.append("giver_receiver_not_complementary")
        if share_permission == PartnerSharePermission.PRIVATE:
            reasons.append("share_permission_private")
        if a.realWorldWillingness == RealWorldWillingness.HARD_NO or b.realWorldWillingness == RealWorldWillingness.HARD_NO:
            reality_bridge_excluded.append(item_id)

        if reasons:
            blocked.append({
                "id": item_id,
                "categoryId": cat_id,
                "label": a.label,
                "reasons": reasons,
                "first": {
                    "fantasyInterest": a.fantasyInterest.value,
                    "textRoleplayWillingness": a.textRoleplayWillingness.value,
                    "realWorldWillingness": a.realWorldWillingness.value,
                    "partnerSharePermission": a.partnerSharePermission.value,
                    "giverReceiverRole": a.giverReceiverRole.value,
                },
                "second": {
                    "fantasyInterest": b.fantasyInterest.value,
                    "textRoleplayWillingness": b.textRoleplayWillingness.value,
                    "realWorldWillingness": b.realWorldWillingness.value,
                    "partnerSharePermission": b.partnerSharePermission.value,
                    "giverReceiverRole": b.giverReceiverRole.value,
                },
            })
            continue

        lowest_intensity = _lowest_intensity(a.intensityPreference, b.intensityPreference)
        shared_role = _shared_role(a.giverReceiverRole, b.giverReceiverRole)
        shareable_comments = []
        if share_permission == PartnerSharePermission.FULL:
            if a.commentsShareable:
                shareable_comments.append({"profileId": first.profileId, "comment": a.commentsShareable})
            if b.commentsShareable:
                shareable_comments.append({"profileId": second.profileId, "comment": b.commentsShareable})

        matches.append({
            "id": item_id,
            "categoryId": cat_id,
            "label": a.label if share_permission != PartnerSharePermission.OVERLAP_ONLY else "Shared compatible theme",
            "fantasyInterest": min(a.fantasyInterest, b.fantasyInterest, key=lambda x: FANTASY_RANK[x]).value,
            "textRoleplayWillingness": min(a.textRoleplayWillingness, b.textRoleplayWillingness, key=lambda x: TEXT_RANK[x]).value,
            "realWorldWillingness": real_world.value,
            "fantasyOnly": fantasy_only,
            "intensityPreference": lowest_intensity.value,
            "giverReceiverRole": shared_role,
            "profileRoles": {
                first.profileId: a.giverReceiverRole.value,
                second.profileId: b.giverReceiverRole.value,
            },
            "partnerSharePermission": share_permission.value,
            "shareableComments": shareable_comments,
            "compatibilityNotes": [
                f"Lowest shared intensity: {lowest_intensity.value}.",
                f"Stricter real-world boundary: {real_world.value}.",
                "Fantasy-only applies." if fantasy_only else "Fantasy-only not required by either profile.",
                f"Least permissive sharing mode: {share_permission.value}.",
            ],
        })

    return {
        "profileIds": [first.profileId, second.profileId],
        "context": context.value,
        "matches": matches,
        "blocked": blocked,
        "realityBridgeExcludedThemeIds": sorted(set(reality_bridge_excluded)),
        "safetyPrinciple": "Fantasy interest is not real-world consent.",
    }


def _eligible_items(
    profile: UserPreferenceProfile,
    context: ContextType,
    category_ids: list[str] | None = None,
    intensity: IntensityPreference | None = None,
    favorites_only: bool = False,
) -> list[tuple[str, PreferenceItem]]:
    allowed_categories = set(category_ids or [])
    eligible: list[tuple[str, PreferenceItem]] = []
    for category_id, item in iter_items(profile):
        if allowed_categories and category_id not in allowed_categories:
            continue
        if context not in item.context:
            continue
        if item.fantasyInterest == FantasyInterest.NONE:
            continue
        if favorites_only and item.fantasyInterest != FantasyInterest.FAVORITE:
            continue
        if item.textRoleplayWillingness == TextRoleplayWillingness.NO:
            continue
        if intensity and item.intensityPreference != intensity:
            continue
        eligible.append((category_id, item))
    return eligible


def build_preference_snapshot(
    profile: UserPreferenceProfile,
    selected: list[tuple[str, PreferenceItem]],
    include_reality_bridge: bool = False,
) -> PreferenceSnapshot:
    all_items = iter_items(profile)
    selected_ids = {item.id for _, item in selected}
    return PreferenceSnapshot(
        profileId=profile.profileId,
        profileVersion=profile.profileVersion,
        displayName=profile.displayName,
        selectedThemes=[
            {
                "id": item.id,
                "categoryId": category_id,
                "label": item.label,
                "description": item.description,
                "fantasyInterest": item.fantasyInterest.value,
                "textRoleplayWillingness": item.textRoleplayWillingness.value,
                "realWorldWillingness": item.realWorldWillingness.value,
                "fantasyOnly": item.fantasyOnly,
                "intensityPreference": item.intensityPreference.value,
                "giverReceiverRole": item.giverReceiverRole.value,
            }
            for category_id, item in selected
        ],
        excludedThemeIds=[item.id for _, item in all_items if item.id not in selected_ids],
        fantasyOnlyThemeIds=[item.id for _, item in selected if item.fantasyOnly],
        realWorldHardNoThemeIds=[
            item.id for _, item in all_items if item.realWorldWillingness == RealWorldWillingness.HARD_NO
        ],
        globalContext={
            "gender": profile.globalPreferences.gender,
            "orientation": profile.globalPreferences.orientation,
            "relationshipStyle": profile.globalPreferences.relationshipStyle,
            "preferredPOV": profile.globalPreferences.preferredPOV.value,
            "fadeToBlack": profile.globalPreferences.fadeToBlack,
            "consentStyle": profile.globalPreferences.consentStyle.value,
        },
        realityBridgeIncluded=include_reality_bridge,
    )


def _weighted_sample(
    items: list[tuple[str, PreferenceItem]],
    count: int,
    explore_lower_interest: bool = False,
) -> list[tuple[str, PreferenceItem]]:
    pool = list(items)
    selected: list[tuple[str, PreferenceItem]] = []
    while pool and len(selected) < count:
        weights = [
            max(1, 5 - FANTASY_RANK[item.fantasyInterest]) if explore_lower_interest else max(1, FANTASY_RANK[item.fantasyInterest])
            for _, item in pool
        ]
        choice = random.choices(pool, weights=weights, k=1)[0]
        selected.append(choice)
        pool.remove(choice)
    return selected


def _compose_synopsis(theme_labels: list[str], identity_bits: list[str], fade_to_black: bool) -> str:
    """One-paragraph blurb that names the selected themes and key context."""
    if theme_labels:
        if len(theme_labels) == 1:
            theme_phrase = theme_labels[0].lower()
        elif len(theme_labels) == 2:
            theme_phrase = f"{theme_labels[0].lower()} and {theme_labels[1].lower()}"
        else:
            theme_phrase = (
                ", ".join(t.lower() for t in theme_labels[:-1])
                + f", and {theme_labels[-1].lower()}"
            )
        body = f"A consent-aware roleplay premise centered on {theme_phrase}."
    else:
        body = "A consent-aware roleplay premise built from your saved preferences."

    if identity_bits:
        body += " Profile context: " + "; ".join(identity_bits) + "."
    if fade_to_black:
        body += " Explicit beats use fade-to-black."
    body += " Fantasy interest is not real-world consent."
    return body


def _compose_content(
    theme_labels: list[str],
    role_bits: list[str],
    identity_bits: list[str],
    intensity: IntensityPreference | None,
    fade_to_black: bool,
    favorites_only: bool,
    explore_lower_interest: bool,
    overlap_only: bool = False,
) -> str:
    """Multi-paragraph draft body. Editable by the user before they hand it to the GM."""
    paragraphs: list[str] = []

    opener = (
        "This draft sketches a story-forward, non-graphic premise the GM can "
        "expand into a full campaign. Treat the themes below as the texture of "
        "the scene, not as actions to perform — fantasy interest is fictional "
        "roleplay data, never real-world consent."
    )
    paragraphs.append(opener)

    if theme_labels:
        bullets = "\n".join(f"- {label}" for label in theme_labels)
        paragraphs.append("Selected themes:\n" + bullets)
    else:
        paragraphs.append(
            "No themes were selected, so the GM should default to slow-burn "
            "tension, clear boundaries, and collaborative worldbuilding."
        )

    framing_bits: list[str] = []
    if intensity is not None:
        framing_bits.append(f"target intensity: {intensity.value}")
    if fade_to_black:
        framing_bits.append("fade-to-black for explicit beats")
    if favorites_only:
        framing_bits.append("favorites-only selection")
    elif explore_lower_interest:
        framing_bits.append("exploring lower-interest themes for variety")
    if overlap_only:
        framing_bits.append("overlap-only with stricter boundaries winning")
    if framing_bits:
        paragraphs.append("Framing: " + "; ".join(framing_bits) + ".")

    if identity_bits:
        paragraphs.append("Protagonist context: " + "; ".join(identity_bits) + ".")

    if role_bits:
        paragraphs.append("Role-side hints:\n" + "\n".join(f"- {bit}" for bit in role_bits))

    paragraphs.append(
        "Opening beat: begin at a quiet decision point where the protagonist "
        "can choose how to engage. Lean into trust, tension, and negotiated "
        "boundaries as story texture, and end the scene at a deliberate prompt "
        "for the next move."
    )

    return "\n\n".join(paragraphs)


def _compose_title(theme_labels: list[str], overlap_only: bool = False) -> str:
    """Title that reads less like placeholder text than `<theme> Fantasy`."""
    if not theme_labels:
        return "Overlap-Compatible Premise" if overlap_only else "Preference-Guided Premise"
    if overlap_only:
        first = theme_labels[0]
        # Avoid stutters like "Shared shared boundaries" when the label already
        # carries a sharedness word.
        if first.lower().startswith(("shared", "mutual", "overlap")):
            return f"{first[:1].upper()}{first[1:]} Premise"
        return f"Shared {first} Premise"
    if len(theme_labels) == 1:
        return f"A {theme_labels[0]} Premise"
    return f"A Premise of {theme_labels[0]} & {theme_labels[1]}"


def build_random_fantasy(
    profile: UserPreferenceProfile,
    context: ContextType = ContextType.AI,
    selected_count: int = 4,
    sharing_mode: SharingMode = SharingMode.PRIVATE,
    category_ids: list[str] | None = None,
    intensity: IntensityPreference | None = None,
    favorites_only: bool = False,
    explore_lower_interest: bool = False,
    include_reality_bridge: bool = False,
) -> GeneratedFantasy:
    eligible = _eligible_items(
        profile,
        context,
        category_ids=category_ids,
        intensity=intensity,
        favorites_only=favorites_only,
    )
    selected = _weighted_sample(eligible, max(1, min(selected_count, 6)), explore_lower_interest=explore_lower_interest)
    snapshot = build_preference_snapshot(profile, selected, include_reality_bridge=include_reality_bridge)

    labels = [item.label for _, item in selected]
    role_bits = [f"{item.label}: {ROLE_DIRECTION_LABELS[item.giverReceiverRole]}" for _, item in selected]
    if not labels:
        labels = ["slow-burn character tension", "clear boundaries", "collaborative worldbuilding"]

    identity_bits = []
    if profile.globalPreferences.gender:
        identity_bits.append(f"gender: {profile.globalPreferences.gender}")
    if profile.globalPreferences.orientation:
        identity_bits.append(f"orientation: {profile.globalPreferences.orientation}")
    if profile.globalPreferences.relationshipStyle:
        identity_bits.append(f"relationship style: {profile.globalPreferences.relationshipStyle}")

    fade_to_black = profile.globalPreferences.fadeToBlack
    title = _compose_title(labels)
    synopsis = _compose_synopsis(labels, identity_bits, fade_to_black)
    content = _compose_content(
        theme_labels=labels,
        role_bits=role_bits,
        identity_bits=identity_bits,
        intensity=intensity,
        fade_to_black=fade_to_black,
        favorites_only=favorites_only,
        explore_lower_interest=explore_lower_interest,
    )
    seed_prompt = (
        "Create a non-graphic adult roleplay scene concept using only the structured preferences below. "
        "Keep the result conceptual, consent-aware, and story-forward. Fantasy interest is not real-world "
        "consent. Do not include private notes. Selected themes: "
        + "; ".join(labels)
        + "."
    )
    if role_bits:
        seed_prompt += " Role-side preferences: " + "; ".join(role_bits) + "."
    if identity_bits:
        seed_prompt += " Profile context: " + "; ".join(identity_bits) + "."
    if category_ids:
        seed_prompt += " Category focus: " + "; ".join(category_ids) + "."
    if intensity:
        seed_prompt += f" Target intensity: {intensity.value}."
    if favorites_only:
        seed_prompt += " Selection mode: favorites only."
    elif explore_lower_interest:
        seed_prompt += " Selection mode: explore lower-interest compatible themes."
    if include_reality_bridge and profile.realityBridge.enabled:
        seed_prompt += " Reality bridge metadata is stored separately for discussion; keep fictional narration separate."
    if profile.globalPreferences.fadeToBlack:
        seed_prompt += " Use fade-to-black handling for explicit detail."

    campaign_seed = CampaignSeed(
        worldConcept=(
            "A flexible roleplay setup shaped by the selected preference themes: "
            + ", ".join(labels)
            + "."
        ),
        startingScene=(
            "Begin at a quiet decision point where the protagonist can choose how to engage. "
            "Use tension, trust, and boundaries as story texture."
        ),
        protagonistGuidance="Reflect the profile's gender, orientation, POV, and role preferences without assuming actions.",
        lorebook={
            "FantasyBoundary": "Fantasy interest is fictional roleplay data and never real-world consent.",
            "Privacy": "Private comments and unshared notes must not appear in narration or exports.",
            "GenerationControls": "Honor category, intensity, context, and sharing controls from the saved preference snapshot.",
        },
        selectedThemeIds=[item.id for _, item in selected],
    )

    now = now_iso()
    return GeneratedFantasy(
        ownerProfileId=profile.profileId,
        ownerUserId=profile.userId,
        title=title,
        createdAt=now,
        updatedAt=now,
        createdFromProfileVersion=profile.profileVersion,
        preferenceSnapshot=snapshot,
        sharingMode=sharing_mode,
        seedPrompt=seed_prompt,
        synopsis=synopsis,
        content=content,
        campaignSeed=campaign_seed,
    )


def build_overlap_fantasy(
    first: UserPreferenceProfile,
    second: UserPreferenceProfile,
    context: ContextType = ContextType.AI,
    selected_count: int = 4,
) -> GeneratedFantasy:
    comparison = compare_profiles(first, second, context=context)
    match_ids = [match["id"] for match in comparison["matches"][:max(1, min(selected_count, 6))]]
    first_items = {item.id: (category_id, item) for category_id, item in iter_items(first)}
    selected = [first_items[item_id] for item_id in match_ids if item_id in first_items]
    snapshot = build_preference_snapshot(first, selected, include_reality_bridge=False)
    labels = [match["label"] for match in comparison["matches"][:len(selected)]]
    if not labels:
        labels = ["shared boundaries", "collaborative pacing", "mutual comfort"]

    seed_prompt = (
        "Create a non-graphic adult roleplay scene concept from mutually compatible overlap only. "
        "Fantasy interest is not real-world consent. Use the stricter boundary, lowest shared intensity, "
        "and fantasy-only constraints from the comparison. Matched themes: "
        + "; ".join(labels)
        + "."
    )
    # Identity bits and intensity for the overlap blurb pull from the matched
    # entries themselves so we don't leak either profile's solo settings.
    intensity_bits = sorted({m.get("intensity") for m in comparison["matches"][:len(selected)] if m.get("intensity")})
    inferred_intensity: IntensityPreference | None = None
    if intensity_bits:
        try:
            inferred_intensity = IntensityPreference(intensity_bits[0])
        except ValueError:
            inferred_intensity = None
    fade_to_black_overlap = bool(
        first.globalPreferences.fadeToBlack or second.globalPreferences.fadeToBlack
    )
    role_bits = [
        f"{match['label']}: shared role {match.get('sharedRole', 'both')}"
        for match in comparison["matches"][:len(selected)]
    ]
    title = _compose_title(labels, overlap_only=True)
    synopsis = _compose_synopsis(labels, identity_bits=[], fade_to_black=fade_to_black_overlap)
    content = _compose_content(
        theme_labels=labels,
        role_bits=role_bits,
        identity_bits=[],
        intensity=inferred_intensity,
        fade_to_black=fade_to_black_overlap,
        favorites_only=False,
        explore_lower_interest=False,
        overlap_only=True,
    )
    campaign_seed = CampaignSeed(
        worldConcept=(
            "A flexible roleplay setup shaped by mutually compatible overlap themes: "
            + ", ".join(labels)
            + "."
        ),
        startingScene=(
            "Begin with a calm, consent-aware setup where both participants can choose how to proceed. "
            "Keep the scene conceptual, story-forward, and bounded by the shared overlap."
        ),
        protagonistGuidance="Reflect shared compatibility without assuming real-world willingness or private notes.",
        lorebook={
            "FantasyBoundary": "Fantasy interest is fictional roleplay data and never real-world consent.",
            "OverlapOnly": "Use only mutually compatible themes from the comparison; stricter boundaries win.",
            "Privacy": "Private comments and unshared notes must not appear in narration or exports.",
        },
        selectedThemeIds=[item.id for _, item in selected],
    )
    now = now_iso()
    return GeneratedFantasy(
        ownerProfileId=first.profileId,
        ownerUserId=first.userId,
        title=title,
        createdAt=now,
        updatedAt=now,
        createdFromProfileVersion=first.profileVersion,
        preferenceSnapshot=snapshot,
        sharingMode=SharingMode.OVERLAP_ONLY,
        seedPrompt=seed_prompt,
        synopsis=synopsis,
        content=content,
        campaignSeed=campaign_seed,
    )


def redact_fantasy(fantasy: GeneratedFantasy, include_private: bool = False, unlocked_content: str | None = None) -> dict[str, Any]:
    data = deepcopy(fantasy).model_dump(mode="json")
    protected = bool(data.get("passwordProtection", {}).get("enabled"))
    data["protectedContent"] = None
    if protected:
        data["content"] = unlocked_content if unlocked_content is not None else ""
        if unlocked_content is None:
            data["locked"] = True
            data["synopsis"] = ""
            data["seedPrompt"] = ""
            data["campaignSeed"] = CampaignSeed().model_dump(mode="json")
            data["realityBridgeNotes"] = ""
    if not include_private:
        data["realityBridgeNotes"] = ""
        data["preferenceSnapshot"]["globalContext"] = {
            k: v for k, v in data["preferenceSnapshot"].get("globalContext", {}).items()
            if k in {"preferredPOV", "fadeToBlack", "consentStyle"}
        }
    return data


def export_fantasy_for_sharing(
    fantasy: GeneratedFantasy,
    mode: SharingMode,
    unlocked_content: str | None = None,
) -> dict[str, Any]:
    protected = fantasy.passwordProtection.enabled
    protected_content_required = mode in {
        SharingMode.PRIVATE,
        SharingMode.FULL_SCENE,
        SharingMode.FULL_SCENE_WITH_NOTES,
    }
    if protected and protected_content_required and unlocked_content is None:
        raise ValueError("Password is required to export protected fantasy content.")

    selected = fantasy.preferenceSnapshot.selectedThemes
    selected_summary = [
        {
            "id": theme.get("id"),
            "label": theme.get("label"),
            "fantasyInterest": theme.get("fantasyInterest"),
            "textRoleplayWillingness": theme.get("textRoleplayWillingness"),
            "realWorldWillingness": theme.get("realWorldWillingness"),
            "fantasyOnly": theme.get("fantasyOnly"),
            "intensityPreference": theme.get("intensityPreference"),
            "giverReceiverRole": theme.get("giverReceiverRole"),
        }
        for theme in selected
    ]
    content = unlocked_content if protected else fantasy.content

    payload: dict[str, Any] = {
        "exportType": "tavern_tales_fantasy_draft",
        "schemaVersion": fantasy.schemaVersion,
        "exportMode": mode.value,
        "safetyPrinciple": "Fantasy interest is not real-world consent.",
        "passwordProtected": protected,
        "owner": {
            "userId": fantasy.ownerUserId,
            "profileId": fantasy.ownerProfileId,
            "profileVersion": fantasy.createdFromProfileVersion,
        },
        "fantasy": {
            "id": fantasy.id,
            "ownerProfileId": fantasy.ownerProfileId,
            "ownerUserId": fantasy.ownerUserId,
            "title": fantasy.title,
            "createdAt": fantasy.createdAt,
            "createdFromProfileVersion": fantasy.createdFromProfileVersion,
            "sharingMode": fantasy.sharingMode.value,
            "synopsis": fantasy.synopsis,
            "selectedThemes": selected_summary,
        },
    }

    if mode == SharingMode.SUMMARY_ONLY:
        return payload

    if mode == SharingMode.OVERLAP_ONLY:
        payload["fantasy"]["synopsis"] = ""
        payload["fantasy"]["selectedThemes"] = [
            theme for theme in selected_summary
            if theme.get("realWorldWillingness") != RealWorldWillingness.HARD_NO.value
        ]
        return payload

    if mode in {SharingMode.PRIVATE, SharingMode.FULL_SCENE, SharingMode.FULL_SCENE_WITH_NOTES}:
        payload["fantasy"]["content"] = content
        payload["fantasy"]["campaignSeed"] = fantasy.campaignSeed.model_dump(mode="json")

    if mode in {SharingMode.PRIVATE, SharingMode.FULL_SCENE_WITH_NOTES}:
        payload["fantasy"]["realityBridgeNotes"] = fantasy.realityBridgeNotes
        payload["fantasy"]["preferenceSnapshot"] = fantasy.preferenceSnapshot.model_dump(mode="json")

    return payload
