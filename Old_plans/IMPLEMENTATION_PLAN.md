# Tavern Tales Reborn — Implementation Plan

**Source audit:** [AUDIT_REPORT.md](AUDIT_REPORT.md)
**Plan status:** APPROVED — ready to execute.
**Approved by:** Matthew Schultz, 2026-04-23
**Executor:** Claude (this agent)

---

## 0. Decisions locked in from Q&A

| # | Decision | Impact |
|---|---|---|
| D1 | **Start fresh.** Legacy `campaign_states.json` + existing chroma data are not migrated. On first startup of the new version, the old file is renamed to `campaign_states.json.legacy.bak` and a warning is logged; existing chroma collections are untouched (leftover data, not used). | No migration code; cleaner schema. |
| D2 | **Utility model (extraction/summarization) is configurable at world creation.** Default fallback chain: `llama3.1:8b-instruct` → `qwen2.5:7b-instruct` → `llama3:8b` → GM model. Both GM model and utility model are selectable in the Campaign Creator UI. | Adult-content tolerant (analytical tasks); clean JSON; user-controllable. |
| D3 | **Full refactor — backend owns system-prompt assembly.** Frontend sends only `{user_message, campaign_id}` (plus per-request options). Backend constructs prompt from persisted state every turn. | Removes the #1 coherence bug; simplifies frontend. |
| D4 | **Test harness is in scope.** pytest + mocked Ollama, snapshot tests for prompt assembly. | Regressions caught automatically. |
| D5 | **World-gen default switched to general creative model.** Default: `llama3.1:8b-instruct`. NSFW tune (`fluffy/l3-8b-stheno-v3.2:latest`) behind an opt-in checkbox on Campaign Creator. | Safer default; explicit user consent for NSFW generation. |
| D6 | **Single approval, execute all four phases.** Pause only if a phase hits a blocker I cannot resolve. | Maximum throughput; final review at end. |
| D7 | **Mobile responsiveness is out of scope.** Desktop-first only. | UX tasks related to mobile skipped. |

---

## 1. Target architecture (post-refactor)

```
┌──────────────────────────────┐          ┌─────────────────────────────────┐
│  Frontend (React, thin)      │          │  Backend (FastAPI)              │
│  ─────────────────────────   │          │  ────────────────────────────   │
│  • Chat UI / Director mode   │  HTTP    │  main.py          (routes)      │
│  • Sends: user_msg +         │  JSON/   │  prompt_builder.py (NEW)        │
│    campaign_id + options     │  SSE     │  summarizer.py    (NEW)         │
│  • Receives: stream +        │ ◄──────► │  extraction.py    (validated)   │
│    state snapshot + stats    │          │  state_manager.py (per-camp)    │
│  • AbortController for stop  │          │  memory.py        (per-camp     │
│  • Token meter, modals,      │          │                    collections) │
│    memory inspector          │          │  model_resolver.py (NEW)        │
│                              │          │  tokenizer.py     (NEW)         │
│                              │          │  schema.py        (NEW, Pydantic)│
│                              │          │  logging_config.py (NEW)        │
└──────────────────────────────┘          └─────────────────────────────────┘
                                                        │
                                                        ├── Ollama (localhost:11434)
                                                        │   • GM model (streaming)
                                                        │   • Utility model (JSON, summary)
                                                        │
                                                        ├── states/{campaign_id}.json
                                                        │   (per-campaign, atomic writes,
                                                        │    asyncio.Lock per id)
                                                        │
                                                        └── chroma_db/
                                                            (one collection per campaign)
```

---

## 2. New campaign-state schema (v2)

```jsonc
{
  "schema_version": 2,
  "campaign_id": "campaign_...",
  "created_at": "2026-04-23T12:00:00Z",
  "models": {
    "gm": "fluffy/l3-8b-stheno-v3.2:latest",
    "utility": "llama3.1:8b-instruct",
    "nsfw_world_gen": false
  },
  "player": {
    "name": "Matt",
    "location": "...",
    "stats": { "Health": 100, "Gold": 50 },
    "inventory": ["Rusty Sword"]
  },
  "npcs": [ { "name": "...", "disposition": "Friendly|Neutral|Suspicious|Hostile", "secrets_known": [...] } ],
  "lorebook": { "Claiming": "..." },
  "world_description": "...",
  "starting_scene": "...",
  "messages": [
    { "id": "msg_01H...", "role": "user|assistant", "content": "...", "timestamp": "..." }
  ],
  "summaries": {
    "short":    "Rolling summary of last ~20 turns (updated every 5 turns).",
    "chapters": [ { "start_turn": 1, "end_turn": 20, "text": "..." } ],
    "arc":      "Long-term campaign arc summary (milestones)."
  },
  "side_effects": {
    "msg_01H...": {
      "memory_ids": ["..."],
      "state_delta": { /* reversible extraction result */ }
    }
  },
  "stat_bounds": {
    "Health": { "min": 0, "max": 9999 },
    "Gold":   { "min": 0, "max": 999999 }
  },
  "sampling_overrides": { /* optional, overrides ollama_client defaults */ }
}
```

---

## 3. Task inventory (quick-reference table)

Legend: **Phase** A=coherence, B=state, C=UX, D=robustness. **Deps** = task IDs that must be complete first.

