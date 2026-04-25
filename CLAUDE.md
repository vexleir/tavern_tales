# Tavern Tales Reborn — Maintainer's Orientation

A local LLM-driven text RPG. FastAPI backend talks to Ollama; React frontend is a thin client.

## Run locally

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev   # http://localhost:5173

# Or: double-click start_all.bat from the repo root.
```

Ollama must be running on `localhost:11434`. Pull at least one GM model (e.g. `ollama pull llama3.1:8b-instruct`). The **Narrator** (GM) model and the **Utility** model (summarization + state extraction) are both selectable in the "Forge Your World" screen; utility auto-falls-back if the preferred isn't pulled.

## Run tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

54 tests across `backend/tests/`. Ollama is mocked — tests do not require a live server. The prompt-builder suite is the regression anchor for the #1 coherence bug: if `WORLD` / `OPENING SCENE` / `PROTAGONIST` / `CAST` / `LOREBOOK` ever drop out of the system prompt on a non-kickoff turn, `test_second_turn_prompt_contains_world` in `test_chat_flow.py` fails.

Full local quality gate:

```powershell
.\check.ps1
```

The script runs backend tests, frontend lint, and frontend production build. In the Codex sandbox, pytest and Vite build may require approval because they create temp directories or spawn helper processes.

## Module map

**Backend (`backend/`)**

| File | One-liner |
|------|-----------|
| `main.py` | FastAPI app. Routes. Streams `start/token/error/done` ndjson events. Owns the chat flow. |
| `schema.py` | Pydantic v2 models — the source of truth for campaign state shape (`SCHEMA_VERSION = 2`), revisions, turn IDs, rules, quests, conditions, and event log. |
| `state_manager.py` | Per-campaign files under `states/{id}.json`. Atomic writes + `asyncio.Lock` per id. `apply_state_delta` + `apply_reversal` for message-level rollback. |
| `prompt_builder.py` | **The coherence fix.** Assembles the full system prompt every turn from live state. |
| `game_rules.py` | Lightweight d20 action checks for risky player actions; outputs binding prompt context. |
| `prompt_templates.py` | Static strings (role rules, GM-only marker). |
| `ollama_client.py` | Streaming + non-streaming Ollama callers. Emits `StreamEvent` dicts. Sampling defaults tuned to stop runaway repetition. |
| `summarizer.py` | Three-tier hierarchical summary (short @ 5 turns, chapter @ 20, arc when >5 chapters). Never overwrites. |
| `extraction.py` | Utility-model JSON extraction of state changes from a turn. Validated via `StateDelta`. |
| `memory.py` | Lazy ChromaDB client, one collection per campaign, compact event memories, hybrid semantic/recency retrieval, per-message rollback. |
| `model_resolver.py` | Maps preferred model names → available Ollama tags with a fallback chain. |
| `tokenizer.py` | Cheap token counting (~4 chars/token; opportunistic tiktoken). |
| `logging_config.py` | Structured logs with `campaign_id` + `request_id` context vars. |
| `rate_limit.py` | In-memory token-bucket (60 req/min) on chat routes. |
| `tests/` | Pytest + mocked Ollama. |

**Frontend (`frontend/src/`)**

| File | One-liner |
|------|-----------|
| `App.jsx` | Thin client. Consumes the ndjson stream. Menu / Setup / Play modes. Director mode + undo. |
| `CampaignCreator.jsx` | World forge screen. GM + utility model pickers, NSFW toggle, lorebook/NPC editors. |
| `components/ModalProvider.jsx` + `hooks/useModal.js` | Modal context — replaces `confirm`/`alert`. |
| `components/BannerProvider.jsx` + `hooks/useBanner.js` | Toast-style error surface. |
| `hooks/useNdjsonStream.js` | Shared stream parser and stop/abort handling. |
| `lib/api.js` | Centralized API base URL and error parsing. |

## Recurring tasks — how to add …

### A new sampling parameter

1. Add the field to `SamplingOverrides` in `schema.py`.
2. Plumb it through `ollama_client._build_options`.
3. (Optional) surface a control in the frontend; it already sends `overrides` on chat requests.

### A new top-level state field

1. Add to `CampaignState` (or a sub-model) in `schema.py`. Default factories are mandatory — schema v2 does not migrate.
2. If it should appear in the prompt, add a render + token-count block in `prompt_builder._build_system_prompt` and a matching field on `BlockTokens`.
3. If director-mode should edit it, add a focused PATCH shape in `main.py` and a UI control in `App.jsx` that calls the patch helper.

### A new route

1. Add it in `main.py`. If it's user-triggered generation, include `dependencies=[Depends(chat_rate_limit)]`.
2. If it takes user input, cap the input with Pydantic `max_length`.
3. Set `campaign_id_ctx` early so log lines are tagged.

## Where the important things live

- **The system prompt is built in** `backend/prompt_builder.py`, specifically `_build_system_prompt`. Every turn. All state is re-injected. This is the fix for the original "the GM forgets the world after turn 1" bug — do not reintroduce frontend-side prompt assembly.
- **Turn-level rollback lives in** `state_manager.apply_state_delta` (returns a `reversal` dict) and `apply_reversal`. User and assistant messages now share a `turn_id`; normal delete removes the whole turn and rolls back assistant side effects.
- **Director edits use PATCH + revision checks.** Avoid full-state PUTs from the UI. Stale edits return 409 instead of clobbering new messages or side effects.
- **Action checks live in** `backend/game_rules.py`. Risky actions get a d20-style resolution, which is sent to the frontend and injected into the prompt as binding context.
- **Debug bundles are exposed at** `GET /api/campaign/{id}/debug` and include state, last prompt, memory count, and recent event log entries.
- **Legacy migration:** on first startup, `backend/campaign_states.json` (v1) is renamed to `.legacy.bak` and not migrated. A warning is logged. Create new campaigns.

## Architecture references

- Full audit that motivated the current shape: [AUDIT_REPORT.md](AUDIT_REPORT.md).
- Phased plan + progress log (what's done, what's left): [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
