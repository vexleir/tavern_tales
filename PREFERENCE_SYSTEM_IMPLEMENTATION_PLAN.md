# Tavern Tales Preference System - Living Implementation Plan

**Created:** 2026-04-27  
**Status:** Active living plan  
**Scope:** Persistent multi-profile fantasy, roleplay, partner-sharing, compatibility, saved fantasy, and campaign handoff system for Tavern Tales.

This document tracks what is complete, what remains, and the intended order of work. It should be updated after each implementation slice so the feature stays understandable as it grows.

---

## Product Principles

1. Fantasy interest is never real-world consent.
2. Fantasy, text-roleplay willingness, and real-world willingness remain separate fields and UI concepts.
3. Private notes are never shared, exported, printed, or prompted unless the user explicitly chooses a private-inclusive path.
4. Saved fantasy drafts retain the preference snapshot used at creation time.
5. Profile edits affect future generation, not previously generated drafts.
6. Password-protected fantasies remain inaccessible unless unlocked with the password.
7. Local-first behavior is the current target; future account/network sharing should not require rewriting the model.

---

## Current Implementation Status

Overall status: **roughly 70-75% complete for a local-first version**.

The system is no longer just a standalone profile editor. It now has encrypted persistence, saved fantasy drafts, profile comparison, and a path from saved drafts into campaign setup. The next major gap is live roleplay prompt integration.

---

## Completed Work

### Architecture And Storage

- [x] Reviewed Tavern Tales architecture before implementation.
- [x] Added encrypted-at-rest storage for sensitive preference and fantasy data.
- [x] Added local automatic key handling.
- [x] Added encrypted profile persistence under backend preference storage.
- [x] Added encrypted saved fantasy persistence independent of campaigns.
- [x] Added Windows-friendly encrypted write fallback for local storage environments that deny rename/delete operations.
- [x] Added backend tests for encrypted profile/fantasy behavior.

Primary modules:

- `backend/secure_storage.py`
- `backend/preference_store.py`
- `backend/preference_schema.py`
- `backend/tests/test_preferences.py`

### Multi-Profile Preference System

- [x] Added persistent multi-profile support.
- [x] Added profile create/edit/list flow.
- [x] Added profile deletion as soft delete.
- [x] Added profile import/export.
- [x] Added global profile fields: gender, orientation, relationship style, consent style, POV, role preference, fade-to-black, aftercare.
- [x] Added expanded neutral BDSM-style checklist categories.
- [x] Added custom questions with archive/delete support.
- [x] Added giver/receiver/both field to checklist items and custom questions.
- [x] Removed redundant visible fantasy-only checkbox from the UI.
- [x] Derived `fantasyOnly` from stricter real-world interest values in the editor.

Primary modules:

- `backend/preference_defaults.py`
- `backend/preference_schema.py`
- `backend/preference_store.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Reality Bridge

- [x] Added separate `realityBridge` data layer.
- [x] Added UI fields for bridge enabled, intent, comfort, non-negotiables, conditions, and partner sharing.
- [x] Redacts reality bridge data from normal non-private exports.
- [x] Matching excludes hard-no themes from reality bridge suggestions.

### Random Fantasy Drafts

- [x] Added random fantasy draft generation from profile preferences.
- [x] Added gender, orientation, relationship style, giver/receiver role, fade-to-black, and safety principle into generated seed prompt context.
- [x] Stored profile version and preference snapshot on generated fantasies.
- [x] Saved drafts exist independently of campaigns.
- [x] Drafts can be opened, edited, and saved.
- [x] Drafts can be password protected.
- [x] Protected drafts hide protected content until unlocked.
- [x] Protected draft edits re-encrypt content on save.
- [x] Protected encrypted payload is not returned to the frontend.

Primary modules:

- `backend/preference_logic.py`
- `backend/preference_store.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Compatibility / Two-Person Mode