| ID  | Title                                           | Phase | Deps        | Audit refs       |
|-----|-------------------------------------------------|-------|-------------|------------------|
| A1  | Pydantic schema module                          | A     | —           | 2.7, 2.12, 4.7   |
| A2  | Tokenizer utility                               | A     | —           | 1.3              |
| A3  | Model resolver with fallback chain              | A     | —           | 2.17, D2         |
| A4  | Per-campaign atomic state manager               | A     | A1          | 2.2, 2.3, 2.4, 4.6, 4.8 |
| A5  | Ollama client sampling fix + error-channel      | A     | —           | 1.2, 2.19, 4.2   |
| A6  | Prompt builder (full state injection)           | A     | A1, A2      | 1.1, 1.3, 1.6    |
| A7  | Hierarchical progressive summarizer             | A     | A1, A3, A4  | 1.4, 4.4         |
| A8  | Validated extraction with utility model         | A     | A1, A3, A4  | 2.5, 2.6, 2.7, 1.10, 4.5, 4.7 |
| A9  | Chat endpoint rewrite (backend owns prompt)     | A     | A4, A5, A6  | 1.1, 1.7, 2.2, 2.20, 4.1, 4.10 |
| A10 | Kickoff endpoint with explicit user turn        | A     | A9          | 1.9              |
| A11 | Campaign creator UI — model pickers + NSFW      | A     | A1          | 2.16, 2.17, 4.20, D2, D5 |
| A12 | Frontend thin-client refactor                   | A     | A9, A10     | 1.1, 4.1         |
| B1  | Message IDs + side-effect tracking              | B     | A4, A8      | 2.8, 2.9, 4.9    |
| B2  | Regenerate + delete with rollback               | B     | B1          | 2.8, 2.9, 4.9    |
| B3  | Per-campaign chroma collection + proper delete  | B     | A4          | 2.10, 4.8        |
| B4  | Override-state schema validation                | B     | A1, A4      | 2.1              |
| B5  | Stat clamp + absolute-vs-delta guard            | B     | A1, A8      | 2.6              |
| B6  | NPC disposition normalization                   | B     | A1, A8      | 2.7              |
| B7  | Dynamic stat schema (new stats allowed)         | B     | A1, A8      | 2.5              |
| C1  | Stop button / stream cancellation               | C     | A9, A12     | 4.11             |
| C2  | Continue button / continuation endpoint         | C     | A9, A12     | 4.12             |
| C3  | Token/context meter UI                          | C     | A6, A12     | 4.13             |
| C4  | Memory inspector panel                          | C     | A6, A12     | 4.14             |
| C5  | Styled modal component + replace confirm/alert  | C     | A12         | 4.15             |
| C6  | Campaign export/import                          | C     | A4, B3      | 4.16             |
| C7  | Lore/NPC editor in director mode                | C     | A12, B4     | 4.17             |
| C8  | Error banner system                             | C     | A12         | 4.19, 2.13       |
| C9  | Persisted model preference (localStorage)       | C     | A12         | 4.20, 2.16       |
| C10 | Director-mode undo stack                        | C     | A12         | 3.*              |
| C11 | Structured logging (replace print)              | C     | —           | 4.22             |
| D1  | CORS allowlist                                  | D     | —           | 2.15, 4.21       |
| D2  | pytest harness + mocked Ollama                  | D     | A1..A9      | 4.24, D4         |
| D3  | Request tracing IDs (middleware)                | D     | C11         | 4.23             |
| D4  | Rate limit + input size limits                  | D     | —           | 4.* (hardening)  |
| D5  | CLAUDE.md architecture reference                | D     | all         | — (developer UX) |

Total: 36 tasks across 4 phases.

---

## 4. Detailed task specs

Each task includes: **files**, **what**, **how**, **acceptance**. When executing, work top-to-bottom within a phase; cross-phase deps in the table above.

---

### Phase A — Coherence First

