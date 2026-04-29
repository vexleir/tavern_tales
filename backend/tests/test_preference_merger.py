"""Multiplayer preference merge rules."""

from __future__ import annotations

from preference_merger import merge_preferences, merge_summary
from preference_schema import (
    ContextType,
    FantasyInterest,
    GlobalPreferences,
    IntensityPreference,
    PartnerSharePermission,
    PreferenceCategory,
    PreferenceItem,
    RealWorldWillingness,
    TextRoleplayWillingness,
    UserPreferenceProfile,
)


def _profile(*items: PreferenceItem) -> UserPreferenceProfile:
    return UserPreferenceProfile(
        profileId="profile_test",
        displayName="Tester",
        categories=[PreferenceCategory(id="cat", label="Category", items=list(items))],
    )


def _item(
    item_id: str,
    *,
    interest: FantasyInterest = FantasyInterest.MEDIUM,
    real_world: RealWorldWillingness = RealWorldWillingness.YES,
    text: TextRoleplayWillingness = TextRoleplayWillingness.YES,
    intensity: IntensityPreference = IntensityPreference.MODERATE,
    contexts: list[ContextType] | None = None,
) -> PreferenceItem:
    return PreferenceItem(
        id=item_id,
        label=item_id.replace("_", " ").title(),
        fantasyInterest=interest,
        realWorldWillingness=real_world,
        textRoleplayWillingness=text,
        intensityPreference=intensity,
        context=contexts or [ContextType.MULTIPLAYER],
    )


def test_single_profile_is_used_when_partner_profile_missing():
    profile = _profile(
        _item("shared_theme", intensity=IntensityPreference.INTENSE),
        _item("hard_no_theme", real_world=RealWorldWillingness.HARD_NO),
        _item("ai_only", contexts=[ContextType.AI]),
    )

    merged = merge_preferences(profile, None)

    assert merged.enabled is True
    assert [theme["id"] for theme in merged.selected_themes] == ["shared_theme"]
    assert merged.selected_themes[0]["intensityPreference"] == "intense"
    assert merged.real_world_hard_no_theme_ids == ["hard_no_theme"]
    assert "ai_only" not in merged.real_world_hard_no_theme_ids


def test_hard_veto_excludes_shared_item():
    host = _profile(_item("theme"))
    guest = _profile(_item("theme", text=TextRoleplayWillingness.NO))

    merged = merge_preferences(host, guest)

    assert merged.selected_themes == []
    assert merged.real_world_hard_no_theme_ids == ["theme"]


def test_intensity_minimum_wins_when_both_share():
    host = _profile(_item("theme", intensity=IntensityPreference.INTENSE))
    guest = _profile(_item("theme", intensity=IntensityPreference.LIGHT))

    merged = merge_preferences(host, guest)

    assert len(merged.selected_themes) == 1
    assert merged.selected_themes[0]["intensityPreference"] == "light"


def test_fantasy_interest_minimum_drops_when_min_is_none():
    host = _profile(_item("theme", interest=FantasyInterest.HIGH))
    guest = _profile(_item("theme", interest=FantasyInterest.NONE))

    merged = merge_preferences(host, guest)
    assert merged.selected_themes == []


def test_soft_caution_keeps_item_but_flags_it():
    host = _profile(_item("theme", real_world=RealWorldWillingness.SOFT_NO))
    guest = _profile(_item("theme"))

    merged = merge_preferences(host, guest)
    assert len(merged.selected_themes) == 1
    assert merged.selected_themes[0]["softCaution"] is True
    assert "softCaution" in merged.safety_principle or "soft" in merged.safety_principle.lower()


def test_overlap_only_drops_item_when_partner_lacks_interest():
    host_item = _item("theme", interest=FantasyInterest.HIGH)
    host_item.partnerSharePermission = PartnerSharePermission.OVERLAP_ONLY
    guest_item = _item("theme", interest=FantasyInterest.NONE)

    merged = merge_preferences(_profile(host_item), _profile(guest_item))
    assert merged.selected_themes == []


def test_fade_to_black_is_union():
    host = _profile(_item("theme"))
    host.globalPreferences = GlobalPreferences(fadeToBlack=False)
    guest = _profile(_item("theme"))
    guest.globalPreferences = GlobalPreferences(fadeToBlack=True)

    merged = merge_preferences(host, guest)
    assert merged.global_context["fadeToBlack"] is True


def test_summary_helper_reports_counts():
    host = _profile(_item("ok_theme"), _item("soft_theme", real_world=RealWorldWillingness.SOFT_NO))
    guest = _profile(_item("ok_theme"), _item("soft_theme"), _item("vetoed", real_world=RealWorldWillingness.HARD_NO))

    merged = merge_preferences(host, guest)
    summary = merge_summary(merged)
    assert summary["enabled"] is True
    assert summary["selected_count"] == 2
    assert summary["soft_caution_count"] == 1
    assert summary["hard_no_count"] == 1


def test_both_profiles_none_returns_disabled_context():
    merged = merge_preferences(None, None)
    assert merged.enabled is False
    assert merged.selected_themes == []
