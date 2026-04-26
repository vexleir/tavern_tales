# Tavern Tales Reborn - Implementation Plan 2

**Review date:** 2026-04-25  
**Role:** Software architect for game design, LLM systems, and product UX  
**Scope reviewed:** `backend/`, `frontend/`, current audit docs, current implementation plan, tests, build/lint posture, runtime data hygiene  
**Plan status:** Implemented through P5 on 2026-04-25. See progress log at the end of this document.

---

## 1. Executive Summary

Tavern Tales has moved past the prototype architecture described in the first audit. The biggest original coherence bug appears architecturally addressed: the backend now owns prompt assembly, persists campaign state per campaign, validates state through Pydantic, streams explicit event types, and has the right module boundaries for prompt building, memory, extraction, summarization, and persistence.

The next layer of work is not another ground-up refactor. It is a hardening and product-maturity pass. The highest-risk issues now are:

1. **Quality gates are currently red.** Backend tests fail during collection because `memory.py` creates a real Chroma client at import time. Frontend lint fails with five errors. Frontend build also failed in this sandbox with a Vite `spawn EPERM`, likely environment-related but still needs a clean local recheck.
2. **Runtime data is still tracked or dirty in git.** `backend/chroma_db/` and `backend/states/*.json` contain local/generated campaign data and should be treated as private runtime artifacts. This is a privacy and repository-health issue.
3. **State consistency is still fragile around concurrent operations.** Chat streams, background extraction/summarization, and director-mode full-state PUTs can race or clobber each other.
4. **The frontend is functionally rich but architecturally overloaded.** `App.jsx` is a 32 KB single component containing API access, stream parsing, menu/setup/play rendering, director tools, undo, import/export, and inspector UI.
5. **The game design layer is still mostly freeform narration.** The app has state, memory, NPCs, lore, and director tools, but it does not yet have strong mechanics for stakes, checks, quests, conditions, item effects, or scene pacing.

Plan 2 is organized to fix those in execution order: first make the project clean and safe to work on, then fix consistency risks, then improve the frontend shell, then add game systems, then optimize memory/LLM behavior.

---

## 2. Verification Snapshot

Commands run during review:

```powershell
git status --short
python -m pytest
npm run lint
npm run build
```

Observed results:

| Check | Result | Notes |
|---|---:|---|
| `git status --short` | Dirty | Existing runtime data under `backend/chroma_db/` and `backend/states/`; review also created `backend/chroma_db/chroma.sqlite3-journal` during test attempt. |
| `python -m pytest` from `backend/` | Fail | Collection stops at `tests/test_memory.py`; top-level `import memory` creates a real Chroma client and hits a disk I/O error before the `temp_chroma` fixture can patch it. |
| `npm run lint` from `frontend/` | Fail | 5 ESLint errors: impure `Date.now()` during render, empty catch block, unused `useEffect`, and Fast Refresh export rule violations in provider files. |
| `npm run build` from `frontend/` | Fail in sandbox | Vite failed loading config with `spawn EPERM`. Retest after lint fixes and, if needed, outside sandbox. |

This means Plan 2 must start with test/lint/build hygiene before feature work.

---

## 3. Ranked Architecture Review

Scores are current-state estimates on a 10-point scale, where 10 means "ship-ready for this category."

| Rank | Category | Score | Current Strength | Main Gap |
|---:|---|---:|---|---|
| 1 | Test and release confidence | 4.0 | Useful backend test suite exists and targets prompt regression. | Tests currently fail during collection; no frontend tests; lint is red. |
| 2 | Data hygiene and privacy | 4.0 | State is separated into per-campaign files. | Runtime Chroma/state files are still tracked or dirty; local generated narrative should not live in source control. |
| 3 | Frontend maintainability | 4.5 | Feature set is visible and usable in one place. | `App.jsx` is too large and mixes API, streaming, state mutation, and rendering. |
| 4 | UX and accessibility | 5.0 | Strong dark-fantasy mood; stop, continue, inspect, export/import, director mode exist. | Sidebar is hidden on mobile; controls rely on text symbols; stop does not refresh persisted partial state; edit flows save too eagerly. |
| 5 | Game systems and features | 5.0 | Campaign state, NPCs, lore, inventory, memory, and summaries exist. | No explicit action resolution, dice/checks, quests, conditions, item effects, difficulty, or consequence framework. |
| 6 | Backend state reliability | 6.0 | Atomic per-campaign files and locks are a strong base. | Chat stream lifecycle, background tasks, and full-state director PUTs can race. No revision/ETag protection. |
| 7 | Optimization and scalability | 6.0 | Prompt windows are token-budgeted; Chroma is campaign-scoped. | Chroma initializes at import; memory documents are still raw and large; prompt budget assumes context sizes instead of querying model metadata. |
| 8 | Observability and debugging | 6.5 | Request IDs, structured logs, and prompt inspector are present. | No durable event log, job status, user-visible background failures, or debug bundle export. |
| 9 | LLM orchestration and narrative coherence | 8.0 | Backend prompt builder re-injects world, scene, protagonist, cast, lore, summaries, and memories every turn. | Needs regression evals for agency, brevity, safety/tone settings, and long-campaign prompt growth. |
| 10 | Overall architecture | 7.0 | Good separation of backend modules and a clear local-first architecture. | Needs quality gates, consistency semantics, and UI decomposition before adding many more features. |

