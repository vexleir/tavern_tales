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
import socket
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

import extraction
import game_rules
import memory
import model_resolver
import preference_merger
import preference_logic
import preference_store
import prompt_builder
import session_manager
import state_manager
import summarizer
from logging_config import campaign_id_ctx, configure_logging, request_id_ctx
from model_resolver import NSFW_CREATIVE_MODEL
from ollama_client import complete_json_detail, stream_chat
from preference_schema import (
    ContextType,
    GeneratedFantasy,
    IntensityPreference,
    SharingMode,
    UserPreferenceProfile,
)
from rate_limit import chat_rate_limit
from schema import (
    SCHEMA_VERSION,
    CampaignState,
    MessageSideEffects,
    ModelConfig,
    NPC,
    Player,
    PlayerCharacter,
    PlayerSlot,
    ReversalPatch,
    Role,
    RulesConfig,
    SamplingOverrides,
    SessionStatus,
    StatBound,
)
from secure_storage import SecureStorageError, export_local_key_backup, password_encrypt_text

configure_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="Tavern Tales Reborn GM Engine")
WEBSOCKET_DISCONNECT_GRACE_SECONDS = 2.0
SESSION_EXPIRED_MESSAGE = (
    "Session expired - the reconnect window closed. Please contact the host for a new room code."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
    ],
    # Allow loopback plus RFC1918 private-network LAN IPs and the Tailscale
    # CGNAT range (100.64.0.0/10) so multiplayer guests on the same network or
    # connected via Tailscale can reach the API. Internet-mode tunnel hostnames
    # (ngrok, Cloudflare) require their own CORS configuration via that tunnel.
    allow_origin_regex=(
        r"^http://("
        r"localhost|127\.0\.0\.1|\[::1\]|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|"
        r"100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"
        r"):\d+$"
    ),
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
        response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "connect-src 'self' http://localhost:* http://127.0.0.1:* http://[::1]:* "
            "http://*:8000 ws://localhost:* ws://127.0.0.1:* ws://[::1]:* ws://*:8000; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        return response
    finally:
        request_id_ctx.reset(token)


@app.on_event("startup")
async def _startup() -> None:
    await state_manager.initialize()
    await preference_store.initialize()
    await session_manager.initialize()
    memory.purge_deleted_memory_artifacts()
    asyncio.create_task(_session_cleanup_loop())
    log.info("Tavern Tales backend started (schema v%d).", SCHEMA_VERSION)


async def _session_cleanup_loop() -> None:
    """Archive stale paused sessions every 30 minutes."""
    while True:
        await asyncio.sleep(1800)
        try:
            removed = await session_manager.cleanup_expired_sessions()
            if removed:
                log.info("Session cleanup: archived %d expired session(s).", removed)
        except Exception:
            log.exception("Session cleanup loop error.")


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
    player_gender: str = "Unspecified"
    player_appearance: str = ""
    player_description: str = ""
    stats: dict[str, int]
    inventory: list[str] = Field(default_factory=list)
    npcs: list[dict[str, Any]] = Field(default_factory=list)
    lorebook: dict[str, str] = Field(default_factory=dict)
    story_summary: str = ""
    world_description: str = ""
    starting_scene: str = ""
    preference_context: dict[str, Any] = Field(default_factory=dict)
    gm_model: str = "llama3"
    utility_model: str | None = None
    nsfw_world_gen: bool = False
    summary_short_interval: int = 5
    summary_chapter_interval: int = 20


class GenerateWorldRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    nsfw: bool = False
    gm_model: str | None = None
    utility_model: str | None = None
    # Legacy clients sent the narrator model here. Keep accepting the field,
    # but don't use it as the world-generation model.
    model: str | None = None


class DirectorPatchRequest(BaseModel):
    expected_revision: int | None = None
    player: dict[str, Any] | None = None
    stats: dict[str, int] | None = None
    inventory: list[str] | None = None
    npcs: list[dict[str, Any]] | None = None
    lorebook: dict[str, str] | None = None
    stat_bounds: dict[str, Any] | None = None


class CreatePreferenceProfileRequest(BaseModel):
    displayName: str = Field(default="Default Profile", max_length=120)
    userId: str = Field(default="local_default", max_length=120)


class ImportPreferenceProfileRequest(BaseModel):
    profile: dict[str, Any]
    userId: str = Field(default="local_default", max_length=120)
    displayNameSuffix: str = Field(default="(Imported)", max_length=80)


class RandomFantasyRequest(BaseModel):
    context: ContextType = ContextType.AI
    selectedCount: int = Field(default=4, ge=1, le=6)
    sharingMode: SharingMode = SharingMode.PRIVATE
    categoryIds: list[str] = Field(default_factory=list)
    intensity: IntensityPreference | None = None
    favoritesOnly: bool = False
    exploreLowerInterest: bool = False
    includeRealityBridge: bool = False
    save: bool = True


class CompareProfilesRequest(BaseModel):
    firstProfileId: str
    secondProfileId: str
    context: ContextType = ContextType.AI


class OverlapFantasyRequest(CompareProfilesRequest):
    selectedCount: int = Field(default=4, ge=1, le=6)
    save: bool = True


class ProtectFantasyRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=512)
    hint: str = Field(default="", max_length=160)


class UnlockFantasyRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=512)


class SaveFantasyRequest(BaseModel):
    fantasy: dict[str, Any]
    password: str | None = Field(default=None, min_length=1, max_length=512)


class ExportFantasyRequest(BaseModel):
    mode: SharingMode = SharingMode.SUMMARY_ONLY
    password: str | None = Field(default=None, min_length=1, max_length=512)


class CreateSessionRequest(BaseModel):
    campaign_id: str
    host_character: dict[str, Any] | None = None
    reconnect_window_seconds: int = Field(default=300, ge=30, le=86_400)


class LeaveSessionRequest(BaseModel):
    slot: PlayerSlot


class UpdateSessionCharacterRequest(BaseModel):
    slot: PlayerSlot
    name: str | None = Field(default=None, max_length=80)
    gender: str | None = Field(default=None, max_length=40)
    appearance: str | None = Field(default=None, max_length=600)
    description: str | None = Field(default=None, max_length=1200)
    location: str | None = Field(default=None, max_length=200)
    stats: dict[str, int] | None = Field(default=None, max_length=50)
    inventory: list[str] | None = Field(default=None, max_length=100)


# ---------------------------------------------------------------------------
# Root / diagnostics
# ---------------------------------------------------------------------------


@app.get("/")
def read_root():
    return {"status": "Tavern Tales backend is running.", "schema_version": SCHEMA_VERSION}


@app.get("/api/health")
async def get_health():
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("http://localhost:11434/api/tags", timeout=2.0)
            res.raise_for_status()
            data = res.json()
            return {"ollama": "ok", "models_available": len(data.get("models", []))}
        except Exception as e:
            log.warning("Ollama health check failed: %s", e)
            return {"ollama": "unreachable", "models_available": 0}


