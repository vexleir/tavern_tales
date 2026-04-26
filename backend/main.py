"""
Tavern Tales Reborn — FastAPI app.

This version owns system-prompt assembly server-side. The frontend sends only
`{campaign_id, user_message}` (plus optional overrides) and receives a Server-
Sent Events stream of narrative tokens followed by a terminal `done` event
with prompt stats and the updated state snapshot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import extraction
import game_rules
import memory
import prompt_builder
import state_manager
import summarizer
from logging_config import campaign_id_ctx, configure_logging, request_id_ctx
from model_resolver import DEFAULT_CREATIVE_MODEL, NSFW_CREATIVE_MODEL
from ollama_client import complete_json, stream_chat
from rate_limit import chat_rate_limit
from schema import (
    SCHEMA_VERSION,
    CampaignState,
    MessageSideEffects,
    ModelConfig,
    NPC,
    Player,
    ReversalPatch,
    Role,
    SamplingOverrides,
    StatBound,
)

configure_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="Tavern Tales Reborn GM Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # tightened in D1
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


# ---------------------------------------------------------------------------
# Middleware — request-id tracing (D3, pulled forward because it's tiny)
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request, call_next):
    req_id = uuid.uuid4().hex[:12]
    token = request_id_ctx.set(req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = req_id
        return response
    finally:
        request_id_ctx.reset(token)


@app.on_event("startup")
async def _startup() -> None:
    await state_manager.initialize()
    log.info("Tavern Tales backend started (schema v%d).", SCHEMA_VERSION)


# Cache of the most recently assembled prompt per campaign (for memory inspector, C4)
_LAST_PROMPT: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    campaign_id: str
    user_message: str = Field(..., min_length=1, max_length=4000)
    overrides: SamplingOverrides | None = None


class InitCampaignRequest(BaseModel):
    campaign_id: str
    player_name: str
    starting_location: str
    stats: dict[str, int]
    inventory: list[str] = Field(default_factory=list)
    npcs: list[dict[str, Any]] = Field(default_factory=list)
    lorebook: dict[str, str] = Field(default_factory=dict)
    story_summary: str = ""
    world_description: str = ""
    starting_scene: str = ""
    gm_model: str = "llama3"
    utility_model: str | None = None
    nsfw_world_gen: bool = False


class GenerateWorldRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    nsfw: bool = False
    model: str | None = None


class DirectorPatchRequest(BaseModel):
    expected_revision: int | None = None
    player: dict[str, Any] | None = None
    stats: dict[str, int] | None = None
    inventory: list[str] | None = None
    npcs: list[dict[str, Any]] | None = None
    lorebook: dict[str, str] | None = None
    stat_bounds: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Root / diagnostics
# ---------------------------------------------------------------------------


@app.get("/")
def read_root():
    return {"status": "Tavern Tales backend is running.", "schema_version": SCHEMA_VERSION}


@app.get("/api/models")
async def get_models():
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("http://localhost:11434/api/tags", timeout=10.0)
            res.raise_for_status()
            data = res.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            log.warning("Failed to fetch Ollama model list: %s", e)
            return []


# ---------------------------------------------------------------------------
# Campaign lifecycle
# ---------------------------------------------------------------------------


@app.post("/api/campaign/init")
async def init_campaign(req: InitCampaignRequest):
    campaign_id_ctx.set(req.campaign_id)

    existing = await state_manager.load_state(req.campaign_id)
    if existing is not None:
        raise HTTPException(409, "campaign_id already exists")

    npcs: list[NPC] = []
    for n in req.npcs:
        try:
            npcs.append(NPC.model_validate(n))
        except Exception:
            log.warning("Skipping malformed NPC payload: %r", n)

    # Register bounds for the explicitly-chosen stats so dynamic additions stay clamped.
    stat_bounds = {name: StatBound() for name in req.stats.keys()}

    state = CampaignState(
        campaign_id=req.campaign_id,
        models=ModelConfig(
            gm=req.gm_model,
            utility=req.utility_model or "llama3.1:8b-instruct",
            nsfw_world_gen=req.nsfw_world_gen,
        ),
        player=Player(
            name=req.player_name,
            location=req.starting_location,
            stats=dict(req.stats),
            inventory=list(req.inventory),
        ),
        npcs=npcs,
        lorebook=dict(req.lorebook),
        world_description=req.world_description,
        starting_scene=req.starting_scene,
        stat_bounds=stat_bounds,
    )
    if req.story_summary:
        state.summaries.short = req.story_summary
    state_manager.record_event(state, "campaign.init", "Campaign created.")

    await state_manager.save_state(state)
    return {"status": "success", "campaign_id": req.campaign_id}


@app.get("/api/campaigns")
async def list_campaigns():
    summaries = await state_manager.list_campaigns()
    return [s.model_dump() for s in summaries]


@app.delete("/api/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str):
    campaign_id_ctx.set(campaign_id)
    deleted = await state_manager.delete_campaign(campaign_id)
    memory.delete_campaign_memory(campaign_id)
    return {"status": "success" if deleted else "not_found"}


@app.get("/api/state/{campaign_id}")
async def get_state(campaign_id: str):
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")
    return state.model_dump(mode="json")


@app.put("/api/state/{campaign_id}")
async def override_state(campaign_id: str, body: dict):
    """Director-mode override. Validates full state via Pydantic (B4)."""
    campaign_id_ctx.set(campaign_id)
    body["campaign_id"] = campaign_id
    body.setdefault("schema_version", SCHEMA_VERSION)
    try:
        new_state = CampaignState.model_validate(body)
    except Exception as e:
        raise HTTPException(400, f"invalid state: {e}")
    async with state_manager.campaign_lock(campaign_id):
        await state_manager.save_state(new_state)
    return {"status": "success"}


@app.patch("/api/state/{campaign_id}")
async def patch_state(campaign_id: str, req: DirectorPatchRequest):
    """Narrow Director-mode patch with optimistic revision checking."""
    campaign_id_ctx.set(campaign_id)

    async def _apply(state: CampaignState) -> CampaignState:
        if req.expected_revision is not None and state.revision != req.expected_revision:
            raise HTTPException(409, {
                "message": "campaign state changed; refresh before applying this edit",
                "current_revision": state.revision,
            })

        if req.player is not None:
            if "name" in req.player:
                state.player.name = str(req.player["name"])
            if "location" in req.player:
                state.player.location = str(req.player["location"])

        if req.stats is not None:
            state.player.stats.update({str(k): int(v) for k, v in req.stats.items()})

        if req.inventory is not None:
            state.player.inventory = [str(item) for item in req.inventory if str(item).strip()]

        if req.npcs is not None:
            state.npcs = [NPC.model_validate(n) for n in req.npcs]

        if req.lorebook is not None:
            state.lorebook = {str(k): str(v) for k, v in req.lorebook.items() if str(k).strip()}

        if req.stat_bounds is not None:
            state.stat_bounds = {
                str(k): StatBound.model_validate(v) for k, v in req.stat_bounds.items()
            }

        state_manager.record_event(state, "director.patch", "Director-mode state patch applied.")
        return state

    new_state = await state_manager.mutate_state(campaign_id, _apply)
    if new_state is None:
        raise HTTPException(404, "campaign not found")
    return {"status": "success", "state": new_state.model_dump(mode="json")}


@app.post("/api/campaigns/{campaign_id}/fork")
async def fork_campaign(campaign_id: str):
    campaign_id_ctx.set(campaign_id)
    source = await state_manager.load_state(campaign_id)
    if source is None:
        raise HTTPException(404, "campaign not found")

    import time
    new_id = f"{campaign_id}_fork_{int(time.time())}"
    clone = source.model_copy(deep=True)
    clone.campaign_id = new_id
    clone.created_at = datetime.now(timezone.utc).isoformat()
    await state_manager.save_state(clone)
    memory.duplicate_campaign_memory(campaign_id, new_id)
    return {"status": "success", "new_campaign_id": new_id}


# ---------------------------------------------------------------------------
# Chat / kickoff / continue
# ---------------------------------------------------------------------------


def _sse_pack(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


async def _background_after_turn(
    campaign_id: str,
    user_action: str,
    gm_msg_id: str,
    gm_text: str,
) -> None:
    """Save vector memory, run extraction + reversal tagging, run summarizer cadence."""
    campaign_id_ctx.set(campaign_id)

    gm_excerpt = gm_text.strip()
    if len(gm_excerpt) > 900:
        gm_excerpt = gm_excerpt[:900].rsplit(" ", 1)[0] + " [truncated]"
    mem_content = f"Event memory\nPlayer action: {user_action}\nOutcome: {gm_excerpt}"

    async def _apply(state: CampaignState) -> CampaignState:
        side = state.side_effects.setdefault(gm_msg_id, MessageSideEffects())
        side.status = "pending"
        side.error = ""

        try:
            mem_id = memory.add_memory(
                campaign_id,
                gm_msg_id,
                mem_content,
                turn=len(state.messages),
                kind="event",
                location=state.player.location,
            )
            side.memory_ids.append(mem_id)

            delta = await extraction.extract_state_changes(state, user_action, gm_text)
            reversal_dict = state_manager.apply_state_delta(state, delta)
            side.reversal = ReversalPatch.model_validate(reversal_dict)

            await summarizer.maybe_summarize(state)
            side.status = "complete"
            state_manager.record_event(state, "turn.postprocess.complete", f"Post-turn updates complete for {gm_msg_id}.")
        except Exception as e:
            side.status = "failed"
            side.error = str(e)
            state_manager.record_event(state, "turn.postprocess.failed", f"Post-turn updates failed for {gm_msg_id}: {e}")
            log.exception("Post-turn work failed for msg=%s", gm_msg_id)
        return state

    await state_manager.mutate_state(campaign_id, _apply)


async def _run_chat_stream(
    campaign_id: str,
    user_message: str | None,
    is_kickoff: bool,
    overrides: SamplingOverrides | None,
) -> AsyncGenerator[bytes, None]:
    async with state_manager.turn_lock(campaign_id):
        state = await state_manager.load_state(campaign_id)
        if state is None:
            yield _sse_pack({"type": "error", "data": "campaign not found"})
            yield _sse_pack({"type": "done", "stop_reason": "error"})
            return

        # Build prompt + window from the freshest state after acquiring the turn lock.
        query_for_memory = user_message or "Begin the scene."
        memories = memory.retrieve_relevant_memories(campaign_id, query_for_memory, n_results=4)
        action_resolution = game_rules.resolve_action(state, user_message or "")
        turn_context = game_rules.render_resolution(action_resolution)
        built = prompt_builder.build_prompt(
            state=state,
            user_message=user_message,
            retrieved_memories=memories,
            turn_context=turn_context,
        )
        _LAST_PROMPT[campaign_id] = {
            "system_prompt": built.system_prompt,
            "stats": built.stats.model_dump(),
            "memories": memories,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        yield _sse_pack({
            "type": "start",
            "stats": built.stats.model_dump(),
            "action_resolution": action_resolution.model_dump() if action_resolution else None,
        })

        buf: list[str] = []
        stop_reason = "stop"
        error: str | None = None
        cancelled = False

        try:
            async for event in stream_chat(
                built.messages,
                model=state.models.gm,
                overrides=overrides or state.sampling_overrides,
            ):
                et = event.get("type")
                if et == "token":
                    chunk = event["data"]
                    buf.append(chunk)
                    yield _sse_pack({"type": "token", "data": chunk})
                elif et == "error":
                    error = event.get("data") or "unknown error"
                    yield _sse_pack({"type": "error", "data": error})
                elif et == "done":
                    stop_reason = event.get("stop_reason", "stop")
        except asyncio.CancelledError:
            # Client disconnect (C1 stop button). Persist the partial and exit
            # the generator without re-raising so starlette cleans up cleanly.
            stop_reason = "cancelled"
            cancelled = True

        gm_text = "".join(buf).strip()

        if not gm_text and error:
            # Nothing narrated — error already sent. Don't pollute history.
            yield _sse_pack({"type": "done", "stop_reason": "error"})
            return

        partial = stop_reason in ("cancelled", "length") or (error is not None and bool(gm_text))
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"

        async def _persist(st: CampaignState) -> CampaignState:
            import schema as _schema
            if user_message is not None:
                st.messages.append(_schema.Message(
                    turn_id=turn_id,
                    role=Role.USER,
                    content=user_message,
                    is_kickoff=is_kickoff,
                ))
            gm_msg = _schema.Message(
                turn_id=turn_id,
                role=Role.ASSISTANT,
                content=gm_text,
                partial=partial,
                is_kickoff=is_kickoff,
            )
            st.messages.append(gm_msg)
            st.side_effects.setdefault(gm_msg.id, MessageSideEffects(status="skipped" if cancelled else "pending"))
            state_manager.record_event(st, "turn.stream.complete", f"GM message {gm_msg.id} saved with stop_reason={stop_reason}.")
            return st

        new_state = await state_manager.mutate_state(campaign_id, _persist)

        gm_msg_id: str | None = None
        if new_state is not None:
            gm_msg_id = new_state.messages[-1].id

        yield _sse_pack({
            "type": "done",
            "stop_reason": stop_reason,
            "prompt_stats": built.stats.model_dump(),
            "partial": partial,
            "gm_msg_id": gm_msg_id,
            "turn_id": turn_id,
        })

        # Extraction + summarization run AFTER the stream closes. They make
        # another LLM call (utility model) and would otherwise keep the
        # frontend's "weaving the thread" indicator up well past the visible
        # narration. mutate_state has its own lock so concurrency with a
        # follow-up turn is safe.
        if gm_msg_id and gm_text and not cancelled:
            asyncio.create_task(_background_after_turn(
                campaign_id=campaign_id,
                user_action=user_message or "",
                gm_msg_id=gm_msg_id,
                gm_text=gm_text,
            ))


@app.post("/api/chat/stream", dependencies=[Depends(chat_rate_limit)])
async def chat_stream(req: ChatRequest):
    campaign_id_ctx.set(req.campaign_id)
    state = await state_manager.load_state(req.campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    return StreamingResponse(
        _run_chat_stream(
            campaign_id=req.campaign_id,
            user_message=req.user_message,
            is_kickoff=False,
            overrides=req.overrides,
        ),
        media_type="application/x-ndjson",
    )


@app.post("/api/campaign/{campaign_id}/kickoff", dependencies=[Depends(chat_rate_limit)])
async def kickoff_campaign(campaign_id: str):
    """Opening-scene narration with an explicit synthetic user turn (A10)."""
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    if any(m.role == Role.ASSISTANT for m in state.messages):
        raise HTTPException(400, "campaign already has messages; use /chat/stream instead")

    kickoff_prompt = (
        "Begin the scene. Narrate the opening in vivid detail using the world, "
        "scene, and protagonist context provided. End at a decision point."
    )

    return StreamingResponse(
        _run_chat_stream(
            campaign_id=campaign_id,
            user_message=kickoff_prompt,
            is_kickoff=True,
            overrides=None,
        ),
        media_type="application/x-ndjson",
    )


@app.post("/api/campaign/{campaign_id}/continue", dependencies=[Depends(chat_rate_limit)])
async def continue_chat(campaign_id: str):
    """
    Continue the most recent assistant message without repeating (C2).
    Appends to the same message rather than creating a new turn.
    """
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    last_gm = next((m for m in reversed(state.messages) if m.role == Role.ASSISTANT), None)
    if last_gm is None:
        raise HTTPException(400, "no assistant message to continue")

    continue_prompt = (
        "Continue the previous narration without repeating anything you already wrote. "
        "Pick up mid-scene and keep the prose flowing."
    )

    async def _gen() -> AsyncGenerator[bytes, None]:
        async with state_manager.turn_lock(campaign_id):
            fresh = await state_manager.load_state(campaign_id)
            if fresh is None:
                yield _sse_pack({"type": "error", "data": "campaign not found"})
                yield _sse_pack({"type": "done", "stop_reason": "error"})
                return

            fresh_last_gm = next((m for m in reversed(fresh.messages) if m.role == Role.ASSISTANT), None)
            if fresh_last_gm is None:
                yield _sse_pack({"type": "error", "data": "no assistant message to continue"})
                yield _sse_pack({"type": "done", "stop_reason": "error"})
                return

            memories = memory.retrieve_relevant_memories(campaign_id, fresh_last_gm.content, n_results=3)
            built = prompt_builder.build_prompt(
                state=fresh,
                user_message=continue_prompt,
                retrieved_memories=memories,
            )
            _LAST_PROMPT[campaign_id] = {
                "system_prompt": built.system_prompt,
                "stats": built.stats.model_dump(),
                "memories": memories,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield _sse_pack({"type": "start", "stats": built.stats.model_dump()})

            buf: list[str] = []
            stop_reason = "stop"
            async for event in stream_chat(built.messages, model=fresh.models.gm):
                et = event.get("type")
                if et == "token":
                    buf.append(event["data"])
                    yield _sse_pack({"type": "token", "data": event["data"]})
                elif et == "error":
                    yield _sse_pack({"type": "error", "data": event.get("data", "error")})
                elif et == "done":
                    stop_reason = event.get("stop_reason", "stop")

            appended = "".join(buf).strip()
            if appended:
                async def _apply(st: CampaignState) -> CampaignState:
                    for m in reversed(st.messages):
                        if m.role == Role.ASSISTANT:
                            separator = "" if m.content.endswith(("\n", " ")) else " "
                            m.content = m.content + separator + appended
                            m.partial = stop_reason in ("cancelled", "length")
                            break
                    return st
                await state_manager.mutate_state(campaign_id, _apply)

            yield _sse_pack({
                "type": "done",
                "stop_reason": stop_reason,
                "prompt_stats": built.stats.model_dump(),
                "appended_chars": len(appended),
            })

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Message-level operations (rollback — B1/B2)
# ---------------------------------------------------------------------------


@app.delete("/api/campaign/{campaign_id}/message/{msg_id}")
async def delete_message(campaign_id: str, msg_id: str):
    campaign_id_ctx.set(campaign_id)

    async def _apply(state: CampaignState) -> CampaignState:
        target_index = next((i for i, m in enumerate(state.messages) if m.id == msg_id), -1)
        if target_index < 0:
            return state

        target = state.messages[target_index]
        if target.turn_id:
            remove_ids = {m.id for m in state.messages if m.turn_id == target.turn_id}
        elif target.role == Role.ASSISTANT and target_index > 0 and state.messages[target_index - 1].role == Role.USER:
            remove_ids = {state.messages[target_index - 1].id, target.id}
        else:
            remove_ids = {target.id}

        for removed_id in list(remove_ids):
            side = state.side_effects.get(removed_id)
            if side:
                state_manager.apply_reversal(state, side.reversal.model_dump())
                if side.memory_ids:
                    memory.delete_memories_for_message(campaign_id, side.memory_ids)
                state.side_effects.pop(removed_id, None)

        state.messages = [m for m in state.messages if m.id not in remove_ids]
        return state

    new_state = await state_manager.mutate_state(campaign_id, _apply)
    if new_state is None:
        raise HTTPException(404, "campaign not found")
    return {"status": "success"}


@app.post("/api/campaign/{campaign_id}/regenerate/{msg_id}")
async def regenerate_message(campaign_id: str, msg_id: str):
    """Delete the target assistant message (with rollback), then regenerate from the previous user turn."""
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    target_index = next((i for i, m in enumerate(state.messages) if m.id == msg_id), -1)
    if target_index < 0 or state.messages[target_index].role != Role.ASSISTANT:
        raise HTTPException(400, "target must be an existing assistant message")

    prev_user: str | None = None
    for m in reversed(state.messages[:target_index]):
        if m.role == Role.USER:
            prev_user = m.content
            break
    if prev_user is None:
        raise HTTPException(400, "no preceding user message to regenerate from")

    # Delete the target (and its user counterpart, which we'll re-send).
    async def _prune(st: CampaignState) -> CampaignState:
        idx = next((i for i, m in enumerate(st.messages) if m.id == msg_id), -1)
        if idx < 0:
            return st

        target = st.messages[idx]
        if target.turn_id:
            remove_ids = {m.id for m in st.messages if m.turn_id == target.turn_id}
        elif idx > 0 and st.messages[idx - 1].role == Role.USER:
            remove_ids = {st.messages[idx - 1].id, target.id}
        else:
            remove_ids = {target.id}

        for removed_id in list(remove_ids):
            side = st.side_effects.get(removed_id)
            if side:
                state_manager.apply_reversal(st, side.reversal.model_dump())
                if side.memory_ids:
                    memory.delete_memories_for_message(campaign_id, side.memory_ids)
                st.side_effects.pop(removed_id, None)

        st.messages = [m for m in st.messages if m.id not in remove_ids]
        return st

    pruned = await state_manager.mutate_state(campaign_id, _prune)
    if pruned is None:
        raise HTTPException(404, "campaign disappeared")

    return StreamingResponse(
        _run_chat_stream(
            campaign_id=campaign_id,
            user_message=prev_user,
            is_kickoff=False,
            overrides=None,
        ),
        media_type="application/x-ndjson",
    )


# ---------------------------------------------------------------------------
# World generation
# ---------------------------------------------------------------------------


@app.post("/api/world/generate")
async def generate_world(req: GenerateWorldRequest):
    # Decide which model to use (A11 + C11).
    if req.model:
        model = req.model
    elif req.nsfw:
        model = NSFW_CREATIVE_MODEL
    else:
        model = DEFAULT_CREATIVE_MODEL

    sys_prompt = f"""You are an expert worldbuilder for a text RPG. Expand the user's vague concept into a richly detailed starting state.