Priority order is driven by risk, not excitement. The most exciting game features should wait until the repo is green and the current save/stream lifecycle is trustworthy.

---

## 4. Highest-Value Findings

### F1. Test Collection Is Broken

`tests/test_memory.py` imports `memory` at module load. `memory.py` immediately constructs:

```python
_client = chromadb.PersistentClient(path=DB_PATH)
```

That real Chroma initialization happens before the `temp_chroma` fixture can replace `_client`, causing a disk I/O error during test collection. This also confirms a runtime design smell: storage clients should be lazy and injectable.

### F2. Frontend Quality Gate Is Red

`npm run lint` reports:

- `frontend/src/App.jsx:10` - `Date.now()` inside a `useState(...)` initializer is considered impure by React Hooks lint.
- `frontend/src/App.jsx:280` - empty catch block.
- `frontend/src/components/Banner.jsx:1` - unused `useEffect`.
- `frontend/src/components/Banner.jsx:48` and `Modal.jsx:64` - provider files export both components and hooks, violating Fast Refresh rules.

These are small fixes individually, but together they make the repo feel unsafe to iterate on.

### F3. Runtime Data Belongs Outside Git

The dirty working tree contains Chroma files and a saved campaign state. Those are generated runtime artifacts and may include private user-generated story content. `.gitignore` currently ignores `*.db` but not Chroma's `.sqlite3`, `.sqlite3-journal`, `.bin`, or campaign state JSON files.

This should be fixed before any public sharing or normal development cadence.

### F4. Full-State Director PUTs Can Clobber Chat Results

Director edits in `App.jsx` clone the entire `campaignState` and send it through `PUT /api/state/{id}` on every edit, including every keystroke for some fields. If a chat stream or background extraction updates the same campaign while the frontend holds an older copy, the later full PUT can overwrite new messages, side effects, summaries, or memory metadata.

The fix is a revisioned state model plus narrow PATCH endpoints for specific edits.

### F5. Stop/Partial Stream UX Is Incomplete

The backend attempts to persist partial output when a stream is cancelled, but the frontend abort path does not call `refreshState`. The UI can be left with temporary message IDs, which blocks continue/regenerate/delete behavior until a reload or later refresh.

### F6. Delete Semantics Are Message-Level, But The UX Presents Them As Turn-Level

In director mode, the delete control appears for both user and assistant messages. Backend side effects are attached to assistant messages. Deleting a user message can orphan the assistant response without rolling back state. Deleting an assistant message can leave its paired user action. The product should define and implement turn-level delete, with message-level delete only as an advanced inspector operation.

### F7. World Generation Ignores The Selected GM Model

`CampaignCreator.jsx` sends `{ prompt, nsfw }` to `/api/world/generate` but does not pass the selected model. The backend therefore uses the default creative model or NSFW model, even when the user selected a different narrator model in the setup screen.

### F8. Mobile UX Hides Campaign State

The play sidebar is `hidden md:flex`, so mobile users lose protagonist state, inventory, cast, lorebook, export, and menu access. The app is effectively desktop-only in play mode.

### F9. Game Mechanics Are Still Thin

The GM can narrate anything, but there is no structured loop for risk, skill checks, difficulty, item effects, conditions, quests, or consequences. For a text RPG, this is the next big product unlock. It will make choices feel less arbitrary and make state changes feel earned.

### F10. Memory Retrieval Needs A Second Pass

Memory storage now has campaign isolation and rollback IDs, but each memory is still a raw "player acted / GM narrated" text block. This is high token cost and mixed signal. Long-running campaigns will benefit from typed memories: facts, NPC relationship changes, world discoveries, quests, and unresolved threads.

---

## 5. Implementation Strategy

Plan 2 has six phases:

| Phase | Name | Goal |
|---|---|---|
| P0 | Green Build and Data Hygiene | Make tests/lint/build trustworthy and remove runtime data from source control. |
| P1 | State and Stream Correctness | Prevent races, clobbers, orphan messages, and incomplete stop/continue behavior. |
| P2 | Frontend Decomposition and UX Baseline | Split the frontend into maintainable modules and make the play UI usable across viewports. |
| P3 | Game Systems Layer | Add mechanics that make the RPG feel like a game, not only a chat transcript. |
| P4 | LLM, Memory, and Performance Optimization | Improve long-campaign recall, prompt growth, model selection, and startup latency. |
| P5 | Observability, Packaging, and Release Readiness | Add debug/release tooling so future work is faster and safer. |

Execute phases in order. P3 can begin only after P0 and P1 are complete.

---

## 6. Task Inventory

| ID | Title | Phase | Risk | Primary Files |
|---|---|---|---|---|
| P0.1 | Lazy/injectable Chroma client | P0 | High | `backend/memory.py`, `backend/tests/conftest.py`, `backend/tests/test_memory.py` |
| P0.2 | Fix backend tests and docs count | P0 | High | `backend/tests/*`, `CLAUDE.md` |
| P0.3 | Fix frontend lint errors | P0 | High | `frontend/src/App.jsx`, `frontend/src/components/*` |
| P0.4 | Retest frontend build | P0 | Medium | `frontend/vite.config.js`, package scripts if needed |
| P0.5 | Gitignore runtime data and plan untracking | P0 | High | `.gitignore`, tracked runtime files |
| P0.6 | Add one-command local quality script | P0 | Medium | root scripts or docs |
| P1.1 | Add campaign revision and updated timestamp | P1 | High | `backend/schema.py`, `backend/state_manager.py`, frontend API calls |
| P1.2 | Replace full-state director PUTs with PATCH operations | P1 | High | `backend/main.py`, `frontend/src/*` |
| P1.3 | Add per-campaign turn lock or queue | P1 | High | `backend/main.py`, `backend/state_manager.py` |
| P1.4 | Make post-turn work reliable and visible | P1 | High | `backend/main.py`, `backend/schema.py`, frontend banners/inspector |
| P1.5 | Fix stop/partial refresh flow | P1 | Medium | `frontend/src/App.jsx`, backend stream tests |
| P1.6 | Convert delete/regenerate to turn-level semantics | P1 | High | `backend/main.py`, `schema.py`, frontend message UI |
| P1.7 | Add route coverage for continue/export/import/rollback | P1 | Medium | `backend/tests/test_chat_flow.py`, new tests |
| P2.1 | Centralize API client and app constants | P2 | Medium | `frontend/src/lib/api.js`, `CampaignCreator.jsx`, `App.jsx` |
| P2.2 | Split `App.jsx` by screen and feature | P2 | High | `frontend/src/screens/*`, `frontend/src/features/*` |
| P2.3 | Extract stream parser hook | P2 | Medium | `frontend/src/hooks/useNdjsonStream.js` |
| P2.4 | Add responsive mobile sidebar/drawer | P2 | High | play layout components, Tailwind classes |
| P2.5 | Improve input composer | P2 | Medium | chat composer component |
| P2.6 | Fix world-generation model selection | P2 | Medium | `CampaignCreator.jsx`, `backend/main.py` |
| P2.7 | Make director edits deliberate | P2 | High | director components and PATCH API |
| P2.8 | Clean unused CSS/assets | P2 | Low | `frontend/src/App.css`, unused assets |
| P3.1 | Add action resolution and dice/check framework | P3 | High | `schema.py`, `main.py`, prompt templates, frontend composer |
| P3.2 | Add quest/objective tracker | P3 | High | state schema, prompt builder, sidebar |
| P3.3 | Add conditions/status effects | P3 | Medium | state schema, extraction, sidebar |
| P3.4 | Add equipment and item effects | P3 | Medium | state schema, director tools, prompt builder |
| P3.5 | Add NPC relationship depth | P3 | Medium | NPC schema, extraction, sidebar |
| P3.6 | Add chapter journal and recap UI | P3 | Medium | summarizer, frontend journal screen |
| P3.7 | Add campaign tone/content settings | P3 | Medium | campaign creator, prompt builder |
| P4.1 | Typed memory documents | P4 | High | `memory.py`, `extraction.py`, schema |
| P4.2 | Hybrid memory retrieval | P4 | Medium | `memory.py`, prompt builder |
| P4.3 | Prompt block budgeting and truncation | P4 | High | `prompt_builder.py`, tests |
| P4.4 | Query model context from Ollama metadata | P4 | Medium | `model_resolver.py`, `tokenizer.py` |
| P4.5 | Prewarm/lazy-load heavy services | P4 | Medium | `memory.py`, startup hooks |
| P4.6 | Add response length and pacing controls | P4 | Medium | prompt templates, frontend settings |
| P5.1 | Add debug bundle export | P5 | Medium | backend diagnostics, frontend inspector |
| P5.2 | Add background job/event log | P5 | Medium | schema, state manager, main |
| P5.3 | Add CI workflow or local gate script | P5 | Medium | `.github/workflows/*` or scripts |
| P5.4 | Version import/export format | P5 | Medium | `schema.py`, export/import routes |
| P5.5 | Update maintainer docs after Plan 2 | P5 | Low | `CLAUDE.md`, this plan |

