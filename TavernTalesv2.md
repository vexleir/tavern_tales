# Tavern Tales Reborn — v2 Implementation Plan

**Document Status:** Draft for Developer Review  
**Based On:** QA/UX Evaluation (playthrough2_notes.md, 2026-04-30)  
**Architecture Snapshot:** FastAPI backend (`backend/`) + React/Vite frontend (`frontend/src/`)  
**Schema Version:** 2 (no migration; all new fields require `Field(default_factory=...)`)

---

## How to Use This Document

This plan is organized into **7 Epics**, each containing **Stories**, each containing **Tasks**. Tasks are atomic enough for a single developer to own without coordination risk. Stories may have dependencies on other stories — these are noted at the story level.

**Conventions used:**
- `BE` = backend-only change
- `FE` = frontend-only change
- `BE+FE` = requires coordinated backend and frontend change
- `SCHEMA` = adds or modifies a Pydantic model in `backend/schema.py` (always backward-compatible via default factories)
- `TEST` = requires new or updated test in `backend/tests/`
- File paths are relative to the repo root

---

## Architecture Principles (Do Not Break)

1. **System prompt is assembled server-side every turn** in `backend/prompt_builder.py`. Never reassemble it on the frontend.
2. **Atomic file writes** in `state_manager.save_state` use a temp-file + rename pattern. Always go through `mutate_state()` for state changes, never write directly.
3. **Multiplayer session state** has two layers: durable (in `CampaignState.multiplayer`, on disk) and runtime (in `session_manager._sessions`, in memory). Status and character updates must be persisted via `_persist_session_status` or `mutate_state`.
4. **Schema v2 does not migrate from v1.** Any new field on a Pydantic model must have a `default_factory` or `default` value so existing state files deserialize without error.
5. **Rate limiting** applies to all chat-generating routes via `Depends(chat_rate_limit)`.
6. **No secrets or private preference content** goes into `CampaignPreferenceContext` — only prompt-safe guidance.

---

## Epic 1: Single-Player UX Polish

**Goal:** Address the highest-friction single-player usability issues. These are almost entirely frontend changes with no schema impact, so multiple developers can parallelize freely within this epic.

**Estimated Team Size:** 1–2 frontend developers  
**Blocks:** Nothing downstream depends on this epic.

---

### Story 1.1 — Input & Control Relabeling

**Goal:** Replace terminology that causes player confusion on first encounter.

**Acceptance Criteria:**
- The send button in the play view reads "Send" (not "Commit")
- The "Fork Timeline" button reads "Branch Story"
- The "Director Mode" / "Exit Director Mode" buttons include a subtitle hint: "Director Mode — edit world state"
- All changes match existing button styling (no new CSS classes needed)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.1.1 | FE | `frontend/src/App.jsx` | Line ~1062: change button label from `"Commit"` to `"Send"`. Also update the stop button from `"Stop"` to `"Stop"` (already correct) — no change needed. |
| 1.1.2 | FE | `frontend/src/App.jsx` | Line ~969: change `"Fork Timeline"` to `"Branch Story"` and update the `title` attribute to match. |
| 1.1.3 | FE | `frontend/src/App.jsx` | Line ~975–977: update Director Mode button label to `"Director Mode"` with an adjacent `<span>` subtitle `"edit world state"` styled in `text-xs text-slate-500`; same for the Exit state. |

---

### Story 1.2 — Director Mode Discoverability & Prompt Inspector

**Goal:** Make Director Mode findable, and decouple the Prompt Inspector from Director Mode.

