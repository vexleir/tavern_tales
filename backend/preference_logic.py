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
            blocked.append({"id": item_id, "categoryId": cat_id, "label": a.label, "reasons": reasons})
            continue

        matches.append({
            "id": item_id,
            "categoryId": cat_id,
            "label": a.label if share_permission != PartnerSharePermission.OVERLAP_ONLY else "Shared compatible theme",
            "fantasyInterest": lowest_interest,
            "textRoleplayWillingness": min(a.textRoleplayWillingness, b.textRoleplayWillingness, key=lambda x: TEXT_RANK[x]).value,
            "realWorldWillingness": real_world.value,
            "fantasyOnly": fantasy_only,
            "intensityPreference": _lowest_intensity(a.intensityPreference, b.intensityPreference).value,
            "giverReceiverRole": _shared_role(a.giverReceiverRole, b.giverReceiverRole),
            "profileRoles": {
                first.profileId: a.giverReceiverRole.value,
                second.profileId: b.giverReceiverRole.value,
            },
            "partnerSharePermission": share_permission.value,
            "commentsShareable": (
                a.commentsShareable if share_permission == PartnerSharePermission.FULL else ""
            ),
        })

    return {
        "profileIds": [first.profileId, second.profileId],
        "context": context.value,
        "matches": matches,
        "blocked": blocked,
        "realityBridgeExcludedThemeIds": sorted(set(reality_bridge_excluded)),
        "safetyPrinciple": "Fantasy interest is not real-world consent.",
    }


def _eligible_items(profile: UserPreferenceProfile, context: ContextType) -> list[tuple[str, PreferenceItem]]:
    eligible: list[tuple[str, PreferenceItem]] = []
    for category_id, item in iter_items(profile):
        if context not in item.context:
            continue
        if item.fantasyInterest == FantasyInterest.NONE:
            continue
        if item.textRoleplayWillingness == TextRoleplayWillingness.NO:
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


def _weighted_sample(items: list[tuple[str, PreferenceItem]], count: int) -> list[tuple[str, PreferenceItem]]:
    pool = list(items)
    selected: list[tuple[str, PreferenceItem]] = []
    while pool and len(selected) < count:
        weights = [max(1, FANTASY_RANK[item.fantasyInterest]) for _, item in pool]
        choice = random.choices(pool, weights=weights, k=1)[0]
        selected.append(choice)
        pool.remove(choice)
    return selected


def build_random_fantasy(
    profile: UserPreferenceProfile,
    context: ContextType = ContextType.AI,
    selected_count: int = 4,
    sharing_mode: SharingMode = SharingMode.PRIVATE,
) -> GeneratedFantasy:
    eligible = _eligible_items(profile, context)
    selected = _weighted_sample(eligible, max(1, min(selected_count, 6)))
    snapshot = build_preference_snapshot(profile, selected, include_reality_bridge=False)

    labels = [item.label for _, item in selected]
    role_bits = [f"{item.label}: {item.giverReceiverRole.value}" for _, item in selected]
    if not labels:
        labels = ["slow-burn character tension", "clear boundaries", "collaborative worldbuilding"]

    identity_bits = []
    if profile.globalPreferences.gender:
        identity_bits.append(f"gender: {profile.globalPreferences.gender}")
    if profile.globalPreferences.orientation:
        identity_bits.append(f"orientation: {profile.globalPreferences.orientation}")
    if profile.globalPreferences.relationshipStyle:
        identity_bits.append(f"relationship style: {profile.globalPreferences.relationshipStyle}")

    title = "Preference-Guided Fantasy"
    if selected:
        title = f"{selected[0][1].label} Fantasy"

    synopsis = (
        "A non-graphic, story-oriented roleplay premise built from the profile's fantasy and text-roleplay "
        "preferences. It treats real-world willingness as separate discussion data, not consent."
    )
    seed_prompt = (
        "Create a non-graphic adult roleplay scene concept using only the structured preferences below. "
        "Keep the result conceptual, consent-aware, and story-forward. Fantasy interest is not real-world "
        "consent. Do not include private notes. Selected themes: "
        + "; ".join(labels)
        + "."
    )
    if role_bits:
        seed_prompt += " Giver/receiver preferences: " + "; ".join(role_bits) + "."
    if identity_bits:
        seed_prompt += " Profile context: " + "; ".join(identity_bits) + "."
    if profile.globalPreferences.fadeToBlack:
        seed_prompt += " Use fade-to-black handling for explicit detail."

    campaign_seed = CampaignSeed(
        worldConcept="A flexible roleplay setup shaped by the selected preference themes.",
        startingScene=(
            "Begin at a quiet decision point where the protagonist can choose how to engage. "
            "Use tension, trust, and boundaries as story texture."
        ),
        protagonistGuidance="Reflect the profile's gender, orientation, POV, and role preferences without assuming actions.",
        lorebook={
            "FantasyBoundary": "Fantasy interest is fictional roleplay data and never real-world consent.",
            "Privacy": "Private comments and unshared notes must not appear in narration or exports.",
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
        content=synopsis,
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