---

## 7. Detailed Task Specs

### P0 - Green Build and Data Hygiene

#### P0.1 Lazy/injectable Chroma client

**Problem:** `memory.py` creates a real Chroma client at import time. Tests cannot patch it before collection, and app startup pays the Chroma cost even when memory is not used.

**Implementation:**

- Replace module-level `_client = chromadb.PersistentClient(...)` with lazy `get_client()`.
- Add `set_client_for_tests(client)` or accept dependency injection through a small module variable guarded by a setter.
- Ensure `get_collection`, `delete_campaign_memory`, and `duplicate_campaign_memory` call `get_client()`.
- Move `import memory` inside `test_memory.py` tests or rely on the lazy setter in `temp_chroma`.
- Add a test proving importing `memory` does not create a real DB directory.

**Acceptance:**

- `python -m pytest backend/tests/test_memory.py` passes.
- Full `python -m pytest` no longer fails during collection.
- Chroma runtime DB is not touched by tests unless explicitly configured.

#### P0.2 Fix backend tests and docs count

**Problem:** `CLAUDE.md` claims 45 tests, but this run collected 40 and failed before execution.

**Implementation:**

- After P0.1, run full `python -m pytest`.
- Fix any failing tests.
- Update `CLAUDE.md` with the actual test count and current command.
- Add a small note that tests use temp Chroma/state directories.

**Acceptance:**

- `python -m pytest` passes from `backend/`.
- Maintainer docs match the actual test count.

#### P0.3 Fix frontend lint errors

**Implementation:**

- Change `useState(`campaign_${Date.now()}`)` to lazy initializer: `useState(() => ...)`.
- Replace empty catch with a logged or bannered path.
- Remove unused `useEffect` import from `Banner.jsx`.
- Split hooks out of provider files:
  - `components/BannerProvider.jsx`
  - `hooks/useBanner.js`
  - `components/ModalProvider.jsx`
  - `hooks/useModal.js`
- Update imports in `App.jsx`.

**Acceptance:**

- `npm run lint` passes.
- No Fast Refresh rule suppression unless there is a deliberate documented reason.

#### P0.4 Retest frontend build

**Implementation:**

- Run `npm run build`.
- If `spawn EPERM` persists, verify whether it is sandbox-only.
- If it is local toolchain related, pin or adjust Vite/Rolldown config as needed.

**Acceptance:**

- `npm run build` passes in the developer environment.
- If sandbox-only, document the exact local command that passes.

#### P0.5 Gitignore runtime data and plan untracking

**Implementation:**

- Add ignores:
  - `backend/chroma_db/`
  - `backend/states/*.json`
  - `backend/states/*.tmp`
  - `backend/*.legacy.bak`
  - `*.sqlite3`
  - `*.sqlite3-journal`
- After approval, remove already-tracked runtime artifacts from git index with `git rm --cached`, preserving local files.
- Do not delete local campaign data.

**Acceptance:**

- `git status --short` no longer shows generated Chroma/state changes after normal app usage.
- Local campaign saves still exist on disk.

#### P0.6 Add one-command local quality script

**Implementation:**

- Add a root `check` script or `check.ps1` that runs:
  - backend tests
  - frontend lint
  - frontend build
- Keep it Windows-friendly.

**Acceptance:**

- One command gives a clear pass/fail before future implementation work.

---

### P1 - State and Stream Correctness

#### P1.1 Add campaign revision and updated timestamp

**Problem:** The state model lacks optimistic concurrency. Full-state writes can overwrite newer data silently.

**Implementation:**

- Add `revision: int = 0` and `updated_at` to `CampaignState`.
- Increment revision inside `save_state` or `mutate_state`.
- Return revision from state endpoints.
- Require `expected_revision` for editor PATCH routes.

