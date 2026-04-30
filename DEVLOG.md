# Tavern Tales Reborn — v2 Developer Log

This file is the coordination hub for v2 implementation. **Every developer working on this project must update this file** when they complete a story or discover something that affects another story's implementation. Read the relevant sections before starting any story.

Reference: [TavernTalesv2.md](TavernTalesv2.md) for the full implementation plan.

---

## How to Use This Log

- **Before starting a story:** Read the "Cross-Story Notes" section and the relevant epic section below.
- **After completing a story:** Add an entry under "Completed Work" with date, story ID, what changed, and any gotchas.
- **If you discover something that affects another story:** Add it to "Cross-Story Notes" immediately.

---

## Cross-Story Notes

*Critical information that affects multiple stories. Read this before touching any file.*

### App.jsx State & Structure
- `App.jsx` is large (~1,100 lines). The main state variables live in `AppInner()` (line 34+). Do not add more top-level state than necessary — prefer deriving values from existing state.
- `campaignState` is the full `CampaignState` JSON from the backend. Access nested fields defensively (e.g., `campaignState?.player?.stats`).
- The `pushStatePatch` function (line 391) is the correct way to make Director Mode edits — it handles optimistic update + 409 conflict + undo stack. Use it for any new editable field.
- `useNdjsonStream` hook owns the streaming lifecycle. Do not add a second streaming mechanism.
- React 19 hook linting rejects synchronous `setState` inside effects. Prefer lazy initial state or async/event callbacks. This affected the first-run Help implementation.

### Schema Changes (v2 additions)
All new schema fields have defaults. When a field is added to `backend/schema.py`, existing state files on disk will deserialize without error because Pydantic v2 uses the default. **Never remove a default or change a field type** — that would break existing campaigns.

Fields added so far by v2 work:
- *(none yet — update this list as you add fields)*

### Backend Test Mocking
`backend/tests/conftest.py` mocks:
- ChromaDB client (`mock_chroma_client` fixture)
- Ollama HTTP calls via `httpx_mock` or `respx`
- State directories via `tmp_path`

When adding new tests, import these fixtures. Do not call real Ollama or real ChromaDB in tests.

### Multiplayer WebSocket Protocol
The WS protocol is: first message after `onopen` must be `join` or `reconnect`. Server responds with `slot_assigned`. All subsequent messages are typed with a `type` field. When adding new WS message types, add them to both the backend handler (`main.py` WS endpoint) and the frontend hook (`useMultiplayerSession.js`). Document them in the "New WebSocket Message Types" table in `TavernTalesv2.md`.

### CORS & LAN Access
The CORS config in `main.py` allows localhost and RFC1918 addresses. If adding new endpoints that guests (on LAN) need to reach, no CORS change is required. Internet tunnel access requires `TT_EXTRA_CORS_ORIGINS` env var — do not hardcode tunnel hostnames.

### Rate Limiting
All routes that trigger LLM generation must have `dependencies=[Depends(chat_rate_limit)]`. New generation routes added in Epic 3 (kickoff, reroll, continue via WS) run inside the WS handler and are not subject to the HTTP rate limiter — the turn lock in `session_manager` serves as the equivalent gate.

### Preference Profile API Naming
The implemented endpoint family is `/api/preference-profiles`. Some v2 plan text references `/api/preferences/profiles`; treat that as a plan typo unless an intentional API rename is scheduled.

### Roll Result Persistence
`ActionResolution` is emitted in the HTTP/SSE `start` event and is not persisted on `Message`. Current inline roll UI can display the latest streamed turn, but historical roll badges will disappear after reload. If future work needs durable per-turn roll display, add a backward-compatible schema field or side-effect record.

### Quick Start Auto-Forge
`CampaignCreator.handleGenerateWorld()` returns generated JSON in addition to updating state. `handleStart()` uses that returned object directly when Quick Start auto-forges, because waiting for React state updates would create a race and could save a blank world.

### Utility Model Auto Mode
`utilityModel === ''` is now intentional auto mode in CampaignCreator. Do not "fix" it by preselecting a specific utility model unless the backend model resolver behavior changes.

