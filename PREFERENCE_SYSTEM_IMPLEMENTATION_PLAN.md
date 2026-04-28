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

### Phase 7 - Preference UX Polish And Hardening

Goal: make the completed local-first system clearer, safer, and easier to test manually.

Tasks:

- [x] Clarify stored giver/receiver/both wording throughout profile editing, onboarding, generation, and comparison with explicit initiate/direct vs follow/yield labels.
- [x] Add per-item direction selection to regular Profile Onboarding.
- [x] Remove ambiguous checklist language where the profile's desired side of a theme could be misread.
- [ ] Add manual test notes for profile creation, onboarding, generation, comparison, export/import, and campaign handoff.
- [ ] Review responsive layout density for the profile editor and generator side panel.
- [ ] Add profile/fantasy tag filtering polish if needed.
- [ ] Add import/export key-backup warnings or recovery affordances if needed.

Suggested files:

- `frontend/src/PreferenceProfiles.jsx`
- `backend/preference_defaults.py`
- `backend/preference_logic.py`
- `backend/tests/test_preferences.py`

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

- [x] Add onboarding completion state handling in UI.
- [x] Create step-based questionnaire: identity/context, global prefs, core categories, sharing defaults, reality bridge.
- [x] Let users skip categories and return later.
- [x] Save progress safely.
- [x] Mark `onboardingCompletedAt` after completion.
- [x] Keep advanced editor available from main profile page.
- [x] Add tests for onboarding persistence where feasible.

Suggested files:

- `frontend/src/PreferenceProfiles.jsx`
- Potential new component: `frontend/src/preferences/PreferenceOnboarding.jsx`

### Phase 3 - Generation Controls

Goal: give users better control over random/preference-aware fantasy generation.

Tasks:

- [x] Add controls for selected categories.
- [x] Add controls for intensity target.
- [x] Add controls for context: AI, partner, multiplayer.
- [x] Add option to bias toward favorites or explore lower-interest themes.
- [x] Add option to include/exclude reality bridge notes from generation metadata, still not from fictional content unless explicitly requested.
- [x] Add "regenerate draft" and "duplicate draft" actions.
- [x] Add fantasy draft import/export.

Suggested files:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Phase 4 - Sharing, Export, And Print

Goal: implement privacy-respecting sharing and output flows.

Tasks:

- [x] Implement fantasy export modes: private, summary only, overlap only, full scene, full scene with notes.
- [x] Ensure password-protected fantasies require unlock before any protected export.
- [x] Ensure private comments are omitted unless user explicitly exports private data.
- [x] Add printable fantasy view.
- [x] Add printable profile comparison summary.
- [x] Add tests for each export mode.
- [x] Add UI language that clearly distinguishes fictional sharing from real-world consent.