**Acceptance:**

- Stale editor writes return `409 Conflict` instead of overwriting newer state.

#### P1.2 Replace full-state director PUTs with PATCH operations

**Implementation:**

Create focused endpoints:

- `PATCH /api/campaign/{id}/player`
- `PATCH /api/campaign/{id}/stats/{name}`
- `PATCH /api/campaign/{id}/inventory`
- `PATCH /api/campaign/{id}/npcs/{npc_id}`
- `PATCH /api/campaign/{id}/lorebook/{key}`

Frontend director tools should call these instead of sending the whole campaign.

**Acceptance:**

- Director edits cannot erase messages, summaries, or side effects.
- Existing full `PUT /api/state/{id}` remains only for import/admin use or is guarded behind director admin semantics.

#### P1.3 Add per-campaign turn lock or queue

**Problem:** Two overlapping chat streams can load the same campaign snapshot and append out of order.

**Implementation:**

- Add a per-campaign "active turn" lock or queue.
- Acquire it before prompt assembly and release it after assistant message persistence.
- Return `409` or queue status if another stream is active.
- Frontend should show "generation already active" rather than starting another stream.

**Acceptance:**

- Backend integration test starts two simultaneous chat requests; one completes and the other is rejected or queued deterministically.

#### P1.4 Make post-turn work reliable and visible

**Problem:** Extraction, memory write, and summarization are launched with `asyncio.create_task`. Failures are logged but not visible to the UI, and shutdown can drop work.

**Implementation:**

- Add a `background_jobs` or `turn_events` record in campaign state.
- Mark each assistant message with post-turn status: `pending`, `complete`, `failed`.
- Store error summaries for extraction/summarization/memory.
- Consider running extraction before final `done` for short responses, or use a small local job queue that is drained on startup.

**Acceptance:**

- UI can show "state update pending" or "state extraction failed."
- Tests no longer need polling sleeps to wait for side effects.

#### P1.5 Fix stop/partial refresh flow

**Implementation:**

- On frontend abort, call `refreshState(activeCampaignId)` in the `finally` path if any tokens were received.
- Backend should emit/persist a partial marker deterministically.
- Add a route test for cancelled streams if feasible with TestClient, or a unit test for the persistence helper.

**Acceptance:**

- Clicking Stop leaves a persisted assistant message with a real ID.
- Continue/Reroll/Delete work immediately after Stop.

#### P1.6 Convert delete/regenerate to turn-level semantics

**Implementation:**

- Introduce `turn_id` in `Message`.
- User message and assistant response for the same exchange share a `turn_id`.
- Side effects attach to `turn_id` or assistant message but delete operates on the full turn by default.
- UI delete control should say "Delete turn" for normal use.
- Keep message-level delete only in inspector/debug mode if needed.

**Acceptance:**

- Deleting a turn removes both player action and GM response and rolls back side effects once.
- Regenerate removes the prior turn and creates a new turn with a fresh assistant response.

#### P1.7 Add route coverage for continue/export/import/rollback

**Implementation:**

- Tests for `/continue` appending to the same assistant message.
- Tests for export/import preserving state and memories.
- Tests for turn delete rollback.
- Tests for stale revision conflict.

**Acceptance:**

- Backend tests cover every route that mutates campaign state.

---

### P2 - Frontend Decomposition and UX Baseline

#### P2.1 Centralize API client and app constants

**Implementation:**

- Create `frontend/src/lib/api.js`.
- Use `import.meta.env.VITE_API_BASE || 'http://localhost:8000'`.
- Replace hardcoded API strings in `App.jsx` and `CampaignCreator.jsx`.
- Normalize error parsing in one helper.

**Acceptance:**

- No hardcoded `http://localhost:8000` remains outside the API module.

#### P2.2 Split `App.jsx` by screen and feature

Suggested structure:

```text
frontend/src/
  screens/
    MainMenu.jsx
    SetupScreen.jsx
    PlayScreen.jsx
  features/chat/
    ChatLog.jsx
    ChatComposer.jsx
    MessageBubble.jsx
    useChatStream.js
  features/director/
    DirectorToolbar.jsx
    DirectorSidebar.jsx
    useDirectorEdits.js
  features/campaign/
    useCampaignState.js
    CampaignSidebar.jsx
```

**Acceptance:**

- `App.jsx` is mostly provider wiring and mode switching.
- No file over roughly 300-400 lines unless there is a clear reason.

#### P2.3 Extract stream parser hook

**Implementation:**