def _detect_lan_ip() -> str:
    """Best-effort active LAN address detection with localhost fallback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@app.get("/api/server/info")
def get_server_info(request: Request):
    host_header = request.headers.get("host", "")
    port = 8000
    if ":" in host_header and not host_header.startswith("["):
        with suppress(ValueError):
            port = int(host_header.rsplit(":", 1)[1])
    return {
        "lan_ip": _detect_lan_ip(),
        "port": port,
        "version": f"schema-v{SCHEMA_VERSION}",
    }


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
# Preference profiles / saved fantasies
# ---------------------------------------------------------------------------


def _sensitive_storage_http_error(e: Exception) -> HTTPException:
    if isinstance(e, SecureStorageError):
        return HTTPException(500, str(e))
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    if isinstance(e, ValidationError):
        return HTTPException(422, e.errors())
    return HTTPException(500, str(e))


@app.get("/api/preference-profiles")
async def list_preference_profiles(include_archived: bool = False):
    try:
        profiles = await preference_store.list_profiles(include_archived)
        # Build reverse-lookup: profile_id → list of campaign IDs that reference it.
        linked: dict[str, list[str]] = {}
        try:
            summaries = await state_manager.list_campaigns()
            for summary in summaries:
                state = await state_manager.load_state(summary.id)
                if state and state.preference_context and state.preference_context.enabled:
                    pid = state.preference_context.profile_id or ""
                    if pid:
                        linked.setdefault(pid, []).append(summary.id)
        except Exception:
            log.warning("Could not build preference profile cross-reference.")
        result = []
        for p in profiles:
            d = p.model_dump(mode="json")
            d["linked_campaigns"] = linked.get(p.profileId, [])
            result.append(d)
        return result
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/preference-profiles")
async def create_preference_profile(req: CreatePreferenceProfileRequest):
    try:
        profile = await preference_store.create_profile(req.displayName, user_id=req.userId)
        return preference_logic.redact_profile(profile, include_private=True)
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.get("/api/preference-profiles/{profile_id}")
async def get_preference_profile(profile_id: str, include_private: bool = True):
    try:
        profile = await preference_store.load_profile(profile_id)
        if profile is None or profile.status.value == "deleted":
            raise HTTPException(404, "preference profile not found")
        return preference_logic.redact_profile(profile, include_private=include_private)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.put("/api/preference-profiles/{profile_id}")
async def update_preference_profile(profile_id: str, body: dict[str, Any]):
    try:
        existing = await preference_store.load_profile(profile_id)
        if existing is not None and existing.status.value == "deleted":
            raise HTTPException(404, "preference profile not found")
        body["profileId"] = profile_id
        profile = UserPreferenceProfile.model_validate(body)
        saved = await preference_store.save_profile(profile, bump_version=True)
        return preference_logic.redact_profile(saved, include_private=True)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.delete("/api/preference-profiles/{profile_id}")
async def delete_preference_profile(profile_id: str):
    try:
        deleted = await preference_store.delete_profile(profile_id)
        if not deleted:
            raise HTTPException(404, "preference profile not found")
        return {"status": "success", "profileId": profile_id}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.get("/api/preference-profiles/{profile_id}/export")
async def export_preference_profile(profile_id: str, include_private: bool = False):
    try:
        profile = await preference_store.load_profile(profile_id)
        if profile is None or profile.status.value == "deleted":
            raise HTTPException(404, "preference profile not found")
        payload = preference_logic.redact_profile(profile, include_private=include_private)
        suffix = "private" if include_private else "redacted"
        return JSONResponse(
            content={
                "exportType": "tavern_tales_preference_profile",
                "schemaVersion": profile.schemaVersion,
                "exportedAt": datetime.now(timezone.utc).isoformat(),
                "owner": {
                    "userId": profile.userId,
                    "profileId": profile.profileId,
                    "profileVersion": profile.profileVersion,
                    "displayName": profile.displayName,
                },
                "profile": payload,
                "exportIncludesPrivate": include_private,
                "fantasiesIncluded": False,
            },
            headers={"Content-Disposition": f'attachment; filename="{profile_id}.{suffix}.preferences.json"'},
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/preference-profiles/import")
async def import_preference_profile(req: ImportPreferenceProfileRequest):
    try:
        profile = await preference_store.import_profile(req.profile, user_id=req.userId, display_name_suffix=req.displayNameSuffix)
        return preference_logic.redact_profile(profile, include_private=True)
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.get("/api/preferences/key-backup")
async def export_preference_key_backup():
    try:
        return export_local_key_backup()
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/preference-profiles/{profile_id}/random-fantasy")
async def create_random_preference_fantasy(profile_id: str, req: RandomFantasyRequest):
    try:
        profile = await preference_store.load_profile(profile_id)
        if profile is None or profile.status.value == "deleted":
            raise HTTPException(404, "preference profile not found")
        fantasy = preference_logic.build_random_fantasy(
            profile,
            context=req.context,
            selected_count=req.selectedCount,
            sharing_mode=req.sharingMode,
            category_ids=req.categoryIds,
            intensity=req.intensity,
            favorites_only=req.favoritesOnly,
            explore_lower_interest=req.exploreLowerInterest,
            include_reality_bridge=req.includeRealityBridge,
        )
        if req.save:
            fantasy = await preference_store.save_fantasy(fantasy)
        return preference_logic.redact_fantasy(fantasy, include_private=True)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/compatibility/compare")
async def compare_preference_profiles(req: CompareProfilesRequest):
    try:
        first = await preference_store.load_profile(req.firstProfileId)
        second = await preference_store.load_profile(req.secondProfileId)
        if first is None or second is None or first.status.value == "deleted" or second.status.value == "deleted":
            raise HTTPException(404, "one or more preference profiles were not found")
        return preference_logic.compare_profiles(first, second, context=req.context)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/compatibility/overlap-fantasy")
async def create_overlap_fantasy(req: OverlapFantasyRequest):
    try:
        first = await preference_store.load_profile(req.firstProfileId)
        second = await preference_store.load_profile(req.secondProfileId)
        if first is None or second is None or first.status.value == "deleted" or second.status.value == "deleted":
            raise HTTPException(404, "one or more preference profiles were not found")
        fantasy = preference_logic.build_overlap_fantasy(
            first,
            second,
            context=req.context,
            selected_count=req.selectedCount,
        )
        if req.save:
            fantasy = await preference_store.save_fantasy(fantasy)
        return preference_logic.redact_fantasy(fantasy, include_private=True)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.get("/api/fantasies")
async def list_saved_fantasies(profile_id: str | None = None):
    try:
        return [f.model_dump(mode="json") for f in await preference_store.list_fantasies(profile_id)]
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/fantasies")
async def save_generated_fantasy(req: SaveFantasyRequest):
    try:
        fantasy = GeneratedFantasy.model_validate(req.fantasy)
        saved = await preference_store.save_fantasy(fantasy)
        return preference_logic.redact_fantasy(saved, include_private=True)
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.put("/api/fantasies/{fantasy_id}")
async def update_saved_fantasy(fantasy_id: str, req: SaveFantasyRequest):
    try:
        existing = await preference_store.load_fantasy(fantasy_id)
        if existing is None:
            raise HTTPException(404, "fantasy not found")
        fantasy = GeneratedFantasy.model_validate(req.fantasy)
        fantasy.id = fantasy_id
        if existing.passwordProtection.enabled:
            fantasy.passwordProtection = existing.passwordProtection
            if req.password:
                preference_store.unlock_fantasy_content(existing, req.password)
                fantasy.protectedContent = password_encrypt_text(fantasy.content, req.password)
            else:
                fantasy.protectedContent = existing.protectedContent
            fantasy.content = ""
        saved = await preference_store.save_fantasy(fantasy)
        return preference_logic.redact_fantasy(saved, include_private=True)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.get("/api/fantasies/{fantasy_id}")
async def get_saved_fantasy(fantasy_id: str, include_private: bool = False):
    try:
        fantasy = await preference_store.load_fantasy(fantasy_id)
        if fantasy is None:
            raise HTTPException(404, "fantasy not found")
        return preference_logic.redact_fantasy(fantasy, include_private=include_private)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/fantasies/{fantasy_id}/protect")
async def protect_saved_fantasy(fantasy_id: str, req: ProtectFantasyRequest):
    try:
        fantasy = await preference_store.protect_fantasy(fantasy_id, req.password, hint=req.hint)
        if fantasy is None:
            raise HTTPException(404, "fantasy not found")
        return preference_logic.redact_fantasy(fantasy, include_private=True)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/fantasies/{fantasy_id}/unlock")
async def unlock_saved_fantasy(fantasy_id: str, req: UnlockFantasyRequest):
    try:
        fantasy = await preference_store.load_fantasy(fantasy_id)
        if fantasy is None:
            raise HTTPException(404, "fantasy not found")
        content = preference_store.unlock_fantasy_content(fantasy, req.password)
        return preference_logic.redact_fantasy(fantasy, include_private=True, unlocked_content=content)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


@app.post("/api/fantasies/{fantasy_id}/export")
async def export_saved_fantasy(fantasy_id: str, req: ExportFantasyRequest):
    try:
        fantasy = await preference_store.load_fantasy(fantasy_id)
        if fantasy is None:
            raise HTTPException(404, "fantasy not found")
        unlocked_content = None
        if fantasy.passwordProtection.enabled and req.password:
            unlocked_content = preference_store.unlock_fantasy_content(fantasy, req.password)
        return preference_logic.export_fantasy_for_sharing(fantasy, req.mode, unlocked_content=unlocked_content)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sensitive_storage_http_error(e)


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
        rules=RulesConfig(
            summary_short_interval=max(1, req.summary_short_interval),
            summary_chapter_interval=max(1, req.summary_chapter_interval),
        ),
        player=Player(
            name=req.player_name,
            location=req.starting_location,
            gender=req.player_gender or "Unspecified",
            appearance=req.player_appearance,
            description=req.player_description,
            stats=dict(req.stats),
            inventory=list(req.inventory),
        ),
        npcs=npcs,
        lorebook=dict(req.lorebook),
        world_description=req.world_description,
        starting_scene=req.starting_scene,
        preference_context=req.preference_context,
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
    _LAST_PROMPT.pop(campaign_id, None)
    return {"status": "success" if deleted else "not_found"}


class RenameCampaignRequest(BaseModel):
    title: str = Field(..., max_length=120)


@app.post("/api/campaigns/{campaign_id}/rename")
async def rename_campaign(campaign_id: str, req: RenameCampaignRequest):
    campaign_id_ctx.set(campaign_id)
    new_title = req.title.strip()

    async def _apply(state: CampaignState) -> CampaignState:
        state.title = new_title
        state_manager.record_event(
            state,
            "campaign.rename",
            f"Campaign renamed to {new_title!r}." if new_title else "Campaign title cleared.",
        )
        return state

    new_state = await state_manager.mutate_state(campaign_id, _apply)
    if new_state is None:
        raise HTTPException(404, "campaign not found")
    return {"status": "success", "title": new_state.title}


@app.get("/api/state/{campaign_id}")
async def get_state(campaign_id: str, x_player_slot: str | None = Header(default=None)):
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")
    _ensure_host_state_access(state, x_player_slot)
    return state.model_dump(mode="json")


@app.put("/api/state/{campaign_id}")
async def override_state(
    campaign_id: str,
    body: dict,
    x_player_slot: str | None = Header(default=None),
):
    """Director-mode override. Validates full state via Pydantic (B4)."""
    campaign_id_ctx.set(campaign_id)
    existing = await state_manager.load_state(campaign_id)
    if existing is not None:
        _ensure_host_state_access(existing, x_player_slot)
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
async def patch_state(
    campaign_id: str,
    req: DirectorPatchRequest,
    x_player_slot: str | None = Header(default=None),
):
    """Narrow Director-mode patch with optimistic revision checking."""
    campaign_id_ctx.set(campaign_id)

    async def _apply(state: CampaignState) -> CampaignState:
        _ensure_host_state_access(state, x_player_slot)
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
            if "gender" in req.player:
                state.player.gender = str(req.player["gender"]) or "Unspecified"
            if "appearance" in req.player:
                state.player.appearance = str(req.player["appearance"])
            if "description" in req.player:
                state.player.description = str(req.player["description"])

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


@app.post("/api/campaigns/{campaign_id}/convert_to_solo")
async def convert_to_solo(campaign_id: str):
    """Strip archived multiplayer config so the campaign resumes as single-player."""
    campaign_id_ctx.set(campaign_id)
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")
    if state.multiplayer is None:
        raise HTTPException(400, "campaign has no multiplayer config")
    if state.multiplayer.session_status.value != "archived":
        raise HTTPException(400, "session must be archived before converting to solo")

    def _strip(st):
        st.multiplayer = None
        return st

    new_state = await state_manager.mutate_state(campaign_id, _strip)
    if new_state is None:
        raise HTTPException(404, "campaign not found")
    return {"status": "success"}


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
# Multiplayer sessions
# ---------------------------------------------------------------------------


def _require_host_slot(x_player_slot: str | None) -> None:
    if x_player_slot != PlayerSlot.HOST.value:
        raise HTTPException(403, "host slot required")


def _ensure_host_state_access(state: CampaignState, x_player_slot: str | None) -> None:
    if state.multiplayer is not None and x_player_slot != PlayerSlot.HOST.value:
        raise HTTPException(403, "multiplayer campaign state is host-only")


def _host_character_from_state(
    state: CampaignState,
    payload: dict[str, Any] | None,
) -> PlayerCharacter:
    if payload is not None:
        data = dict(payload)
        data["slot"] = PlayerSlot.HOST
        return PlayerCharacter.model_validate(data)

    p = state.player
    return PlayerCharacter(
        slot=PlayerSlot.HOST,
        name=p.name,
        location=p.location,
        gender=p.gender,
        appearance=p.appearance,
        description=p.description,
        stats=dict(p.stats),
        inventory=list(p.inventory),
    )


def _session_join_url(request: Request, room_code: str) -> str:
    lan_ip = _detect_lan_ip()
    origin = request.headers.get("origin", "")
    scheme = "http"
    port = "5173"
    if origin:
        with suppress(ValueError):
            parsed = httpx.URL(origin)
            scheme = parsed.scheme or scheme
            port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
    return f"{scheme}://{lan_ip}:{port}/?room_code={room_code}"


def _profile_from_json(raw: dict[str, Any] | None) -> UserPreferenceProfile | None:
    if raw is None:
        return None
    return UserPreferenceProfile.model_validate(raw)


async def _refresh_merged_preferences(rt: session_manager.SessionRuntime):
    host_profile = None
    guest_profile = None
    host = rt.players.get(PlayerSlot.HOST)
    guest = rt.players.get(PlayerSlot.GUEST)
    if host is not None and host.preference_profile_json is not None:
        host_profile = _profile_from_json(host.preference_profile_json)
    if guest is not None and guest.preference_profile_json is not None:
        guest_profile = _profile_from_json(guest.preference_profile_json)

    context = preference_merger.merge_preferences(host_profile, guest_profile)

    async def _apply(st: CampaignState) -> CampaignState:
        if st.multiplayer is not None:
            st.multiplayer.merged_preference_context = context
        return st

    await state_manager.mutate_state(rt.campaign_id, _apply)
    return context


async def _session_payload(rt: session_manager.SessionRuntime) -> dict[str, Any]:
    state = await state_manager.load_state(rt.campaign_id)
    multiplayer = state.multiplayer if state is not None else None
    merged = multiplayer.merged_preference_context if multiplayer is not None else None
    return {
        "session_state": rt.public_state(),
        "multiplayer": multiplayer.model_dump(mode="json") if multiplayer is not None else None,
        "merged_preferences": merged.model_dump(mode="json") if merged is not None else None,
        "merged_preference_summary": (
            preference_merger.merge_summary(merged) if merged is not None else None
        ),
    }


async def _broadcast_session_state(rt: session_manager.SessionRuntime) -> None:
    await session_manager.broadcast(rt, {"type": "session_state", **await _session_payload(rt)})


async def _send_ws_error(
    websocket: WebSocket,
    message: str,
    code: str = "bad_request",
) -> None:
    await websocket.send_json({"type": "error", "message": message, "code": code})


def _coerce_slot(value: Any) -> PlayerSlot | None:
    if value in (None, ""):
        return None
    try:
        return PlayerSlot(str(value))
    except ValueError:
        return None


@app.post("/api/session/create")
async def create_multiplayer_session(req: CreateSessionRequest, request: Request):
    campaign_id_ctx.set(req.campaign_id)
    state = await state_manager.load_state(req.campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    try:
        host_character = _host_character_from_state(state, req.host_character)
        rt = await session_manager.create_session(
            req.campaign_id,
            host_character,
            reconnect_window_seconds=req.reconnect_window_seconds,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except ValidationError as e:
        raise HTTPException(422, e.errors())

    payload = await _session_payload(rt)
    lan_ip = _detect_lan_ip()
    return {
        "room_code": rt.room_code,
        "join_url": _session_join_url(request, rt.room_code),
        "lan_ip": lan_ip,
        **payload,
    }


@app.get("/api/session/{room_code}/state")
async def get_multiplayer_session_state(room_code: str):
    rt = await session_manager.get_session(room_code)
    if rt is None:
        raise HTTPException(404, "session not found")
    return await _session_payload(rt)


@app.get("/api/session/{room_code}/exists")
async def multiplayer_session_exists(room_code: str):
    rt = await session_manager.get_session(room_code)
    return {
        "exists": rt is not None,
        "status": rt.status.value if rt is not None else None,
    }


@app.post("/api/session/{room_code}/character")
async def update_multiplayer_character(room_code: str, req: UpdateSessionCharacterRequest):
    try:
        rt = await session_manager.update_character(
            room_code,
            req.slot,
            name=req.name,
            gender=req.gender,
            appearance=req.appearance,
            description=req.description,
            location=req.location,
            stats=req.stats,
            inventory=req.inventory,
        )
        await _broadcast_session_state(rt)
        return await _session_payload(rt)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/session/{room_code}/leave")
async def leave_multiplayer_session(room_code: str, req: LeaveSessionRequest):
    rt = await session_manager.mark_disconnected(room_code, req.slot)
    if rt is None:
        raise HTTPException(404, "session not found")
    deadline = None
    if rt.paused_since is not None:
        deadline = (
            rt.paused_since.timestamp() + rt.reconnect_window_seconds
        )
    if rt.status == SessionStatus.PAUSED:
        await session_manager.broadcast(
            rt,
            {
                "type": "session_paused",
                "disconnected_slot": req.slot.value,
                "reconnect_deadline": deadline,
            },
        )
    await _broadcast_session_state(rt)
    return await _session_payload(rt)


@app.post("/api/session/{room_code}/archive")
async def archive_multiplayer_session(
    room_code: str,
    x_player_slot: str | None = Header(default=None),
):
    _require_host_slot(x_player_slot)
    rt = await session_manager.get_session(room_code)
    if rt is None:
        raise HTTPException(404, "session not found")
    await session_manager.broadcast(rt, {"type": "session_archived", "reason": "host_archived"})
    archived = await session_manager.archive_session(room_code)
    return await _session_payload(archived)


@app.delete("/api/session/{room_code}")
async def delete_multiplayer_session(
    room_code: str,
    x_player_slot: str | None = Header(default=None),
):
    _require_host_slot(x_player_slot)
    rt = await session_manager.get_session(room_code)
    if rt is None:
        raise HTTPException(404, "session not found")
    await session_manager.broadcast(rt, {"type": "session_archived", "reason": "host_deleted"})
    campaign_id = rt.campaign_id
    deleted = await session_manager.delete_session(room_code)
    memory.delete_campaign_memory(campaign_id)
    _LAST_PROMPT.pop(campaign_id, None)
    return {"status": "success" if deleted else "not_found"}


def _display_multiplayer_action(content: str) -> str:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith("Submitted action text"):
            continue
        _, _, first = line.partition(":")
        action_lines = [first.strip()]
        for follow in lines[idx + 1:]:
            if follow.startswith("Required response style:") or follow.startswith("After the GM response,"):
                break
            action_lines.append(follow)
        action = "\n".join(action_lines).strip()
        return action or content
    return content


def _multiplayer_actor_name(state: CampaignState, slot: PlayerSlot | None) -> str:
    if state.multiplayer is None:
        return ""
    if slot == PlayerSlot.HOST:
        return state.multiplayer.host_character.name or "Host"
    if slot == PlayerSlot.GUEST and state.multiplayer.guest_character is not None:
        return state.multiplayer.guest_character.name or "Guest"
    return ""


@app.post("/api/session/{room_code}/export")
async def export_multiplayer_narrative(room_code: str):
    rt = await session_manager.get_session(room_code)
    if rt is None:
        raise HTTPException(404, "session not found")
    state = await state_manager.load_state(rt.campaign_id)
    if state is None:
        raise HTTPException(404, "campaign not found")

    actions_by_turn = {
        msg.turn_id: _display_multiplayer_action(msg.content)
        for msg in state.messages
        if msg.turn_id and msg.role == Role.USER
    }

    turns = []
    for msg in state.messages:
        if msg.role != Role.ASSISTANT:
            continue
        turns.append({
            "id": msg.id,
            "turn_id": msg.turn_id,
            "timestamp": msg.timestamp,
            "content": msg.content,
            "gm_content": msg.content,
            "player_action": actions_by_turn.get(msg.turn_id, ""),
            "is_kickoff": msg.is_kickoff,
            "partial": msg.partial,
            "player_slot": msg.player_slot,
            "actor_name": "Opening Scene" if msg.is_kickoff else _multiplayer_actor_name(state, _coerce_slot(msg.player_slot)),
        })
    narrative = "\n\n".join(t["gm_content"] for t in turns)
    return {
        "room_code": room_code.upper(),
        "campaign_id": rt.campaign_id,
        "turns": turns,
        "narrative": narrative,
    }


@app.websocket("/api/session/{room_code}/ws")
async def multiplayer_session_ws(websocket: WebSocket, room_code: str):
    await websocket.accept()
    rt: session_manager.SessionRuntime | None = None
    player_slot: PlayerSlot | None = None
    player_connection_id: str | None = None

    try:
        first = await websocket.receive_json()
        msg_type = first.get("type")
        if msg_type not in {"join", "reconnect"}:
            await _send_ws_error(websocket, "first message must be join or reconnect", "join_required")
            await websocket.close(code=1008)
            return

        desired_slot = _coerce_slot(first.get("slot")) if msg_type == "reconnect" else _coerce_slot(first.get("slot"))
        if msg_type == "reconnect" and desired_slot is None:
            await _send_ws_error(websocket, "reconnect requires slot", "slot_required")
            await websocket.close(code=1008)
            return

        preference_profile = first.get("preference_profile")
        if preference_profile is not None:
            _profile_from_json(preference_profile)

        existing_rt = await session_manager.get_session(room_code)
        if (
            msg_type == "reconnect"
            and existing_rt is not None
            and await session_manager.reconnect_window_expired(existing_rt)
        ):
            await _send_ws_error(websocket, SESSION_EXPIRED_MESSAGE, "session_expired")
            await websocket.close(code=1008)
            return

        try:
            rt, player = await session_manager.join_session(
                room_code,
                websocket=websocket,
                display_name=str(first.get("display_name") or ""),
                character_name=str(first.get("character_name") or ""),
                client_id=str(first.get("client_id") or ""),
                preference_profile_json=preference_profile,
                preference_source=str(first.get("preference_source") or "none"),
                desired_slot=desired_slot,
            )
        except ValueError as e:
            await _send_ws_error(websocket, str(e), "join_failed")
            await websocket.close(code=1008)
            return

        player_slot = player.slot
        player_connection_id = player.connection_id
        ooc_log = await session_manager.read_ooc_log(rt.room_code)
        await websocket.send_json({
            "type": "slot_assigned",
            "slot": player_slot.value,
            "display_name": player.display_name,
            "character_name": player.character_name,
            "connection_id": player_connection_id,
            "ooc_log": ooc_log,
        })
        await _refresh_merged_preferences(rt)
        if msg_type == "reconnect":
            await session_manager.broadcast(rt, {"type": "session_resumed", "slot": player_slot.value})
        else:
            await session_manager.broadcast(
                rt,
                {
                    "type": "player_joined",
                    "slot": player_slot.value,
                    "display_name": player.display_name,
                    "character_name": player.character_name,
                },
            )
        await _broadcast_session_state(rt)

        while True:
            incoming = await websocket.receive_json()
            msg_type = incoming.get("type")

            if msg_type in {"ready", "unready"}:
                before_status = rt.status
                rt = await session_manager.set_ready(
                    rt.room_code,
                    player_slot,
                    is_ready=(msg_type == "ready"),
                )
                await _refresh_merged_preferences(rt)
                await session_manager.broadcast(
                    rt,
                    {
                        "type": "player_ready",
                        "slot": player_slot.value,
                        "is_ready": msg_type == "ready",
                    },
                )
                if rt.status != before_status:
                    active = session_manager.current_active_slot(rt)
                    await session_manager.broadcast(
                        rt,
                        {"type": "floor_passed", "active_slot": active.value if active else None},
                    )
                await _broadcast_session_state(rt)
                if rt.kickoff_needed:
                    asyncio.create_task(_run_multiplayer_kickoff(rt.room_code))

            elif msg_type == "set_starting_slot":
                if player_slot != PlayerSlot.HOST:
                    await _send_ws_error(websocket, "host slot required", "host_only")
                    continue
                if rt.status != SessionStatus.LOBBY:
                    await _send_ws_error(websocket, "starting slot can only be changed in the lobby", "invalid_state")
                    continue
                try:
                    target_slot = PlayerSlot(str(incoming.get("slot") or "").lower())
                except ValueError:
                    await _send_ws_error(websocket, "slot must be host or guest", "invalid_slot")
                    continue
                rt = await session_manager.set_starting_slot(rt.room_code, target_slot)
                await _broadcast_session_state(rt)

            elif msg_type == "submit_action":
                action_text = str(incoming.get("text") or "")
                try:
                    rt, _result = await session_manager.submit_action(
                        rt.room_code,
                        player_slot,
                        action_text,
                    )
                except ValueError as e:
                    await _send_ws_error(websocket, str(e), "not_your_turn" if "not your turn" in str(e) else "submit_failed")
                    continue

                player = rt.players.get(player_slot)
                await session_manager.broadcast(
                    rt,
                    {
                        "type": "generation_start",
                        "turn_number": rt.turn_number,
                        "acting_slot": player_slot.value,
                        "actor_name": player.character_name if player else player_slot.value.title(),
                        "player_action": action_text.strip(),
                    },
                )
                # Spawn the AI turn so the WS remains responsive to OOC and
                # disconnect events while the model is generating.
                asyncio.create_task(_run_multiplayer_turn(rt.room_code))
                await _broadcast_session_state(rt)

            elif msg_type == "gift_turn":
                if player_slot != PlayerSlot.HOST:
                    await _send_ws_error(websocket, "host slot required", "host_only")
                    continue
                if rt.status != SessionStatus.HOST_TURN:
                    await _send_ws_error(websocket, "gift turn is only available during the host turn", "invalid_state")
                    continue
                if rt.kickoff_needed or rt.kickoff_in_progress:
                    await _send_ws_error(websocket, "opening scene in progress", "submit_failed")
                    continue
                rt = await session_manager.begin_next_round(rt.room_code)
                active = session_manager.current_active_slot(rt)
                await session_manager.broadcast(
                    rt,
                    {"type": "floor_passed", "active_slot": active.value if active else None},
                )
                await _broadcast_session_state(rt)

            elif msg_type in {"request_reroll", "request_continue"}:
                target_message_id = str(
                    incoming.get("message_id") or incoming.get("target_message_id") or ""
                ).strip() or None
                try:
                    rt, restore_status = await session_manager.begin_aux_generation(rt.room_code)
                except ValueError as e:
                    await _send_ws_error(websocket, str(e), "generation_unavailable")
                    continue
                if msg_type == "request_reroll":
                    asyncio.create_task(_run_multiplayer_reroll(rt.room_code, restore_status, target_message_id))
                else:
                    asyncio.create_task(_run_multiplayer_continue(rt.room_code, restore_status, target_message_id))
                await _broadcast_session_state(rt)

            elif msg_type == "composing":
                active = session_manager.current_active_slot(rt)
                if active == player_slot:
                    await session_manager.broadcast_except(
                        rt,
                        player_slot,
                        {"type": "partner_composing", "active_slot": player_slot.value},
                    )

            elif msg_type == "ooc_message":
                text = str(incoming.get("text") or "").strip()
                if not text:
                    continue
                text = text[:session_manager.MAX_OOC_MESSAGE_LEN]
                player = rt.players.get(player_slot)
                display_name = player.display_name if player else player_slot.value
                ts = datetime.now(timezone.utc).isoformat()
                await session_manager.broadcast(
                    rt,
                    {
                        "type": "ooc_message",
                        "slot": player_slot.value,
                        "display_name": display_name,
                        "text": text,
                        "ts": ts,
                    },
                )
                try:
                    await session_manager.append_ooc(rt.room_code, player_slot, display_name, text, ts)
                except Exception:
                    log.exception("Failed to persist OOC message for room %s", rt.room_code)

            elif msg_type == "update_character":
                rt = await session_manager.update_character(
                    rt.room_code,
                    player_slot,
                    name=incoming.get("name"),
                    gender=incoming.get("gender"),
                    appearance=incoming.get("appearance"),
                    description=incoming.get("description"),
                    location=incoming.get("location"),
                    stats=incoming.get("stats"),
                    inventory=incoming.get("inventory"),
                )
                await _broadcast_session_state(rt)

            elif msg_type == "archive_session":
                if player_slot != PlayerSlot.HOST:
                    await _send_ws_error(websocket, "host slot required", "host_only")
                    continue
                await session_manager.broadcast(rt, {"type": "session_archived", "reason": "host_archived"})
                await session_manager.archive_session(rt.room_code)
                await websocket.close(code=1000)
                return

            elif msg_type == "delete_session":
                if player_slot != PlayerSlot.HOST:
                    await _send_ws_error(websocket, "host slot required", "host_only")
                    continue
                await session_manager.broadcast(rt, {"type": "session_archived", "reason": "host_deleted"})
                campaign_id = rt.campaign_id
                await session_manager.delete_session(rt.room_code)
                memory.delete_campaign_memory(campaign_id)
                _LAST_PROMPT.pop(campaign_id, None)
                await websocket.close(code=1000)
                return

            elif msg_type == "eject_guest":
                if player_slot != PlayerSlot.HOST:
                    await _send_ws_error(websocket, "host slot required", "host_only")
                    continue
                rt = await session_manager.eject_guest(rt.room_code)
                await session_manager.broadcast(rt, {"type": "player_ejected", "slot": PlayerSlot.GUEST.value})
                await _broadcast_session_state(rt)

            else:
                await _send_ws_error(websocket, f"unknown message type: {msg_type}", "unknown_type")

    except WebSocketDisconnect:
        if rt is not None and player_slot is not None:
            # Fast reloads and transient socket swaps can close the old socket
            # after the same slot has already opened a replacement.
            await asyncio.sleep(WEBSOCKET_DISCONNECT_GRACE_SECONDS)
            paused = await session_manager.mark_disconnected(
                rt.room_code,
                player_slot,
                connection_id=player_connection_id,
            )
            if paused is not None:
                current = paused.players.get(player_slot)
                if (
                    current is not None
                    and current.is_connected
                    and current.connection_id != player_connection_id
                ):
                    return
                deadline = None
                if paused.paused_since is not None:
                    deadline = paused.paused_since.timestamp() + paused.reconnect_window_seconds
                if paused.status == SessionStatus.PAUSED:
                    if await session_manager.reconnect_window_expired(paused):
                        await session_manager.broadcast(
                            paused,
                            {
                                "type": "error",
                                "message": SESSION_EXPIRED_MESSAGE,
                                "code": "session_expired",
                            },
                        )
                    await session_manager.broadcast(
                        paused,
                        {
                            "type": "session_paused",
                            "disconnected_slot": player_slot.value,
                            "reconnect_deadline": deadline,
                        },
                    )
                await _broadcast_session_state(paused)
    except ValidationError as e:
        await _send_ws_error(websocket, str(e), "validation_error")
        await websocket.close(code=1008)


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
            except Exception as _mem_write_err:
                log.warning("Memory write failed for %s msg %s: %s", campaign_id, gm_msg_id, _mem_write_err)

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
        memory_warning = False
        try:
            memories = memory.retrieve_relevant_memories(campaign_id, query_for_memory, n_results=4)
        except Exception as _mem_err:
            log.warning("Memory retrieval failed for %s: %s", campaign_id, _mem_err)
            memories = []
            memory_warning = True
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
            "memory_warning": memory_warning or None,
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
        except Exception as _stream_err:
            # Ollama connection dropped mid-stream (6.4). Preserve partial content.
            log.warning("Ollama stream dropped for %s: %s", campaign_id, _stream_err)
            error = "Connection to AI dropped."
            stop_reason = "cancelled"  # treat as partial so continue/reroll are offered
            yield _sse_pack({"type": "error", "data": error, "partial": True})

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


async def _background_after_multiplayer_turn(
    room_code: str,
    campaign_id: str,
    acting_slot: PlayerSlot,
    action_text: str,
    gm_msg_id: str,
    gm_text: str,
) -> None:
    """Slot-aware extraction + memory + summary cadence for a multiplayer turn."""
    campaign_id_ctx.set(campaign_id)

    gm_excerpt = gm_text.strip()
    if len(gm_excerpt) > 900:
        gm_excerpt = gm_excerpt[:900].rsplit(" ", 1)[0] + " [truncated]"

    async def _apply(state: CampaignState) -> CampaignState:
        side = state.side_effects.setdefault(gm_msg_id, MessageSideEffects())
        side.status = "pending"
        side.error = ""
        side.extra_reversals = []

        try:
            mp = state.multiplayer
            if mp is not None and acting_slot == PlayerSlot.HOST:
                actor = mp.host_character
            elif mp is not None and mp.guest_character is not None:
                actor = mp.guest_character
            else:
                actor = None
            actor_name = actor.name if actor is not None and actor.name else acting_slot.value.title()
            actor_loc = actor.location if actor is not None else state.player.location
            mem_content = (
                "Multiplayer event memory\n"
                f"{actor_name} action: {action_text}\n"
                f"Outcome: {gm_excerpt}"
            )
            mem_id = memory.add_memory(
                campaign_id,
                gm_msg_id,
                mem_content,
                turn=len(state.messages),
                kind="event",
                location=actor_loc,
            )
            side.memory_ids.append(mem_id)

            delta = await extraction.extract_state_changes_for_slot(
                state, acting_slot, action_text, gm_text
            )
            reversal = state_manager.apply_state_delta(state, delta, acting_slot)
            side.reversal = ReversalPatch.model_validate(reversal)

            await summarizer.maybe_summarize(state)
            side.status = "complete"
            state_manager.record_event(
                state,
                "turn.postprocess.complete",
                f"Multiplayer post-turn updates complete for {gm_msg_id}.",
            )
        except Exception as e:
            side.status = "failed"
            side.error = str(e)
            state_manager.record_event(
                state,
                "turn.postprocess.failed",
                f"Multiplayer post-turn updates failed for {gm_msg_id}: {e}",
            )
            log.exception("Multiplayer post-turn work failed for msg=%s", gm_msg_id)
        return state

    await state_manager.mutate_state(campaign_id, _apply)
    rt = await session_manager.get_session(room_code)
    if rt is not None:
        await _broadcast_session_state(rt)


def _rollback_message_group(st: CampaignState, campaign_id: str, msg_id: str) -> None:
    idx = next((i for i, m in enumerate(st.messages) if m.id == msg_id), -1)
    if idx < 0:
        return

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


def _latest_assistant_index(state: CampaignState, target_message_id: str | None = None) -> int:
    if target_message_id:
        return next((i for i, m in enumerate(state.messages) if m.id == target_message_id), -1)
    return next((i for i in range(len(state.messages) - 1, -1, -1) if state.messages[i].role == Role.ASSISTANT), -1)


async def _run_multiplayer_reroll(
    room_code: str,
    restore_status: SessionStatus,
    target_message_id: str | None,
) -> None:
    """Regenerate a multiplayer assistant message without consuming the current floor."""
    rt = await session_manager.get_session(room_code)
    if rt is None:
        return

    campaign_id = rt.campaign_id
    campaign_id_ctx.set(campaign_id)
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    gm_msg_id: str | None = None
    stop_reason = "stop"
    partial = False
    gm_text = ""
    acting_slot: PlayerSlot | None = None
    actor_name = ""
    player_action = ""
    resolved_target_id: str | None = None
    target_is_kickoff = False

    try:
        async with state_manager.turn_lock(campaign_id):
            state = await state_manager.load_state(campaign_id)
            if state is None or state.multiplayer is None:
                await session_manager.broadcast(rt, {"type": "error", "message": "campaign missing or not multiplayer", "code": "campaign_missing"})
                return

            target_index = _latest_assistant_index(state, target_message_id)
            if target_index < 0 or state.messages[target_index].role != Role.ASSISTANT:
                await session_manager.broadcast(rt, {"type": "error", "message": "target must be an assistant message", "code": "invalid_message"})
                return
            target = state.messages[target_index]
            resolved_target_id = target.id
            target_is_kickoff = target.is_kickoff
            acting_slot = _coerce_slot(target.player_slot)
            actor_name = "Opening Scene" if target.is_kickoff else _multiplayer_actor_name(state, acting_slot)

            prev_user = None
            if target.turn_id:
                prev_user = next((m for m in state.messages if m.turn_id == target.turn_id and m.role == Role.USER), None)
            if prev_user is None:
                prev_user = next((m for m in reversed(state.messages[:target_index]) if m.role == Role.USER), None)
            if prev_user is None:
                await session_manager.broadcast(rt, {"type": "error", "message": "no user message to regenerate from", "code": "invalid_message"})
                return
            player_action = "" if target.is_kickoff else _display_multiplayer_action(prev_user.content)

            async def _prune(st: CampaignState) -> CampaignState:
                _rollback_message_group(st, campaign_id, target.id)
                return st

            pruned = await state_manager.mutate_state(campaign_id, _prune)
            if pruned is None:
                await session_manager.broadcast(rt, {"type": "error", "message": "campaign disappeared", "code": "campaign_missing"})
                return

            memories = memory.retrieve_relevant_memories(campaign_id, prev_user.content, n_results=4)
            built = prompt_builder.build_prompt(
                state=pruned,
                user_message=prev_user.content,
                retrieved_memories=memories,
                acting_slot=acting_slot,
            )
            _LAST_PROMPT[campaign_id] = {
                "system_prompt": built.system_prompt,
                "stats": built.stats.model_dump(),
                "memories": memories,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await session_manager.broadcast(
                rt,
                {
                    "type": "generation_start",
                    "turn_number": rt.turn_number,
                    "acting_slot": acting_slot.value if acting_slot else None,
                    "actor_name": actor_name,
                    "player_action": player_action,
                    "is_kickoff": target.is_kickoff,
                    "mode": "reroll",
                    "target_message_id": target.id,
                    "prompt_stats": built.stats.model_dump(),
                },
            )

            buf: list[str] = []
            error: str | None = None
            try:
                async for event in stream_chat(
                    built.messages,
                    model=pruned.models.gm,
                    overrides=pruned.sampling_overrides,
                ):
                    et = event.get("type")
                    if et == "token":
                        chunk = event["data"]
                        buf.append(chunk)
                        await session_manager.broadcast(rt, {"type": "token", "text": chunk})
                    elif et == "error":
                        error = event.get("data") or "unknown error"
                        await session_manager.broadcast(rt, {"type": "error", "message": error, "code": "stream_error"})
                    elif et == "done":
                        stop_reason = event.get("stop_reason", "stop")
            except Exception as e:
                error = str(e)
                log.exception("Multiplayer reroll stream failed for room %s", room_code)
                await session_manager.broadcast(rt, {"type": "error", "message": error, "code": "stream_exception"})

            gm_text = "".join(buf).strip()
            partial = stop_reason == "length" or (error is not None and bool(gm_text))

            if gm_text:
                async def _persist(st: CampaignState) -> CampaignState:
                    import schema as _schema

                    st.messages.append(
                        _schema.Message(
                            turn_id=turn_id,
                            role=Role.USER,
                            content=prev_user.content,
                            is_kickoff=target_is_kickoff,
                            player_slot=acting_slot.value if acting_slot else None,
                        )
                    )
                    gm_msg = _schema.Message(
                        turn_id=turn_id,
                        role=Role.ASSISTANT,
                        content=gm_text,
                        partial=partial,
                        is_kickoff=target_is_kickoff,
                        player_slot=acting_slot.value if acting_slot else None,
                    )
                    st.messages.append(gm_msg)
                    status = "skipped" if target_is_kickoff else "pending"
                    st.side_effects.setdefault(gm_msg.id, MessageSideEffects(status=status))
                    state_manager.record_event(
                        st,
                        "turn.multiplayer.reroll",
                        f"Multiplayer reroll saved (msg={gm_msg.id}, stop={stop_reason}).",
                    )
                    return st

                new_state = await state_manager.mutate_state(campaign_id, _persist)
                if new_state is not None:
                    gm_msg_id = new_state.messages[-1].id
    finally:
        restored = await session_manager.finish_aux_generation(room_code, restore_status)
        if restored is not None:
            active = session_manager.current_active_slot(restored)
            await session_manager.broadcast(
                restored,
                {
                    "type": "generation_done",
                    "turn_number": restored.turn_number,
                    "turn_id": turn_id,
                    "gm_msg_id": gm_msg_id,
                    "target_message_id": resolved_target_id,
                    "stop_reason": stop_reason,
                    "partial": partial,
                    "acting_slot": acting_slot.value if acting_slot else None,
                    "actor_name": actor_name,
                    "player_action": player_action,
                    "is_kickoff": target_is_kickoff,
                    "mode": "reroll",
                    "next_active_slot": active.value if active else None,
                },
            )
            await _broadcast_session_state(restored)

    if gm_msg_id and gm_text and acting_slot is not None and not target_is_kickoff:
        asyncio.create_task(
            _background_after_multiplayer_turn(
                room_code=room_code,
                campaign_id=campaign_id,
                acting_slot=acting_slot,
                action_text=player_action,
                gm_msg_id=gm_msg_id,
                gm_text=gm_text,
            )
        )


async def _run_multiplayer_continue(
    room_code: str,
    restore_status: SessionStatus,
    target_message_id: str | None,
) -> None:
    """Append continuation text to the latest multiplayer assistant message."""
    rt = await session_manager.get_session(room_code)
    if rt is None:
        return

    campaign_id = rt.campaign_id
    campaign_id_ctx.set(campaign_id)
    stop_reason = "stop"
    partial = False
    appended = ""
    gm_msg_id: str | None = None
    acting_slot: PlayerSlot | None = None
    actor_name = ""
    player_action = ""

    continue_prompt = (
        "Continue the previous narration without repeating anything you already wrote. "
        "Pick up mid-scene and keep the prose flowing."
    )

    try:
        async with state_manager.turn_lock(campaign_id):
            state = await state_manager.load_state(campaign_id)
            if state is None or state.multiplayer is None:
                await session_manager.broadcast(rt, {"type": "error", "message": "campaign missing or not multiplayer", "code": "campaign_missing"})
                return

            target_index = _latest_assistant_index(state, target_message_id)
            if target_index < 0 or state.messages[target_index].role != Role.ASSISTANT:
                await session_manager.broadcast(rt, {"type": "error", "message": "target must be an assistant message", "code": "invalid_message"})
                return
            target = state.messages[target_index]
            gm_msg_id = target.id
            acting_slot = _coerce_slot(target.player_slot)
            actor_name = "Opening Scene" if target.is_kickoff else _multiplayer_actor_name(state, acting_slot)
            if target.turn_id:
                user_msg = next((m for m in state.messages if m.turn_id == target.turn_id and m.role == Role.USER), None)
                if user_msg is not None:
                    player_action = "" if target.is_kickoff else _display_multiplayer_action(user_msg.content)

            memories = memory.retrieve_relevant_memories(campaign_id, target.content, n_results=3)
            built = prompt_builder.build_prompt(
                state=state,
                user_message=continue_prompt,
                retrieved_memories=memories,
                acting_slot=acting_slot,
            )
            _LAST_PROMPT[campaign_id] = {
                "system_prompt": built.system_prompt,
                "stats": built.stats.model_dump(),
                "memories": memories,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await session_manager.broadcast(
                rt,
                {
                    "type": "generation_start",
                    "turn_number": rt.turn_number,
                    "acting_slot": acting_slot.value if acting_slot else None,
                    "actor_name": actor_name,
                    "player_action": player_action,
                    "is_kickoff": target.is_kickoff,
                    "mode": "continue",
                    "target_message_id": target.id,
                    "prompt_stats": built.stats.model_dump(),
                },
            )

            buf: list[str] = []
            error: str | None = None
            try:
                async for event in stream_chat(
                    built.messages,
                    model=state.models.gm,
                    overrides=state.sampling_overrides,
                ):
                    et = event.get("type")
                    if et == "token":
                        chunk = event["data"]
                        buf.append(chunk)
                        await session_manager.broadcast(rt, {"type": "token", "text": chunk})
                    elif et == "error":
                        error = event.get("data") or "unknown error"
                        await session_manager.broadcast(rt, {"type": "error", "message": error, "code": "stream_error"})
                    elif et == "done":
                        stop_reason = event.get("stop_reason", "stop")
            except Exception as e:
                error = str(e)
                log.exception("Multiplayer continue stream failed for room %s", room_code)
                await session_manager.broadcast(rt, {"type": "error", "message": error, "code": "stream_exception"})

            appended = "".join(buf).strip()
            partial = stop_reason == "length" or (error is not None and bool(appended))

            if appended:
                async def _apply(st: CampaignState) -> CampaignState:
                    for message in reversed(st.messages):
                        if message.id == target.id and message.role == Role.ASSISTANT:
                            separator = "" if message.content.endswith(("\n", " ")) else " "
                            message.content = message.content + separator + appended
                            message.partial = partial
                            break
                    state_manager.record_event(
                        st,
                        "turn.multiplayer.continue",
                        f"Multiplayer continuation appended to {target.id} (stop={stop_reason}).",
                    )
                    return st

                await state_manager.mutate_state(campaign_id, _apply)
    finally:
        restored = await session_manager.finish_aux_generation(room_code, restore_status)
        if restored is not None:
            active = session_manager.current_active_slot(restored)
            await session_manager.broadcast(
                restored,
                {
                    "type": "generation_done",
                    "turn_number": restored.turn_number,
                    "gm_msg_id": gm_msg_id,
                    "target_message_id": gm_msg_id,
                    "stop_reason": stop_reason,
                    "partial": partial,
                    "acting_slot": acting_slot.value if acting_slot else None,
                    "actor_name": actor_name,
                    "player_action": player_action,
                    "mode": "continue",
                    "next_active_slot": active.value if active else None,
                },
            )
            await _broadcast_session_state(restored)


async def _run_multiplayer_kickoff(room_code: str) -> None:
    """Generate and persist the shared multiplayer opening scene."""
    rt = await session_manager.begin_kickoff_if_needed(room_code)
    if rt is None:
        return

    campaign_id = rt.campaign_id
    campaign_id_ctx.set(campaign_id)
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    gm_msg_id: str | None = None
    stop_reason = "stop"
    partial = False
    started = False

    try:
        async with state_manager.turn_lock(campaign_id):
            state = await state_manager.load_state(campaign_id)
            if state is None or state.multiplayer is None:
                await session_manager.broadcast(
                    rt,
                    {
                        "type": "error",
                        "message": "campaign missing or not multiplayer",
                        "code": "campaign_missing",
                    },
                )
                return

            if any(m.is_kickoff and m.role == Role.ASSISTANT for m in state.messages):
                return

            kickoff_prompt = (
                "Begin the shared opening scene for this multiplayer session. "
                "Introduce both player characters, establish the immediate situation, "
                "and end at a decision point for the host to answer first."
            )
            built = prompt_builder.build_prompt(
                state=state,
                user_message=kickoff_prompt,
                retrieved_memories=[],
                turn_context="",
            )
            _LAST_PROMPT[campaign_id] = {
                "system_prompt": built.system_prompt,
                "stats": built.stats.model_dump(),
                "memories": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await session_manager.broadcast(
                rt,
                {
                    "type": "generation_start",
                    "turn_number": rt.turn_number,
                    "acting_slot": None,
                    "actor_name": "Opening Scene",
                    "player_action": "",
                    "is_kickoff": True,
                    "prompt_stats": built.stats.model_dump(),
                },
            )
            started = True

            buf: list[str] = []
            error: str | None = None
            try:
                async for event in stream_chat(
                    built.messages,
                    model=state.models.gm,
                    overrides=state.sampling_overrides,
                ):
                    et = event.get("type")
                    if et == "token":
                        chunk = event["data"]
                        buf.append(chunk)
                        await session_manager.broadcast(rt, {"type": "token", "text": chunk})
                    elif et == "error":
                        error = event.get("data") or "unknown error"
                        await session_manager.broadcast(rt, {"type": "error", "message": error, "code": "stream_error"})
                    elif et == "done":
                        stop_reason = event.get("stop_reason", "stop")
            except Exception as e:
                error = str(e)
                log.exception("Multiplayer kickoff stream failed for room %s", room_code)
                await session_manager.broadcast(
                    rt,
                    {"type": "error", "message": error, "code": "stream_exception"},
                )

            gm_text = "".join(buf).strip()
            partial = stop_reason == "length" or (error is not None and bool(gm_text))

            if gm_text:
                async def _persist(st: CampaignState) -> CampaignState:
                    import schema as _schema

                    st.messages.append(
                        _schema.Message(
                            turn_id=turn_id,
                            role=Role.USER,
                            content=kickoff_prompt,
                            is_kickoff=True,
                        )
                    )
                    gm_msg = _schema.Message(
                        turn_id=turn_id,
                        role=Role.ASSISTANT,
                        content=gm_text,
                        partial=partial,
                        is_kickoff=True,
                    )
                    st.messages.append(gm_msg)
                    st.side_effects.setdefault(gm_msg.id, MessageSideEffects(status="skipped"))
                    state_manager.record_event(
                        st,
                        "turn.multiplayer.kickoff",
                        f"Multiplayer kickoff saved (msg={gm_msg.id}, stop={stop_reason}).",
                    )
                    return st

                new_state = await state_manager.mutate_state(campaign_id, _persist)
                if new_state is not None:
                    gm_msg_id = new_state.messages[-1].id
    finally:
        finished = await session_manager.finish_kickoff(room_code)
        if finished is not None and started:
            await session_manager.broadcast(
                finished,
                {
                    "type": "generation_done",
                    "turn_number": finished.turn_number,
                    "turn_id": turn_id,
                    "gm_msg_id": gm_msg_id,
                    "stop_reason": stop_reason,
                    "partial": partial,
                    "acting_slot": None,
                    "actor_name": "Opening Scene",
                    "player_action": "",
                    "is_kickoff": True,
                    "next_active_slot": PlayerSlot.HOST.value,
                },
            )
            await _broadcast_session_state(finished)


async def _run_multiplayer_turn(room_code: str) -> None:
    """Drive one full AI turn for a multiplayer session.

    Triggered by the WS handler after the active player submits. Acquires the
    campaign turn lock, builds an attributed prompt, streams tokens to all
    connected clients, and persists results. On completion, passes the floor to
    the other player.
    """
    rt = await session_manager.get_session(room_code)
    if rt is None:
        log.warning("Multiplayer turn invoked for missing room %s", room_code)
        return

    campaign_id = rt.campaign_id
    campaign_id_ctx.set(campaign_id)

    actions = await session_manager.consume_pending_actions(room_code)
    if len(actions) != 1:
        log.warning("Multiplayer turn started with %s pending actions; aborting.", len(actions))
        await session_manager.broadcast(
            rt,
            {"type": "error", "message": "missing player action", "code": "missing_actions"},
        )
        await session_manager.begin_next_round(room_code)
        return
    acting_slot, action_text = next(iter(actions.items()))
    actor_name: str | None = None

    async with state_manager.turn_lock(campaign_id):
        state = await state_manager.load_state(campaign_id)
        if state is None or state.multiplayer is None:
            await session_manager.broadcast(
                rt,
                {"type": "error", "message": "campaign missing or not multiplayer", "code": "campaign_missing"},
            )
            return

        mp = state.multiplayer
        actor = (
            mp.host_character
            if acting_slot == PlayerSlot.HOST
            else mp.guest_character
        )
        actor_name = actor.name if actor is not None and actor.name else acting_slot.value.title()
        next_slot = PlayerSlot.GUEST if acting_slot == PlayerSlot.HOST else PlayerSlot.HOST
        next_actor = (
            mp.host_character
            if next_slot == PlayerSlot.HOST
            else mp.guest_character
        )
        next_actor_name = (
            next_actor.name
            if next_actor is not None and next_actor.name
            else next_slot.value.title()
        )
        user_message = prompt_builder.format_multiplayer_turn_message(
            actor_name,
            action_text,
            next_actor_name=next_actor_name,
        )

        memories = memory.retrieve_relevant_memories(campaign_id, user_message, n_results=4)
        action_resolution = game_rules.resolve_action(state, action_text, player_slot=acting_slot)
        turn_context = game_rules.render_resolution(action_resolution)

        built = prompt_builder.build_prompt(
            state=state,
            user_message=user_message,
            retrieved_memories=memories,
            turn_context=turn_context,
            acting_slot=acting_slot,
        )
        _LAST_PROMPT[campaign_id] = {
            "system_prompt": built.system_prompt,
            "stats": built.stats.model_dump(),
            "memories": memories,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        buf: list[str] = []
        stop_reason = "stop"
        error: str | None = None

        try:
            async for event in stream_chat(
                built.messages,
                model=state.models.gm,
                overrides=state.sampling_overrides,
            ):
                et = event.get("type")
                if et == "token":
                    chunk = event["data"]
                    buf.append(chunk)
                    await session_manager.broadcast(rt, {"type": "token", "text": chunk})
                elif et == "error":
                    error = event.get("data") or "unknown error"
                    await session_manager.broadcast(rt, {"type": "error", "message": error, "code": "stream_error"})
                elif et == "done":
                    stop_reason = event.get("stop_reason", "stop")
        except Exception as e:
            error = str(e)
            log.exception("Multiplayer stream failed for room %s", room_code)
            await session_manager.broadcast(
                rt, {"type": "error", "message": error, "code": "stream_exception"}
            )

        gm_text = "".join(buf).strip()
        partial = stop_reason == "length" or (error is not None and bool(gm_text))
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"

        gm_msg_id: str | None = None

        if gm_text:
            async def _persist(st: CampaignState) -> CampaignState:
                import schema as _schema

                st.messages.append(
                    _schema.Message(
                        turn_id=turn_id,
                        role=Role.USER,
                        content=user_message,
                        player_slot=acting_slot.value,
                    )
                )
                gm_msg = _schema.Message(
                    turn_id=turn_id,
                    role=Role.ASSISTANT,
                    content=gm_text,
                    partial=partial,
                    player_slot=acting_slot.value,
                )
                st.messages.append(gm_msg)
                st.side_effects.setdefault(gm_msg.id, MessageSideEffects(status="pending"))
                state_manager.record_event(
                    st,
                    "turn.multiplayer.complete",
                    f"Multiplayer turn {rt.turn_number} saved (msg={gm_msg.id}, stop={stop_reason}).",
                )
                return st

            new_state = await state_manager.mutate_state(campaign_id, _persist)
            if new_state is not None:
                gm_msg_id = new_state.messages[-1].id

    next_rt = await session_manager.begin_next_round(room_code)
    next_active = session_manager.current_active_slot(next_rt)
    await session_manager.broadcast(
        next_rt,
        {
            "type": "generation_done",
            "turn_number": next_rt.turn_number,
            "turn_id": turn_id,
            "gm_msg_id": gm_msg_id,
            "stop_reason": stop_reason,
            "partial": partial,
            "acting_slot": acting_slot.value,
            "actor_name": actor_name or acting_slot.value.title(),
            "next_active_slot": next_active.value if next_active else None,
        },
    )
    await _broadcast_session_state(next_rt)

    if gm_msg_id and gm_text:
        asyncio.create_task(
            _background_after_multiplayer_turn(
                room_code=room_code,
                campaign_id=campaign_id,
                acting_slot=acting_slot,
                action_text=action_text,
                gm_msg_id=gm_msg_id,
                gm_text=gm_text,
            )
        )


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
    # World generation needs reliable JSON, so route it through the utility
    # fallback chain. Stale clients may still send `model` as the narrator;
    # treat that only as a GM hint, never as the world-gen model itself.
    selected_utility = req.utility_model
    gm_hint = req.gm_model or req.model or ""
    if gm_hint and selected_utility == gm_hint:
        selected_utility = None

    if req.nsfw and await model_resolver.is_model_available(NSFW_CREATIVE_MODEL):
        model = NSFW_CREATIVE_MODEL
    else:
        model = await model_resolver.resolve_world_generation_model(selected_utility)
        if model is None:
            raise HTTPException(
                400,
                "World generation requires an available utility/summary model. "
                "Select one in Utility Model or pull llama3.1:8b-instruct/qwen2.5:7b-instruct.",
            )

    sys_prompt = f"""You are an expert worldbuilder for a text RPG. Expand the user's vague concept into a richly detailed starting state.