### Multiplayer Player Action Display
Story 3.2 derives `player_action` from the persisted prompt-formatted user message in `/api/session/{room_code}/export`. This preserves prompt history while giving the UI raw-looking action text. A future message schema field would be cleaner, but is not required for v2.

### Multiplayer Opening Kickoff Lifecycle
Story 3.1 adds runtime-only `kickoff_needed` and `kickoff_in_progress` flags to `SessionRuntime`. These flags gate the transition after both players ready up and prevent player actions from racing the opening scene. The durable source of truth is an assistant `Message` with `is_kickoff=True`; recovery or restart work should check persisted messages, not only runtime flags. The plan referenced `prompt_builder.build_kickoff_prompt()`, but the implementation uses `prompt_builder.build_prompt()` with a multiplayer-specific synthetic prompt because no kickoff-specific helper exists yet.

### Multiplayer Character Sheets
Story 3.3 reads character sheet data directly from `multiplayer.host_character` and `multiplayer.guest_character` in the existing `session_state` payload. After background extraction finishes for a multiplayer turn, `_background_after_multiplayer_turn()` now rebroadcasts session state so both clients see updated stats/location/inventory without refreshing. Story 3.4 extended this same panel with own-character edit mode; future character-sheet work should keep building there rather than adding a separate editor.

### Multiplayer Character Editing
Story 3.4 uses the WebSocket `update_character` message for play-view edits. The handler updates the sender's assigned slot and ignores any `slot` field in the payload, so guests cannot target the host through the play UI. The HTTP `POST /api/session/{room_code}/character` route was also extended for stats/inventory compatibility, but it still trusts the body `slot`; add explicit slot/auth enforcement before using that route for privileged guest-facing edits.

### Multiplayer Reconnect Window
Story 3.5 removes the frontend's fixed retry cap and uses the server reconnect window as the effective limit. Because an already-disconnected WebSocket cannot receive a final error, the backend sends `code: "session_expired"` when a reconnect attempt arrives after the paused window has elapsed. The still-connected client relies on `session_state.paused_since` and `reconnect_window_seconds` for the countdown.

### Multiplayer OOC Log
Story 3.6 persists OOC chat to `backend/sessions/{room_code}_ooc.jsonl`. The server sends the latest 100 entries as `slot_assigned.ooc_log`, and the frontend hydrates its local OOC list with a reducer action named `ooc_hydrate` capped to 50 messages. There is no standalone `ooc_hydrate` WebSocket event. `delete_session()` removes the OOC log; `archive_session()` leaves it on disk.

### Multiplayer Turn Controls
Story 3.7 made `starting_slot_this_round` player-selectable in the lobby. `set_ready()` now honors that value when the session leaves LOBBY. Gift Turn uses `begin_next_round()`, so it increments `turn_number` even though no AI response is generated. `SessionRuntime.public_state()` now exposes `kickoff_needed` to let the frontend hide turn controls while the opening scene is queued but not yet streaming.

### Multiplayer Reroll/Continue
Story 3.8 uses `session_manager.begin_aux_generation()` / `finish_aux_generation()` for rewrite/continuation streams. These temporarily set status to `GENERATING`, then restore the previous `HOST_TURN` or `GUEST_TURN`. Reroll rewrites the target turn and restores the same floor; Continue appends to the existing assistant message. The frontend currently confirms reroll with `window.confirm()` until multiplayer has access to the shared modal provider.

### Multiplayer Join UX
Story 3.9 adds `GET /api/session/{room_code}/exists` for unauthenticated room validation. It only returns `exists` and `status`; keep it metadata-light. The join form's validation and countdown effects schedule state updates through timers because React 19 lint rejects synchronous `setState` in effect bodies.

---

## Completed Work

### Epic 1 — Single-Player UX Polish

#### 2026-04-30 — Story 1.1: Input & Control Relabeling
- Completed tasks: 1.1.1, 1.1.2, 1.1.3.
- Changed `Commit` to `Send`, `Fork Timeline` to `Branch Story`, updated the branch title, and added the Director Mode subtitle in both enter and exit states.
- Also updated HelpModal references so in-app docs match the new labels.