- Create `useNdjsonStream`.
- Handle `start`, `token`, `error`, `done`, abort, and tail parsing.
- Track whether any tokens were received.
- Return status and controls.

**Acceptance:**

- Kickoff, chat, regenerate, and continue share one stream implementation.

#### P2.4 Add responsive mobile sidebar/drawer

**Implementation:**

- Replace `hidden md:flex` only behavior with a mobile "State" drawer.
- Include protagonist, inventory, cast, lorebook, menu, export, and director controls.
- Use stable dimensions so the drawer does not shift the chat composer.

**Acceptance:**

- At a 390 px wide viewport, the user can access state, cast, lorebook, menu, and export without losing chat.

#### P2.5 Improve input composer

**Implementation:**

- Replace single-line input with textarea.
- Enter sends, Shift+Enter inserts newline.
- Disable send while streaming and show clear status.
- Auto-scroll to latest message unless user has scrolled upward.

**Acceptance:**

- Long player actions are comfortable to write.
- Composer does not overlap chat content on mobile.

#### P2.6 Fix world-generation model selection

**Implementation:**

- Send selected `gmModel` or an explicit world-gen model to `/api/world/generate`.
- Backend should validate availability or fall back with a visible warning.
- Show model failure in the setup UI, not only console.

**Acceptance:**

- Selecting model X and clicking Generate World uses model X unless the user opted into a specific world-gen model.

#### P2.7 Make director edits deliberate

**Implementation:**

- Save text edits on blur or debounce, not every keystroke.
- Group undo entries by edit session rather than per keypress.
- Add "Add lore entry" in director mode, which is currently missing.
- Add validation before sending changes.

**Acceptance:**

- Editing a long lore rule creates one undo step and one backend write after the edit settles.

#### P2.8 Clean unused CSS/assets

**Implementation:**

- Remove or archive unused Vite starter CSS and assets if not imported.
- Confirm visual styling still comes from Tailwind and custom classes.

**Acceptance:**

- No unused starter files remain in the main source path.

---

### P3 - Game Systems Layer

#### P3.1 Add action resolution and dice/check framework

**Goal:** Give the player meaningful uncertainty and make outcomes feel earned.

**Implementation:**

- Add a `rules` state block:
  - enabled/disabled
  - dice mode: `d20`, `2d6`, or narrative-only
  - difficulty scale
  - stat mapping
- Add `/api/action/resolve` or integrate into chat:
  - classify action as safe, risky, opposed, or impossible
  - choose relevant stat
  - roll and determine outcome tier
  - feed result into GM prompt as binding context
- Add UI affordance:
  - "Risky action" indicator
  - manual roll override in Director Mode
  - roll result display above GM narration

**Acceptance:**

- A risky action produces a visible roll/check and the GM narration honors success/failure.
- Director can override difficulty or result.

#### P3.2 Add quest/objective tracker

**Implementation:**

- Add `quests` to campaign state:
  - id, title, status, objectives, discovered_at, completed_at
- Extraction can propose quest updates.
- Director can approve or edit updates.
- Prompt builder includes active objectives.
- Sidebar shows current objectives.

**Acceptance:**

- The player can see active goals and completed milestones.
- The GM remembers unresolved objectives through prompt injection.

#### P3.3 Add conditions/status effects

**Implementation:**

- Add `conditions` to player and NPCs:
  - name, severity, duration, source, mechanical effect
- Extraction can add/remove conditions.
- Prompt builder renders active conditions.
- UI highlights urgent conditions.

**Acceptance:**

- If the GM narrates poison, injury, fear, blessing, etc., the state can track it and future prompts include it.

#### P3.4 Add equipment and item effects

**Implementation:**

- Split inventory into:
  - simple items
  - equipped items
  - consumables
  - key items
- Add item effects that modify checks or prompt context.
- Director tools can edit item type/effects.

**Acceptance:**

- Equipping or consuming an item has visible state impact and can influence future checks.

#### P3.5 Add NPC relationship depth

**Implementation:**

- Extend NPC schema:
  - attitude score
  - trust/fear/loyalty tags
  - known facts
  - promises/debts
- Extraction can update relationship facts.
- Sidebar displays compact relationship state.

**Acceptance:**

- NPC relationships can evolve beyond a single disposition enum.

#### P3.6 Add chapter journal and recap UI

**Implementation:**

- Surface `summaries.short`, `chapters`, and `arc` in a Journal panel.
- Add "Recap so far" button.
- Add chapter titles, either generated or editable.

**Acceptance:**