Return ONLY a JSON object matching this schema:
{{
    "world_description": "<string: 2-3 paragraphs — lore, atmosphere, factions>",
    "starting_scene": "<string: 1-2 paragraphs — exactly where the protagonist stands and what is happening right now>",
    "player_starting_location": "<string>",
    "story_summary": "<string: 3-4 sentences — background history + player's current situation>",
    "lorebook": [ {{"keyword": "<string>", "rule": "<string>"}} ],
    "npcs": [ {{"name": "<string>", "disposition": "Friendly|Neutral|Suspicious|Hostile", "secrets_known": ["<string>"]}} ]
}}
Ensure exactly 3 NPCs and at least 3 lorebook entries.

User Concept: {req.prompt}"""

    result = await complete_json(
        messages=[{"role": "user", "content": sys_prompt}],
        model=model,
        timeout=120.0,
    )
    if result is None:
        raise HTTPException(502, f"World generation failed (model {model} unavailable or returned no JSON)")
    return result


# ---------------------------------------------------------------------------
# Inspector / diagnostics (C3 + C4)
# ---------------------------------------------------------------------------


@app.get("/api/campaign/{campaign_id}/last_prompt")
async def get_last_prompt(campaign_id: str):
    if campaign_id not in _LAST_PROMPT:
        return {"available": False}
    return {"available": True, **_LAST_PROMPT[campaign_id]}


@app.get("/api/campaign/{campaign_id}/debug")
async def get_debug_bundle(campaign_id: str):
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    memory_count = 0
    with suppress(Exception):
        memory_count = memory.get_collection(campaign_id).count()

    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "state": state.model_dump(mode="json"),
        "last_prompt": _LAST_PROMPT.get(campaign_id),
        "memory_count": memory_count,
        "recent_events": [e.model_dump(mode="json") for e in state.events[-25:]],
    }


# ---------------------------------------------------------------------------
# Export / import (C6)
# ---------------------------------------------------------------------------


@app.get("/api/campaign/{campaign_id}/export")
async def export_campaign(campaign_id: str):
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    coll = memory.get_collection(campaign_id)
    try:
        mem_data = coll.get()
    except Exception:
        mem_data = {"ids": [], "documents": [], "metadatas": []}

    payload = {
        "schema_version": SCHEMA_VERSION,
        "state": state.model_dump(mode="json"),
        "memories": {
            "ids": mem_data.get("ids", []),
            "documents": mem_data.get("documents", []),
            "metadatas": mem_data.get("metadatas", []),
        },
    }
    return JSONResponse(content=payload, headers={"Content-Disposition": f'attachment; filename="{campaign_id}.json"'})


class ImportRequest(BaseModel):
    state: dict
    memories: dict | None = None


@app.post("/api/campaign/import")
async def import_campaign(body: ImportRequest):
    import time
    try:
        inbound = CampaignState.model_validate(body.state)
    except Exception as e:
        raise HTTPException(400, f"invalid state payload: {e}")

    new_id = f"{inbound.campaign_id}_import_{int(time.time())}"
    inbound.campaign_id = new_id
    inbound.created_at = datetime.now(timezone.utc).isoformat()
    await state_manager.save_state(inbound)

    mems = body.memories or {}
    ids = mems.get("ids") or []
    docs = mems.get("documents") or []
    metas = mems.get("metadatas") or []
    if ids and docs and len(ids) == len(docs):
        coll = memory.get_collection(new_id)
        new_metas = []
        for m in metas:
            m = dict(m or {})
            m["campaign"] = new_id
            new_metas.append(m)
        with suppress(Exception):
            coll.add(ids=[f"imp_{i}" for i in ids], documents=docs, metadatas=new_metas or None)

    return {"status": "success", "campaign_id": new_id}