#### 2026-04-30 — Story 1.2: Director Mode Discoverability & Prompt Inspector
- Completed tasks: 1.2.1, 1.2.2.
- Moved `Inspect Prompt` into the always-visible play header and kept `Debug Bundle` gated behind Director Mode.
- Verified the Director Mode title describes editing NPCs, stats, and world details.

#### 2026-04-30 — Story 1.3: Token Bar & Roll Result Feedback
- Completed tasks: 1.3.1, 1.3.2, 1.3.3.
- Token usage now shows percent full with raw token counts in the tooltip.
- Added `RollResultBadge` and render the latest risky roll inline between the player action and the GM response.
- Note: roll result display is latest-turn only until `ActionResolution` is persisted per message.

#### 2026-04-30 — Story 1.4: Campaign List Cleanup
- Completed tasks: 1.4.1, 1.4.2.
- Verified `created_at` is returned from `state_manager.list_campaigns`.
- Campaign cards now show `Started Mon DD, YYYY` and keep the raw ID only as hover title text.

#### 2026-04-30 — Story 1.5: Quick Actions Defaults & Improvement
- Completed tasks: 1.5.1, 1.5.2, 1.5.3.
- Quick Actions default to visible unless `tt_quick_actions=false`.
- Placeholder templates now open an inline fill-in form before insertion, dismissible by Escape or outside click.

#### 2026-04-30 — Story 1.6: Narrative Scroll & Textarea Auto-Grow
- Completed tasks: 1.6.1, 1.6.2.
- Textarea auto-grows up to 160px and streaming messages keep the bottom anchor in view.
- Fixed a render-time bug where `isStreaming` was referenced before `useNdjsonStream()` declared it.

#### 2026-04-30 — Story 1.7: Bug Fixes
- Completed tasks: 1.7.1, 1.7.2, 1.7.3, 1.7.4.
- Continue now respects `partial` first and uses a more complete terminal punctuation regex.
- CampaignCreator rejects duplicate stat names with an inline error.
- Director Mode has no stat-name edit/add control; added an unknown-key guard for stat value edits.
- Reroll asks for confirmation before discarding partial responses.

#### 2026-04-30 — Story 1.8: Preference System Surface Improvements
- Completed tasks: 1.8.1, 1.8.2.
- Active Preference Context opens Preference Profiles in an overlay.
- Main menu shows a first-time profile nudge when there are no campaigns and no preference profiles.

### Epic 2 — Onboarding & World Creation

#### 2026-04-30 — Story 2.1: First-Run Experience
- Completed tasks: 2.1.1, 2.1.2, 2.1.3.
- Help opens automatically when `tt_has_launched` is absent.
- HelpModal includes a "Don't show this automatically next time" checkbox.
- Main menu now has a "What is this?" help link next to the `?` button.

#### 2026-04-30 — Story 2.2: Quick Start Mode in World Forge
- Completed tasks: 2.2.1, 2.2.2, 2.2.3.
- CampaignCreator now opens with Quick Start fields only: world concept, character name, and Begin.
- Advanced Setup persists in `sessionStorage` under `tt_advanced_open`.
- Quick Start auto-runs world generation before campaign init when world details are still empty.

#### 2026-04-30 — Story 2.3: World Templates Library
- Completed tasks: 2.3.1, 2.3.2, 2.3.3.
- Added `frontend/src/data/worldTemplates.js` with six templates.
- Template cards appear in Quick Start mode, prefill concept, character name/location, NPCs, and lorebook, and support Clear.

#### 2026-04-30 — Story 2.4: Ollama Health Check & Model Selection Clarity
- Completed tasks: 2.4.1, 2.4.2, 2.4.3.
- Added `GET /api/health`, with tests covering reachable and unreachable Ollama responses.
- CampaignCreator shows a red Ollama banner with pull command and Retry.
- Utility Model defaults to amber-labeled auto mode.