#### A1. Pydantic schema module
- **Files:** `backend/schema.py` (new).
- **What:** Typed models for the v2 state: `CampaignState`, `Player`, `NPC` (with `Disposition` enum `Friendly|Neutral|Suspicious|Hostile`), `Message`, `Summaries`, `ModelConfig`, `StatBounds`, `SamplingOverrides`. Include `SCHEMA_VERSION = 2`.
- **How:** Pydantic v2. `NPC.disposition: Disposition`. `Message.id: str` auto-generated via `uuid4` default factory. Validators for stat values (ints). `from_legacy(dict) -> CampaignState` helper returns `None` (we don't migrate) but documents the old shape for the startup warning.
- **Acceptance:** `python -c "from backend.schema import CampaignState; print(CampaignState.model_json_schema())"` prints the schema without error. All downstream modules import from here.

#### A2. Tokenizer utility
- **Files:** `backend/tokenizer.py` (new).
- **What:** Approximate token counter for prompt-budgeting. No heavy deps (tiktoken builds painfully on Windows).
- **How:** Heuristic: `ceil(len(text) / 4)` as baseline, with optional upgrade path if `tiktoken` happens to be installed (try-import). Expose `count_tokens(text: str) -> int` and `count_messages(msgs: list[dict]) -> int`.
- **Acceptance:** Unit test in D2 asserts counts are within ±15% of tiktoken gpt-4 counts on a fixture string.

#### A3. Model resolver with fallback chain
- **Files:** `backend/model_resolver.py` (new).
- **What:** Given a preferred model name (from campaign config), verify it's pulled in Ollama; if not, try fallbacks; if none pull, use the GM model and log a warning.
- **How:** Async function `resolve_utility_model(preferred: str, gm_fallback: str) -> str`. Queries `GET http://localhost:11434/api/tags`; caches the tag list for 60 s. Fallback chain for utility: `[preferred, 'llama3.1:8b-instruct', 'qwen2.5:7b-instruct', 'llama3:8b', gm_fallback]`. Returns first available. Separate `resolve_gm_model` just passes through (no fallback — GM must be chosen).
- **Acceptance:** Unit tested with mocked `/api/tags`. Logs warning when preferred unavailable.

#### A4. Per-campaign atomic state manager
- **Files:** `backend/state_manager.py` (rewrite).
- **What:** Replaces the single-file store with per-campaign files + async locks + atomic writes.
- **How:**
  - Path: `backend/states/{campaign_id}.json`. Create dir on import.
  - Startup: if legacy `backend/campaign_states.json` exists, rename to `campaign_states.json.legacy.bak` and log a one-line warning. Do not migrate.
  - Public API:
    - `async load_state(id) -> CampaignState | None`
    - `async save_state(state: CampaignState) -> None` (atomic: write to `.tmp`, fsync, `os.replace`)
    - `async list_campaigns() -> list[CampaignSummary]`
    - `async delete_campaign(id) -> None`
    - `async with campaign_lock(id):` context manager (dict of `asyncio.Lock` keyed by id; lazily created)
    - `async mutate_state(id, fn)` — takes a callback; handles load + lock + save so callers don't forget
  - Validation: on load, run through `CampaignState.model_validate`; on failure rename to `.corrupt-{ts}.bak` and return None with a logged error.
- **Acceptance:** Concurrent writes to same campaign serialize (test in D2); crash mid-write never yields empty file (interrupt-safe via tmp+replace); unknown campaign returns `None` (does not silently create).

#### A5. Ollama client sampling fix + error channel
- **Files:** `backend/ollama_client.py` (rewrite).
- **What:** New defaults, configurable overrides, error is no longer yielded as text.
- **How:**
  - Defaults: `temperature=0.8, repeat_penalty=1.15, top_p=0.9, top_k=40, min_p=0.05, num_predict=512, stop=["\nUser:", "\nPlayer:", "User:", "[END]"]` (remove the `"\n\n\n\n"` hack).
  - Signature: `async def stream_chat(messages, model, overrides: dict | None = None) -> AsyncGenerator[StreamEvent, None]` where `StreamEvent` is `{"type": "token"|"error"|"done", "data": ...}`. Callers route tokens to the frontend and handle errors explicitly.
  - Errors: connection/timeout/HTTP errors become `{"type": "error", ...}` events; never yielded as narration.
  - Track: total tokens emitted, stop-reason from Ollama's final JSON chunk (`done=true` has `done_reason`).
- **Acceptance:** Mocked-Ollama test asserts error path does not contaminate message buffer. Manual check: runaway `………` no longer observed with default sampling on `fluffy/l3-8b-stheno-v3.2`.

#### A6. Prompt builder
- **Files:** `backend/prompt_builder.py` (new).
- **What:** Assembles the full system prompt from live campaign state every turn.
- **How:**
  - `async build_prompt(state: CampaignState, user_message: str, window_budget_tokens: int = 6000) -> BuiltPrompt` where `BuiltPrompt = {messages: list, stats: PromptStats}`.
  - Blocks in order, each gated on non-empty:
    1. **Role rules** — dark-fantasy GM instruction. Constant from `prompt_templates.py`.
    2. **World description** — `state.world_description`.
    3. **Opening scene** — `state.starting_scene`.
    4. **Protagonist block** — name, location, stats (rendered as `Health: 100`), inventory.
    5. **Cast codex** — NPCs with disposition + secrets (secrets block marked `[GM-only knowledge]`).
    6. **Lorebook** — ALL entries, rendered as `[KEYWORD]: rule`. (No keyword-match filtering.)
    7. **Arc summary** — `state.summaries.arc` if present.
    8. **Chapter summaries** — last 3 chapters, oldest→newest.
    9. **Short summary** — `state.summaries.short`.
    10. **Relevant memories** — top K from vector search, deduped against messages already in the window.
  - Recent-message window: select messages from `state.messages` by token budget (reserve ~1,500 tokens for system prompt + 512 for response). Oldest-dropped-first.
  - Append user message as final turn (or prepend with assistant turn if this is kickoff — see A10).
  - `PromptStats`: per-block token count, total system tokens, total window tokens, response budget, model context window (looked up by name, with a map `{"llama3": 8192, "llama3.1:8b": 131072, ...}`, default 8192).
- **Acceptance:** Snapshot test (D2) asserts golden prompt for a fixture state. Manual check: player's name/stats/NPC list visible in the rendered prompt for every turn, not just kickoff.

#### A7. Hierarchical progressive summarizer
- **Files:** `backend/summarizer.py` (new). Remove the inline summarizer in `main.py`.
- **What:** Three-tier summary that never overwrites.
- **How:**
  - `async update_short_summary(state, utility_model)` — invoked every 5 turns. Prompt: `"Produce a factual 4-6 sentence summary of these events. Retain all major events, decisions, and objectives. Prior summary: {short}. New events: {messages since last short-update}."` Writes the new text back.
  - `async rollup_chapter(state, utility_model)` — invoked when short summary has grown to cover ~20 turns OR when `len(messages)` exceeds chapter threshold. Compresses the short summary + its window into a "chapter" {start_turn, end_turn, text} and resets short summary to empty.
  - `async update_arc(state, utility_model)` — invoked every 5 chapters OR on explicit milestone tag. Compresses chapter summaries into a single arc narrative. Chapters older than the 10th are dropped once folded into arc.
  - All three go through `model_resolver.resolve_utility_model(state.models.utility, state.models.gm)`.
- **Acceptance:** Unit test: feed synthetic 60-turn campaign; verify short, chapter, and arc all populated and non-overwriting.

#### A8. Validated extraction with utility model
- **Files:** `backend/extraction.py` (rewrite).
- **What:** State extraction uses the utility model, outputs validated Pydantic, supports dynamic stats, clamps and guards.
- **How:**
  - Output schema (Pydantic):
    ```python
    class StateDelta(BaseModel):
        stats_changes: dict[str, int] = {}
        location: str | None = None
        inventory_added: list[str] = []
        inventory_removed: list[str] = []
        npc_updates: list[NPCUpdate] = []
    ```
  - Prompt unchanged in intent but clarifies: "Return integers as DELTAS, not absolute values. Unknown stats may be introduced."
  - Clamping (task B5): if `|delta| > current * 10 and current > 0`, treat as suspicious — log + halve the delta.
  - NPC disposition normalized (task B6) via enum matching (substring: "hostile" → `Hostile`, "more suspicious" → `Suspicious`). Unknown → keep previous.
  - New stats: if extracted stat not in `player.stats`, add with starting value `0 + delta` and default bounds `{min: 0, max: 9999}`.
  - Returns `(delta: StateDelta, reversal: ReversalPatch)` — the reversal is the inverse to enable B2 rollback.
- **Acceptance:** Validation test: malformed JSON returns `StateDelta()` defaults. Stat explosion test: delta of +10000 on Health=100 gets capped/halved with a warning.

#### A9. Chat endpoint rewrite
- **Files:** `backend/main.py`.
- **What:** Backend owns prompt assembly. Frontend sends only `user_message` + `campaign_id` + options.
- **How:**
  - New request shape:
    ```python
    class ChatRequest(BaseModel):
        campaign_id: str
        user_message: str
        overrides: SamplingOverrides | None = None
    ```
  - Handler flow:
    1. Load state via A4; 404 if missing.
    2. Append user message (with new msg_id) to state.messages; persist.
    3. Retrieve top-K memories from chroma (campaign-scoped).
    4. Build prompt via A6.
    5. Stream via A5 (yield tokens only; handle error events separately).
    6. When stream completes: append assistant message with msg_id, persist; schedule background tasks: (a) add to memory, (b) extract state delta (A8) and store reversal in `side_effects[msg_id]`, (c) run summarizer hooks (A7) if turn-cadence triggers.
    7. Return final stream event `{type: "done", prompt_stats, new_state_snapshot, msg_id}` so frontend updates without a second fetch.
  - Stop mutating `req.messages` — always build a fresh list in the prompt builder.
  - Turn counting: drop `turn` from request entirely. Summarizer uses `len(messages)` as ground truth.
- **Acceptance:** Happy-path integration test in D2 hits the endpoint with mocked Ollama, asserts state updated once, memory added once, no duplicate history writes.

#### A10. Kickoff endpoint with explicit user turn
- **Files:** `backend/main.py`, `frontend/src/App.jsx`.
- **What:** Replace the system-only opening with a proper user→assistant exchange.
- **How:**
  - New endpoint `POST /api/campaign/{id}/kickoff` — server-side: build prompt (A6) with a synthetic user message `"Begin the scene."`, stream the GM's opening, persist as messages with IDs (user message retained so it's visible in `messages` but optionally hidden in UI).
  - Frontend: on load of a campaign with empty messages, call `/kickoff` instead of manually POSTing to `/chat/stream`. UI hides the synthetic `"Begin the scene."` user message (flag it in message metadata: `is_kickoff: true`).
