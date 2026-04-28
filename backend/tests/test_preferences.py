from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def temp_preference_dirs(monkeypatch):
    import preference_store
    import secure_storage

    root = BACKEND_DIR / f"pytest-cache-files-prefs-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    monkeypatch.setattr(preference_store, "PREFERENCES_DIR", root / "preferences")
    monkeypatch.setattr(preference_store, "FANTASIES_DIR", root / "fantasies")
    monkeypatch.setattr(preference_store, "_profile_locks", {})
    monkeypatch.setattr(preference_store, "_fantasy_locks", {})
    monkeypatch.setattr(secure_storage, "SECURE_DIR", root / "secure")
    monkeypatch.setattr(secure_storage, "KEY_FILE", root / "secure" / "local.key")
    return root


def _mark_first_item(profile, *, private_note: str = "private note"):
    from preference_schema import (
        FantasyInterest,
        GiverReceiverRole,
        PartnerSharePermission,
        RealWorldWillingness,
        TextRoleplayWillingness,
    )

    item = profile.categories[0].items[0]
    item.fantasyInterest = FantasyInterest.FAVORITE
    item.textRoleplayWillingness = TextRoleplayWillingness.YES
    item.realWorldWillingness = RealWorldWillingness.HARD_NO
    item.giverReceiverRole = GiverReceiverRole.BOTH
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
    assert loaded.categories[0].items[0].giverReceiverRole == "both"


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


def test_default_profile_has_bdsm_style_checklist_domains(temp_preference_dirs):
    import preference_store

    profile = preference_store.new_profile("Jordan")
    categories = {category.id: category for category in profile.categories}

    for required in {
        "power_dynamics",
        "control_themes",
        "fantasy_elements",
        "social_dynamics",
        "emotional_tone",
        "interaction_style",
    }:
        assert required in categories

    assert "sensation_play" in categories
    assert "symbols_and_gear" in categories
    assert len(categories["power_dynamics"].items) >= 8
    assert "initiates/directs, follows/yields" in categories["power_dynamics"].description
    all_item_ids = {item.id for category in profile.categories for item in category.items}
    assert "power_submission" in all_item_ids
    assert "control_restraint_light" in all_item_ids
    assert "sensation_impact_symbolic" in all_item_ids
    assert "style_safeword_visible" in all_item_ids


@pytest.mark.asyncio
async def test_existing_profiles_receive_new_default_items(temp_preference_dirs):
    import preference_store

    profile = preference_store.new_profile("Legacy")
    profile.categories = profile.categories[:1]
    profile.categories[0].items = profile.categories[0].items[:1]
    profile.categories[0].items[0].label = "Guidance and leadership"
    saved = await preference_store.save_profile(profile, bump_version=False)

    loaded = await preference_store.load_profile(saved.profileId)
    assert loaded is not None
    categories = {category.id: category for category in loaded.categories}
    assert "sensation_play" in categories
    assert any(item.id == "power_submission" for item in categories["power_dynamics"].items)
    assert categories["power_dynamics"].items[0].label == "Dominance, guidance, or leadership"


def test_matching_keeps_fantasy_and_real_world_boundaries_separate(temp_preference_dirs):
    import preference_logic
    import preference_store
    from preference_schema import GiverReceiverRole, PartnerSharePermission, RealWorldWillingness, TextRoleplayWillingness

    first = preference_store.new_profile("First")
    second = preference_store.new_profile("Second")
    a = _mark_first_item(first)
    b = second.categories[0].items[0]
    b.fantasyInterest = a.fantasyInterest
    b.textRoleplayWillingness = TextRoleplayWillingness.YES
    b.realWorldWillingness = RealWorldWillingness.YES
    b.giverReceiverRole = GiverReceiverRole.RECEIVER
    b.partnerSharePermission = PartnerSharePermission.FULL

    result = preference_logic.compare_profiles(first, second)
    assert result["safetyPrinciple"] == "Fantasy interest is not real-world consent."
    assert result["matches"][0]["realWorldWillingness"] == "hard_no"
    assert result["matches"][0]["giverReceiverRole"] == "receiver"
    assert result["matches"][0]["partnerSharePermission"] == "summary"
    assert result["matches"][0]["compatibilityNotes"]
    assert result["matches"][0]["shareableComments"] == []
    assert a.id in result["realityBridgeExcludedThemeIds"]