#### 2026-04-30 — Story 2.5: World Generation Re-roll & Pass Turn
- Completed tasks: 2.5.1, 2.5.2.
- Auto-Forge exposes Regenerate after a successful generation.
- Single-player play view now includes Pass Turn, disabled during streaming.

### Epic 3 — Multiplayer Core Fixes

#### 2026-04-30 — Story 3.1: Multiplayer Opening Kickoff Scene
- Completed tasks: 3.1.1, 3.1.2, 3.1.3, 3.1.4, 3.1.5, 3.1.6.
- When both players ready up and no kickoff exists, the session starts a shared opening scene before any player action can be submitted.
- Kickoff streams over the existing multiplayer `generation_start` / `token` / `generation_done` flow with `is_kickoff=true`, then persists a shared assistant message with `is_kickoff=True`.
- Multiplayer play/export now displays kickoff narration as "Opening Scene" and keeps input locked while it is pending or streaming.
- Note for Story 3.10: the kickoff runtime flags are not persisted. If server recovery needs to regenerate an interrupted opening, use persisted `is_kickoff` messages plus session status/turn state to decide what is safe.

#### 2026-04-30 — Story 3.2: Player Actions Visible in Multiplayer Narrative
- Completed tasks: 3.2.1, 3.2.2, 3.2.3, 3.2.4, 3.2.5, 3.2.6.
- Session export now pairs assistant turns with the matching user action by `turn_id`.
- Live `generation_start` events include `player_action`, and `MultiplayerPlay` displays it above the streaming GM response.
- `NarrationBlock` now shows `{actor} said: "{playerAction}"` above GM narration.
- Backward compatibility: export still includes `content` alongside new `gm_content`.

#### 2026-04-30 — Story 3.3: Character Sheet Panel in Multiplayer Play
- Completed tasks: 3.3.1, 3.3.2, 3.3.3, 3.3.4.
- `MultiplayerPlay` now includes a read-only Character Sheets panel for own and partner character data.
- Sheets show name, location, gender, stats, and inventory from the durable `multiplayer` config and collapse on mobile by default.
- Multiplayer post-turn background extraction now sends a fresh `session_state` broadcast after applying state deltas.
- Story 3.4 later reused `CharacterSheetCard` for edit mode and added the stats/inventory backend extension.

#### 2026-04-30 — Story 3.4: Multiplayer Director Mode (Own Character Only)
- Completed tasks: 3.4.1, 3.4.2, 3.4.3, 3.4.4, 3.4.5.
- `update_character()` now accepts full stats and inventory replacement updates, with backend sanitization.
- The WebSocket play path is sender-slot scoped and ignores payload `slot`, preventing guests from editing host character data through the play UI.
- Own character sheets now support inline editing for location, appearance, stats, and inventory.
- Note: stats/inventory saves replace the whole field, not a partial patch.

#### 2026-04-30 — Story 3.5: WebSocket Reconnect Hardening
- Completed tasks: 3.5.1, 3.5.2, 3.5.3, 3.5.4, 3.5.5, 3.5.6.
- Frontend reconnects indefinitely with capped exponential delay until unmount or terminal server error.
- Backend rejects reconnects after the reconnect window expires with `code: "session_expired"`.
- Multiplayer play shows both a reconnect attempt banner and a paused countdown from `paused_since + reconnect_window_seconds`.
- Note: expiry is enforced on reconnect, not during the original disconnect event, because the original socket is already closed.

#### 2026-04-30 — Story 3.6: OOC Message Persistence
- Completed tasks: 3.6.1, 3.6.2, 3.6.3, 3.6.4, 3.6.5, 3.6.6, 3.6.7.
- Added JSONL-backed OOC persistence through `session_manager.append_ooc()` and `session_manager.read_ooc_log()`.
- WebSocket `ooc_message` broadcasts now include `ts`, then append the same message to the room log.
- `slot_assigned` now carries `ooc_log` so join/reconnect hydrates recent OOC history.
- The frontend caps hydrated and live OOC display to the latest 50 messages.
- Note: OOC chat remains separate from campaign messages and transcripts unless a future story intentionally folds it in.