Return ONLY a JSON object matching this schema:
{{
    "world_description": "<string: 2-3 paragraphs — lore, atmosphere, factions>",
    "starting_scene": "<string: 1-2 paragraphs — exactly where the protagonist stands and what is happening right now>",
    "player_starting_location": "<string>",
    "player_gender": "M|F|NB",
    "player_appearance": "<string: 1-2 sentences — visible physical traits, clothing, distinguishing marks>",
    "player_description": "<string: 1-2 sentences — personality, background, motivation>",
    "story_summary": "<string: 3-4 sentences — background history + player's current situation>",
    "lorebook": [ {{"keyword": "<string>", "rule": "<string>"}} ],
    "npcs": [ {{
        "name": "<string>",
        "disposition": "Friendly|Neutral|Suspicious|Hostile",
        "gender": "M|F|NB",
        "appearance": "<string: 1 sentence — visible physical traits and clothing>",
        "description": "<string: 1 sentence — personality and role in the world>",
        "secrets_known": ["<string>"]
    }} ]
}}
Ensure exactly 3 NPCs and at least 3 lorebook entries. Every player and NPC field must be filled (do not leave any blank).

User Concept: {req.prompt}"""

    result, err = await complete_json_detail(
        messages=[{"role": "user", "content": sys_prompt}],
        model=model,
        timeout=180.0,
        num_predict=2048,
    )
    if result is None:
        raise HTTPException(502, f"World generation failed on model {model}: {err or 'unknown error'}")
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
