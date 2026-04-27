from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_preference_dirs(tmp_path, monkeypatch):
    import preference_store
    import secure_storage

    monkeypatch.setattr(preference_store, "PREFERENCES_DIR", tmp_path / "preferences")
    monkeypatch.setattr(preference_store, "FANTASIES_DIR", tmp_path / "fantasies")
    monkeypatch.setattr(preference_store, "_profile_locks", {})
    monkeypatch.setattr(preference_store, "_fantasy_locks", {})
    monkeypatch.setattr(secure_storage, "SECURE_DIR", tmp_path / "secure")
    monkeypatch.setattr(secure_storage, "KEY_FILE", tmp_path / "secure" / "local.key")
    return tmp_path


def _mark_first_item(profile, *, private_note: str = "private note"):
    from preference_schema import (
        FantasyInterest,
        PartnerSharePermission,
        RealWorldWillingness,
        TextRoleplayWillingness,
    )

    item = profile.categories[0].items[0]
    item.fantasyInterest = FantasyInterest.FAVORITE
    item.textRoleplayWillingness = TextRoleplayWillingness.YES
    item.realWorldWillingness = RealWorldWillingness.HARD_NO
    item.partnerSharePermission = PartnerSharePermission.SUMMARY
    item.commentsPrivate = private_note
    item.commentsShareable = "shareable note"
    return item


@pytest.mark.asyncio
async def test_preference_profiles_are_encrypted_at_rest(temp_preference_dirs):
    import preference_store

    profile = preference_store.new_profile("Alex")
    _mark_first_item(profile, private_note="keep this private")
    saved = await preference_store.save_profile(profile, bump_version=False)

    path = preference_store.PREFERENCES_DIR / f"{saved.profileId}.json"
    raw = path.read_text(encoding="utf-8")
    assert json.loads(raw)["encrypted"] is True
    assert "Alex" not in raw
    assert "keep this private" not in raw

    loaded = await preference_store.load_profile(saved.profileId)
    assert loaded is not None
    assert loaded.displayName == "Alex"
    assert loaded.categories[0].items[0].commentsPrivate == "keep this private"


def test_redaction_omits_private_notes_and_reality_bridge(temp_preference_dirs):
    import preference_logic
    import preference_store

    profile = preference_store.new_profile("Casey")
    _mark_first_item(profile, private_note="do not export")
    profile.realityBridge.enabled = True
    profile.realityBridge.conditions = ["private condition"]

    redacted = preference_logic.redact_profile(profile, include_private=False)
    item = redacted["categories"][0]["items"][0]
    assert item["commentsPrivate"] == ""
    assert redacted["realityBridge"]["enabled"] is False
    assert redacted["realityBridge"]["conditions"] == []


def test_matching_keeps_fantasy_and_real_world_boundaries_separate(temp_preference_dirs):
    import preference_logic
    import preference_store
    from preference_schema import PartnerSharePermission, RealWorldWillingness, TextRoleplayWillingness

    first = preference_store.new_profile("First")
    second = preference_store.new_profile("Second")
    a = _mark_first_item(first)
    b = second.categories[0].items[0]
    b.fantasyInterest = a.fantasyInterest
    b.textRoleplayWillingness = TextRoleplayWillingness.YES
    b.realWorldWillingness = RealWorldWillingness.YES
    b.partnerSharePermission = PartnerSharePermission.FULL

    result = preference_logic.compare_profiles(first, second)
    assert result["safetyPrinciple"] == "Fantasy interest is not real-world consent."
    assert result["matches"][0]["realWorldWillingness"] == "hard_no"
    assert result["matches"][0]["partnerSharePermission"] == "summary"
    assert a.id in result["realityBridgeExcludedThemeIds"]


def test_random_fantasy_uses_profile_context_and_creates_campaign_seed(temp_preference_dirs):
    import preference_logic
    import preference_store

    profile = preference_store.new_profile("Morgan")
    profile.globalPreferences.gender = "woman"
    profile.globalPreferences.orientation = "bi"
    _mark_first_item(profile)

    fantasy = preference_logic.build_random_fantasy(profile)
    assert fantasy.ownerProfileId == profile.profileId
    assert fantasy.createdFromProfileVersion == profile.profileVersion
    assert "Fantasy interest is not real-world consent" in fantasy.seedPrompt
    assert "gender: woman" in fantasy.seedPrompt
    assert fantasy.campaignSeed.lorebook["FantasyBoundary"]
    assert fantasy.preferenceSnapshot.selectedThemes


@pytest.mark.asyncio
async def test_password_protected_fantasy_hides_and_unlocks_content(temp_preference_dirs):
    import preference_logic
    import preference_store

    profile = preference_store.new_profile("Riley")
    _mark_first_item(profile)
    fantasy = preference_logic.build_random_fantasy(profile)
    fantasy.content = "private fantasy body"
    saved = await preference_store.save_fantasy(fantasy)

    protected = await preference_store.protect_fantasy(saved.id, "correct horse battery staple", hint="long phrase")
    assert protected is not None
    assert protected.content == ""
    assert protected.passwordProtection.enabled is True

    listed = await preference_store.list_fantasies(profile.profileId)
    assert listed[0].passwordProtected is True

    loaded = await preference_store.load_fantasy(saved.id)
    assert loaded is not None
    assert preference_store.unlock_fantasy_content(loaded, "correct horse battery staple") == "private fantasy body"
    assert preference_logic.redact_fantasy(loaded)["content"] == ""


def test_preference_api_create_export_and_random_fantasy(temp_preference_dirs):
    import main

    c = TestClient(main.app)
    created = c.post("/api/preference-profiles", json={"displayName": "Taylor"}).json()
    profile_id = created["profileId"]

    assert created["displayName"] == "Taylor"
    assert created["categories"]

    exported = c.get(f"/api/preference-profiles/{profile_id}/export").json()
    assert exported["exportIncludesPrivate"] is False
    assert exported["profile"]["realityBridge"]["enabled"] is False

    # Save once with an eligible item so random generation has profile data.
    created["categories"][0]["items"][0]["fantasyInterest"] = "favorite"
    created["categories"][0]["items"][0]["textRoleplayWillingness"] = "yes"
    r = c.put(f"/api/preference-profiles/{profile_id}", json=created)
    assert r.status_code == 200

    random_fantasy = c.post(f"/api/preference-profiles/{profile_id}/random-fantasy", json={"save": True}).json()
    assert random_fantasy["ownerProfileId"] == profile_id
    assert random_fantasy["campaignSeed"]["selectedThemeIds"]

    listed = c.get(f"/api/fantasies?profile_id={profile_id}").json()
    assert listed[0]["id"] == random_fantasy["id"]