#### 2026-04-30 — Story 3.7: Turn Order Controls & Pass Turn
- Completed tasks: 3.7.1, 3.7.2, 3.7.3, 3.7.4, 3.7.5, 3.7.6.
- Host can choose Host or Guest as first actor from the lobby; this persists through `starting_slot_this_round`.
- Ready-up now advances to the configured first actor rather than always host.
- Players can Pass Turn, which submits `I wait and observe this turn.` as a normal action and generates a GM response.
- Host can Gift Turn during `HOST_TURN`, advancing to the guest without generation.
- Note: Gift Turn increments `turn_number` because it reuses `begin_next_round()`.

#### 2026-04-30 — Story 3.8: Reroll & Continue in Multiplayer
- Completed tasks: 3.8.1, 3.8.2, 3.8.3, 3.8.4, 3.8.5.
- Added WebSocket `request_reroll` and `request_continue`.
- Reroll rolls back/removes the target turn group, streams a replacement, persists a new turn group, and restores the same active floor.
- Continue appends streamed text to the existing assistant message and restores the same active floor.
- Multiplayer live-state handling now tracks generation mode and target message IDs so the UI can replace or append the latest block.
- Note: the frontend uses `window.confirm()` for reroll until multiplayer gets the shared modal provider.

#### 2026-04-30 — Story 3.9: Multiplayer UX Polish
- Completed tasks: 3.9.1, 3.9.2, 3.9.3, 3.9.4, 3.9.5, 3.9.6, 3.9.7.
- Added play-view confirmation prompts for Archive and Delete.
- Party labels now use character/display names instead of raw slot keys.
- Lobby character fields auto-save on blur with a debounced save and temporary `✓ Saved` badge.
- Added a 3-second start countdown after lobby ready-up.
- Added `GET /api/session/{room_code}/exists` and join-form room validation.
- Join form now confirms before leaving with a configured quick/imported preference profile.

### Epic 4 — Multiplayer New Features

*(Entries added below as stories complete)*

### Epic 5 — Narrative & Discovery Features

*(Entries added below as stories complete)*

### Epic 6 — Infrastructure & Stability

#### 2026-04-30 — Story 6.1: Rate Limit UX
- Completed tasks: 6.1 (rate_limit.py).
- Added `Retry-After` header computed from actual bucket state.
- HTTP 429 response now includes a descriptive message with seconds to wait.

#### 2026-04-30 — Story 6.2: Memory Store Isolation
- Completed tasks: 6.2 (main.py).
- Wrapped `memory.retrieve_relevant_memories()` in try/except; degraded-mode fallback returns `[]`.
- If retrieval fails, the `start` event includes `memory_warning: true`; frontend shows an amber banner.
- Wrapped `memory.add_memory()` similarly — failures log a warning and do not abort the turn.

#### 2026-04-30 — Story 6.3: Ollama Stream Drop Recovery
- Completed tasks: 6.3 (main.py).
- Catching `Exception` during the streaming token loop; emits `type: error` with `partial: True` flag.
- Frontend `onError` handler checks `evt?.partial` and shows a banner suggesting Continue or Reroll.
- `useNdjsonStream.js` updated to pass the full event object as second arg to `onError`.

#### 2026-04-30 — Story 6.4: GENERATING State Recovery on Restart
- Completed tasks: 6.4 (session_manager.py).
- `session_manager.initialize()` now detects sessions whose durable state is `GENERATING`.
- Derives the correct next turn slot from `starting_slot_this_round` and sets `paused_status_before` accordingly, so reconnects resume to the right player rather than staying stuck in GENERATING.

#### 2026-04-30 — Story 6.5: Session Expiry Cleanup Loop
- Completed tasks: 6.5 (main.py).
- Added `_session_cleanup_loop()` background task in `_startup()` (runs every 30 minutes).
- Calls `session_manager.cleanup_expired_sessions()` and logs how many were archived.