**Acceptance Criteria:**
- The Prompt Inspector ("Inspect Prompt") is available as a standalone header button regardless of Director Mode state.
- The Director Mode button has a `title` attribute that reads: "Open the editor to change NPCs, stats, and world details mid-story"
- The Debug Bundle button remains Director Mode-only (it's power-user territory)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.2.1 | FE | `frontend/src/App.jsx` | Move the "Inspect Prompt" button out of the `{directorMode && ( ... )}` block and into the always-visible header controls area. Retain its existing `onClick={openInspector}` and `title` attribute. |
| 1.2.2 | FE | `frontend/src/App.jsx` | Ensure the Director Mode toggle button has `title="Open the editor to change NPCs, stats, and world details mid-story"` (already partially there — verify and update). |

---

### Story 1.3 — Token Bar & Roll Result Feedback

**Goal:** Surface prompt usage and dice roll outcomes in a way that casual players understand.

**Acceptance Criteria:**
- Token bar has a tooltip reading: "AI memory usage — green: plenty of room, amber: getting full, red: near limit"
- Token bar label shows percentage instead of raw numbers by default, with raw numbers in the tooltip: "38% full — 12,432 / 32,768 tokens"
- When an action roll fires, the result appears as an inline element *within the message area* above the GM response, not only in the header badge. The header badge can remain as a secondary indicator.
- Roll result inline element uses the existing amber/emerald/red color scheme from `ActionResolution.outcome`

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.3.1 | FE | `frontend/src/App.jsx` | Modify the token bar `<div>` (line ~952): change displayed text from `total_used / model_context_window` to `{ctx}% full`; move the raw numbers to the `title` attribute. Update tooltip text. |
| 1.3.2 | FE | `frontend/src/App.jsx` | In the `messages.map` render loop (line ~988), after the user message and before the assistant message for the same turn, conditionally render a `<RollResultBadge resolution={lastResolution} />` component if `lastResolution` is non-null. This component renders the `resolution.summary` string in a styled block. Clear `lastResolution` when a new turn starts (it's already reset in `onStart`). |
| 1.3.3 | FE | `frontend/src/App.jsx` | Create the `RollResultBadge` functional component inline in App.jsx or in a new `components/RollResultBadge.jsx`. Style: `bg-slate-800 border border-amber-600/40 text-amber-200 rounded-lg px-4 py-2 text-sm font-sans italic`. Include outcome icon mapping: critical_success → 🎯, success → ✅, partial_success → ⚠️, failure → ❌, critical_failure → 💀. |

---

### Story 1.4 — Campaign List Cleanup

**Goal:** Hide internal IDs from the campaign list; show creation date instead.

**Acceptance Criteria:**
- Campaign cards no longer display the raw `campaign_XXXXXX` ID string
- A human-readable creation date is shown instead: "Started Apr 28, 2026"
- `CampaignSummary` in schema already has `created_at`; the list endpoint must include it

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.4.1 | BE | `backend/main.py` | Verify the `GET /api/campaigns` route returns `created_at` in `CampaignSummary`. `CampaignSummary.created_at` already exists in schema. Confirm it is populated from `CampaignState.created_at` in the `list_campaigns` handler. |
| 1.4.2 | FE | `frontend/src/App.jsx` | In the campaign card render (line ~652), replace `<span className="text-xs text-slate-500">{c.id}</span>` with `<span className="text-xs text-slate-500">{c.created_at ? formatDate(c.created_at) : ''}</span>`. Add a `formatDate` helper above `AppInner` that converts an ISO string to "Apr 28, 2026". |

---

### Story 1.5 — Quick Actions Defaults & Improvement

**Goal:** Make Quick Actions more discoverable for new users; improve template fill-in.

**Acceptance Criteria:**
- Quick Actions are shown by default for first-time users (no localStorage key set)
- Quick Action buttons, when clicked, open a small inline popover/form allowing fill-in of bracketed placeholders before inserting into the textarea
- The popover is dismissible via Escape or clicking outside

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.5.1 | FE | `frontend/src/App.jsx` | Change `showQuickActions` initial value: `localStorage?.getItem('tt_quick_actions') !== 'false'` (default to visible unless explicitly hidden). Update `toggleQuickActions` to set `'false'` when hiding. |
| 1.5.2 | FE | `frontend/src/App.jsx` | Extract brackets from action text with regex `/\[([^\]]+)\]/g`. When a Quick Action button is clicked and its template contains `[...]` placeholders, render a small popover below the button row with labeled inputs for each placeholder. On "Insert" click, replace placeholders with filled values and set `input`. |
| 1.5.3 | FE | `frontend/src/App.jsx` | Add keyboard handler: `onKeyDown` on the document captures `Escape` to close the popover. Add `useRef` for popover click-outside detection. |

---

### Story 1.6 — Narrative Scroll & Textarea Auto-Grow

**Goal:** The action textarea grows with content; streaming narration stays in view.

**Acceptance Criteria:**
- The action textarea in the play view auto-expands to fit content up to `max-h-40`, without requiring the resize drag handle
- During streaming, the narrative scroll area stays scrolled to the bottom as tokens arrive
- No visible layout jump when the textarea expands

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.6.1 | FE | `frontend/src/App.jsx` | In the `<textarea>` element (line ~1039), add `onInput` handler: `(e) => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'; }`. Set initial inline style `style={{ height: '58px', overflow: 'hidden' }}`. Change `rows={1}` to remove it (height is now driven by content). |
| 1.6.2 | FE | `frontend/src/App.jsx` | In the `messages.map` render loop, add a `useEffect` that fires when `messages` changes and the last message is a streaming assistant message: call `scrollAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })`. Gate it on `isStreaming` to avoid disrupting manual scroll when reading. |

---

### Story 1.7 — Bug Fixes (Continue Condition, Duplicate Stats, Reroll Partial)

**Goal:** Fix three correctness issues found during the QA pass.

**Acceptance Criteria:**
- Continue button appears when generation was stopped mid-stream (partial flag is true) regardless of terminal punctuation
- Duplicate stat names are rejected with an inline validation error in both CampaignCreator and Director Mode
- Reroll, when the current assistant message is partial (user stopped it), asks: "Discard the current partial response and generate a new one?" via the existing modal system

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.7.1 | FE | `frontend/src/App.jsx` | Fix `canContinue` (line ~724): change to `const canContinue = !isStreaming && lastGmMsg && (lastGmMsg.partial || !/[.!?…"'"'"')\]]+$/.test((lastGmMsg.content || '').trim()));` — this checks for partial flag first and uses a more robust terminal-punctuation test. |
| 1.7.2 | FE | `frontend/src/CampaignCreator.jsx` | In `addNpc` validation, also check `newStat.name` is not already in `stats.map(s => s.name)`. Show an inline error span `"Stat name already exists"` near the add button. |
| 1.7.3 | FE | `frontend/src/App.jsx` | In Director Mode stat edit (`updateStat`), check if the key already exists under a different internal key — this is naturally avoided since the key is the stat name, but add a UI guard in the `input` onChange handler in the Director Mode sidebar. |
| 1.7.4 | FE | `frontend/src/App.jsx` | In `handleRegenerate`, check if `lastGmMsg?.partial` is true. If so, call `modal.confirm` with message "Discard the current partial response and generate a new one?" before proceeding. |

---

### Story 1.8 — Preference System Surface Improvements

**Goal:** Make active preference profiles more visible and navigable during play.

**Acceptance Criteria:**
- The preference context block in the sidebar is clickable and opens the Preference Profiles screen in a modal overlay (not navigating away from the play view)
- The preference block's header reads "Preference Context — active" with a small green dot indicator
- On the main menu, a small callout appears for first-time users who have no profiles: "Tip: set up Preference Profiles to guide the story tone → [Get Started]"
- "Get Started" navigates to `setAppMode('profiles')`

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 1.8.1 | FE | `frontend/src/App.jsx` | Wrap the preference context block (line ~748–756) in a `<button>` that sets a new state variable `profilesOpen = true`. When `profilesOpen` is true, render `<PreferenceProfiles onBack={() => setProfilesOpen(false)} ... />` as a fixed-position overlay. |
| 1.8.2 | FE | `frontend/src/App.jsx` | In the menu view, if `savedCampaigns.length === 0` and there are no profiles (check via a `GET /api/preferences/profiles` call on menu load), render a small `bg-indigo-950/30 border border-indigo-700/40` nudge block: "Tip: Preference Profiles let you guide the story's tone and themes. [Get Started →]". |

---

## Epic 2: Onboarding & World Creation

**Goal:** Reduce time-to-first-narration and confusion for new users. Introduce Quick Start mode and world templates.

**Estimated Team Size:** 1 full-stack developer  
**Blocks:** None; can be developed in parallel with Epics 1 and 3.

---

### Story 2.1 — First-Run Experience

**Goal:** Automatically surface help to first-time users.

**Acceptance Criteria:**
- On first load (no `tt_has_launched` in localStorage), the HelpModal opens automatically
- A "Don't show again" checkbox in HelpModal prevents auto-open on future visits
- The main menu has a visible "What is this?" link in addition to the `?` button

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 2.1.1 | FE | `frontend/src/App.jsx` | Add `useEffect` on mount: if `!localStorage.getItem('tt_has_launched')`, call `setHelpOpen(true)`. Set `tt_has_launched = '1'` once the modal closes. |
| 2.1.2 | FE | `frontend/src/components/HelpModal.jsx` | Add a checkbox "Don't show this automatically next time" at the bottom. If checked when closing, write `localStorage.setItem('tt_has_launched', '1')`. If unchecked, remove the key. |
| 2.1.3 | FE | `frontend/src/App.jsx` | In the menu header, add a `"What is this?"` text link next to the `?` button that calls `setHelpOpen(true)`. |

---

### Story 2.2 — Quick Start Mode in World Forge

**Goal:** Reduce the "Forge Your World" screen to a two-field entry point for new users.

**Acceptance Criteria:**
- By default, the world forge shows only: world concept prompt textarea, character name input, and "Begin Adventure" button
- An "Advanced Setup ▸" toggle expands all existing sections (Models, Protagonist detail, Cast, Lorebook, Session Mode)
- Advanced sections are preserved/remembered per session (sessionStorage key `tt_advanced_open`)
- In Quick Start mode, Models auto-select first available (existing behavior), stats default to Health=100/Gold=50 (existing defaults), inventory defaults to ["Rusty Sword"] (existing defaults)
- World concept prompt feeds the Auto-Forge World AI call automatically before `handleStart` when `autoForge = true`

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 2.2.1 | FE | `frontend/src/CampaignCreator.jsx` | Add state: `const [advancedOpen, setAdvancedOpen] = useState(() => sessionStorage.getItem('tt_advanced_open') === 'true')`. Toggle saves to sessionStorage. |
| 2.2.2 | FE | `frontend/src/CampaignCreator.jsx` | Restructure JSX: always show the world concept textarea and protagonist name input. Wrap all other sections in `{advancedOpen && (...)}`. Add a toggle button: `"Advanced Setup {advancedOpen ? '▾' : '▸'}"` between the character name field and the world generation sections. |
| 2.2.3 | FE | `frontend/src/CampaignCreator.jsx` | In `handleStart`, if `worldPrompt.trim()` is non-empty and `worldDescription` is empty (user used Quick Start without clicking Generate), run `handleGenerateWorld()` and await its result before calling the campaign init API. Show a "Dreaming up your world…" spinner during this. |

---

### Story 2.3 — World Templates Library

**Goal:** Provide a set of one-click starting worlds to eliminate setup friction.

**Acceptance Criteria:**
- A "Choose a Template" section appears above the world concept textarea in Quick Start mode
- Clicking a template pre-fills: world prompt, protagonist name/location defaults, 1–2 starting NPCs, and 2–3 lorebook entries
- At least 6 templates are provided: High Fantasy, Gritty Dark Fantasy, Sci-Fi, Horror, Historical (medieval), and Modern Paranormal
- Templates can be dismissed (selection is not required)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 2.3.1 | FE | `frontend/src/` | Create `data/worldTemplates.js` exporting an array of template objects: `{ id, label, description, worldPrompt, protagonistName, startingLocation, npcs: [], lorebook: [] }`. Write 6 templates. |
| 2.3.2 | FE | `frontend/src/CampaignCreator.jsx` | Import templates. Add a horizontal scrollable row of template cards above the world concept textarea. Each card shows label + 1-sentence description. Clicking one calls `applyTemplate(template)` which calls `setWorldPrompt`, `setProtagonist`, `setNpcs`, `setLorebook` appropriately. |
| 2.3.3 | FE | `frontend/src/CampaignCreator.jsx` | Add a `selectedTemplate` state. Highlight the active template card. Add a "Clear" or "×" on the selected card to deselect and reset fields. |

---

### Story 2.4 — Ollama Health Check & Model Selection Clarity

**Goal:** Tell users early if Ollama is not running; make auto-selected utility model visually distinct.

**Acceptance Criteria:**
- `GET /api/health` endpoint returns `{ "ollama": "ok" | "unreachable", "models_available": int }`
- CampaignCreator polls this on mount and displays a banner if Ollama is unreachable, with the pull command suggestion
- When `utilityModel === ''` (auto mode), the dropdown shows `"(auto)"` in amber text to visually distinguish from a manually selected model

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 2.4.1 | BE | `backend/main.py` | Add `GET /api/health` route. Call `httpx.get("http://localhost:11434/api/tags", timeout=2.0)`. Return `{"ollama": "ok", "models_available": len(models)}` on success, `{"ollama": "unreachable", "models_available": 0}` on exception. No auth. |
| 2.4.2 | FE | `frontend/src/CampaignCreator.jsx` | On component mount, `apiFetch('/api/health')`. If `ollama === 'unreachable'`, show a prominent `bg-red-950/40 border border-red-700` alert banner above the Models section with the pull command and a "Retry" button. |
| 2.4.3 | FE | `frontend/src/CampaignCreator.jsx` | In the utility model `<select>`, style the first `<option value="">` with `className="text-amber-400"` and add text `"(auto — recommended)"`. Add a sibling note: `{utilityModel === '' && <span className="text-xs text-amber-400 ml-1">auto</span>}` next to the select. |

---

### Story 2.5 — World Generation Re-roll & Pass Turn

**Goal:** Allow regenerating a failed world result; allow players to skip their action.

**Acceptance Criteria:**
- After a successful "Generate World" call in CampaignCreator, a "Regenerate ↻" button appears next to the world concept textarea
- Clicking Regenerate clears the generated fields and re-calls `handleGenerateWorld()`
- In the single-player play view, a "Pass Turn" button appears below the Quick Actions row. It submits the predefined text "I observe and wait, taking no action this turn."
- Pass Turn is disabled while streaming

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 2.5.1 | FE | `frontend/src/CampaignCreator.jsx` | Add state `const [hasGenerated, setHasGenerated] = useState(false)`. In `handleGenerateWorld` success handler, set `setHasGenerated(true)`. Render `{hasGenerated && <button onClick={() => { clearGeneratedFields(); handleGenerateWorld(); }}>Regenerate ↻</button>}`. `clearGeneratedFields` resets `worldDescription`, `startingScene`, `npcs`, `lorebook` to empty defaults. |
| 2.5.2 | FE | `frontend/src/App.jsx` | In the input area (below the Quick Actions row), add `<button onClick={() => { setInput('I observe and wait, taking no action this turn.'); handleSend(); }} disabled={isStreaming}>Pass Turn</button>`. Style: `text-xs text-slate-400 border border-slate-700 hover:border-slate-500 rounded px-2 py-1`. |

---

## Epic 3: Multiplayer Core Fixes

**Goal:** Bring the multiplayer experience to feature parity with single-player on the critical paths: shared narrative clarity, character visibility, reconnection reliability, and session control. This is the highest-priority epic.

**Estimated Team Size:** 2 full-stack developers  
**Internal Dependencies:** Stories 3.1–3.5 should be completed before 3.6–3.11.

---

### Story 3.1 — Multiplayer Opening Kickoff Scene

**Goal:** Before the first player acts, the GM narrates an opening scene establishing the setting for both characters.

**Acceptance Criteria:**
- When both players ready up in the lobby and `session.status` advances to `host_turn`, a kickoff generation fires automatically
- The kickoff generation uses the existing `/api/campaign/{id}/kickoff` endpoint but is triggered server-side by the session state machine, and streamed to both WebSocket clients via `broadcast`
- Both players see the streaming kickoff text in their play view before input is enabled
- After kickoff completes, the session advances to `HOST_TURN` and input is unlocked for the host
- If a kickoff already exists (session resumed), no new kickoff is generated

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.1.1 | BE | `backend/session_manager.py` | In `set_ready()`, after advancing status to `HOST_TURN`, set a new field: `runtime.kickoff_needed = True` if `runtime.turn_number == 0` and no kickoff messages exist. Add `kickoff_needed: bool = False` to `SessionRuntime` dataclass. |
| 3.1.2 | BE | `backend/main.py` | In the WebSocket handler, after broadcasting `session_state` when both players ready up, check `rt.kickoff_needed`. If true, set `rt.kickoff_needed = False` and call `_run_multiplayer_kickoff(rt, campaign_id)` as a background task (`asyncio.create_task`). |
| 3.1.3 | BE | `backend/main.py` | Create `async def _run_multiplayer_kickoff(rt, campaign_id)`. Load state, check if any message has `is_kickoff=True` — if yes, skip. Build prompt via `prompt_builder.build_kickoff_prompt(state)` (existing function). Stream tokens from GM model. Broadcast `{"type": "token", "text": t}` to all connections. On completion, persist the kickoff message with `is_kickoff=True`. Broadcast `{"type": "generation_done", "is_kickoff": True}`. Do NOT advance turn slot — leave status as `HOST_TURN`. |
| 3.1.4 | FE | `frontend/src/MultiplayerPlay.jsx` | During kickoff generation (`currentGeneration?.is_kickoff === true`), show the streaming text in the narrative view but keep the input area locked with placeholder "Waiting for the opening scene…". After kickoff completes, unlock normally. Handle the `is_kickoff` flag on `generation_start` and `generation_done` WS messages. |
| 3.1.5 | FE | `frontend/src/hooks/useMultiplayerSession.js` | In `handleMessage`, extend the `generation_start` dispatch to include `isKickoff: data.is_kickoff || false`. Extend the reducer `generation_start` case to store `currentGeneration.isKickoff`. |
| 3.1.6 | TEST | `backend/tests/test_multiplayer_api.py` | Add test: after both players ready, `kickoff_needed` is True. After kickoff fires, campaign has a message with `is_kickoff=True`. Second ready-up on resumed session does not trigger kickoff. |

---

### Story 3.2 — Player Actions Visible in Multiplayer Narrative

**Goal:** Both players see each other's declared action text alongside the GM's response.

**Acceptance Criteria:**
- The session export endpoint includes each user (player action) message paired with its assistant (GM) response
- In `MultiplayerPlay`, each `NarrationBlock` shows the player's action text above the GM narration, clearly styled as "[Character Name] said: [action text]"
- Player action text is visually distinct from GM narration (different background, italic, smaller font)
- The existing `player_slot` attribution on GM messages is used to match player action to character

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.2.1 | BE | `backend/main.py` | Find the `POST /api/session/{room_code}/export` route. Currently returns only assistant turns. Change to return pairs: for each assistant message with a `turn_id`, also include the user message with the same `turn_id`. Shape the response as `{ turns: [{ gm_content, player_action, player_slot, actor_name, turn_id, timestamp, is_kickoff }] }`. |
| 3.2.2 | FE | `frontend/src/MultiplayerPlay.jsx` | Update `useEffect` that calls the export endpoint. Map the new turn shape. Pass `playerAction` to `NarrationBlock` as a new prop. |
| 3.2.3 | FE | `frontend/src/MultiplayerPlay.jsx` | In `NarrationBlock`, above the GM narration div, add: `{playerAction && <div className="text-xs italic text-slate-400 mb-2 pl-1">"{playerAction}"</div>}`. |
| 3.2.4 | FE | `frontend/src/MultiplayerPlay.jsx` | During live streaming (the `generating && liveAssistantText` block), also show the current player's submitted action text above the live narration. The `currentGeneration` already has `slot` and `actorName`; pass the submitted action text via a new WS message field. |
| 3.2.5 | BE | `backend/main.py` | In `_run_multiplayer_turn()`, when broadcasting `generation_start`, include `"player_action": pending_action.text` in the message payload. |
| 3.2.6 | TEST | `backend/tests/test_multiplayer_api.py` | Add test: session export includes player action text paired with GM response. |

---

### Story 3.3 — Character Sheet Panel in Multiplayer Play

**Goal:** Both players can view their own and their partner's character stats, inventory, and location during the session.

**Acceptance Criteria:**
- The right sidebar in `MultiplayerPlay` gains a third panel: "Character Sheets" (tab or expandable section)
- The panel shows both characters' name, stats, inventory, and location, sourced from `multiplayer.host_character` and `multiplayer.guest_character`
- Stats are read-only (edit capability is in Story 3.4)
- The panel collapses on mobile to preserve narrative space
- Data updates when `session_state` WebSocket messages arrive (they already carry `multiplayer`)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.3.1 | FE | `frontend/src/MultiplayerPlay.jsx` | Add `CharacterSheetsPanel` component at the bottom of the right sidebar (after `OocPanel`). Accept `multiplayer` and `mySlot` props. |
| 3.3.2 | FE | `frontend/src/MultiplayerPlay.jsx` | `CharacterSheetsPanel` renders two collapsible cards: "My Character" (always open by default) and "Partner's Character" (collapsed by default). Each card shows: name (heading), location, gender, stats as `{stat}: {value}` pairs, and inventory as comma-separated chips. Use `slotStyle()` for border/accent colors. |
| 3.3.3 | FE | `frontend/src/MultiplayerPlay.jsx` | Verify that the `multiplayer` prop is updated on each `session_state` WS message (it already is via the reducer). No backend changes needed. |
| 3.3.4 | BE | `backend/session_manager.py` | In the `_refresh_merged_preferences` background call or the `session_state` broadcast, ensure `multiplayer` in the broadcast includes updated `host_character.stats` and `guest_character.stats` after each turn's extraction completes. Currently `_persist_session_status` only updates session-level fields. The `session_state` broadcast after a turn should reload the campaign state and re-emit `multiplayer`. |

---

### Story 3.4 — Multiplayer Director Mode (Own Character Only)

**Goal:** Each player can edit their own character's stats, inventory, and appearance mid-session. The host retains exclusive control over NPCs, lorebook, and world state.

**Acceptance Criteria:**
- A "My Character" edit button appears in the character sheet panel for the player's own card
- Clicking it opens an inline edit form with stat value inputs, inventory add/remove, appearance textarea, and location field
- Changes are saved via `POST /api/session/{room_code}/character` (extended from the existing character update route)
- The host's Director Mode (full world state editing) remains available in its current form when the host navigates to the campaign via the regular play view — this story only adds self-character editing within the multiplayer play view
- Guest cannot edit NPCs, lorebook, or host's character

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.4.1 | BE | `backend/session_manager.py` | Extend `update_character()` to accept `stats` and `inventory` fields in addition to the existing text fields. Update `_apply` mutator to set `char.stats` and `char.inventory` if provided. |
| 3.4.2 | BE | `backend/main.py` | Find the existing WebSocket handler for `update_character` message type. Extend it to accept `stats: dict | None` and `inventory: list | None` in the message payload and pass them to `session_manager.update_character()`. |
| 3.4.3 | FE | `frontend/src/MultiplayerPlay.jsx` | In `CharacterSheetsPanel`, for the player's own card add an "Edit" toggle button. When editing, replace read-only fields with inputs: number inputs per stat, inventory chip list with × remove and + add, textarea for appearance. Add a "Save" button that calls `onUpdateCharacter({ stats, inventory, appearance, location })`. |
| 3.4.4 | FE | `frontend/src/hooks/useMultiplayerSession.js` | The existing `updateCharacter` callback sends `{ type: 'update_character', ...fields }`. Extend it to include `stats` and `inventory` fields. No change needed if fields are spread from the argument. |
| 3.4.5 | TEST | `backend/tests/test_multiplayer_api.py` | Add test: host can update own stats; guest can update own stats; guest cannot update host stats (the validation is slot-scoped — the WebSocket handler always uses the sender's slot, not an arbitrary one). |

---

### Story 3.5 — WebSocket Reconnect Hardening

**Goal:** The frontend WebSocket reconnects for the full server-side window duration, not just 15 seconds.

**Acceptance Criteria:**
- `RECONNECT_DELAYS_MS` is extended to retry indefinitely (or for 5 minutes) with a capped delay of 15 seconds
- A visible reconnection counter appears: "Reconnecting… attempt 3" in the play view header
- When the reconnect window on the server has expired, the frontend displays a clear "Session expired — the reconnect window closed. Please contact the host for a new room code." message
- Partner disconnect shows a countdown timer of remaining reconnect window time

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.5.1 | FE | `frontend/src/hooks/useMultiplayerSession.js` | Replace the fixed `RECONNECT_DELAYS_MS` array with a function: `getReconnectDelay(attempt) => Math.min(500 * 2 ** attempt, 15000)`. Remove the attempt cap — reconnect continues until the WS sends an `error` with `code: 'session_expired'` or until the component unmounts. |
| 3.5.2 | BE | `backend/main.py` | In the WebSocket disconnect handler, after `mark_disconnected()`, check `await session_manager.reconnect_window_expired(rt)`. If expired, send `{"type": "error", "code": "session_expired", "message": "Reconnect window closed."}` before closing. |
| 3.5.3 | FE | `frontend/src/hooks/useMultiplayerSession.js` | In the `closed` handler, if `intentionalCloseRef.current` is false and the last error code was `session_expired`, dispatch `{ type: 'error', message: 'Session expired...' }` and stop retrying (set `intentionalCloseRef.current = true`). |
| 3.5.4 | BE | `backend/main.py` | In the `session_state` broadcast after `mark_disconnected`, include `"paused_since": rt.paused_since.isoformat() if rt.paused_since else None` and `"reconnect_window_seconds": rt.reconnect_window_seconds`. |
| 3.5.5 | FE | `frontend/src/MultiplayerPlay.jsx` | When `status === 'paused'` and `sessionState.paused_since`, compute a countdown from `paused_since + reconnect_window_seconds - now` using a `useEffect` interval (1-second tick). Display: "Partner disconnected — {MM:SS} remaining." Update the `indicatorText` logic. |
| 3.5.6 | FE | `frontend/src/MultiplayerPlay.jsx` | Add a `reconnectAttempt` from `state.reconnectAttempt` when it is > 0: show a non-blocking banner "Reconnecting… attempt {n}" beneath the header. |

---

### Story 3.6 — OOC Message Persistence

**Goal:** Out-of-character messages survive page refreshes and player reconnects.

**Acceptance Criteria:**
- OOC messages are stored in a lightweight log file per session: `backend/sessions/{room_code}_ooc.jsonl`
- Each entry: `{ "slot": "host|guest", "display_name": "...", "text": "...", "ts": "ISO" }`
- On join/reconnect, the server sends the last 100 OOC messages in the `slot_assigned` or `session_state` response
- The in-memory cap remains 50 per client; the file log is the source of truth
- OOC log is deleted when the session is deleted (not archived)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.6.1 | BE | `backend/session_manager.py` | Add `async def append_ooc(room_code, slot, display_name, text, ts)` that appends a JSON line to `SESSIONS_DIR / f"{room_code}_ooc.jsonl"`. |
| 3.6.2 | BE | `backend/session_manager.py` | Add `async def read_ooc_log(room_code, limit=100) -> list[dict]` that reads the last `limit` lines from the JSONL file and returns them as dicts. |
| 3.6.3 | BE | `backend/main.py` | In the WebSocket OOC message handler, after broadcasting, call `await session_manager.append_ooc(room_code, slot, display_name, text, ts)`. |
| 3.6.4 | BE | `backend/main.py` | In the `slot_assigned` response (after join/reconnect succeeds), include `"ooc_log": await session_manager.read_ooc_log(room_code)`. |
| 3.6.5 | FE | `frontend/src/hooks/useMultiplayerSession.js` | In the `slot_assigned` message handler, if `data.ooc_log` is present, dispatch a new action `{ type: 'ooc_hydrate', messages: data.ooc_log }`. Add a `ooc_hydrate` case to the reducer that sets `oocMessages` to the log (capped at 50 most recent). |
| 3.6.6 | BE | `backend/session_manager.py` | In `delete_session()`, after `state_manager.delete_campaign`, delete `SESSIONS_DIR / f"{room_code}_ooc.jsonl"` if it exists. |
| 3.6.7 | TEST | `backend/tests/test_session_manager.py` | Add test: OOC message is persisted to file; read_ooc_log returns it; delete_session removes the file. |

---

### Story 3.7 — Turn Order Controls & Pass Turn

**Goal:** The host can choose which player goes first; any player can pass their turn.

**Acceptance Criteria:**
- In the lobby, the host sees a "Who goes first?" control: "Host" (default) / "Guest" radio buttons
- This setting updates `session.starting_slot_this_round` before the session starts
- Either player can click "Pass Turn" to submit a predefined action: "I wait and observe this turn." — this is treated as a normal action submission and the turn advances
- The host can "Gift Turn" to immediately pass the active floor to the partner (this is distinct from Pass Turn — it advances the turn without generating a response)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.7.1 | BE | `backend/main.py` | Add WebSocket message type `set_starting_slot` accepted from host slot only in LOBBY status. Updates `rt.starting_slot_this_round` and persists. Broadcast `session_state`. |
| 3.7.2 | FE | `frontend/src/MultiplayerLobby.jsx` | In `HostControls` (or a new dedicated area), add a radio group: "First to act: [Host] [Guest]". `onChange` calls a new `onSetStartingSlot(slot)` prop. |
| 3.7.3 | FE | `frontend/src/hooks/useMultiplayerSession.js` | Add `setStartingSlot` callback: `sendJSON({ type: 'set_starting_slot', slot })`. |
| 3.7.4 | FE | `frontend/src/MultiplayerPlay.jsx` | Add "Pass Turn" button next to the Submit button (visible only when `isMyTurn`). Calls `onSubmitAction("I wait and observe this turn.")`. |
| 3.7.5 | BE | `backend/main.py` | Add WebSocket message type `gift_turn` accepted from host slot only when status is `HOST_TURN`. Calls `session_manager.begin_next_round()` without generating. Broadcasts `session_state`. |
| 3.7.6 | FE | `frontend/src/MultiplayerPlay.jsx` | In host-only controls area, add "Gift Turn to [partner name]" button (only visible when `mySlot === 'host'` and `status === 'host_turn'`). |

---

### Story 3.8 — Reroll & Continue in Multiplayer

**Goal:** Either player can request regeneration or continuation of the last GM response.

**Acceptance Criteria:**
- After each GM narration block, "↻ Reroll" and "→ Continue" buttons appear (same logic as single-player)
- Either player can trigger these; the action requires the session not be in GENERATING state
- Reroll shows a confirmation modal: "Request the GM to rewrite the last response?"
- Continue does not require a turn — it appends to the last GM message without consuming anyone's turn
- After Reroll completes, the turn advances normally; after Continue, the floor stays with the same player

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.8.1 | BE | `backend/main.py` | Add WebSocket message type `request_reroll`. Handler: verifies `rt.status` is not GENERATING, calls the existing `regenerate/{msg_id}` logic adapted for multiplayer, streams to all players. After completion, does NOT advance the turn (same player acts next). |
| 3.8.2 | BE | `backend/main.py` | Add WebSocket message type `request_continue`. Handler: calls the continue endpoint logic, streams tokens to all players. Does not change turn. |
| 3.8.3 | FE | `frontend/src/MultiplayerPlay.jsx` | After the last `NarrationBlock` (not during generation), render "↻ Reroll" and "→ Continue" buttons. "→ Continue" appears only if the last message appears partial (ends abruptly — same heuristic as single-player). |
| 3.8.4 | FE | `frontend/src/hooks/useMultiplayerSession.js` | Add `requestReroll` and `requestContinue` callbacks. `requestReroll` first calls `modal.confirm` (passed in from consumer or handled locally). |
| 3.8.5 | TEST | `backend/tests/test_multiplayer_api.py` | Add tests for reroll and continue WS message types. |

---

### Story 3.9 — Multiplayer UX Polish

**Goal:** Fix the collection of small multiplayer UX issues: labels, confirmations, transitions, validation.

**Acceptance Criteria:**
- Archive and Delete buttons in the play view header use the modal confirmation system before executing
- Internal slot identifiers ("host", "guest") are not shown to players in UI labels — character names or display names are used
- The lobby character card auto-saves on blur (with 1-second debounce) and shows a "Saved" badge for 2 seconds
- When both players ready up, a 3-second countdown ("Session starting in 3… 2… 1…") plays before the play view loads
- Room code input on the join screen validates against the server before enabling "Connect": a `GET /api/session/{code}/exists` endpoint returns `{ exists: bool }`
- A warning dialog appears when leaving the multiplayer join form with unsaved preferences

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.9.1 | FE | `frontend/src/MultiplayerPlay.jsx` | Wrap `onArchive` and `onDelete` calls with a local `confirm` (using `window.confirm` or import `useModal` from context). |
| 3.9.2 | FE | `frontend/src/MultiplayerPlay.jsx` | In `RosterPanel`, `slotName` function and NarrationBlock `badge` text — replace "host" and "guest" literal strings with `multiplayer?.host_character?.name || 'Host'` and `multiplayer?.guest_character?.name || 'Guest'`. Update `slotName()` to always return the character name, never the slot key. |
| 3.9.3 | FE | `frontend/src/MultiplayerLobby.jsx` | In `CharacterCard` for the editable card, convert `onSave` button to `onBlur` auto-save (debounced 1000ms) on the form fields. Add a `savedBadge` state that shows "✓ Saved" for 2 seconds after each save. |
| 3.9.4 | FE | `frontend/src/MultiplayerSession.jsx` | After the `session_state` update advances status to a PLAY status from LOBBY, instead of immediately rendering `MultiplayerPlay`, render a countdown overlay (3 seconds) before switching. Use a `useEffect` with `setTimeout`. |
| 3.9.5 | BE | `backend/main.py` | Add `GET /api/session/{room_code}/exists` route returning `{"exists": bool, "status": str | None}`. No auth required. Look up `await session_manager.get_session(room_code)`. |
| 3.9.6 | FE | `frontend/src/MultiplayerSession.jsx` (in `MultiplayerEntry`) | Add `useEffect` on `roomCode` change (debounced 600ms): if `roomCode.length >= 4`, call `/api/session/{roomCode}/exists`. Show a green ✓ or red ✗ indicator next to the room code input. Disable "Connect" if the room doesn't exist. |
| 3.9.7 | FE | `frontend/src/MultiplayerSession.jsx` (in `MultiplayerEntry`) | Track `hasUnsavedPreferences` state (true if preference tab is 'quick' or 'import' and a profile is configured). On `onBack` click, if `hasUnsavedPreferences`, call `window.confirm("Leave? Your preference setup will be lost.")`. |

---

### Story 3.10 — Session Recovery & Return to Solo

**Goal:** Handle the GENERATING-on-restart edge case; allow archiving a multiplayer session and continuing solo.

**Acceptance Criteria:**
- If a session rebuilds from disk with `paused_status_before = GENERATING`, it is corrected to the appropriate turn slot (host/guest based on `starting_slot_this_round`)
- After a session is archived, the host's campaign menu entry shows a "Continue Solo" button
- "Continue Solo" strips the `multiplayer` config from the campaign (sets it to null), then loads the campaign in single-player play mode
- The stripped-multiplayer campaign retains all messages, state, and memories

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.10.1 | BE | `backend/session_manager.py` | In `initialize()`, after rebuilding a session runtime with `status = PAUSED` and `paused_status_before = GENERATING`, override: set `paused_status_before` to the correct next turn slot based on `starting_slot_this_round`. |
| 3.10.2 | BE | `backend/main.py` | Add `POST /api/campaign/{id}/convert_to_solo` route. Loads state, verifies `state.multiplayer is not None` and `state.multiplayer.session_status == ARCHIVED`. Calls `mutate_state` to set `state.multiplayer = None`. Returns updated state. |
| 3.10.3 | FE | `frontend/src/App.jsx` | In the campaign list, check if `c.has_archived_multiplayer` (new field from `CampaignSummary`). If yes, show a "Continue Solo" button. Clicking it calls `POST /api/campaign/{id}/convert_to_solo`, then `loadCampaign(id)`. |
| 3.10.4 | BE | `backend/main.py` | Update `GET /api/campaigns` to include `has_archived_multiplayer: bool` in `CampaignSummary`. Set it if `state.multiplayer` is not None and `session_status == ARCHIVED`. Update `CampaignSummary` in `schema.py` to add this field with `default=False`. |
| 3.10.5 | SCHEMA | `backend/schema.py` | Add `has_archived_multiplayer: bool = False` to `CampaignSummary`. |

---

### Story 3.11 — Guest Session Discovery & Last-Session Rejoin

**Goal:** Guests can find and rejoin their most recent session from the main menu.

**Acceptance Criteria:**
- Last-joined room code and character name are saved in localStorage after a successful join
- The main menu shows a "Rejoin Last Session" card if a recent room code is stored
- The card shows: room code, character name, and a "Rejoin" button
- Clicking "Rejoin" pre-fills the join form and auto-launches
- The card has an "×" dismiss button to forget the stored session

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 3.11.1 | FE | `frontend/src/hooks/useMultiplayerSession.js` | In the `slot_assigned` handler, save to localStorage: `tt_last_room = roomCode`, `tt_last_char = characterName`, `tt_last_display = displayName`. |
| 3.11.2 | FE | `frontend/src/App.jsx` | On menu load, read `tt_last_room` from localStorage. If present, call `/api/session/{code}/exists`. If the session still exists, render a "Rejoin Last Session" card in the saved campaigns section. |
| 3.11.3 | FE | `frontend/src/App.jsx` | The "Rejoin" button sets `multiplayerLaunch` with the stored room code, display name, and character name, then `setAppMode('multiplayer')` with `autoLaunch=true`. |
| 3.11.4 | FE | `frontend/src/App.jsx` | Add an "×" button on the rejoin card that calls `localStorage.removeItem('tt_last_room')` and hides the card. |

---

## Epic 4: Multiplayer New Features

**Goal:** Add quality-of-life and engagement features that meaningfully differentiate the multiplayer experience. These build on top of Epic 3's foundations.

**Estimated Team Size:** 2 developers  
**Depends On:** Epic 3 fully complete before starting Stories 4.3, 4.4, 4.5.

---

### Story 4.1 — Room Code Sharing (QR Code + Share Button)

**Acceptance Criteria:**
- A QR code for the join URL is displayed in the multiplayer lobby
- A "Copy Invite" button produces a formatted message: "Join my Tavern Tales session!\nRoom code: WOLF42\nLink: {join_url}"
- QR code is rendered client-side using the `qrcode.react` package (no server call)
- QR code is hidden when there is no join URL

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.1.1 | FE | `frontend/` | `npm install qrcode.react`. |
| 4.1.2 | FE | `frontend/src/MultiplayerLobby.jsx` | Import `{ QRCodeSVG } from 'qrcode.react'`. In the header section, below the join URL, render `{joinUrl && <QRCodeSVG value={joinUrl} size={120} bgColor="#1e2028" fgColor="#f59e0b" />}`. |
| 4.1.3 | FE | `frontend/src/MultiplayerLobby.jsx` | Replace the existing `"copy"` link with a styled "📋 Copy Invite" button. `onClick`: `navigator.clipboard.writeText("Join my Tavern Tales session!\nRoom: {roomCode}\nLink: {joinUrl}")`. Show a "Copied!" badge for 2s. |

---

### Story 4.2 — Turn Notifications (Browser + Title)

**Acceptance Criteria:**
- When it becomes the player's turn, the browser tab title changes to `"[Your Turn] Tavern Tales"`
- If the Notification API is available and permission is granted, a browser notification fires: "Tavern Tales — it's your turn!"
- A persistent "Enable Turn Notifications" button appears in the play view for first-time users (hidden after permission granted or denied)
- Notification fires on `floor_passed` WS message when `active_slot === mySlot`

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.2.1 | FE | `frontend/src/MultiplayerPlay.jsx` | Add `useEffect` watching `isMyTurn`. When it becomes `true`: `document.title = '[Your Turn] Tavern Tales Reborn'`. When `false`: reset to `'Tavern Tales Reborn'`. Cleanup on unmount. |
| 4.2.2 | FE | `frontend/src/MultiplayerPlay.jsx` | Add `useEffect` on `isMyTurn`. If `Notification.permission === 'granted'` and `isMyTurn` just became true and `document.hidden`, fire `new Notification('Tavern Tales', { body: "It's your turn!", icon: '/favicon.ico' })`. |
| 4.2.3 | FE | `frontend/src/MultiplayerPlay.jsx` | Add `notificationState` (unchecked / granted / denied). Show a small "🔔 Enable turn notifications" button in the header if `notificationState === 'unchecked'`. `onClick`: call `Notification.requestPermission()`. Hide permanently after response. Persist state in localStorage `tt_notif`. |

---

### Story 4.3 — Optional Turn Timer

**Acceptance Criteria:**
- Host can set a per-turn time limit in the lobby: Off / 2 min / 5 min / 10 min
- Timer is stored in `MultiplayerConfig.turn_timer_seconds: int | None = None`
- Server tracks timer start in `SessionRuntime.turn_started_at: datetime | None`
- When timer expires, the server auto-submits "I hesitate and take no action this turn." for the idle player
- Both players see a countdown in the play view header when the timer is active
- Timer resets on each turn start

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.3.1 | SCHEMA | `backend/schema.py` | Add `turn_timer_seconds: int | None = None` to `MultiplayerConfig`. |
| 4.3.2 | BE | `backend/session_manager.py` | Add `turn_started_at: datetime | None = None` to `SessionRuntime`. Set it in `begin_next_round()` if `rt.turn_timer_seconds` is set. |
| 4.3.3 | BE | `backend/main.py` | Add a background task `_watch_turn_timer(rt, room_code)` launched in `begin_next_round` when `turn_timer_seconds` is not None. Task: `await asyncio.sleep(turn_timer_seconds)`. After sleep, if `rt.status` is still the same turn slot, call `submit_action(room_code, active_slot, "I hesitate and take no action this turn.")`. |
| 4.3.4 | BE | `backend/main.py` | Include `"turn_started_at": rt.turn_started_at.isoformat() if rt.turn_started_at else None` and `"turn_timer_seconds": rt.turn_timer_seconds` in `session_state` broadcasts. |
| 4.3.5 | FE | `frontend/src/MultiplayerLobby.jsx` | In `HostControls`, add a "Turn Timer" `<select>`: Off / 2 min / 5 min / 10 min. `onChange` sends `{ type: 'set_turn_timer', seconds: value }` via WS. |
| 4.3.6 | BE | `backend/main.py` | Handle `set_turn_timer` WS message (host only, LOBBY status). Update `rt.turn_timer_seconds` and `state.multiplayer.turn_timer_seconds` via `mutate_state`. |
| 4.3.7 | FE | `frontend/src/MultiplayerPlay.jsx` | When `sessionState.turn_timer_seconds` and `sessionState.turn_started_at` are set, compute remaining seconds with a `useEffect` interval. Display in header: "⏱ {MM:SS}" in amber (normal) or red (< 30s). |
| 4.3.8 | TEST | `backend/tests/` | Add `test_turn_timer.py`: verify timer expiration auto-submits action. |

---

### Story 4.4 — Simultaneous Action Mode

**Goal:** An optional mode where both players submit actions secretly before the GM narrates both together.

**Acceptance Criteria:**
- Host can enable "Simultaneous Mode" in the lobby (checkbox)
- Stored in `MultiplayerConfig.simultaneous_mode: bool = False`
- Session status in simultaneous mode cycles: `BOTH_ACTING → GENERATING → BOTH_ACTING`
- Both players see the input as active but cannot see each other's draft
- The GM generates one response that addresses both characters' actions
- After generation, the system shows each player's submitted action (they were secret until then)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.4.1 | SCHEMA | `backend/schema.py` | Add `simultaneous_mode: bool = False` to `MultiplayerConfig`. Add `BOTH_ACTING = "both_acting"` to `SessionStatus` enum. |
| 4.4.2 | BE | `backend/session_manager.py` | Add `submit_action_simultaneous(room_code, slot, text)`: stores the action without changing status. When both slots have submitted, changes status to GENERATING and returns `"ready_to_generate"`. If only one slot has submitted, returns `"waiting_for_partner"`. |
| 4.4.3 | BE | `backend/main.py` | In the `submit_action` WebSocket handler, check `state.multiplayer.simultaneous_mode`. If True, call `submit_action_simultaneous` instead of `submit_action`. |
| 4.4.4 | BE | `backend/main.py` | In `_run_multiplayer_turn()`, detect simultaneous mode: include both pending actions in the prompt context with labels "Host's action: [text]" and "Guest's action: [text]". Use `format_multiplayer_turn_message()` adapted for two concurrent actions. |
| 4.4.5 | FE | `frontend/src/MultiplayerLobby.jsx` | Add "Simultaneous Mode" checkbox in lobby settings (host only). Sends `{ type: 'set_simultaneous_mode', enabled: bool }` via WS. |
| 4.4.6 | FE | `frontend/src/MultiplayerPlay.jsx` | In simultaneous mode (`sessionState.status === 'both_acting'`): both inputs are unlocked. Show indicator "Both players are submitting their action — your draft is private." After submission, show "Submitted — waiting for partner…" for the submitting player. After generation, reveal the partner's action text. |
| 4.4.7 | TEST | `backend/tests/` | Add `test_simultaneous_mode.py`. |

---

### Story 4.5 — Spectator Mode

**Acceptance Criteria:**
- A third connection type: `{ "type": "join", "slot": "spectator" }` is accepted
- Spectators receive all `token`, `generation_start`, `generation_done`, and `session_state` broadcasts
- Spectators cannot submit actions or OOC messages
- The lobby and play view show a "Spectators: N" count
- Spectators do not affect session status (session advances without spectator readiness)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.5.1 | BE | `backend/session_manager.py` | Add `spectators: dict[str, WebSocket]` to `SessionRuntime` (keyed by UUID). Add `join_as_spectator(room_code, websocket) -> str` (returns spectator_id). Add spectators to the `broadcast` function. |
| 4.5.2 | BE | `backend/main.py` | In the WebSocket join handler, detect `slot == "spectator"` and call `join_as_spectator`. Send `{"type": "slot_assigned", "slot": "spectator"}` back. Include spectator count in `session_state` broadcasts. |
| 4.5.3 | FE | `frontend/src/MultiplayerLobby.jsx` | Show `{sessionState?.spectator_count > 0 && <span>👁 {sessionState.spectator_count} watching</span>}` in the header. |
| 4.5.4 | FE | `frontend/src/MultiplayerPlay.jsx` | If `mySlot === 'spectator'`, render the narrative in full-width read-only mode with no input area and a "You are watching" header. |
| 4.5.5 | FE | `frontend/src/MultiplayerSession.jsx` (in `MultiplayerEntry`) | Add "Join as Spectator" option below the Connect button (small link). Sets `desiredSlot = 'spectator'` in the join payload. |

---

### Story 4.6 — Host-to-Guest Session Transfer

**Acceptance Criteria:**
- The host can click "Transfer Host to [guest name]" in the lobby or play view
- After transfer: the guest becomes the host slot, the host becomes the guest slot
- `MultiplayerConfig.host_character` and `guest_character` are swapped
- Both players' WebSocket slots are updated; they receive a `slot_reassigned` event
- Transfer only available in LOBBY status (to avoid active-turn complications)

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.6.1 | BE | `backend/session_manager.py` | Add `async def transfer_host(room_code)`. Swaps `rt.players[HOST]` ↔ `rt.players[GUEST]` and `rt.connections[HOST]` ↔ `rt.connections[GUEST]`. Updates player slots. Persists character swap to `state.multiplayer`. |
| 4.6.2 | BE | `backend/main.py` | Handle `transfer_host` WS message (host only, LOBBY status). Call `session_manager.transfer_host()`. Broadcast `{"type": "slot_reassigned", "host_slot": old_guest_display_name, ...}` followed by full `session_state`. |
| 4.6.3 | FE | `frontend/src/MultiplayerLobby.jsx` | In `HostControls`, add "Transfer Host to [guest_name]" button (visible only when guest is joined). `onClick` sends `{ type: 'transfer_host' }` via WS. |
| 4.6.4 | FE | `frontend/src/hooks/useMultiplayerSession.js` | Handle `slot_reassigned` message: update `assignedSlotRef`, save to sessionStorage, dispatch `self_assigned`. |

---

### Story 4.7 — Character Relationship Tracking

**Acceptance Criteria:**
- `MultiplayerConfig` gains a `relationship` field: label (string), strength (int 0–100), notes (string)
- The character sheet panel shows the relationship status between both characters
- The host can edit it via Director Mode-style inline editing in the character sheet panel
- The relationship is injected into the system prompt as a brief line in the party section

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.7.1 | SCHEMA | `backend/schema.py` | Add `class PartyRelationship(BaseModel): label: str = ""; strength: int = 50; notes: str = ""`. Add `relationship: PartyRelationship = Field(default_factory=PartyRelationship)` to `MultiplayerConfig`. |
| 4.7.2 | BE | `backend/prompt_builder.py` | In `_render_party()`, after rendering both character cards, append: `\n**Party Dynamic:** {relationship.label} (strength {relationship.strength}/100){'. ' + relationship.notes if relationship.notes else ''}` — only if `relationship.label` is non-empty. |
| 4.7.3 | BE | `backend/main.py` | Handle `update_relationship` WS message (host only). Update `state.multiplayer.relationship` via `mutate_state`. Broadcast updated `session_state`. |
| 4.7.4 | FE | `frontend/src/MultiplayerPlay.jsx` | In `CharacterSheetsPanel`, add a "Party Relationship" section below the two character cards. Show label, a visual strength bar, and notes. Host sees an edit icon; clicking opens inline inputs for label, strength slider, and notes textarea. "Save" sends `{ type: 'update_relationship', label, strength, notes }`. |

---

### Story 4.8 — Session Transcript Export

**Acceptance Criteria:**
- `GET /api/session/{room_code}/transcript` returns a plaintext Markdown document
- Format: session header (room code, date, characters), then alternating player action + GM response blocks
- OOC messages are included in an appendix if the `include_ooc=true` query param is set
- Frontend: "Download Transcript" button in the multiplayer play view header
- Button downloads the file as `{room_code}_transcript.md`

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 4.8.1 | BE | `backend/main.py` | Add `GET /api/session/{room_code}/transcript` route. Load campaign state. Build a Markdown string: `# {world_description or 'Tavern Tales'} — Session {room_code}\n\n`. For each turn (user+assistant pair): `\n\n---\n\n**{character_name}:** {action_text}\n\n{gm_response}`. Return as `StreamingResponse(text, media_type='text/markdown', headers={'Content-Disposition': f'attachment; filename="{room_code}_transcript.md"'})`. |
| 4.8.2 | BE | `backend/main.py` | In the transcript builder, if `include_ooc=True`, read the OOC log and append an `## Out-of-Character Chat\n` appendix section. |
| 4.8.3 | FE | `frontend/src/MultiplayerPlay.jsx` | In the header, add a "📄 Transcript" button (host and guest). `onClick`: `window.open('/api/session/{roomCode}/transcript', '_blank')`. |

---

## Epic 5: Narrative & Discovery Features

**Goal:** Add features that deepen single-player engagement and make story state more accessible.

**Estimated Team Size:** 1 full-stack developer  
**Depends On:** Epics 1–2 for polish; can be started in parallel otherwise.

---

### Story 5.1 — Chapter Summary View

**Goal:** Surface the already-computed hierarchical summaries to players.

**Acceptance Criteria:**
- A collapsible "Story So Far" panel appears at the top of the narrative view (below the header, above messages)
- It shows short summary, latest chapter summary, and arc summary in a collapsed `<details>` element
- Content updates after each turn if summaries are present in campaign state

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 5.1.1 | FE | `frontend/src/App.jsx` | Above the `messages.map` section in the narrative view, add: `{campaignState?.summaries?.short && <SummaryPanel summaries={campaignState.summaries} />}`. |
| 5.1.2 | FE | `frontend/src/App.jsx` | Create `SummaryPanel` component: a `<details className="mb-4 ...">` with `<summary>Story So Far</summary>`. Inside: short summary paragraph, then a list of chapter summaries (most recent 3), then arc summary if present. Each styled with `text-sm text-slate-300 italic`. |

---

### Story 5.2 — Story Bookmarks

**Acceptance Criteria:**
- A bookmark icon appears on hover over each GM message in the narrative view
- Clicking it opens a small popover to add a tag (optional, max 60 chars) and "Bookmark" button
- Bookmarks are stored in `CampaignState.bookmarks: list[Bookmark]` (new schema field)
- A "Bookmarks" section in the sidebar lists all bookmarks; clicking one scrolls to the message
- Bookmarks can be removed with a × button

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 5.2.1 | SCHEMA | `backend/schema.py` | Add `class Bookmark(BaseModel): msg_id: str; tag: str = ""; created_at: str`. Add `bookmarks: list[Bookmark] = Field(default_factory=list)` to `CampaignState`. |
| 5.2.2 | BE | `backend/main.py` | Add `POST /api/campaign/{id}/bookmark` with body `{msg_id, tag}`. Adds a `Bookmark` to state via `mutate_state`. Returns updated bookmarks list. |
| 5.2.3 | BE | `backend/main.py` | Add `DELETE /api/campaign/{id}/bookmark/{msg_id}`. Removes bookmark from state. |
| 5.2.4 | FE | `frontend/src/App.jsx` | On `group` hover of each assistant message block (already has `group relative`), show a `🔖` button absolutely positioned. Clicking opens a small popover with a tag input + "Bookmark" button. Calls `POST /api/campaign/{id}/bookmark`. |
| 5.2.5 | FE | `frontend/src/App.jsx` | In the sidebar, add a "Bookmarks" section below the Lorebook section. Maps `campaignState.bookmarks` to a list. Each item: tag (or message preview), × remove button. Clicking an item calls `document.getElementById(msg_id)?.scrollIntoView()` — requires adding `id={m.id}` to message divs. |

---

### Story 5.3 — Player Journal / Notes

**Acceptance Criteria:**
- A "My Notes" textarea appears in a new sidebar section (collapsed by default)
- Notes are stored in `CampaignState.player_notes: str = ""` (new field, AI-invisible)
- Notes auto-save to backend on blur (debounced 2s)
- Notes are included in campaign export/import
- `player_notes` is explicitly excluded from `_build_system_prompt` — never injected into the prompt

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 5.3.1 | SCHEMA | `backend/schema.py` | Add `player_notes: str = ""` to `CampaignState`. |
| 5.3.2 | BE | `backend/main.py` | In the PATCH state handler, allow `player_notes` as a patchable field. Ensure it is not referenced anywhere in `prompt_builder.py`. |
| 5.3.3 | FE | `frontend/src/App.jsx` | In the sidebar, add a `<details>` section "My Notes". Inside: a `<textarea>` with the current `campaignState.player_notes`. On `onBlur`, call `pushStatePatch({ player_notes: value }, s => { s.player_notes = value; }, 'Update notes')`. |

---

### Story 5.4 — Location Graph (World Map)

**Acceptance Criteria:**
- Campaign state gains `visited_locations: list[LocationNode]` where `LocationNode = { name, first_visited_turn, connections_to: list[str] }`
- The extraction step attempts to infer new location names from the `location` field of `StateDelta`
- A "World Map" panel in the sidebar renders a simple text-based list of visited locations with connections indicated by indentation or arrows
- Full interactive graph (d3 / vis.js) is out of scope for v2 — a formatted text list is acceptable

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 5.4.1 | SCHEMA | `backend/schema.py` | Add `class LocationNode(BaseModel): name: str; first_visited_turn: int = 0; connections_to: list[str] = Field(default_factory=list)`. Add `visited_locations: list[LocationNode] = Field(default_factory=list)` to `CampaignState`. |
| 5.4.2 | BE | `backend/state_manager.py` | In `apply_state_delta`, when `delta.location` is non-empty and differs from the current player location, check if it already exists in `visited_locations`. If not, append a new `LocationNode`. Record a connection from the previous location to the new one. |
| 5.4.3 | FE | `frontend/src/App.jsx` | In the sidebar, add a "World Map" section below Lorebook. Renders `campaignState.visited_locations` as a simple list: `• {location.name}` with sub-items for connections. Style: `text-xs text-slate-300`. |

---

### Story 5.5 — Inline Dice Roller UI

**Acceptance Criteria:**
- A "🎲 Roll" button opens a popover in the action area
- The popover shows: attribute selector (from player stats), a "Roll d20" button, and the current modifier
- Clicking "Roll d20" sends a request to `GET /api/campaign/{id}/preview_roll?stat=Health` which returns the roll result (without consuming a turn)
- The roll result is displayed in the popover theatrically
- An optional "Use this roll in my action" button pre-fills the action textarea with "I roll [outcome] for [stat]."

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 5.5.1 | BE | `backend/main.py` | Add `GET /api/campaign/{id}/preview_roll?stat={stat_name}` route. Load state, find stat value, compute modifier. Call `game_rules.resolve_action(action_text=f"roll {stat_name}", state=state)`. Return the `ActionResolution`. This does NOT save any state — it's read-only. |
| 5.5.2 | FE | `frontend/src/App.jsx` | Add a "🎲 Roll" button in the action area (next to Quick Actions toggle). Clicking opens a popover with: a `<select>` of current player stats, a "Roll d20" button. On roll: `apiFetch('/api/campaign/{id}/preview_roll?stat={selected}')`. Display result: roll value, modifier, outcome label with icon. |
| 5.5.3 | FE | `frontend/src/App.jsx` | Add "Insert into Action" button in the popover that sets `setInput(current_input + ` [Roll result: ${outcome} on ${stat}]`)`. |

---

### Story 5.6 — Ambient Audio Player

**Acceptance Criteria:**
- A small audio control appears in the play view header
- Options: Off, Tavern (gentle crowd noise), Forest (wind and birds), Dungeon (drips and distant echoes), Storm (rain and thunder)
- Audio files are served as static assets from `frontend/public/audio/`
- Audio loops seamlessly; volume is controllable via a slider
- Selection persists in localStorage `tt_audio`
- No audio plays by default

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 5.6.1 | FE | `frontend/public/audio/` | Source or create 4 royalty-free ambient loops (OGG or MP3, ~1–2 MB each): tavern.ogg, forest.ogg, dungeon.ogg, storm.ogg. |
| 5.6.2 | FE | `frontend/src/App.jsx` | Add `audioTrack` and `audioVolume` state (initialized from localStorage). Add a `useRef` for the `<audio>` element. In the header, render a small `<select>` for track selection and a `<input type="range">` for volume. |
| 5.6.3 | FE | `frontend/src/App.jsx` | `useEffect` on `audioTrack`: if non-null, set `audioRef.current.src`, call `.play()`, set `.loop = true`. On track change or component unmount, call `.pause()`. |

---

## Epic 6: Infrastructure & Stability

**Goal:** Close reliability gaps in error handling, cleanup, and configuration.

**Estimated Team Size:** 1 backend developer  
**Blocks:** Nothing downstream; can be worked in parallel with any other epic.

---

### Story 6.1 — Session Cleanup Background Task

**Acceptance Criteria:**
- A background task registered on FastAPI startup calls `session_manager.cleanup_expired_sessions()` every 30 minutes
- Sessions paused for > 24 hours are archived
- A log message is emitted listing how many sessions were cleaned up

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.1.1 | BE | `backend/main.py` | In the `@app.on_event("startup")` handler (or `lifespan` context), launch `asyncio.create_task(_session_cleanup_loop())`. |
| 6.1.2 | BE | `backend/main.py` | `async def _session_cleanup_loop()`: `while True: await asyncio.sleep(1800); removed = await session_manager.cleanup_expired_sessions(); if removed: log.info("Cleaned up %d expired session(s)", removed)`. |

---

### Story 6.2 — Memory Store Error Isolation

**Acceptance Criteria:**
- `memory.add_memory()` and `memory.retrieve_relevant_memories()` are wrapped in `try/except` in the chat handler
- If memory fails, the turn proceeds without memories (degraded mode); a warning is logged
- The error is surfaced to the user as an amber banner ("Memory store unavailable — this turn will not use past memories") rather than a 500

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.2.1 | BE | `backend/main.py` | In the chat stream handler, wrap the `memory.retrieve_relevant_memories()` call in `try/except Exception as e: log.warning("Memory retrieval failed: %s", e); retrieved_memories = []`. |
| 6.2.2 | BE | `backend/main.py` | In the post-turn extraction step, wrap `memory.add_memory()` in `try/except Exception as e: log.warning("Memory write failed: %s", e)`. |
| 6.2.3 | BE | `backend/main.py` | If memory retrieval failed, include `"memory_warning": true` in the `start` SSE event. Frontend reads this and shows an amber `useBanner` toast. |

---

### Story 6.3 — Rate Limit Feedback

**Acceptance Criteria:**
- When a 429 is returned, the error message reads: "Too many requests — please wait {N} seconds and try again."
- The backend includes a `Retry-After` header on 429 responses
- The frontend reads `Retry-After` and automatically re-enables the Send button after that duration

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.3.1 | BE | `backend/rate_limit.py` | In the `chat_rate_limit` dependency, when raising `HTTPException(429)`, include `headers={"Retry-After": "10"}` (or compute remaining seconds from the token bucket). |
| 6.3.2 | FE | `frontend/src/lib/api.js` | In `apiFetch`, if response status is 429, read `response.headers.get('Retry-After')`. Return a structured error object with `{ rateLimited: true, retryAfter: N }`. |
| 6.3.3 | FE | `frontend/src/App.jsx` | In `handleSend`, if the error is `rateLimited`, set a `retryAfterSeconds` state. Show "Rate limited — retrying in {N}s" in the banner. Use a `useEffect` countdown that re-enables the button when `retryAfterSeconds` reaches 0. |

---

### Story 6.4 — Ollama Stream Recovery

**Acceptance Criteria:**
- If the streaming connection to Ollama drops mid-generation, the partial content is preserved in the message
- The message is flagged as `partial = True` in the database
- A recovery banner offers: "The AI connection dropped mid-response. You can → Continue to extend it, or ↻ Reroll to try again."

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.4.1 | BE | `backend/main.py` | In the streaming chat handler, wrap the inner token loop in `try/except (httpx.RemoteProtocolError, httpx.ReadError, asyncio.CancelledError)`. On exception: save the partial message with `partial=True`. Emit a final SSE `{"type": "error", "partial": true, "message": "Connection to AI dropped."}`. |
| 6.4.2 | FE | `frontend/src/App.jsx` | In the `onError` SSE callback, check if `event.partial === true`. If so, show a special banner variant with Continue and Reroll buttons inline (not just the toast). |

---

### Story 6.5 — Multiplayer GENERATING State Recovery on Restart

**Acceptance Criteria:**
- After server restart, any session with `paused_status_before = GENERATING` is corrected to the appropriate `*_TURN` status (the turn that would have followed the interrupted generation)
- A log message is emitted: "Corrected session {code} from GENERATING-before-pause to HOST_TURN/GUEST_TURN"

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.5.1 | BE | `backend/session_manager.py` | In `initialize()`, after setting `runtime.paused_status_before = state.multiplayer.session_status`, add: `if runtime.paused_status_before == SessionStatus.GENERATING: next_slot = PlayerSlot.GUEST if state.multiplayer.starting_slot_this_round == PlayerSlot.HOST else PlayerSlot.HOST; runtime.paused_status_before = SessionStatus.HOST_TURN if next_slot == PlayerSlot.HOST else SessionStatus.GUEST_TURN; log.info("Corrected GENERATING->pause for session %s to %s", runtime.room_code, runtime.paused_status_before)`. |

---

### Story 6.6 — Summarizer Cadence Configuration

**Acceptance Criteria:**
- `RulesConfig` gains `summary_short_interval: int = 5` and `summary_chapter_interval: int = 20`
- These values are used by `summarizer.py` instead of hardcoded constants
- Campaign creator exposes these as an "Advanced" setting: "Summarize every [N] turns"

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.6.1 | SCHEMA | `backend/schema.py` | Add `summary_short_interval: int = 5` and `summary_chapter_interval: int = 20` to `RulesConfig`. |
| 6.6.2 | BE | `backend/summarizer.py` | Replace hardcoded `5` and `20` constants with reads from `state.rules.summary_short_interval` and `state.rules.summary_chapter_interval`. |
| 6.6.3 | FE | `frontend/src/CampaignCreator.jsx` | In the Advanced section, add a "Summarize story every [N] turns" `<select>` with options 3 / 5 / 10 / 20 / Never. Default 5. Pass as part of the campaign init payload. |

---

### Story 6.7 — Preference System Enhancements

**Acceptance Criteria:**
- Each preference profile in the profiles list shows which campaigns it is linked to (reverse lookup)
- The Quick Setup preference form in MultiplayerEntry has a "Save as Profile" button that opens a name-input and calls `POST /api/preferences/profiles` with the generated profile
- A merge preview modal is available from the lobby before both players ready up, showing hypothetical merged output if the partner's profile shape is similar

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 6.7.1 | BE | `backend/main.py` | In `GET /api/preferences/profiles`, cross-reference with all campaigns to find which campaign IDs reference each `profile_id`. Include `linked_campaigns: list[str]` in each profile summary response. |
| 6.7.2 | FE | `frontend/src/PreferenceProfiles.jsx` | In the profile list view, show `{profile.linked_campaigns?.length > 0 && <span>Used in {profile.linked_campaigns.length} campaign(s)</span>}`. |
| 6.7.3 | FE | `frontend/src/MultiplayerSession.jsx` (in `MultiplayerEntry`) | In `QuickPreferenceForm`, after the Apply button, add "Save as Profile" button. Clicking opens a `<dialog>` or inline form with a profile name input. On submit, calls `POST /api/preferences/profiles` with the generated profile object. Shows "Saved!" on success. |

---

## Epic 7: Accessibility & Mobile

**Goal:** Make the app usable via keyboard and on mobile devices; add basic screen reader support.

**Estimated Team Size:** 1 frontend developer  
**Blocks:** Nothing. Can be done entirely in parallel.

---

### Story 7.1 — Keyboard Navigation & Focus Management

**Acceptance Criteria:**
- All interactive elements have visible focus rings (the existing Tailwind `focus:ring-2 focus:ring-fantasy-accent/50` is applied consistently)
- Tab order in the campaign list follows: campaign title → rename → host → delete
- The modal confirmation dialog traps focus while open
- Escape closes modals, popovers, and the sidebar

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 7.1.1 | FE | `frontend/src/App.jsx` | Audit all `<button>` elements that lack `focus:ring` classes. Add `focus:outline-none focus:ring-2 focus:ring-fantasy-accent/50` to any missing. |
| 7.1.2 | FE | `frontend/src/components/ModalProvider.jsx` | Implement focus trap: on modal open, store `document.activeElement` and focus the first focusable element inside the modal. On Tab/Shift+Tab, cycle within modal. On close, restore focus. |
| 7.1.3 | FE | `frontend/src/App.jsx` | Add `useEffect` for `Escape` key: close sidebar, inspector, or any open popover. |

---

### Story 7.2 — Screen Reader & Color Accessibility

**Acceptance Criteria:**
- The narrative message list has `aria-live="polite"` so completed responses are announced
- Connection status indicators include a visually-hidden text label (`sr-only` class)
- The token context bar has `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`
- All icon-only buttons have `aria-label` attributes

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 7.2.1 | FE | `frontend/src/App.jsx` | Add `aria-live="polite" aria-atomic="false"` to the message list container `<div>`. |
| 7.2.2 | FE | `frontend/src/MultiplayerPlay.jsx` | In `RosterPanel`, add `<span className="sr-only">{p?.is_connected ? 'connected' : 'disconnected'}</span>` after each status dot. |
| 7.2.3 | FE | `frontend/src/App.jsx` | Add `role="progressbar" aria-valuenow={ctx} aria-valuemin={0} aria-valuemax={100} aria-label="AI memory usage"` to the token bar container div. |
| 7.2.4 | FE | All button elements | Audit `<button>` elements with only emoji or icon content. Add `aria-label="..."` to each: e.g., the `?` help button, the `✎` rename button, the `✗` delete button. |

---

### Story 7.3 — Mobile-Optimized Layout

**Acceptance Criteria:**
- The single-player sidebar is accessible on mobile via a bottom sheet (swipe up) rather than the current left-side drawer
- The multiplayer play view renders as a full-width single column on screens < 768px, with the OOC and roster panels accessible via tabs below the narrative
- The action textarea stays anchored to the bottom of the viewport on mobile (position: sticky)
- The "State" toggle button on mobile is replaced with a floating action button in the bottom-right corner

**Tasks:**

| # | Type | File | Change |
|---|------|------|--------|
| 7.3.1 | FE | `frontend/src/App.jsx` | On mobile (< `md` breakpoint), change the sidebar from a left-side slide-in to a bottom sheet. Add `transform translate-y-0/translate-y-full` transition class based on `sidebarOpen`. The overlay backdrop remains. |
| 7.3.2 | FE | `frontend/src/App.jsx` | Replace the "State" button in the mobile header with a floating action button (`fixed bottom-20 right-4 z-20 bg-fantasy-accent rounded-full w-12 h-12 shadow-lg`). |
| 7.3.3 | FE | `frontend/src/MultiplayerPlay.jsx` | Change the grid from `lg:grid-cols-[3fr_1fr]` to a single-column layout on `< lg`. Below the narrative and input, add a tab bar: "Party | OOC" that switches which panel is visible below the input. |
| 7.3.4 | FE | `frontend/src/App.jsx` | Add `position: sticky; bottom: 0` to the input area container so it stays in view as the narrative scrolls on mobile. |

---

## Schema Change Summary

All schema changes are additive (default values provided). No migration required.

| Field | Model | Type | Default |
|-------|-------|------|---------|
| `has_archived_multiplayer` | `CampaignSummary` | `bool` | `False` |
| `player_notes` | `CampaignState` | `str` | `""` |
| `bookmarks` | `CampaignState` | `list[Bookmark]` | `[]` |
| `visited_locations` | `CampaignState` | `list[LocationNode]` | `[]` |
| `turn_timer_seconds` | `MultiplayerConfig` | `int \| None` | `None` |
| `simultaneous_mode` | `MultiplayerConfig` | `bool` | `False` |
| `relationship` | `MultiplayerConfig` | `PartyRelationship` | factory |
| `summary_short_interval` | `RulesConfig` | `int` | `5` |
| `summary_chapter_interval` | `RulesConfig` | `int` | `20` |
| `BOTH_ACTING` | `SessionStatus` | enum value | — |

---

## New API Endpoints Summary

| Method | Route | Epic | Description |
|--------|-------|------|-------------|
| GET | `/api/health` | 2 | Ollama connectivity check |
| GET | `/api/session/{code}/exists` | 3 | Room code validation |
| POST | `/api/campaign/{id}/convert_to_solo` | 3 | Strip multiplayer config |
| POST | `/api/campaign/{id}/bookmark` | 5 | Add a story bookmark |
| DELETE | `/api/campaign/{id}/bookmark/{msg_id}` | 5 | Remove a bookmark |
| GET | `/api/campaign/{id}/preview_roll` | 5 | Read-only dice roll preview |
| GET | `/api/session/{code}/transcript` | 4 | Download session as Markdown |

---

## New WebSocket Message Types Summary

| Type | Direction | Epic | Description |
|------|-----------|------|-------------|
| `set_starting_slot` | Client→Server | 3 | Host sets who goes first |
| `gift_turn` | Client→Server | 3 | Host passes floor without action |
| `request_reroll` | Client→Server | 3 | Request regeneration of last response |
| `request_continue` | Client→Server | 3 | Request continuation of last response |
| `update_relationship` | Client→Server | 4 | Update party relationship (host) |
| `set_turn_timer` | Client→Server | 4 | Set/change turn timer (host) |
| `set_simultaneous_mode` | Client→Server | 4 | Toggle simultaneous action mode (host) |
| `transfer_host` | Client→Server | 4 | Transfer host rights to guest |
| `slot_reassigned` | Server→Client | 4 | Notify of host transfer |
| `ooc_hydrate` | Server→Client | 3 | Send OOC log on reconnect |

---

## New npm Dependencies

| Package | Story | Purpose |
|---------|-------|---------|
| `qrcode.react` | 4.1 | QR code generation for room code sharing |

No new Python packages are expected. `apscheduler` is optional for 6.1 (an asyncio task loop is preferred and sufficient).

---

## Suggested Development Order

Given the dependency graph, the recommended implementation sequence for a 2-developer team is:

**Phase 1 (Week 1–2) — Foundation:**
- Dev A: Epic 1 (all stories — frontend only, parallelizable)
- Dev B: Epic 6 (infrastructure fixes — backend only, no frontend needed)

**Phase 2 (Week 3–4) — Onboarding + Multiplayer Core Part 1:**
- Dev A: Epic 2 (world creation improvements)
- Dev B: Epic 3, Stories 3.1–3.5 (kickoff, narrative, character sheet, reconnect)

**Phase 3 (Week 5–6) — Multiplayer Core Part 2:**
- Dev A: Epic 3, Stories 3.6–3.11 (OOC, turns, session control, discovery)
- Dev B: Epic 7 (accessibility and mobile — independent)

**Phase 4 (Week 7–9) — New Features:**
- Dev A + Dev B: Epic 4 (multiplayer new features — can be split by story)

**Phase 5 (Week 10–11) — Narrative Features:**
- Dev A or B: Epic 5 (single-player narrative features — independent)

---

## Testing Requirements

All backend stories require tests. Frontend stories do not require new tests unless they introduce new API interactions not covered by existing mocks.

Backend test files to update or create:
- `backend/tests/test_multiplayer_api.py` — Stories 3.1, 3.2, 3.4, 3.5, 3.7, 3.8
- `backend/tests/test_session_manager.py` — Stories 3.5, 3.6, 3.10, 4.3, 4.6
- `backend/tests/test_chat_flow.py` — Story 5.5 (preview roll)
- `backend/tests/test_multiplayer_api.py` — Story 4.8 (transcript)
- New: `backend/tests/test_turn_timer.py` — Story 4.3
- New: `backend/tests/test_simultaneous_mode.py` — Story 4.4

The `check.ps1` full quality gate must pass before any story is marked complete.