def test_matching_blocks_same_non_flexible_giver_receiver_roles(temp_preference_dirs):
    import preference_logic
    import preference_store
    from preference_schema import GiverReceiverRole, PartnerSharePermission, RealWorldWillingness, TextRoleplayWillingness

    first = preference_store.new_profile("First")
    second = preference_store.new_profile("Second")
    a = _mark_first_item(first)
    a.giverReceiverRole = GiverReceiverRole.GIVER
    b = second.categories[0].items[0]
    b.fantasyInterest = a.fantasyInterest
    b.textRoleplayWillingness = TextRoleplayWillingness.YES
    b.realWorldWillingness = RealWorldWillingness.DISCUSS_ONLY
    b.giverReceiverRole = GiverReceiverRole.GIVER
    b.partnerSharePermission = PartnerSharePermission.SUMMARY

    result = preference_logic.compare_profiles(first, second)
    assert result["matches"] == []
    assert "giver_receiver_not_complementary" in result["blocked"][0]["reasons"]
    assert result["blocked"][0]["first"]["giverReceiverRole"] == "giver"


def test_random_fantasy_uses_profile_context_and_creates_campaign_seed(temp_preference_dirs):
    import preference_logic
    import preference_store
    from preference_schema import IntensityPreference

    profile = preference_store.new_profile("Morgan")
    profile.globalPreferences.gender = "woman"
    profile.globalPreferences.orientation = "bi"
    item = _mark_first_item(profile)
    item.intensityPreference = IntensityPreference.MODERATE

    fantasy = preference_logic.build_random_fantasy(
        profile,
        category_ids=[profile.categories[0].id],
        intensity=IntensityPreference.MODERATE,
        favorites_only=True,
        include_reality_bridge=True,
    )
    assert fantasy.ownerProfileId == profile.profileId
    assert fantasy.createdFromProfileVersion == profile.profileVersion
    assert "Fantasy interest is not real-world consent" in fantasy.seedPrompt
    assert "gender: woman" in fantasy.seedPrompt
    assert "Role-side preferences" in fantasy.seedPrompt
    assert "open to either role" in fantasy.seedPrompt
    assert "Category focus" in fantasy.seedPrompt
    assert "Target intensity: moderate" in fantasy.seedPrompt
    assert "favorites only" in fantasy.seedPrompt
    assert fantasy.campaignSeed.lorebook["FantasyBoundary"]
    assert fantasy.campaignSeed.lorebook["GenerationControls"]
    assert fantasy.preferenceSnapshot.selectedThemes
    assert fantasy.preferenceSnapshot.selectedThemes[0]["giverReceiverRole"] == "both"
    assert fantasy.preferenceSnapshot.selectedThemes[0]["intensityPreference"] == "moderate"
    assert fantasy.preferenceSnapshot.realityBridgeIncluded is True


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
    assert exported["exportType"] == "tavern_tales_preference_profile"
    assert exported["owner"]["profileId"] == profile_id
    assert exported["fantasiesIncluded"] is False
    assert exported["exportIncludesPrivate"] is False
    assert exported["profile"]["realityBridge"]["enabled"] is False

    key_backup = c.get("/api/preferences/key-backup")
    assert key_backup.status_code == 200
    assert key_backup.json()["backupType"] == "tavern_tales_local_encryption_key"
    assert key_backup.json()["key"]

    # Save once with an eligible item so random generation has profile data.
    created["categories"][0]["items"][0]["fantasyInterest"] = "favorite"
    created["categories"][0]["items"][0]["textRoleplayWillingness"] = "yes"
    created["categories"][0]["items"][0]["giverReceiverRole"] = "giver"
    created["categories"][0]["items"][0]["intensityPreference"] = "moderate"
    r = c.put(f"/api/preference-profiles/{profile_id}", json=created)
    assert r.status_code == 200
    saved_profile = r.json()
    saved_profile["onboardingCompletedAt"] = "2026-04-28T00:00:00+00:00"
    saved_profile["lastReviewedAt"] = "2026-04-28T00:00:00+00:00"
    r = c.put(f"/api/preference-profiles/{profile_id}", json=saved_profile)
    assert r.status_code == 200
    assert r.json()["onboardingCompletedAt"] == "2026-04-28T00:00:00+00:00"
    assert next(summary for summary in c.get("/api/preference-profiles").json() if summary["profileId"] == profile_id)["onboardingCompleted"] is True

    random_fantasy = c.post(
        f"/api/preference-profiles/{profile_id}/random-fantasy",
        json={
            "save": True,
            "categoryIds": [created["categories"][0]["id"]],
            "intensity": "moderate",
            "favoritesOnly": True,
            "includeRealityBridge": True,
        },
    ).json()
    assert random_fantasy["ownerProfileId"] == profile_id
    assert random_fantasy["campaignSeed"]["selectedThemeIds"]
    assert random_fantasy["preferenceSnapshot"]["selectedThemes"][0]["giverReceiverRole"] == "giver"
    assert random_fantasy["preferenceSnapshot"]["realityBridgeIncluded"] is True
    assert "Target intensity: moderate" in random_fantasy["seedPrompt"]

    second = c.post("/api/preference-profiles", json={"displayName": "Taylor Partner"}).json()
    second["categories"][0]["items"][0]["fantasyInterest"] = "favorite"
    second["categories"][0]["items"][0]["textRoleplayWillingness"] = "yes"
    second["categories"][0]["items"][0]["giverReceiverRole"] = "receiver"
    second["categories"][0]["items"][0]["partnerSharePermission"] = "summary"
    r = c.put(f"/api/preference-profiles/{second['profileId']}", json=second)
    assert r.status_code == 200
    overlap = c.post(
        "/api/compatibility/overlap-fantasy",
        json={
            "firstProfileId": profile_id,
            "secondProfileId": second["profileId"],
            "selectedCount": 3,
            "save": True,
        },
    )
    assert overlap.status_code == 200
    assert overlap.json()["sharingMode"] == "overlap_only"
    assert "mutually compatible overlap" in overlap.json()["seedPrompt"]

    random_fantasy["title"] = "Edited preference draft"
    random_fantasy["content"] = "edited draft body"
    updated = c.put(f"/api/fantasies/{random_fantasy['id']}", json={"fantasy": random_fantasy}).json()
    assert updated["title"] == "Edited preference draft"
    assert updated["content"] == "edited draft body"

    protected = c.post(
        f"/api/fantasies/{random_fantasy['id']}/protect",
        json={"password": "correct horse battery staple", "hint": "long phrase"},
    ).json()
    assert protected["passwordProtection"]["enabled"] is True
    assert protected["content"] == ""
    assert protected["synopsis"] == ""

    summary_export = c.post(
        f"/api/fantasies/{random_fantasy['id']}/export",
        json={"mode": "summary_only"},
    )
    assert summary_export.status_code == 200
    assert "content" not in summary_export.json()["fantasy"]

    full_export_locked = c.post(
        f"/api/fantasies/{random_fantasy['id']}/export",
        json={"mode": "full_scene"},
    )
    assert full_export_locked.status_code == 400

    full_export = c.post(
        f"/api/fantasies/{random_fantasy['id']}/export",
        json={"mode": "full_scene", "password": "correct horse battery staple"},
    )
    assert full_export.status_code == 200
    assert full_export.json()["exportType"] == "tavern_tales_fantasy_draft"
    assert full_export.json()["owner"]["profileId"] == profile_id
    assert full_export.json()["fantasy"]["content"] == "edited draft body"
    assert "realityBridgeNotes" not in full_export.json()["fantasy"]

    notes_export = c.post(
        f"/api/fantasies/{random_fantasy['id']}/export",
        json={"mode": "full_scene_with_notes", "password": "correct horse battery staple"},
    )
    assert notes_export.status_code == 200
    assert "preferenceSnapshot" in notes_export.json()["fantasy"]

    overlap_export = c.post(
        f"/api/fantasies/{random_fantasy['id']}/export",
        json={"mode": "overlap_only"},
    )
    assert overlap_export.status_code == 200
    assert "content" not in overlap_export.json()["fantasy"]

    unlocked = c.post(
        f"/api/fantasies/{random_fantasy['id']}/unlock",
        json={"password": "correct horse battery staple"},
    ).json()
    unlocked["content"] = "edited protected draft body"
    saved_locked = c.put(
        f"/api/fantasies/{random_fantasy['id']}",
        json={"fantasy": unlocked, "password": "correct horse battery staple"},
    ).json()
    assert saved_locked["content"] == ""
    assert saved_locked["locked"] is True
    unlocked_again = c.post(
        f"/api/fantasies/{random_fantasy['id']}/unlock",
        json={"password": "correct horse battery staple"},
    ).json()
    assert unlocked_again["content"] == "edited protected draft body"

    listed = c.get(f"/api/fantasies?profile_id={profile_id}").json()
    assert any(fantasy["id"] == random_fantasy["id"] for fantasy in listed)
    assert any(fantasy["sharingMode"] == "overlap_only" for fantasy in listed)

    deleted = c.delete(f"/api/preference-profiles/{profile_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "success"
    assert c.get(f"/api/preference-profiles/{profile_id}").status_code == 404
    assert all(summary["profileId"] != profile_id for summary in c.get("/api/preference-profiles").json())


def test_profile_import_creates_conflict_safe_identity(temp_preference_dirs):
    import main

    c = TestClient(main.app)
    created = c.post("/api/preference-profiles", json={"displayName": "Import Source"}).json()
    created["customPreferences"].append({
        "createdBy": created["profileId"],
        "label": "Reusable question",
        "description": "",
        "responseType": "text",
        "options": [],
        "response": "",
        "fantasyInterest": "none",
        "realWorldWillingness": "hard_no",
        "textRoleplayWillingness": "no",
        "fantasyOnly": True,
        "context": ["ai"],
        "partnerSharePermission": "private",
        "commentsPrivate": "",
        "commentsShareable": "",
        "status": "active",
    })
    imported = c.post(
        "/api/preference-profiles/import",
        json={"profile": created, "displayNameSuffix": "(Copy)"},
    ).json()
    assert imported["profileId"] != created["profileId"]
    assert imported["displayName"].endswith("(Copy)")
    assert imported["customPreferences"][0]["createdBy"] == imported["profileId"]


def test_local_dev_cors_allows_vite_alternate_port():
    import main

    c = TestClient(main.app)
    r = c.options(
        "/api/preference-profiles",
        headers={
            "Origin": "http://127.0.0.1:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:5174"


def test_campaign_init_persists_preference_context(temp_preference_dirs, monkeypatch):
    import main
    import state_manager

    state_root = BACKEND_DIR / f"pytest-cache-files-state-{uuid4().hex}"
    state_root.mkdir(parents=True, exist_ok=False)
    monkeypatch.setattr(state_manager, "STATES_DIR", state_root / "states")
    monkeypatch.setattr(state_manager, "LEGACY_FILE", state_root / "campaign_states.json")
    monkeypatch.setattr(state_manager, "_migration_checked", False)
    monkeypatch.setattr(state_manager, "_locks", {})
    monkeypatch.setattr(state_manager, "_turn_locks", {})
    (state_root / "states").mkdir(parents=True, exist_ok=True)

    c = TestClient(main.app)
    payload = {
        "campaign_id": "campaign_pref_context",
        "player_name": "Traveler",
        "starting_location": "The Ember & Ash Tavern",
        "stats": {"Health": 100},
        "preference_context": {
            "enabled": True,
            "source": "saved_fantasy",
            "profile_id": "profile_abc",
            "profile_version": 4,
            "draft_id": "fantasy_123",
            "selected_themes": [{"id": "tone_trust", "label": "Trust", "commentsPrivate": "omit me"}],
            "global_context": {"gender": "woman", "privateSecret": "omit me"},
        },
    }
    r = c.post("/api/campaign/init", json=payload)
    assert r.status_code == 200
    state = c.get("/api/state/campaign_pref_context").json()
    assert state["preference_context"]["enabled"] is True
    assert state["preference_context"]["profile_id"] == "profile_abc"
    assert state["preference_context"]["selected_themes"][0]["label"] == "Trust"