#### 2026-04-30 — Story 6.6: Summarizer Cadence Config
- Completed tasks: 6.6.1 (schema.py), 6.6.2 (summarizer.py), 6.6.3 (main.py), 6.6.4 (CampaignCreator.jsx).
- Added `summary_short_interval` and `summary_chapter_interval` to `RulesConfig` with sane defaults (5 / 20).
- `summarizer.maybe_summarize()` reads from `state.rules` instead of module-level constants.
- `InitCampaignRequest` exposes both fields; `init_campaign()` passes them to `RulesConfig`.
- `CampaignCreator` adds a summarizer cadence selector (3/5/10/20/Never), computing chapter interval as 4× short.

#### 2026-04-30 — Story 6.7: Preference System Enhancements
- Completed tasks: 6.7.1 (main.py), 6.7.2 (PreferenceProfiles.jsx), 6.7.3 (MultiplayerSession.jsx).
- `GET /api/preference-profiles` now builds a reverse-lookup from campaign states and appends `linked_campaigns: [campaignId, ...]` to each profile summary. Bug fixed: used `p.id` instead of `p.profileId` (AttributeError caused 500; fixed to `p.profileId`).
- Profile cards in `PreferenceProfiles.jsx` show "Used in N campaign(s)" when `linked_campaigns` is non-empty.
- `QuickPreferenceForm` in `MultiplayerSession.jsx` gains a "Save as Profile…" button (shown after Apply). Inline name input → `POST /api/preference-profiles/import` → "✓ Saved!" confirmation with error feedback.

#### 2026-04-30 — Story 3.10 & 3.11 (Completed this session)
- Story 3.10: `convert_to_solo` route added (`POST /api/campaigns/{id}/convert_to_solo`). Campaign list shows "Continue Solo" badge when `has_archived_multiplayer` is true.
- Story 3.11: `tt_last_room` localStorage key saved on `slot_assigned`; menu checks `/api/session/{code}/exists` and shows rejoin card if still active. `CampaignSummary` gains `has_archived_multiplayer` field populated by `list_campaigns()`.
- Bug fix: synchronous `setLastRoomCard(null)` in `App.jsx` effect wrapped in `window.setTimeout(..., 0)` to satisfy React 19 lint rule.

### Epic 7 — Accessibility & Mobile

#### 2026-04-30 — Story 7.1: Keyboard Navigation & Focus Management
- Completed tasks: 7.1.1, 7.1.2, 7.1.3.
- Added global `button:focus-visible` rule in `index.css` (`ring-2 ring-amber-600/60`) so all buttons get keyboard focus rings without touching each one individually.
- `ModalProvider.jsx` now implements a full focus trap: on open, saves `document.activeElement` and focuses the first focusable element; on Tab/Shift+Tab, cycles within the modal; on Escape, cancels/confirms; on close, restores prior focus. Added `role="dialog"` and `aria-modal="true"`.
- Added `useEffect` in `App.jsx` (AppInner) that listens for Escape and closes the inspector or sidebar, whichever is open.

#### 2026-04-30 — Story 7.2: Screen Reader & Color Accessibility
- Completed tasks: 7.2.1, 7.2.2, 7.2.3, 7.2.4.
- Previously: `aria-live="polite"` on narrative list; progressbar ARIA attributes on token bar.
- 7.2.2: Added `<span className="sr-only">{connected ? 'connected' : 'disconnected'}</span>` after each status dot in `RosterPanel` (`MultiplayerPlay.jsx`). Also added `aria-hidden="true"` to the visual dot.
- 7.2.4: Added `aria-label` to all icon-only buttons: the `?` help button (both menu and play header), rename (✎), delete (✗), remove inventory (×), remove lore (×), close prompt inspector (✗), and dismiss rejoin card (×). Rename/delete labels include the campaign name for uniqueness.