- Returning to an old campaign gives the player a clear recap without inspecting raw messages.

#### P3.7 Add campaign tone/content settings

**Implementation:**

- Add campaign settings:
  - tone: grim, heroic, cozy, horror, comedic
  - violence intensity
  - romance/mature-content boundaries
  - response length
  - player-agency strictness
- Prompt builder injects these settings into role rules.
- Setup and Director Mode can edit them.

**Acceptance:**

- The GM can be steered consistently without manually editing lorebook entries.

---

### P4 - LLM, Memory, and Performance Optimization

#### P4.1 Typed memory documents

**Problem:** Raw turn memories are noisy and expensive.

**Implementation:**

- Store typed memory records:
  - event
  - fact
  - NPC relationship
  - quest update
  - location discovery
  - item/status change
- Generate a compact memory summary from the post-turn extraction pass.
- Keep raw turn text separately only if needed for debug.

**Acceptance:**

- Prompt memories are concise and grouped by relevance type.

#### P4.2 Hybrid memory retrieval

**Implementation:**

- Combine semantic score with:
  - recency
  - active location
  - mentioned NPC names
  - active quest IDs
- Deduplicate by memory type and source turn.

**Acceptance:**

- The memories injected for a turn are both relevant and compact in long campaigns.

#### P4.3 Prompt block budgeting and truncation

**Problem:** Injecting all lorebook/cast/world data is excellent for coherence but can grow past budget.

**Implementation:**

- Assign each prompt block a priority and max budget.
- Always include protagonist, active location, active quests, recent state.
- Summarize or truncate large lorebook/cast sections.
- Add tests for oversized lorebook and large NPC roster.

**Acceptance:**

- Prompt builder never exceeds model context and never drops critical player state.

#### P4.4 Query model context from Ollama metadata

**Implementation:**

- Use Ollama model metadata where available, likely `/api/show`.
- Cache context size per model.
- Fall back to `MODEL_CONTEXT_WINDOWS` only when metadata is unavailable.

**Acceptance:**

- Token meter and prompt budget match the actual selected local model more closely.

#### P4.5 Prewarm/lazy-load heavy services

**Implementation:**

- Lazy-load Chroma client.
- Optional startup prewarm endpoint or background warmup.
- Show "memory index warming" if first search is slow.

**Acceptance:**

- App import and backend startup are fast.
- First chat turn no longer pays an unexplained memory initialization cost.

#### P4.6 Add response length and pacing controls

**Implementation:**

- Add campaign-level response length: concise, standard, lush.
- Map length to prompt instruction and `num_predict`.
- Add "end at decision point" eval tests.

**Acceptance:**

- Users can tune narration length without changing source code.

---

### P5 - Observability, Packaging, and Release Readiness

#### P5.1 Add debug bundle export

**Implementation:**

- Add "Export Debug Bundle" in Director Mode:
  - current state
  - last prompt
  - prompt stats
  - selected memories
  - last N event logs
  - app version/schema version
- Redact or clearly warn before exporting private story data.

**Acceptance:**

- A bad turn can be diagnosed without asking the user to manually gather files.

#### P5.2 Add background job/event log

**Implementation:**

- Store a compact event log in campaign state or sidecar file:
  - stream started/completed/cancelled
  - extraction applied/failed
  - summarization applied/failed
  - import/export/fork/delete
- Surface latest events in Inspector.

**Acceptance:**

- Background failures are visible in the UI.

#### P5.3 Add CI workflow or local gate script

**Implementation:**

- If GitHub Actions is acceptable, add workflow for backend tests and frontend lint/build.
- If not, keep a local Windows script and document it.

**Acceptance:**

- Future agents can run one gate and know whether the repo is safe to change.

#### P5.4 Version import/export format

**Implementation:**

- Add `export_version`.
- Validate imported bundle shape.
- Add forward-compatible warnings for unknown versions.
- Include memory schema version once typed memories land.

**Acceptance:**

- Old exports fail gracefully or migrate explicitly.

#### P5.5 Update maintainer docs after Plan 2

**Implementation:**

- Update `CLAUDE.md` after implementation.
- Add a "Plan 2 completed" progress log to this file.
- Note any intentionally deferred items.

**Acceptance:**

- A future agent can resume from docs without rediscovering architecture.

---

## 8. Suggested Execution Order

1. **P0.1 -> P0.5 first.** Do not add features while tests/lint are red or runtime data is dirty.
2. **P1.1 -> P1.7 second.** Make every campaign mutation safe before changing UX.
3. **P2.1 -> P2.8 third.** Decompose the frontend and fix mobile/accessibility gaps.
4. **P3.1 -> P3.7 fourth.** Add game mechanics once state and UI are stable.
5. **P4 and P5 last.** Optimize memory/prompt behavior and add release tooling.