Suggested files:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`
- Potential new component: `frontend/src/preferences/FantasyExportPanel.jsx`

### Phase 5 - Better Two-Person Mode

Goal: move from basic comparison to a useful partner planning surface.

Tasks:

- [x] Show blocked theme details and reasons.
- [x] Show shareable comments when sharing permission allows.
- [x] Show strictest boundary and lowest intensity explanation.
- [x] Add partner summary view that omits private notes.
- [x] Add overlap-only fantasy draft generation.
- [x] Add reality bridge discussion view that excludes hard-no items.
- [x] Prepare comparison API shape for future remote/account profiles.

Suggested files:

- `backend/preference_logic.py`
- `backend/main.py`
- `frontend/src/PreferenceProfiles.jsx`

### Phase 6 - Future Account / Network Sharing Readiness

Goal: prepare the local model for later sync and remote sharing without implementing accounts yet.

Tasks:

- [x] Confirm stable user/profile identifiers.
- [x] Add explicit owner fields to exported/shareable payloads.
- [x] Add migration/version strategy for profile schema changes.
- [x] Add import conflict handling.
- [x] Consider key strategy for encrypted sync.
- [x] Document local-key limitations and recovery risk.
- [x] Decide whether saved fantasies should be syncable, export-only, or local-only by default.

Suggested files:

- `backend/preference_schema.py`
- `backend/preference_store.py`
- `backend/secure_storage.py`
- New docs under root or `docs/`

---

## Open Product Decisions

- [x] Should soft-deleted profiles be recoverable from the UI? Decision: no recovery UI; require delete confirmation.
- [x] Should saved fantasy drafts remain visible after their source profile is deleted? Decision: yes.
- [x] Should profile comparison support more than two profiles later? Decision: yes, future multi-profile comparison should be supported.
- [x] Should campaign creation allow selecting a profile directly without first creating a saved fantasy draft? Decision: yes.
- [x] Should generated fantasy drafts have tags/categories for filtering? Decision: yes.
- [x] Should local encrypted key export/backup be offered in-app? Decision: yes.
- [x] Should profile import/export include fantasies, or should those remain separate? Decision: keep profile and fantasy import/export separate.

---

## Current Recommended Next Step

Implement the post-plan polish items chosen from product decisions:

1. Direct profile-to-campaign creation without requiring a saved fantasy draft first.
2. Draft tags/category filters for saved fantasy lists.
3. Optional multi-profile comparison groundwork beyond two profiles.

The original six implementation phases are now functionally complete for the local-first version.

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

### 2026-04-28 - Phase 2 Onboarding

- Added first-time profile onboarding UI for incomplete profiles.
- Onboarding steps cover identity/global context, fantasy/text/real-world boundary sampling, sharing defaults, reality bridge, and review.
- Users can save progress, move between steps, finish onboarding, or jump into the advanced editor.
- Finishing onboarding persists `onboardingCompletedAt` and `lastReviewedAt`.
- Added backend/API test coverage that list summaries report `onboardingCompleted` after profile update.
- Phase 2 is functionally complete for the current local-first profile editor.

### 2026-04-28 - Phase 3 Generation Controls

- Added backend generation controls for selected categories, target intensity, context, sharing mode, favorites-only mode, lower-interest exploration, and reality bridge metadata inclusion.
- Generated draft seed prompts now record category focus, target intensity, and selection mode in safe conceptual language.
- Added frontend generator controls in the preference profile sidebar.
- Added draft regenerate and duplicate actions.
- Added saved fantasy draft export/import from the profile UI. Imported drafts are copied into the active profile and are not imported with password protection enabled.
- Added backend tests for controlled generation behavior and API request persistence.
- Phase 3 is functionally complete for local-first controlled generation.

### 2026-04-28 - Phase 4 Sharing And Export Slice

- Recorded product decisions for delete recovery, fantasy visibility after source deletion, future multi-profile comparison, direct profile campaign creation, draft tags/filtering, local key backup, and separate profile/fantasy export.
- Added backend fantasy export endpoint with privacy modes: private, summary only, overlap only, full scene, and full scene with notes.
- Protected drafts now require a password for content-bearing export modes.
- Added export-mode UI for saved fantasy drafts.
- Added print-friendly fantasy view for unlocked drafts.
- Added backend tests for summary, overlap, full scene, full scene with notes, and protected export behavior.
- Added printable profile comparison summary.
- Phase 4 is functionally complete for local-first sharing/export/print workflows.

### 2026-04-28 - Phase 5 Two-Person Mode

- Expanded comparison API results with blocked theme details, per-profile boundary summaries, compatibility notes, profile roles, and shareable comments when both profiles allow full sharing.
- Comparison UI now shows blocked details, strictest real-world boundary, lowest shared intensity, fantasy-only status, least permissive sharing, and shareable partner comments.
- Added overlap-only fantasy draft generation from two compatible profiles.
- Reality bridge exclusions remain explicit and hard-no themes stay out of bridge suggestions.
- Comparison result shape now carries profile ids and per-profile role/boundary data, keeping it ready for future account/network profile sources.
- Phase 5 is functionally complete for local two-profile comparison.

### 2026-04-28 - Phase 6 Account/Network Readiness

- Added explicit owner/export metadata to profile exports and fantasy exports.
- Profile exports now state that fantasies are not included, matching the product decision to keep exports separate.
- Profile import now creates a fresh profile id, appends a configurable suffix, resets versioning, and rewrites custom-question ownership from the old profile id to the new one.
- Added local encryption key backup endpoint and UI button.
- Added `PREFERENCE_SYSTEM_DATA_NOTES.md` documenting identifiers, export boundaries, schema migration strategy, encryption key risks, and future sharing assumptions.
- Added backend tests for key backup, export metadata, and conflict-safe profile import.
- Verified Phase 6 with focused backend preference/prompt tests, frontend lint, and frontend production build.
- Phase 6 is complete for local-first future-readiness.

### 2026-04-28 - Phase 7 Preference UX Polish

- Renamed ambiguous giver/receiver UI language to side-specific wording: initiate/direct, follow/yield, or either role.
- Added per-item side selection to regular Profile Onboarding, not only the advanced editor.
- Updated comparison, print, and generated seed prompt wording so side preference is explicit.
- Refreshed built-in checklist labels/descriptions to reduce ambiguity around who is doing or receiving a theme.
- Updated default category merge behavior so existing profiles receive improved built-in copy while preserving answers and notes.
- Verified with focused backend preference/prompt tests, frontend lint, and frontend production build.

### 2026-04-28 - Phase 7 Role-Side Clarity Follow-Up

- Replaced remaining give/receive wording in user-facing role-side choices with first-person initiate/direct vs follow/yield language.
- Added onboarding/editor help text clarifying that for submission or surrender themes, follow/yield means this profile is the submitting side, while initiate/direct means this profile guides a submitting partner.
- Updated power, control, and sensation default descriptions to define what each role-side choice means for the specific item.
