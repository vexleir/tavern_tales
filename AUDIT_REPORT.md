# Tavern Tales Reborn — Engineering Audit Report

**Audit scope:** Entire `backend/` + `frontend/` codebase, with primary focus on the LLM orchestration layer.
**Audit date:** 2026-04-23
**Auditor role:** Game developer, LLM integrations specialist.

---

## Executive Summary

Tavern Tales is architecturally sound at the high level — FastAPI backend, streaming Ollama client, ChromaDB vector memory, state extraction via a second LLM call, React frontend with director tooling. The scaffolding is all in the right places.

However, the reason the product **"constantly defaults to lengthy outputs that lose context and degrade into gibberish"** is not one bug — it is a chain of small mistakes in the context-assembly pipeline that individually look harmless and collectively destroy the model's coherence. In short: **the LLM is being asked to narrate a world it no longer remembers, using sampling parameters that encourage runaway repetition, with memory injection that actively dilutes the prompt.**

A concrete proof of the degeneration is visible in [campaign_states.json:46](backend/campaign_states.json#L46): the saved assistant message ends with hundreds of `………` characters — a textbook runaway-sampling artifact.

The rest of this document breaks down exactly why, where, and what to do about it.

---

## 1. Why the model produces lengthy, drifting, eventually incoherent output

### 1.1 The world is forgotten after turn 1 (the single biggest issue)

The opening system prompt in [App.jsx:50-58](frontend/src/App.jsx#L50-L58) — the one that contains `world_description` and `starting_scene` — is **only** sent during `handleKickoff`. On every subsequent turn, the frontend rebuilds a system prompt from scratch at [App.jsx:207-210](frontend/src/App.jsx#L207-L210):

```js
apiMessages.unshift({
  role: 'system',
  content: 'You are the Game Master in a dark fantasy text RPG. ...'
});
```

That replacement prompt contains **no world description, no scene, no protagonist name, no NPC roster, no stats, no inventory, no location, no lorebook**. The backend then injects a story summary, some vector-retrieved memories, and *only those lorebook entries whose keyword literally appears in the latest user message* ([main.py:198-201](backend/main.py#L198-L201)).

This means: after the opening turn, the GM is effectively roleplaying with a generic fantasy prompt + the last 15 chat messages + a rolling 3-4 sentence summary + whichever lore rules happen to be keyword-matched. The carefully crafted world-building is gone. The protagonist's name, gear, and location are gone. Coherent narration is impossible.

### 1.2 Sampling parameters invite repetition, and the fix is a hack

In [ollama_client.py:13-19](backend/ollama_client.py#L13-L19):

```python
"temperature": 0.7,
"repeat_penalty": 1.05,       # too weak — Ollama default is 1.1
"top_p": 0.9,
"num_predict": 250,           # short, causes mid-sentence cuts
"stop": ["\nUser:", "\nPlayer:", "User:", "[END]", "\n\n\n\n"]
```

- `repeat_penalty: 1.05` is *below* the Ollama default and far below what instruction-tuned Llama3 derivatives (and the user's `fluffy/l3-8b-stheno-v3.2`) need to avoid loop-collapse. Once the model starts to repeat, there is no pressure pulling it back.
- `num_predict: 250` tokens is ~180 English words — RPG narrations routinely want more, which trains the model (through clipped samples in history) to run long and unstructured.
- The `"\n\n\n\n"` stop token is a **band-aid** for runaway output; the actual symptom — endless `…………` — slips right past it because there are no newlines in the degenerated run.
- There is no `frequency_penalty`, no `presence_penalty`, no `mirostat`, no `seed` for reproducibility.

### 1.3 The sliding window is too small and not structured

[App.jsx:200](frontend/src/App.jsx#L200): `const windowedMessages = newMessages.slice(-contextWindow)` with default `contextWindow = 15`. Once the window rolls past message 15, the character's opening, the NPCs they've been talking to, and the plot setup vanish — and nothing structured replaces them. The "rolling summary" (1.4) is the only bridge, and it is weak.

### 1.4 The rolling summary overwrites rather than accumulates

[main.py:63-68](backend/main.py#L63-L68): every 10 turns the background summarizer **overwrites** `story_summary` with a fresh 3-4 sentence summary of the last N-5 messages. That means long-arc context (the quest the player took in turn 3) is permanently lost once it falls off the window. A progressive / hierarchical summary is needed.

### 1.5 Memory retrieval is semantically noisy

In [memory.py:20-33](backend/memory.py#L20-L33) memories are stored as:

```
"Turn {turn}: Player acted: {user_action}\nGM narrated: {gm_response}"
```

…and retrieved with the *current* user query as the search text ([main.py:191](backend/main.py#L191)). Consequences:

- Every memory looks the same to the embedder (same prefix boilerplate), so cosine similarity is dominated by surface action phrasing, not *topical* similarity.
- Only **3** memories are retrieved, yet each one can be multiple paragraphs of GM text — high token cost, low signal.
- There is no deduplication, no recency weighting, no filter for "this memory is already in the sliding window."

### 1.6 Keyword-based lorebook triggers fire on user input only

[main.py:198-201](backend/main.py#L198-L201) lowercases `user_query` and checks `if keyword.lower() in query_lower`. Two failure modes:

- If the player types "I walk forward silently" but the lore keyword is `Magic`, the `Magic is illegal` rule is **not** injected — even if the scene is steeped in magic.
- If the player types "I cast a claiming spell" when the keyword is `Claiming`, the rule fires — but the rule itself was authored *about the narrative world*, not as instruction for the GM, and it gets injected raw into the system prompt without a role tag telling the model what to do with it.

### 1.7 The incoming request is mutated in place

[main.py:216](backend/main.py#L216): `req.messages[0]["content"] += injection_block`. Because Pydantic doesn't deep-copy nested dicts, and because the model references are shared with whatever framework code handles the request, this is a latent footgun. If the server ever re-processes a request object (retry, background handler), the injection block gets appended a second time.

### 1.8 Turn numbering is inconsistent and breaks cadences

- Frontend sends `turn: newMessages.length` ([App.jsx:219](frontend/src/App.jsx#L219)) — a count of frontend messages, not game turns.
- Backend runs the summarizer at `req.turn % 10 == 0` ([main.py:101](backend/main.py#L101)).
- Because `newMessages.length` grows by 1 per user-send (not per exchange), and because `handleKickoff` sends `turn: 0`, the summarizer fires at `newMessages.length = 10, 20, …`, not every 10 in-game turns.
- Memory IDs use `{campaign_id}_{turn}_{uuid[:8]}` — two "turns" can collide if the frontend reloads and the count resets.

### 1.9 Opening turn sends no user message

[App.jsx:64-69](frontend/src/App.jsx#L64-L69): kickoff sends `messages: [{ role: 'system', content: sysPrompt }]`. Ollama's chat endpoint with system-only history is undefined behavior for most instruct models — many will respond meta-narratively, some will produce empty or looping output. An explicit user turn like `{role: 'user', content: 'Begin the scene.'}` would make this deterministic.

### 1.10 The same creative model performs extraction and summarization

[extraction.py:7-52](backend/extraction.py#L7-L52) and the summarizer both use `req.model` — i.e., whichever model the player picked for narration. An uncensored NSFW creative-writing tune (like `fluffy/l3-8b-stheno-v3.2`) is a poor JSON emitter and a worse summarizer. It will sometimes embed commentary into JSON, sometimes summarize in-character rather than factually, and bloat state with fabricated stat changes.

---

## 2. Code that is broken, unreachable, or doesn't do what it intends

| # | Location | Issue | Impact |
|---|---|---|---|
| 2.1 | [main.py:127-135](backend/main.py#L127-L135) `override_state` | Uses `load_all_states` / `save_all_states` before they are imported ([imported at main.py:137](backend/main.py#L137)). Works only by Python's late binding; if this handler is the first touched after a reload, unclear. Also replaces the entire state dict with raw client JSON — no schema validation. | Director-mode edits can corrupt a campaign (e.g., wiping `messages`). |
| 2.2 | [main.py:73-102](backend/main.py#L73-L102) `stream_and_intercept` | Saves `saved_history` **plus** then schedules a background task that re-reads state and can race with the frontend's `syncMessagesToBackend`. Both write `campaign_states.json` without any locking. | Dropped messages, partial writes, corruption under even moderate concurrency. |
| 2.3 | [state_manager.py:16-18](backend/state_manager.py#L16-L18) `save_all_states` | Non-atomic write (`open(... 'w')` truncates then writes). A crash mid-write produces an empty/corrupted file, taking every campaign with it. | Single-point-of-failure save path. |
| 2.4 | [state_manager.py:20-38](backend/state_manager.py#L20-L38) `get_campaign_state` | Returns an in-memory default for non-existent campaigns but does **not** persist it. Any subsequent `update_campaign_state` call then creates it, which silently invents a campaign at the default location ("The Ember & Ash Tavern") — hiding bugs where the frontend queries the wrong `campaign_id`. | Ghost campaigns; mis-routed state. |
| 2.5 | [extraction.py](backend/extraction.py) | Prompts the chat LLM to emit JSON with `"format": "json"`. The `active_stats` list is the **current keys** of `player.stats`, so if the GM describes gaining a new stat ("Your Sanity drops"), the extractor has no slot for it and either hallucinates into an existing stat or loses the change. | Stats schema is frozen at campaign creation. |
| 2.6 | [state_manager.py:50-55](backend/state_manager.py#L50-L55) | `stats_changes` is additively merged with `get(k, 0) + v`. If the model returns the new *absolute* value instead of the delta (common mis-read), stats double. No clamping, so Health can go to 1,000,000 or -500 silently. | Stat drift/explosion. |
| 2.7 | [state_manager.py:71-87](backend/state_manager.py#L71-L87) | `disposition_change` is written as-is without validation against `Friendly|Neutral|Suspicious|Hostile`. The model will sometimes write `"more suspicious"` or `"becomes hostile"` (prose). The UI then renders prose where a label is expected. | UI breaks; disposition filter logic breaks. |
| 2.8 | [App.jsx:276-286](frontend/src/App.jsx#L276-L286) `handleRegenerate` | Pops the last GM message and re-sends the last player message — but the backend's previous write of `messages` already includes the now-popped GM reply, and the background memory/extraction have already fired for it. The vector DB now contains a memory of a turn that was rewritten. | Memory pollution from regenerated turns. |
| 2.9 | [App.jsx:288-293](frontend/src/App.jsx#L288-L293) `handleDelete` | Same class of bug: vector memory and extracted state changes for a deleted message are never rolled back. | Ghost consequences (e.g., inventory items, stat changes) persist from deleted messages. |
| 2.10 | [main.py:282-288](backend/main.py#L282-L288) `delete_campaign` | Deletes `campaign_states.json` entry and chroma entries — but does **not** delete the chroma collection's on-disk directory (visible: new `c67e58e2-…` dir in `chroma_db/` from the current git status). | Slow disk bloat. |
| 2.11 | [main.py:283-286](backend/main.py#L283-L286) | Inline `from memory import delete_campaign_memory` and similar lazy imports are scattered. Harmless at runtime, but hides the module's true dependency graph and breaks static analysis. | Maintainability. |
| 2.12 | [campaign_states.json:41](backend/campaign_states.json#L41) | Real persisted data has a typo (`"laimed"` instead of `"Claimed"`) in the `Thrall` lorebook entry. This came from user input, but the system has no lore-edit UX after creation — so typos are baked in forever. | Sticky content errors. |
| 2.13 | [main.py:108-120](backend/main.py#L108-L120) `/api/models` | 10 s timeout, no caching. Called on every frontend mount, and silently returns `[]` on failure — the UI then shows a near-empty model selector with no error banner. | Silent misconfiguration. |
| 2.14 | [memory.py:8-18](backend/memory.py#L8-L18) | Chroma's default embedder (`all-MiniLM-L6-v2`) is loaded on first DB op. Cold-start on the first chat stream adds ~2-5 s of latency that the frontend attributes to the LLM. | Perceived slowness on first message. |
| 2.15 | [main.py:14-20](backend/main.py#L14-L20) | `allow_origins=["*"]` with `allow_credentials=True` is both a CORS spec violation and an unnecessary exposure since the product is localhost-only. | Security posture / production-readiness. |
| 2.16 | [App.jsx:44](frontend/src/App.jsx#L44) | On mount, picks `data[0]` as the model — whichever Ollama happens to list first. For most users that is **not** the correct RP model. | Poor defaults. |
| 2.17 | [main.py:253](backend/main.py#L253) `generate_world` | Hardcoded model `fluffy/l3-8b-stheno-v3.2:latest`. If the user doesn't have that model pulled, world-gen silently 404s inside Ollama and returns an error blob the frontend doesn't surface. | Opaque failure on first run. |
| 2.18 | [App.jsx:196](frontend/src/App.jsx#L196) | Appends an empty GM placeholder before fetch starts. If the fetch itself fails (not the stream), the empty bubble stays. | Ghost empty messages. |
| 2.19 | [ollama_client.py:35-36](backend/ollama_client.py#L35-L36) | On `ConnectError`, yields a string into the streaming body. The frontend happily appends that string to the GM message as if it were narration. | Error messages get persisted as game text. |
| 2.20 | [App.jsx:219](frontend/src/App.jsx#L219) | `turn: newMessages.length` (discussed in 1.8). | Summarization cadence wrong. |

---

## 3. User-experience friction

- **No stop / cancel button.** Once a stream starts, a user who notices it's degenerating has to wait for the entire `num_predict` budget.
- **No continue button.** Because `num_predict: 250` frequently clips narrations mid-sentence, the user has no way to say "keep going." They can only re-roll.
- **Reroll loses the previous draft.** No side-by-side, no history of alternatives.
- **No dice / skill-check affordance.** A TTRPG that runs purely on LLM narration slowly loses stakes; a simple `/roll` parser or a "contested action" button would anchor the fiction.
- **`confirm()` dialogs** ([App.jsx:121](frontend/src/App.jsx#L121)) break the visual aesthetic of the otherwise-polished dark-fantasy UI.
- **Director Mode** is powerful but lacks undo. One accidental edit of stats or location is permanent.
- **No campaign export/import.** Saves live in a single JSON on the backend; the user can't back up or share a campaign.
- **No visible token/context meter.** Power users cannot see that they're about to fall off the window.
- **World generation has a fixed model** (see 2.17) and no progress feedback beyond the word "Dreaming…".
- **Mobile layout** is effectively broken — the sidebar is `hidden md:flex`, which hides player state entirely on small screens with no alternative disclosure.
- **Error surface is silent.** Extraction failures, summarization failures, model-list failures, CORS failures — all `print(...)` to the backend console and return empty/defaults. The player has zero signal.
- **No input validation on stats / inventory.** You can type `NaN` into a stat; `parseInt(e.target.value) || 0` will coerce it, but a negative Health doesn't trigger any UI affordance for death.
- **Kickoff re-runs automatically if messages is empty** on load — good — but there is no "restart campaign" button that intentionally clears messages and re-runs it.
- **Memory is invisible.** Players cannot inspect what the GM "remembers," which makes drift feel random rather than debuggable.

---

## 4. Recommended fixes — prioritized for an implementation plan

### Priority 1 — Stop the gibberish (biggest user-visible win)

1. **Reconstruct the system prompt every turn from full campaign state.** Move system-prompt assembly from the frontend to the backend. Backend should inject, on every chat request:
   - World description + starting scene (static block).
   - Player name, location, stats, inventory (live block).
   - NPC roster with disposition and known secrets (live block).
   - Full lorebook, not keyword-filtered (it's small; cost is negligible vs. incoherence).
   - Rolling hierarchical summary (see #4 below).
   - Top-K vector memories with de-duplication against the window.
2. **Fix sampling parameters.** Set `repeat_penalty: 1.15`, `top_p: 0.9`, `top_k: 40`, `min_p: 0.05`, `temperature: 0.8`, `num_predict: 512`. Remove the `"\n\n\n\n"` stop hack. Make these per-model-tunable in a config file so different creative tunes can be set appropriately.
3. **Larger + smarter context window.** Default `contextWindow` to 30 and add token-based truncation (counted, not message-counted) so the model gets as much real history as fits, stopping exactly at token budget minus response reservation.
4. **Hierarchical progressive summary.** Keep three layers: (a) running short summary of last ~20 turns, (b) chapter summaries of older ranges, (c) long-term arc summary updated at milestone events. Never *overwrite* — only compact.
5. **Switch extraction + summarization to a dedicated small JSON-capable model** (e.g., `llama3.1:8b-instruct`, `qwen2.5:7b-instruct`) configurable separately from the GM model.

### Priority 2 — Make state reliable

6. **Atomic state writes.** Write to `campaign_states.json.tmp`, `fsync`, then `os.replace`. Add an `asyncio.Lock` per campaign id to serialize writes.
7. **Validate extraction output** against a Pydantic schema; clamp stat changes to a sensible range; require disposition ∈ enum; drop unknown keys.
8. **Separate per-campaign files** (`states/{campaign_id}.json`) so one corrupted save doesn't kill everything.
9. **Rollback memory + state on `handleDelete` and `handleRegenerate`.** Tag memories and extractions with the message id they came from; when a message is deleted/regenerated, reverse those side effects.
10. **Stop mutating `req.messages`** in place; build a new list.

### Priority 3 — UX polish

11. **Stop button** during streaming (`AbortController` on the frontend, closes the Ollama stream).
12. **Continue button** when a stream ends near the token budget without an end-of-turn cue.
13. **Visible context meter** — show "X / Y tokens used" near the Director controls.
14. **In-app memory inspector** — a panel that shows the exact system prompt (collapsed) and retrieved memories for the current turn. Enormous debugging value and makes drift feel explainable.
15. **Replace browser `confirm()`** with styled modal dialogs.
16. **Campaign export/import** as a JSON download/upload.
17. **Lore/NPC editor after creation** (edit mode on the sidebar codex).
18. **Mobile disclosure** for the sidebar via a slide-over drawer.
19. **Error banners** for model-list failures, extraction failures, and connectivity loss — instead of silent `print`.
20. **Configurable default model** stored in localStorage (currently always resets to `data[0]`).

### Priority 4 — Robustness / production-readiness

21. Replace `"*"` CORS with an explicit `http://localhost:5173` allowlist.
22. Add structured logging (`logging` module with levels) to replace `print`.
23. Add request-level tracing IDs so that a single "bad turn" can be followed through chat → extraction → memory → save.
24. Introduce a lightweight test harness that replays a saved `messages[]` against a mocked Ollama to snapshot-test prompt assembly — this is how regressions in context injection should be caught going forward.
25. Gate the NSFW default model (`fluffy/l3-8b-stheno-v3.2`) behind a user-settings toggle rather than hard-coding it in `/api/world/generate`.

---

## 5. Suggested implementation sequencing

A reasonable three-phase plan:

- **Phase A (1-2 days of work): "Coherence first."** Items 1, 2, 3, 5, 10. This is what the player will notice immediately — outputs stop degrading and the GM remembers the world.
- **Phase B (2-3 days): "Trustworthy state."** Items 4, 6, 7, 8, 9. Once coherence is restored, the campaign state must stop silently corrupting.
- **Phase C (2-3 days): "UX & observability."** Items 11-20, plus 22-24. This is where the product stops feeling like a prototype.
- **Phase D (ongoing): hardening.** Items 21, 25, plus test coverage.

---

## 6. One-line root-cause summary

> The LLM is losing context because the frontend throws away the world prompt after turn 1, the backend only re-injects a thin slice of state, the sampling parameters don't penalize repetition enough, and the rolling summary overwrites rather than accumulates. Every other bug in this report is downstream of that or independent.