- [x] Added backend compatibility comparison.
- [x] Enforced stricter boundary wins.
- [x] Kept fantasy interest separate from real-world willingness.
- [x] Blocked non-mutual text-roleplay themes.
- [x] Blocked private share permission from shared matches.
- [x] Added giver/receiver compatibility logic.
- [x] Added UI comparison panel for two local profiles.
- [x] Comparison UI shows matches, blocked count, reality-bridge exclusions, shared intensity, real-world boundary, and giver/receiver role.

Primary modules:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Campaign Handoff

- [x] Added app-level handoff from saved fantasy draft to campaign setup.
- [x] Added "Use Draft in Campaign Setup" action.
- [x] Prefilled setup world prompt, world description, story summary, starting scene, protagonist guidance, and lorebook from draft campaign seed.
- [x] Added consent boundary and saved draft source lore entries during handoff.
- [x] Protected locked drafts cannot be handed off until unlocked.

Primary modules:

- `frontend/src/App.jsx`
- `frontend/src/CampaignCreator.jsx`
- `frontend/src/PreferenceProfiles.jsx`

### Safety And Product Cleanup

- [x] Removed campaign NSFW checkbox.
- [x] Forced legacy campaign NSFW fields false in campaign creation.
- [x] Improved CORS/local API base behavior after profile creation fetch failures.
- [x] Added clearer backend unreachable error text.

---

## Verification Snapshot

Latest successful checks:

```powershell
cd backend
python -m pytest tests/test_preferences.py --tb=short

cd frontend
npm run lint
npm run build
```

Current known caveat:

- Backend/frontend servers are not started by Codex at the user's request. Manual backend restart is needed after backend route/schema changes.
- `TODO` currently appears deleted in git status; this was not part of the preference implementation work and should be handled only if the user asks.

---

## Remaining Phases

### Phase 1 - Live Roleplay Preference Integration

Goal: make preference profiles affect actual Tavern Tales narration after campaign creation.

Tasks:

- [x] Extend campaign state or metadata to store active `preferenceProfileId`, `preferenceProfileVersion`, and/or saved fantasy draft id.
- [x] Store a redacted preference snapshot on campaign creation when launched from a draft.
- [x] Add backend prompt-builder integration for preference guidance every turn.
- [x] Include only safe, conceptual, non-private preference context in prompts.
- [x] Include hard boundaries, fade-to-black, intensity, text-roleplay willingness, and fantasy-only constraints.
- [x] Ensure private notes and protected content never enter live prompts.
- [x] Add tests proving prompt context includes boundaries and excludes private fields.
- [x] Add UI surface showing which profile/draft is active for the campaign.

Suggested files:

- `backend/schema.py`
- `backend/main.py`
- `backend/prompt_builder.py`
- `backend/tests/test_preferences.py`
- `frontend/src/App.jsx`
- `frontend/src/CampaignCreator.jsx`

### Phase 2 - Onboarding Questionnaire

Goal: replace the dense editor-first experience with a guided first-time flow while keeping the advanced editor.

Tasks:

- [ ] Add onboarding completion state handling in UI.
- [ ] Create step-based questionnaire: identity/context, global prefs, core categories, sharing defaults, reality bridge.
- [ ] Let users skip categories and return later.
- [ ] Save progress safely.
- [ ] Mark `onboardingCompletedAt` after completion.
- [ ] Keep advanced editor available from main profile page.
- [ ] Add tests for onboarding persistence where feasible.

Suggested files:

- `frontend/src/PreferenceProfiles.jsx`
- Potential new component: `frontend/src/preferences/PreferenceOnboarding.jsx`

### Phase 3 - Generation Controls

Goal: give users better control over random/preference-aware fantasy generation.

Tasks:

- [ ] Add controls for selected categories.
- [ ] Add controls for intensity target.
- [ ] Add controls for context: AI, partner, multiplayer.
- [ ] Add option to bias toward favorites or explore lower-interest themes.
- [ ] Add option to include/exclude reality bridge notes from generation metadata, still not from fictional content unless explicitly requested.
- [ ] Add "regenerate draft" and "duplicate draft" actions.
- [ ] Add fantasy draft import/export.

Suggested files:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Phase 4 - Sharing, Export, And Print

Goal: implement privacy-respecting sharing and output flows.

Tasks:

- [ ] Implement fantasy export modes: private, summary only, overlap only, full scene, full scene with notes.
- [ ] Ensure password-protected fantasies require unlock before any protected export.
- [ ] Ensure private comments are omitted unless user explicitly exports private data.
- [ ] Add printable fantasy view.
- [ ] Add printable profile comparison summary.
- [ ] Add tests for each export mode.
- [ ] Add UI language that clearly distinguishes fictional sharing from real-world consent.

Suggested files:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`
- Potential new component: `frontend/src/preferences/FantasyExportPanel.jsx`

### Phase 5 - Better Two-Person Mode

Goal: move from basic comparison to a useful partner planning surface.

Tasks:

- [ ] Show blocked theme details and reasons.
- [ ] Show shareable comments when sharing permission allows.
- [ ] Show strictest boundary and lowest intensity explanation.
- [ ] Add partner summary view that omits private notes.
- [ ] Add overlap-only fantasy draft generation.
- [ ] Add reality bridge discussion view that excludes hard-no items.
- [ ] Prepare comparison API shape for future remote/account profiles.

Suggested files:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Phase 6 - Future Account / Network Sharing Readiness

Goal: prepare the local model for later sync and remote sharing without implementing accounts yet.

Tasks:

- [ ] Confirm stable user/profile identifiers.
- [ ] Add explicit owner fields to exported/shareable payloads.
- [ ] Add migration/version strategy for profile schema changes.
- [ ] Add import conflict handling.
- [ ] Consider key strategy for encrypted sync.
- [ ] Document local-key limitations and recovery risk.
- [ ] Decide whether saved fantasies should be syncable, export-only, or local-only by default.

Suggested files:

- `backend/preference_schema.py`
- `backend/preference_store.py`
- `backend/secure_storage.py`
- New docs under root or `docs/`

---

## Open Product Decisions

- [ ] Should soft-deleted profiles be recoverable from the UI?
- [ ] Should saved fantasy drafts remain visible after their source profile is deleted?
- [ ] Should profile comparison support more than two profiles later?
- [ ] Should campaign creation allow selecting a profile directly without first creating a saved fantasy draft?
- [ ] Should generated fantasy drafts have tags/categories for filtering?
- [ ] Should local encrypted key export/backup be offered in-app?
- [ ] Should profile import/export include fantasies, or should those remain separate?

---

## Current Recommended Next Step

Implement **Phase 1 - Live Roleplay Preference Integration**.

Smallest useful slice:

1. Add optional preference snapshot metadata to campaign state.
2. Pass draft/profile snapshot into campaign init when launching from a saved fantasy draft.
3. Add prompt-builder section with safe redacted preference guidance.
4. Test that private comments, protected content, and reality bridge private fields are excluded.
5. Surface active profile/draft context in the play UI.

This will make the preference system part of actual Tavern Tales gameplay instead of only setup and drafting.

---

## Progress Log

### 2026-04-27

- Created this living implementation plan.
- Current completed implementation includes encrypted local multi-profile storage, expanded preference checklist, custom questions, reality bridge, random fantasy drafts, password protection, draft editing, profile deletion, compatibility comparison, and draft-to-campaign setup handoff.
- Latest verification passed:
  - `python -m pytest tests/test_preferences.py --tb=short`
  - `npm run lint`
  - `npm run build`

### 2026-04-27 - Phase 1 Slice

- Added `CampaignPreferenceContext` to persistent campaign state.
- Campaign setup launched from saved fantasy drafts now sends a redacted preference context into `/api/campaign/init`.
- Prompt builder now renders a dedicated `PREFERENCE GUIDANCE (fictional boundaries)` section on every turn for campaigns with preference context.
- Prompt guidance includes safety principle, source profile/draft, selected themes, fantasy-only ids, hard-no ids, safe global context, intensity, text-roleplay willingness, real-world willingness, and giver/receiver role.
- Added tests for prompt rendering and campaign init persistence.
- Added an in-play sidebar surface showing active saved fantasy/profile context and the consent boundary.
- Phase 1 is functionally complete for local saved-fantasy-launched campaigns.