- **Acceptance:** Kickoff run on fresh campaign produces a coherent narration (spot-check manually); `messages` array has two entries afterwards.

#### A11. Campaign creator UI — model pickers + NSFW toggle
- **Files:** `frontend/src/CampaignCreator.jsx`, `backend/main.py`.
- **What:** Let user choose GM model, utility model, and opt-in NSFW world-gen.
- **How:**
  - Two `<select>` dropdowns populated from `/api/models`: "Narrator Model (GM)" and "Utility Model (summary + state extraction)". Defaults: user's first available for GM, `llama3.1:8b-instruct` (or next available from fallback chain) for utility.
  - Checkbox: "Use uncensored creative model for world generation (NSFW)". When checked, world-gen uses `fluffy/l3-8b-stheno-v3.2:latest`; when unchecked, uses `llama3.1:8b-instruct`.
  - Both models + NSFW flag persisted in `CampaignState.models` on `/api/campaign/init`.
  - `generate_world` endpoint picks model based on the NSFW flag passed in its request body.
- **Acceptance:** New campaign saves chosen models; world-gen respects NSFW toggle; existing default path still works for "create world with defaults."

#### A12. Frontend thin-client refactor
- **Files:** `frontend/src/App.jsx`.
- **What:** Strip system-prompt assembly from the frontend; use new chat endpoint shape.
- **How:**
  - Remove the `apiMessages.unshift({role: 'system', ...})` block and the `sysPrompt` construction in `handleKickoff`.
  - `handleSend` sends `{campaign_id, user_message}`; reads SSE stream; applies final `new_state_snapshot` from the `done` event.
  - `handleKickoff` becomes a single call to `/kickoff`.
  - Drop `contextWindow` slider from the UI — token budget is now server-side. (Replace with token meter in C3.)
  - Keep the Director-mode scaffolding for later C tasks.
- **Acceptance:** Frontend never references `world_description`, `starting_scene`, or system-prompt text. A grep for `"role: 'system'"` in the frontend returns zero results.

---

### Phase B — Trustworthy State

#### B1. Message IDs + side-effect tracking
- **Files:** `backend/schema.py`, `backend/main.py`, `backend/memory.py`, `backend/extraction.py`.
- **What:** Every message gets a UUID. Memory insertions and state deltas are recorded per-message so they can be reversed.
- **How:**
  - `Message.id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")`.
  - Memory writes include `msg_id` metadata on the chroma entry.
  - Extraction returns `(delta, reversal)`; handler records `state.side_effects[msg_id] = {memory_ids, reversal}`.
- **Acceptance:** After one turn, `state.side_effects[last_msg_id]` contains non-empty `memory_ids` and a `reversal` patch.

