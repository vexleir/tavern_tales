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

45 tests across `backend/tests/`. Ollama is mocked — tests do not require a live server. The prompt-builder suite is the regression anchor for the #1 coherence bug: if `WORLD` / `OPENING SCENE` / `PROTAGONIST` / `CAST` / `LOREBOOK` ever drop out of the system prompt on a non-kickoff turn, `test_second_turn_prompt_contains_world` in `test_chat_flow.py` fails.

## Module map

**Backend (`backend/`)**

| File | One-liner |
|------|-----------|
| `main.py` | FastAPI app. Routes. Streams `start/token/error/done` ndjson events. Owns the chat flow. |
| `schema.py` | Pydantic v2 models — the source of truth for campaign state shape (`SCHEMA_VERSION = 2`). |
| `state_manager.py` | Per-campaign files under `states/{id}.json`. Atomic writes + `asyncio.Lock` per id. `apply_state_delta` + `apply_reversal` for message-level rollback. |
| `prompt_builder.py` | **The coherence fix.** Assembles the full system prompt every turn from live state. |
| `prompt_templates.py` | Static strings (role rules, GM-only marker). |
| `ollama_client.py` | Streaming + non-streaming Ollama callers. Emits `StreamEvent` dicts. Sampling defaults tuned to stop runaway repetition. |
| `summarizer.py` | Three-tier hierarchical summary (short @ 5 turns, chapter @ 20, arc when >5 chapters). Never overwrites. |
| `extraction.py` | Utility-model JSON extraction of state changes from a turn. Validated via `StateDelta`. |
| `memory.py` | One ChromaDB collection per campaign. Per-message memory tracking for rollback. |
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
| `components/Modal.jsx` | `useModal()` context — replaces `confirm`/`alert`. |
| `components/Banner.jsx` | `useBanner()` context — toast-style error surface. |

## Recurring tasks — how to add …

### A new sampling parameter

1. Add the field to `SamplingOverrides` in `schema.py`.
2. Plumb it through `ollama_client._build_options`.
3. (Optional) surface a control in the frontend; it already sends `overrides` on chat requests.

### A new top-level state field

1. Add to `CampaignState` (or a sub-model) in `schema.py`. Default factories are mandatory — schema v2 does not migrate.
2. If it should appear in the prompt, add a render + token-count block in `prompt_builder._build_system_prompt` and a matching field on `BlockTokens`.
3. If director-mode should edit it, add a UI control in `App.jsx` under `pushStateEdit`.

### A new route

1. Add it in `main.py`. If it's user-triggered generation, include `dependencies=[Depends(chat_rate_limit)]`.
2. If it takes user input, cap the input with Pydantic `max_length`.
3. Set `campaign_id_ctx` early so log lines are tagged.

## Where the important things live

- **The system prompt is built in** `backend/prompt_builder.py`, specifically `_build_system_prompt`. Every turn. All state is re-injected. This is the fix for the original "the GM forgets the world after turn 1" bug — do not reintroduce frontend-side prompt assembly.
- **Message-level rollback lives in** `state_manager.apply_state_delta` (returns a `reversal` dict) and `apply_reversal`. Every assistant message has a `MessageSideEffects` record with its `memory_ids` and `reversal`. The `DELETE /api/campaign/{id}/message/{msg_id}` and `regenerate` routes use this.
- **Legacy migration:** on first startup, `backend/campaign_states.json` (v1) is renamed to `.legacy.bak` and not migrated. A warning is logged. Create new campaigns.

## Architecture references

- Full audit that motivated the current shape: [AUDIT_REPORT.md](AUDIT_REPORT.md).
- Phased plan + progress log (what's done, what's left): [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