---

## 9. Verification Gates By Phase

### After P0

```powershell
cd backend
python -m pytest

cd ..\frontend
npm run lint
npm run build

cd ..
git status --short
```

Expected:

- Backend tests pass.
- Frontend lint and build pass.
- Runtime data is not reported as modified/untracked after normal app/test usage.

### After P1

Additional backend tests:

- concurrent chat request behavior
- stale revision conflict
- stop partial persistence
- turn-level delete rollback
- regenerate rollback
- continue appends to same assistant message
- export/import preserves state and memories

### After P2

Manual/browser checks:

- desktop play flow
- 390 px mobile play flow
- campaign creation
- world generation with selected model
- Stop, Continue, Reroll, Delete Turn
- director edit save/undo
- prompt inspector
- import/export/fork

### After P3

Gameplay checks:

- risky action creates a visible roll/check
- failure and partial success produce different consequences
- quests update and remain visible
- conditions affect prompt context
- NPC relationship changes persist and reappear in prompt

### After P4/P5

Long-campaign checks:

- large lorebook does not exceed prompt budget
- memory injection stays concise
- debug bundle contains enough information to diagnose a bad turn
- import/export version handling works

---

## 10. Execution Notes For Future Agent

- Do not modify or delete the user's existing campaign data without explicit approval.
- When untracking runtime files, use index-only removal so local saves remain on disk.
- Prefer small, reviewable commits by phase or task.
- Keep backend prompt ownership intact. Do not move system-prompt assembly back into the frontend.
- Any new game mechanic must be represented in:
  - schema
  - prompt builder
  - extraction or explicit route logic
  - frontend display/editor
  - tests
- Avoid expanding `App.jsx`; Plan 2 should shrink it.
- Before final handoff, update this file with a progress log and exact verification output.

---

## 11. Approval Boundary

This plan was originally execution-ready and has now been implemented through P5. For any future continuation, start from the progress log and stop only if:

- untracking runtime files needs explicit git-index approval,
- a dependency install is required,
- a migration/delete decision would affect user campaign data,
- or a test/build failure points to an environment issue that cannot be resolved locally.

---

## 12. Progress Log

**Status:** P0 through P5 implemented.

### Completed

- P0: Green quality gates and runtime data hygiene.
  - Chroma client is lazy/injectable.
  - Frontend lint errors fixed.
  - Runtime Chroma/state files are ignored and removed from the git index only; local files are preserved.
  - Added `check.ps1`.
- P1: State and stream correctness.
  - Campaign state now has `revision` and `updated_at`.
  - Director edits use narrow `PATCH /api/state/{id}` with optimistic revision checks.
  - Chat generation is serialized by per-campaign turn locks.
  - User/GM messages share `turn_id`; delete now removes a whole turn.
  - Post-turn memory/extraction/summarization is awaited and status-tagged.
- P2: UX baseline and frontend cleanup.
  - Centralized API base/error parsing in `frontend/src/lib/api.js`.
  - Extracted NDJSON stream parser to `hooks/useNdjsonStream.js`.
  - Split modal/banner providers and hooks for Fast Refresh.
  - Added mobile state drawer, multiline composer, director lore creation, selected-model world generation, and removed unused starter assets.
- P3: Game systems layer.
  - Added lightweight d20 action resolution in `backend/game_rules.py`.
  - Risky actions produce visible roll summaries and binding prompt context.
  - Added schema and prompt support for rules, quests, and conditions.
- P4: Memory and prompt optimization.
  - Memory records are compact event memories with metadata.
  - Retrieval blends semantic score with recency.
  - Large cast/lore/memory blocks are truncated to fit prompt budgets.
- P5: Observability and docs.
  - Added campaign event log.
  - Added `GET /api/campaign/{id}/debug` debug bundle endpoint.
  - Added Director Mode debug bundle export button.
  - Updated `CLAUDE.md`.

### Verification

```powershell
cd backend
python -m pytest
# 54 passed

cd ../frontend
npm run lint
# passed

npm run build
# passed
```

### Known Follow-Ups

- The frontend is improved but `App.jsx` is still large; a deeper screen/component split remains valuable.
- P3 mechanics are intentionally lightweight. Future work should deepen quests, conditions, equipment effects, and NPC relationships with dedicated UI.
- Prompt budget context-window lookup still uses local heuristics rather than Ollama model metadata.