#### B2. Regenerate + delete with rollback
- **Files:** `backend/main.py`, `frontend/src/App.jsx`.
- **What:** Reverting a message reverses its side effects.
- **How:**
  - `DELETE /api/campaign/{id}/message/{msg_id}` — apply reversal patch, delete associated memories (by the stored `memory_ids`), remove message from `messages`, clear `side_effects[msg_id]`.
  - `POST /api/campaign/{id}/regenerate/{msg_id}` — delete target assistant message (via the delete handler's logic), then re-run generation from the previous user message.
  - Frontend `handleRegenerate` / `handleDelete` call these endpoints instead of splicing arrays locally.
- **Acceptance:** Integration test: user gains item "Sword" in msg X → delete msg X → inventory no longer contains "Sword"; chroma count decreased by the memory ids stored.

#### B3. Per-campaign chroma collection + proper delete
- **Files:** `backend/memory.py`.
- **What:** One chroma collection per campaign for clean lifecycle.
- **How:**
  - Collection name: `tt_campaign_{campaign_id}`.
  - `get_collection(campaign_id)` creates-if-missing.
  - `delete_campaign_memory(campaign_id)` calls `client.delete_collection(name=...)`.
- **Acceptance:** After `DELETE /api/campaigns/{id}`, no chroma collection matching that name exists.

#### B4. Override-state schema validation
- **Files:** `backend/main.py`.
- **What:** `PUT /api/state/{id}` validates the payload.
- **How:** Replace `request: dict` with `request: CampaignState`. Return 400 on validation failure. Strip `schema_version` mismatch protection: if incoming omits it, inject the current version.
- **Acceptance:** Malformed PUT returns 400, does not mutate disk.

#### B5. Stat clamp + absolute-vs-delta guard
- **Files:** `backend/extraction.py`, `backend/state_manager.py`.
- **Acceptance:** In state_manager merge, clamp final stat to `stat_bounds[stat]`. If incoming delta magnitude > `max(10, current * 10)` and current > 0, halve it and log a warning. Dynamic-added stat gets default bounds `{0, 9999}`.

#### B6. NPC disposition normalization
- **Files:** `backend/extraction.py` (or a small `normalizers.py`).
- **How:** Case-insensitive substring match against enum. Fall back: keep previous disposition and log. Applied after extraction, before merge.
- **Acceptance:** Unit test: prose values `"more suspicious"`, `"becomes hostile"`, `"HOSTILE"`, `"frend"` normalize to the correct enum or keep previous.

#### B7. Dynamic stat schema
- **Files:** `backend/extraction.py`, `backend/state_manager.py`.
- **How:** Already scaffolded in A8; B7 is the integration: when extraction returns a stat name not in `player.stats`, insert it with the delta applied on top of `0`, register in `stat_bounds` with defaults. Surface the new stat in the UI automatically (the sidebar already iterates `Object.entries(stats)`).
- **Acceptance:** After GM narrates a Sanity drop, `player.stats.Sanity` appears in the sidebar and the next turn's prompt includes it.

---

### Phase C — UX Polish

#### C1. Stop button
- **Files:** `frontend/src/App.jsx`, `backend/main.py`, `backend/ollama_client.py`.
- **How:** Frontend: `AbortController` on the fetch; a Stop button while `isStreaming`. Backend: on `StreamingResponse` client disconnect, cancel the Ollama httpx stream. Save partial content as that turn's assistant message (marked `partial: true` in metadata).
- **Acceptance:** Clicking Stop interrupts generation within 1 s; partial content is persisted.

#### C2. Continue button
- **Files:** `frontend/src/App.jsx`, `backend/main.py`.
- **How:** New `POST /api/campaign/{id}/continue` — reassembles prompt with an explicit directive to continue the last assistant message without repeating. Appends output to the existing message (same `msg_id`, extends `content`). Button appears when the last message's stop-reason was `length` (num_predict exhausted) OR the content does not end in sentence-terminating punctuation.
- **Acceptance:** After a clipped response, clicking Continue extends the message with a natural-feeling continuation.

#### C3. Token/context meter
- **Files:** `frontend/src/App.jsx`, `backend/main.py`.
- **How:** Backend's `done` event already includes `prompt_stats` (from A6). Frontend renders a small meter near the header: `[████████░░] 3,421 / 8,192 tokens (system 1,203 · history 2,218 · response 512)`.
- **Acceptance:** Meter updates after each turn; matches backend log output.

#### C4. Memory inspector panel
- **Files:** `frontend/src/App.jsx`, `backend/main.py`.
- **How:** New endpoint `GET /api/campaign/{id}/last_prompt` → returns the assembled prompt used on the most recent turn (cached in memory on the backend, not persisted). Director-mode-only side panel: collapsible sections for each prompt block + retrieved memories with their similarity scores + token counts per block.
- **Acceptance:** Panel shows exactly what was fed to the model on the last turn; useful as a debugging affordance.

#### C5. Styled modal component + replace confirm/alert
- **Files:** `frontend/src/components/Modal.jsx` (new), `frontend/src/App.jsx`, `frontend/src/CampaignCreator.jsx`.
- **How:** Small Tailwind modal (no new deps). Imperative API via a context provider: `const { confirm, alert } = useModal(); await confirm({title, message, confirmLabel, danger: true})`. Replace every `window.confirm` and `alert` usage.
- **Acceptance:** No calls to `confirm(` or `alert(` remain in frontend source (grep).

#### C6. Campaign export/import
- **Files:** `backend/main.py`, `frontend/src/App.jsx`.
- **How:**
  - `GET /api/campaign/{id}/export` returns a ZIP-ish JSON: `{state: ..., memories: [{document, metadata, id}, ...]}`.
  - `POST /api/campaign/import` accepts the same shape; generates new id; restores both.
  - UI: download-on-menu button; upload button prompting for file.
- **Acceptance:** Export then import produces a campaign whose state and memory counts match the source.

#### C7. Lore/NPC editor in director mode
- **Files:** `frontend/src/App.jsx`.
- **How:** In director mode, sidebar lore and NPC codex gain inline edit (pencil) + add + delete. Writes go through `PUT /api/state/{id}` (now validated — B4).
- **Acceptance:** Adding an NPC and a lore rule persists across reload; the next prompt includes them.

#### C8. Error banner system
- **Files:** `frontend/src/components/Banner.jsx` (new), `frontend/src/App.jsx`.
- **How:** Small toast-like banner at the top of the main area. Error context provider; dismissable; auto-dismiss on success. Hook into fetch failures across the app and into stream error events (A5).
- **Acceptance:** Killing the backend while a chat is open shows a visible banner rather than silent console.error.

#### C9. Persisted model preference
- **Files:** `frontend/src/App.jsx`.
- **How:** On change, `localStorage.setItem('tt_preferred_model', ...)`. On mount, prefer it if present in fetched list. (Only applies at world creation now — the model is baked into the campaign once chosen — so this actually applies to the CampaignCreator defaults.)
- **Acceptance:** Choosing model X, reloading, then opening CampaignCreator pre-selects X.

#### C10. Director-mode undo stack
- **Files:** `frontend/src/App.jsx`.
- **How:** Small in-memory stack (last 20) of `{type, before, after}` entries for stat/location/inventory/NPC/lore edits. `Ctrl+Z` or a visible Undo button reverts one step, which also PATCHes the backend.
- **Acceptance:** Editing a stat, then Ctrl+Z, restores the previous value both locally and on disk.

#### C11. Structured logging
- **Files:** `backend/logging_config.py` (new), `backend/main.py`, all backend modules.
- **How:** Configure `logging` with a formatter `%(asctime)s %(levelname)s [%(name)s] [campaign=%(campaign_id)s req=%(request_id)s] %(message)s`. Replace every `print(...)` with `log.info/debug/warning/error`. Attach campaign_id/request_id via `contextvars` + a `logging.Filter`.
- **Acceptance:** `grep -rn "print(" backend/` returns zero results (except tests).

---

### Phase D — Robustness

#### D1. CORS allowlist
- **Files:** `backend/main.py`.
- **How:** Replace `["*"]` with `["http://localhost:5173"]`; env var `TT_CORS_ORIGINS` allows override.
- **Acceptance:** Request from `http://evil.local` is rejected; the Vite dev server origin works.

#### D2. pytest harness + mocked Ollama
- **Files:** `backend/tests/` (new), `backend/pytest.ini` (new), `backend/requirements-dev.txt` (new).
- **How:**
  - `conftest.py`: fixtures for a temp state dir, a temp chroma dir, a mock Ollama server (FastAPI-in-thread on a random port, with scripted responses).
  - Test files: `test_schema.py`, `test_state_manager.py` (concurrency, atomicity), `test_prompt_builder.py` (snapshot), `test_summarizer.py`, `test_extraction.py`, `test_chat_flow.py` (integration), `test_memory.py`.
  - Snapshot library: `syrupy` (mature, JSON-friendly).
  - Coverage: aim for ~70% on backend modules touched in phases A/B.
- **Acceptance:** `pytest` runs green on a clean checkout. Prompt-builder snapshot test catches the original bug by failing if world_description is missing from any generated prompt.

#### D3. Request tracing IDs
- **Files:** `backend/main.py`, `backend/logging_config.py`.
- **How:** `@app.middleware("http")` assigns `request_id = uuid4().hex[:12]`, stores in a `contextvars.ContextVar`, echoes in `X-Request-Id` response header. Logging filter picks it up.
- **Acceptance:** Every log line includes a non-empty `req=...` tag; response header visible in browser devtools.

#### D4. Rate limit + input size limits
- **Files:** `backend/main.py`.
- **How:** `slowapi` dependency; 60 req/min per IP on `/api/chat/*`. Pydantic `constr(max_length=4000)` on `user_message`; reject oversized world-gen prompts (>2000 chars).
- **Acceptance:** Flood test yields 429s after the limit; oversized input yields 422.

#### D5. CLAUDE.md architecture reference
- **Files:** `CLAUDE.md` (new, repo root).
- **How:** Short doc: run-locally, key modules (~1 line each), how to add a new state field, how to add a new sampling parameter. This is a developer-UX artifact so I (and future agents) can orient fast.
- **Acceptance:** Document present, covers the four phases' major additions.

---

## 5. Execution notes (for me, the agent)

- **Commit cadence:** one commit per task (or per pair of tightly-coupled tasks). Commit messages prefixed `phase-a/`, `phase-b/`, etc.
- **Branch:** work on a new branch `refactor/llm-coherence` off `main`. Do not push unless explicitly asked.
- **Safety:** destructive changes (deleting legacy state file) are gated on the startup warning pattern — user sees the message, no data is actually deleted (`.legacy.bak` preserved).
- **Verification cadence:** after each phase, run `pytest` + do a smoke-test kickoff + one turn + one regen + one delete.
- **If blocked:** pause and report in plain text. Don't work around.
- **Deferred reading:** if I lose context, the minimum re-read list is this file + `schema.py` + `state_manager.py` + `prompt_builder.py`.
- **Do not touch without re-confirmation:** mobile layout, authentication, hosting/deploy concerns — all explicitly out of scope.

---

## 6. Out-of-scope (explicitly deferred)

- Mobile-responsive sidebar.
- Authentication / multi-user.
- Hosted deployment (Docker, systemd, etc.).
- Alternative LLM backends (OpenAI, Anthropic API, etc.) — Ollama-only for now.
- Voice/audio generation.
- Dice-roll / skill-check mechanics (mentioned in audit §3 as nice-to-have; deferred unless user adds it later).
- Image generation for scenes or NPCs.

---

**End of plan. Ready to execute on approval.**

---

## 7. Progress log (resume-safe)

**Status:** ALL PHASES COMPLETE. Ready for user review / commit.
**Branch:** `refactor/llm-coherence` — all work uncommitted (`git status` will show it). User has not approved a commit yet; do NOT commit without asking. Main branch remains untouched.
**Tests:** 45/45 passing (`pytest` from `backend/`).
**Live smoke:** passed — real Ollama (mistral-nemo) kickoff narrated correctly using injected context ("Tester", "Test Room", "Notebook", "green check mark"); turn-2 prompt verified to contain world / scene / protagonist / cast / lorebook blocks.

### 7.1 What's done

**Phase A — all 12 tasks complete.** Coherence refactor is in:

| Task | File(s) | Notes |
|------|---------|-------|
| A1 | `backend/schema.py` (new) | Pydantic v2 models, `SCHEMA_VERSION = 2`, `Disposition` enum, `Message.id` auto-UUID, `SamplingOverrides`, `StateDelta`, `BuiltPrompt`, `PromptStats`, `ReversalPatch`, `MessageSideEffects`. |
| A2 | `backend/tokenizer.py` (new) | Heuristic (~4 ch/token) with opportunistic tiktoken. `MODEL_CONTEXT_WINDOWS` map + substring lookup. |
| A3 | `backend/model_resolver.py` (new) | Tag-cache (60 s TTL) + fallback chain: `preferred → llama3.1:8b-instruct → qwen2.5:7b-instruct → llama3:8b → gm_fallback`. `DEFAULT_CREATIVE_MODEL` + `NSFW_CREATIVE_MODEL` constants. |
| A4 | `backend/state_manager.py` (rewrite) | Per-campaign `states/{id}.json`, atomic `tmp + fsync + os.replace`, per-id `asyncio.Lock`, `mutate_state(cb)` wrapper, `apply_state_delta` + `apply_reversal` with B5 suspicious-delta guard, B6 disposition normalization, B7 dynamic-stat support. Legacy `campaign_states.json` auto-renamed to `.legacy.bak` on startup. |
| A5 | `backend/ollama_client.py` (rewrite) | New defaults `repeat_penalty=1.15, temperature=0.8, top_k=40, min_p=0.05, num_predict=512`. Dropped the `"\n\n\n\n"` stop hack. Emits `StreamEvent` dicts: `token`/`error`/`done`. New `complete_json` + `complete_text` helpers for utility tasks. |
| A6 | `backend/prompt_builder.py` + `backend/prompt_templates.py` (new) | Full state injection every turn: role rules → world → scene → protagonist → cast → lorebook (all entries, no keyword filter) → arc → chapters → short summary → deduped memories. Token-budget-driven window. |
| A7 | `backend/summarizer.py` (new) | Three tiers (short @ every 5 turns, chapter @ every 20, arc when >5 chapters); never overwrites. Runs through `resolve_utility_model`. |
| A8 | `backend/extraction.py` (rewrite) | Utility-model JSON extraction; `StateDelta` Pydantic validation; delta-not-absolute guidance. |
| A9 | `backend/main.py` (rewrite) | Backend owns prompt. `/api/chat/stream` sends `start`/`token`/`error`/`done` ndjson events. Background task fires extraction + summarizer after stream completes. |
| A10 | `backend/main.py` | `/api/campaign/{id}/kickoff` with explicit synthetic user turn `"Begin the scene."`. |
| A11 | `frontend/src/CampaignCreator.jsx` (rewrite) | GM-model + utility-model dropdowns (with localStorage prefs), NSFW toggle, error banner. |
| A12 | `frontend/src/App.jsx` (rewrite) | Thin client. No system-prompt assembly. Consumes ndjson stream. |

**Phase B — B1 through B7 landed as part of the A wave.** Fully functional:

| Task | Where |
|------|-------|
| B1 | `schema.Message.id` + `MessageSideEffects`; main.py's `_persist` and `_background_after_turn` populate `state.side_effects[msg_id]`. |
| B2 | `DELETE /api/campaign/{id}/message/{msg_id}` + `POST /api/campaign/{id}/regenerate/{msg_id}` in main.py; `handleDeleteMessage` / `handleRegenerate` in App.jsx call them. |
| B3 | `memory.py` now uses per-campaign collections (`tt_camp_{safe_id}`); `delete_campaign_memory` drops the whole collection. |
| B4 | `PUT /api/state/{id}` validates via `CampaignState.model_validate`, 400 on failure. |
| B5 | `state_manager.apply_state_delta` halves suspicious deltas (verified via smoke test). |
| B6 | `state_manager._normalize_disposition` substring-matches against enum. |
| B7 | Dynamic stat registration in `apply_state_delta`; default bounds `{0, 9999}`. |

**Phase C — rolled into the frontend rewrite.** Shipped:

| Task | Where |
|------|-------|
| C1 | `AbortController` in `streamEndpoint`; Stop button swaps in for Commit while streaming. Backend `_run_chat_stream` catches `CancelledError`, persists partial. |
| C2 | `/api/campaign/{id}/continue` backend endpoint + Continue button (shows when last GM msg is `partial` or lacks terminal punctuation). Appends to the same message. |
| C3 | Token meter in header, fed by `promptStats` from the `done` event and from `/last_prompt`. |
| C4 | Prompt Inspector modal (director mode only), backed by `/api/campaign/{id}/last_prompt` (in-memory cache). |
| C5 | `frontend/src/components/Modal.jsx` (new) with `useModal()` context — every `confirm`/`alert` routed through it. |
| C6 | `/api/campaign/{id}/export` + `/api/campaign/import` backend; download/upload buttons in App.jsx menu/sidebar. |
| C7 | Director-mode inline edit for NPCs + lorebook in sidebar. |
| C8 | `frontend/src/components/Banner.jsx` (new) with `useBanner()` + toast stack; wired to all fetch error paths. |
| C9 | `localStorage.tt_preferred_gm` + `tt_preferred_utility` persisted by CampaignCreator. |
| C10 | `undoStack` + `pushStateEdit` + `handleUndo` + `Ctrl+Z` handler. Only applies to director-mode edits. |
| C11 | `backend/logging_config.py` (new) with context filter; replaces `print`s in touched modules. |

**Phase D — complete.**

| Task | Status | Where |
|------|--------|-------|
| D1 | ✅ | `main.py` CORS restricted to `http://localhost:5173`. |
| D2 | ✅ | `backend/tests/` — 8 test files, 45 tests, all passing. Mock Ollama in `conftest.py`. `test_chat_flow.py::test_second_turn_prompt_contains_world` is the explicit regression anchor for the #1 coherence bug. |
| D3 | ✅ | Request-ID middleware in `main.py`; `X-Request-Id` header exposed. |
| D4 | ✅ | `backend/rate_limit.py` — 60 req/min per IP on chat/kickoff/continue routes via `Depends(chat_rate_limit)`. Input size caps via Pydantic `max_length` on `ChatRequest.user_message` (4000) and `GenerateWorldRequest.prompt` (2000). |
| D5 | ✅ | `CLAUDE.md` at repo root — run-local, module map, "how to add …" recipes, pointers to audit + plan. |

### 7.2 What's still open for the user

1. **Frontend end-to-end smoke with live UI.** The backend/API smoke was done via curl (§7.5 below) and confirms the coherence fix end-to-end. A human-driven pass through the React UI is still worth doing before ship:
   - Start backend (`python -m uvicorn main:app --reload --port 8000`) and frontend (`npm run dev`).
   - Forge a new world with a chosen GM model and utility model.
   - Verify kickoff narrates coherently using world + protagonist context.
   - Send turns; verify sidebar updates (stats/inventory/NPCs) as the GM narrates state-changing events.
   - Open the Prompt Inspector (director mode) and confirm world/scene/cast/lorebook blocks are visible every turn.
   - Test Stop, Continue, Regenerate, Delete-message, Undo, Fork, Export/Import flows against a running campaign.

2. **Known-suspect areas to poke during smoke test:**
   - `_background_after_turn` is launched via `asyncio.create_task` after `/chat/stream` returns. Verified working under TestClient and uvicorn (extraction writes `side_effects` correctly).
   - Frontend's `pushStateEdit` PUTs the whole state; if a chat stream's `_persist` interleaves, the PUT could stomp a newly-appended message. Backend holds a per-id lock, but the PUT still does last-write-wins because it doesn't read-modify-write. Acceptable for single-user but flag if observed.
   - `Message.id` collision across forks is theoretically possible but vanishingly unlikely (12-hex-char UUID prefix). Not worth code for now.
   - `messages` are filtered client-side for `is_kickoff` flag — only kickoff `user` message is hidden; kickoff `assistant` shows.

3. **Commit decision.** All changes are uncommitted on `refactor/llm-coherence`. User to approve before committing or merging to `main`.

### 7.3 Files created/modified this session

**Created:**
- `backend/schema.py`
- `backend/tokenizer.py`
- `backend/model_resolver.py`
- `backend/prompt_builder.py`
- `backend/prompt_templates.py`
- `backend/summarizer.py`
- `backend/logging_config.py`
- `backend/rate_limit.py`
- `backend/pytest.ini`
- `backend/requirements-dev.txt`
- `backend/states/` (auto-created at startup)
- `frontend/src/components/Modal.jsx`
- `frontend/src/components/Banner.jsx`

**Rewritten:**
- `backend/main.py`
- `backend/state_manager.py`
- `backend/ollama_client.py`
- `backend/extraction.py`
- `backend/memory.py`
- `frontend/src/App.jsx`
- `frontend/src/CampaignCreator.jsx`

**Renamed by runtime (not by me):**
- `backend/campaign_states.json` → `backend/campaign_states.json.legacy.bak` (happens once on first backend startup).

### 7.4 Live smoke results (2026-04-24)

Ran against real Ollama (`mistral-nemo:latest`). Created campaign `smoke_test` with protagonist "Tester" in "Test Room" holding a "Notebook", world = "A test realm of CI pipelines", scene = "You stand before a green build light".

Kickoff narration — verbatim excerpt:

> "As Tester, you find yourself standing alone in the dim glow of an empty Test Room. The air is thick with the hum of distant machinery… You're bathed in the verdant light of the build status indicator above—a green checkmark, steady and reassuring… Your gaze falls upon your Notebook…"

Every piece of injected context surfaced: protagonist name, location, inventory item, scene element. This is the exact behavior the original `………` bug was failing.

Turn-2 inspector (`/api/campaign/smoke_test/last_prompt`) confirmed:

```
world_description present: True
starting_scene present:    True
protagonist name present:  True
location present:          True
inventory present:         True
NPC cast present:          True
lorebook present:          True
```

Campaign deleted cleanly; state file + chroma collection removed.

### 7.5 Resume recipe (if ever needed again)

```bash
# from repo root
git status                               # confirm branch + uncommitted state
git diff --stat                          # scope of the session's work

# Backend sanity
cd backend
python -c "import main; print('ok')"     # must still import cleanly
cd ..

# Frontend sanity
cd frontend
npx vite build                           # must still build
cd ..
```

Then open `IMPLEMENTATION_PLAN.md` → §7.2 and work top-down. When D2 and D5 are done, run the §7.2 (3) smoke-test checklist, then loop back to the user for sign-off / commit.

**Minimum re-read list on cold start:** this file (§7), `backend/main.py`, `backend/schema.py`, `backend/prompt_builder.py`, `backend/state_manager.py`. The rest can be re-derived.