#### 2026-04-30 — Story 7.3: Mobile-Optimized Layout
- Completed tasks: 7.3.1, 7.3.2, 7.3.3, 7.3.4.
- 7.3.1: Single-player sidebar changes from `fixed inset-y-0 left-0` (left drawer) to `fixed inset-x-0 bottom-0 rounded-t-2xl max-h-[80vh]` on mobile. On md+ it stays as the persistent left panel.
- 7.3.2: Added floating action button (`fixed bottom-24 right-4 z-20 rounded-full w-12 h-12`) in `AppInner`; removed the old "State" text button from the mobile play header.
- 7.3.3: `MultiplayerPlay` sidebar changed from `grid lg:grid-cols-[3fr_1fr]` (always two columns) to a single column on mobile with a tab bar (Party | OOC Chat) that shows/hides panels. On lg+ the sidebar always shows all panels.
- 7.3.4: Input area container in single-player play now has `sticky bottom-0 z-10` so it stays anchored to the viewport bottom as the narrative scrolls.

---

## Known Issues & Deferred Items

*(Add anything discovered during implementation that cannot be fixed in the current story)*

---

## Test Results

| Date | Epic | Test Command | Result |
|------|------|-------------|--------|
| 2026-04-30 | Epic 1 / Story 2.1 / partial 7.2 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 1 / Story 2.1 / partial 7.2 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 1 / Story 2.1 / partial 7.2 | `.\check.ps1` | Pass: 108 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 2 | `python -m pytest tests/test_chat_flow.py` | Pass: 22 tests |
| 2026-04-30 | Epic 2 | `.\check.ps1` | Pass: 110 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.2 | `python -m pytest tests/test_multiplayer_api.py` | Pass: 3 tests |
| 2026-04-30 | Epic 3 Story 3.2 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.2 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 2 + Epic 3 Story 3.2 | `.\check.ps1` | Pass: 110 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.1 | `python -m pytest tests/test_session_manager.py tests/test_multiplayer_api.py` | Pass: 11 tests |
| 2026-04-30 | Epic 3 Story 3.1 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.1 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.1 | `.\check.ps1` | Pass: 112 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.3 | `python -m pytest tests/test_multiplayer_api.py tests/test_multiplayer_state_delta.py` | Pass: 8 tests |
| 2026-04-30 | Epic 3 Story 3.3 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.3 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.3 | `.\check.ps1` | Pass: 112 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.4 | `python -m pytest tests/test_multiplayer_api.py tests/test_session_manager.py` | Pass: 12 tests |
| 2026-04-30 | Epic 3 Story 3.4 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.4 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.4 | `.\check.ps1` | Pass: 113 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.5 | `python -m pytest tests/test_multiplayer_api.py tests/test_session_manager.py` | Pass: 13 tests |
| 2026-04-30 | Epic 3 Story 3.5 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.5 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.5 | `.\check.ps1` | Pass: 114 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.6 | `python -m pytest tests/test_session_manager.py tests/test_multiplayer_api.py` | Pass: 14 tests |
| 2026-04-30 | Epic 3 Story 3.6 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.6 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.6 | `.\check.ps1` | Pass: 115 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.7 | `python -m pytest tests/test_session_manager.py tests/test_multiplayer_api.py` | Pass: 17 tests |
| 2026-04-30 | Epic 3 Story 3.7 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.7 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.7 | `.\check.ps1` | Pass: 118 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.8 | `python -m pytest tests/test_multiplayer_api.py tests/test_session_manager.py` | Pass: 19 tests |
| 2026-04-30 | Epic 3 Story 3.8 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.8 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.8 | `.\check.ps1` | Pass: 120 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 3 Story 3.9 | `python -m pytest tests/test_multiplayer_api.py tests/test_session_manager.py` | Pass: 20 tests |
| 2026-04-30 | Epic 3 Story 3.9 | `npm run lint` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.9 | `npm run build` (frontend) | Pass |
| 2026-04-30 | Epic 3 Story 3.9 | `.\check.ps1` | Pass: 121 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epics 3 (3.10/3.11) + 6 (6.1–6.7) | `.\check.ps1` | Pass: 121 backend tests, frontend lint, frontend build |
| 2026-04-30 | Epic 7 (7.1, 7.2.2, 7.2.4, 7.3) | `.\check.ps1` | Pass: 121 backend tests, frontend lint, frontend build |
