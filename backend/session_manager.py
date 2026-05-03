"""Multiplayer session lifecycle and runtime management.

A "session" pairs a Tavern Tales campaign with a 6-character room code and
a pair of player slots (host + optional guest). The host runs the FastAPI
backend and Ollama; the guest connects via WebSocket from a browser.

Persistence model:
    - Durable session config (room code, characters, merged preferences,
      session status) lives on `CampaignState.multiplayer` (a MultiplayerConfig).
    - Per-server-process runtime state (WebSocket connections, pending actions,
      ready flags, paused-since timestamp) lives in this module's in-memory
      `_sessions` registry. On server restart the runtime is rebuilt from the
      campaign's MultiplayerConfig and starts in a PAUSED state until both
      players reconnect.

Turn flow (sequential):
    LOBBY → both ready → HOST_TURN
    *_TURN + active player submits → GENERATING (caller invokes the chat handler)
    GENERATING + generation_done() → flip active slot → next *_TURN
    Disconnect at any non-LOBBY status → PAUSED, save status_before
    Reconnect within window → restore status_before
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

import state_manager
from schema import (
    CampaignState,
    MultiplayerConfig,
    PlayerCharacter,
    PlayerSlot,
    SessionStatus,
)

log = logging.getLogger(__name__)

# Excludes 0/O/1/I to avoid lookalike confusion when typing the code.
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_LEN = 6
DEFAULT_RECONNECT_WINDOW_SECONDS = 300
SESSION_PAUSE_ARCHIVE_SECONDS = 86_400  # 24h paused → eligible for cleanup
MAX_OOC_MESSAGE_LEN = 1000
MAX_ACTION_TEXT_LEN = 4000
MAX_PROFILE_JSON_BYTES = 100_000  # 100 KB cap on imported preference JSON
MAX_CHARACTER_STATS = 50
MAX_CHARACTER_INVENTORY = 100

_BACKEND_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = _BACKEND_DIR / "sessions"


# ---------------------------------------------------------------------------
# Runtime data classes (in-memory only)
# ---------------------------------------------------------------------------


@dataclass
class ConnectedPlayer:
    slot: PlayerSlot
    display_name: str
    character_name: str
    connection_id: str
    client_id: str = ""
    is_ready: bool = False
    is_connected: bool = True
    preference_profile_json: dict[str, Any] | None = None
    preference_source: str = "none"  # "imported" | "lobby_form" | "none"

    def to_public(self) -> dict[str, Any]:
        return {
            "slot": self.slot.value,
            "display_name": self.display_name,
            "character_name": self.character_name,
            "is_ready": self.is_ready,
            "is_connected": self.is_connected,
            "preference_source": self.preference_source,
        }


@dataclass
class PendingAction:
    slot: PlayerSlot
    text: str
    submitted_at: datetime

    def to_public(self) -> dict[str, Any]:
        return {"slot": self.slot.value, "submitted_at": self.submitted_at.isoformat()}


@dataclass
class SessionRuntime:
    room_code: str
    campaign_id: str
    status: SessionStatus = SessionStatus.LOBBY
    starting_slot_this_round: PlayerSlot = PlayerSlot.HOST
    turn_number: int = 0
    reconnect_window_seconds: int = DEFAULT_RECONNECT_WINDOW_SECONDS
    paused_status_before: SessionStatus | None = None
    paused_since: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    players: dict[PlayerSlot, ConnectedPlayer] = field(default_factory=dict)
    pending_actions: dict[PlayerSlot, PendingAction] = field(default_factory=dict)
    kickoff_needed: bool = False
    kickoff_in_progress: bool = False

    # In-memory only — never serialized.
    connections: dict[PlayerSlot, WebSocket] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)

    def public_state(self) -> dict[str, Any]:
        return {
            "room_code": self.room_code,
            "campaign_id": self.campaign_id,
            "status": self.status.value,
            "turn_number": self.turn_number,
            "starting_slot_this_round": self.starting_slot_this_round.value,
            "active_slot": self._active_slot_value(),
            "players": {slot.value: p.to_public() for slot, p in self.players.items()},
            "pending_actions": {slot.value: pa.to_public() for slot, pa in self.pending_actions.items()},
            "kickoff_needed": self.kickoff_needed,
            "kickoff_in_progress": self.kickoff_in_progress,
            "paused_since": self.paused_since.isoformat() if self.paused_since else None,
            "reconnect_window_seconds": self.reconnect_window_seconds,
            "last_activity": self.last_activity.isoformat(),
        }

    def _active_slot_value(self) -> str | None:
        if self.status == SessionStatus.HOST_TURN:
            return PlayerSlot.HOST.value
        if self.status == SessionStatus.GUEST_TURN:
            return PlayerSlot.GUEST.value
        return None


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------


_sessions: dict[str, SessionRuntime] = {}
_sessions_guard = asyncio.Lock()
_ooc_log_guard = asyncio.Lock()


# ---------------------------------------------------------------------------
# Initialization (called from main app startup)
# ---------------------------------------------------------------------------


async def initialize() -> None:
    """Rebuild session runtimes from any campaigns that have multiplayer configs.

    Called during FastAPI startup. Sessions begin in PAUSED state until both
    players reconnect — connections are not persisted.
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    summaries = await state_manager.list_campaigns()
    rebuilt = 0
    for summary in summaries:
        try:
            state = await state_manager.load_state(summary.id)
        except Exception:
            log.exception("Failed to load campaign %s during session rebuild", summary.id)
            continue
        if state is None or state.multiplayer is None:
            continue
        if state.multiplayer.session_status == SessionStatus.ARCHIVED:
            continue
        runtime = _runtime_from_campaign(state)
        # Sessions always come back paused on restart — connections are gone.
        runtime.status = SessionStatus.PAUSED
        runtime.paused_status_before = state.multiplayer.session_status
        # GENERATING (server crashed mid-stream) and PAUSED (already paused on
        # disk before restart) are not valid resume targets. If we restored to
        # PAUSED, the session would lock forever once both players reconnect.
        # Derive the correct next-turn slot from the round-starter instead.
        if runtime.paused_status_before in (SessionStatus.GENERATING, SessionStatus.PAUSED):
            previous = runtime.paused_status_before
            starter = state.multiplayer.starting_slot_this_round
            # PAUSED on disk means we lost the pre-pause status. Best guess:
            # hand the floor to the round-starter so the game can resume.
            # GENERATING means a turn was mid-generation; the next actor is the
            # other player.
            if previous == SessionStatus.GENERATING:
                next_slot = PlayerSlot.GUEST if starter == PlayerSlot.HOST else PlayerSlot.HOST
            else:  # PAUSED
                next_slot = starter
            runtime.paused_status_before = (
                SessionStatus.HOST_TURN if next_slot == PlayerSlot.HOST else SessionStatus.GUEST_TURN
            )
            log.info(
                "Corrected %s->pause for session %s to %s",
                previous.value,
                runtime.room_code,
                runtime.paused_status_before,
            )
        runtime.paused_since = datetime.now(timezone.utc)
        async with _sessions_guard:
            _sessions[runtime.room_code] = runtime
        rebuilt += 1
    if rebuilt:
        log.info("Rebuilt %d multiplayer session runtime(s) in PAUSED state", rebuilt)


def _runtime_from_campaign(state: CampaignState) -> SessionRuntime:
    assert state.multiplayer is not None
    mp = state.multiplayer
    runtime = SessionRuntime(
        room_code=mp.room_code,
        campaign_id=state.campaign_id,
        status=mp.session_status,
        starting_slot_this_round=mp.starting_slot_this_round,
        turn_number=mp.turn_number,
        reconnect_window_seconds=mp.reconnect_window_seconds,
    )
    runtime.players[PlayerSlot.HOST] = ConnectedPlayer(
        slot=PlayerSlot.HOST,
        display_name="Host",
        character_name=mp.host_character.name,
        connection_id="",
        is_connected=False,
    )
    if mp.guest_character is not None:
        runtime.players[PlayerSlot.GUEST] = ConnectedPlayer(
            slot=PlayerSlot.GUEST,
            display_name="Guest",
            character_name=mp.guest_character.name,
            connection_id="",
            is_connected=False,
        )
    return runtime


# ---------------------------------------------------------------------------
# Room code generation
# ---------------------------------------------------------------------------


def _generate_room_code() -> str:
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LEN))


def _ooc_log_path(room_code: str) -> Path:
    return SESSIONS_DIR / f"{(room_code or '').strip().upper()}_ooc.jsonl"


async def _unique_room_code() -> str:
    for _ in range(40):
        code = _generate_room_code()
        async with _sessions_guard:
            if code not in _sessions:
                return code
    # Astronomically unlikely; fall back to longer code.
    return uuid4().hex[:10].upper()


# ---------------------------------------------------------------------------
# Session creation / retrieval
# ---------------------------------------------------------------------------


async def create_session(
    campaign_id: str,
    host_character: PlayerCharacter,
    *,
    reconnect_window_seconds: int = DEFAULT_RECONNECT_WINDOW_SECONDS,
    show_player_actions: bool = False,
) -> SessionRuntime:
    """Attach a new multiplayer session to an existing campaign.

    Persists `MultiplayerConfig` onto the campaign and registers the runtime.
    """
    state = await state_manager.load_state(campaign_id)
    if state is None:
        raise ValueError(f"campaign {campaign_id!r} not found")
    if state.multiplayer is not None and state.multiplayer.session_status != SessionStatus.ARCHIVED:
        raise ValueError(f"campaign {campaign_id!r} already has an active multiplayer session")

    code = await _unique_room_code()

    async def _apply(st: CampaignState) -> CampaignState:
        st.multiplayer = MultiplayerConfig(
            room_code=code,
            host_character=host_character,
            session_status=SessionStatus.LOBBY,
            starting_slot_this_round=PlayerSlot.HOST,
            turn_number=0,
            reconnect_window_seconds=reconnect_window_seconds,
            show_player_actions=show_player_actions,
        )
        state_manager.record_event(st, "session.create", f"Multiplayer session opened (room {code}).")
        return st

    new_state = await state_manager.mutate_state(campaign_id, _apply)
    if new_state is None:
        raise ValueError(f"campaign {campaign_id!r} disappeared during create_session")

    runtime = SessionRuntime(
        room_code=code,
        campaign_id=campaign_id,
        status=SessionStatus.LOBBY,
        reconnect_window_seconds=reconnect_window_seconds,
    )
    async with _sessions_guard:
        _sessions[code] = runtime
    log.info("Created multiplayer session %s for campaign %s", code, campaign_id)
    return runtime


async def get_session(room_code: str) -> SessionRuntime | None:
    async with _sessions_guard:
        return _sessions.get(room_code.upper())


async def list_sessions() -> list[dict[str, Any]]:
    async with _sessions_guard:
        return [s.public_state() for s in _sessions.values()]


# ---------------------------------------------------------------------------
# Player join / leave / ready
# ---------------------------------------------------------------------------


async def join_session(
    room_code: str,
    *,
    websocket: WebSocket,
    display_name: str,
    character_name: str,
    client_id: str = "",
    preference_profile_json: dict[str, Any] | None = None,
    preference_source: str = "none",
    desired_slot: PlayerSlot | None = None,
) -> tuple[SessionRuntime, ConnectedPlayer]:
    """Add a player to an existing session and bind their WebSocket.

    The first connection lands in HOST. The second lands in GUEST. Reconnection
    of an already-known slot replaces the prior WebSocket with the new one.
    """
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError(f"session {room_code!r} not found")

    async with rt.lock:
        if rt.status == SessionStatus.ARCHIVED:
            raise ValueError("session is archived")

        normalized_client_id = (client_id or "").strip()[:120]

        # Reconnect path: same slot already known, just replace the WS.
        if desired_slot is not None and desired_slot in rt.players:
            existing = rt.players[desired_slot]
            existing.is_connected = True
            existing.connection_id = uuid4().hex[:12]
            if normalized_client_id:
                existing.client_id = normalized_client_id
            rt.connections[desired_slot] = websocket
            await _maybe_resume_from_pause(rt)
            rt.touch()
            return rt, existing

        # Same browser/device rejoining without a known slot. This covers
        # refreshes, temporary network drops, and React dev StrictMode's
        # mount/unmount/remount cycle without opening a fake "third player".
        if normalized_client_id:
            for existing_slot, existing in rt.players.items():
                if existing.client_id == normalized_client_id:
                    existing.is_connected = True
                    existing.connection_id = uuid4().hex[:12]
                    existing.display_name = (display_name or existing.display_name).strip()[:80] or existing.display_name
                    existing.character_name = (character_name or existing.character_name).strip()[:80] or existing.character_name
                    rt.connections[existing_slot] = websocket
                    await _sync_character_to_campaign(rt, existing_slot, existing.character_name)
                    await _maybe_resume_from_pause(rt)
                    rt.touch()
                    return rt, existing

        # New player. Decide slot.
        if desired_slot is None:
            slot = PlayerSlot.HOST if PlayerSlot.HOST not in rt.players else PlayerSlot.GUEST
        else:
            slot = desired_slot

        if slot in rt.players:
            existing = rt.players[slot]
            same_legacy_guest = (
                slot == PlayerSlot.GUEST
                and not existing.client_id
                and (display_name or "").strip()[:80] == existing.display_name
                and (character_name or "").strip()[:80] == existing.character_name
            )
            if existing.is_connected and not same_legacy_guest:
                raise ValueError(f"slot {slot.value!r} already taken")
            existing.is_connected = True
            existing.connection_id = uuid4().hex[:12]
            if normalized_client_id:
                existing.client_id = normalized_client_id
            existing.display_name = (display_name or existing.display_name).strip()[:80] or existing.display_name
            existing.character_name = (character_name or existing.character_name).strip()[:80] or existing.character_name
            existing.preference_profile_json = preference_profile_json or existing.preference_profile_json
            existing.preference_source = preference_source if preference_profile_json else existing.preference_source
            rt.connections[slot] = websocket
            await _sync_character_to_campaign(rt, slot, existing.character_name)
            await _maybe_resume_from_pause(rt)
            rt.touch()
            return rt, existing
        if slot == PlayerSlot.GUEST and PlayerSlot.HOST not in rt.players:
            raise ValueError("host must join before guest")

        # Validate preference JSON size if provided.
        if preference_profile_json is not None:
            import json as _json

            raw = _json.dumps(preference_profile_json)
            if len(raw.encode("utf-8")) > MAX_PROFILE_JSON_BYTES:
                raise ValueError("preference profile JSON exceeds size cap")

        cp = ConnectedPlayer(
            slot=slot,
            display_name=(display_name or slot.value).strip()[:80] or slot.value,
            character_name=(character_name or "").strip()[:80] or "Unnamed",
            connection_id=uuid4().hex[:12],
            client_id=normalized_client_id,
            preference_profile_json=preference_profile_json,
            preference_source=preference_source if preference_profile_json else "none",
        )
        rt.players[slot] = cp
        rt.connections[slot] = websocket

        # Ensure the campaign reflects the joined character (especially for guest).
        await _sync_character_to_campaign(rt, slot, character_name)
        rt.touch()
        return rt, cp


async def _sync_character_to_campaign(
    runtime: SessionRuntime, slot: PlayerSlot, character_name: str
) -> None:
    async def _apply(st: CampaignState) -> CampaignState:
        if st.multiplayer is None:
            return st
        if slot == PlayerSlot.HOST:
            st.multiplayer.host_character.name = (character_name or st.multiplayer.host_character.name).strip()
        else:
            if st.multiplayer.guest_character is None:
                st.multiplayer.guest_character = PlayerCharacter(
                    slot=PlayerSlot.GUEST,
                    name=(character_name or "Guest").strip() or "Guest",
                )
            else:
                st.multiplayer.guest_character.name = (
                    character_name or st.multiplayer.guest_character.name
                ).strip()
        return st

    await state_manager.mutate_state(runtime.campaign_id, _apply)


async def update_character(
    room_code: str,
    slot: PlayerSlot,
    *,
    name: str | None = None,
    gender: str | None = None,
    appearance: str | None = None,
    description: str | None = None,
    location: str | None = None,
    stats: dict[str, Any] | None = None,
    inventory: list[Any] | None = None,
) -> SessionRuntime:
    """Update a lobby character card for either player slot."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")

    cleaned_stats = _clean_character_stats(stats) if stats is not None else None
    cleaned_inventory = _clean_character_inventory(inventory) if inventory is not None else None

    async def _apply(st: CampaignState) -> CampaignState:
        if st.multiplayer is None:
            raise ValueError("campaign is not multiplayer")
        char = (
            st.multiplayer.host_character
            if slot == PlayerSlot.HOST
            else st.multiplayer.guest_character
        )
        if char is None:
            char = PlayerCharacter(slot=PlayerSlot.GUEST, name=name or "Guest")
            st.multiplayer.guest_character = char
        if name is not None:
            char.name = name.strip()[:80] or char.name
        if gender is not None:
            char.gender = gender.strip()[:40] or char.gender
        if appearance is not None:
            char.appearance = appearance.strip()[:600]
        if description is not None:
            char.description = description.strip()[:1200]
        if location is not None:
            char.location = location.strip()[:200]
        if cleaned_stats is not None:
            char.stats = cleaned_stats
        if cleaned_inventory is not None:
            char.inventory = cleaned_inventory
        return st

    new_state = await state_manager.mutate_state(rt.campaign_id, _apply)
    if new_state is None:
        raise ValueError("campaign not found")

    async with rt.lock:
        player = rt.players.get(slot)
        if player is not None and name is not None:
            player.character_name = name.strip()[:80] or player.character_name
        rt.touch()
    return rt


def _clean_character_stats(stats: dict[str, Any]) -> dict[str, int]:
    if not isinstance(stats, dict):
        raise ValueError("stats must be an object")
    cleaned: dict[str, int] = {}
    for raw_key, raw_value in list(stats.items())[:MAX_CHARACTER_STATS]:
        key = str(raw_key).strip()[:80]
        if not key:
            continue
        try:
            cleaned[key] = int(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"stat {key!r} must be an integer")
    return cleaned


def _clean_character_inventory(inventory: list[Any]) -> list[str]:
    if not isinstance(inventory, list):
        raise ValueError("inventory must be a list")
    cleaned: list[str] = []
    for raw_item in inventory[:MAX_CHARACTER_INVENTORY]:
        item = str(raw_item).strip()[:120]
        if item:
            cleaned.append(item)
    return cleaned


async def update_guest_character(
    room_code: str,
    *,
    name: str | None = None,
    gender: str | None = None,
    appearance: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> SessionRuntime:
    """Update the guest character's editable fields from the lobby form."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")

    async def _apply(st: CampaignState) -> CampaignState:
        if st.multiplayer is None:
            raise ValueError("campaign is not multiplayer")
        gc = st.multiplayer.guest_character
        if gc is None:
            gc = PlayerCharacter(slot=PlayerSlot.GUEST, name=name or "Guest")
            st.multiplayer.guest_character = gc
        if name is not None:
            gc.name = name.strip()[:80] or gc.name
        if gender is not None:
            gc.gender = gender.strip()[:40] or gc.gender
        if appearance is not None:
            gc.appearance = appearance.strip()[:600]
        if description is not None:
            gc.description = description.strip()[:1200]
        if location is not None:
            gc.location = location.strip()[:200]
        return st

    await state_manager.mutate_state(rt.campaign_id, _apply)
    return rt


async def set_ready(room_code: str, slot: PlayerSlot, is_ready: bool) -> SessionRuntime:
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        cp = rt.players.get(slot)
        if cp is None:
            raise ValueError(f"slot {slot.value} not joined")
        cp.is_ready = is_ready
        rt.touch()
        # If both ready in LOBBY, advance to the configured first actor.
        if (
            rt.status == SessionStatus.LOBBY
            and PlayerSlot.HOST in rt.players
            and PlayerSlot.GUEST in rt.players
            and rt.players[PlayerSlot.HOST].is_ready
            and rt.players[PlayerSlot.GUEST].is_ready
        ):
            rt.status = _turn_status_for_slot(rt.starting_slot_this_round)
            state = await state_manager.load_state(rt.campaign_id)
            rt.kickoff_needed = (
                rt.turn_number == 0
                and state is not None
                and not any(getattr(message, "is_kickoff", False) for message in state.messages)
            )
            await _persist_session_status(rt)
        return rt


async def mark_disconnected(
    room_code: str,
    slot: PlayerSlot,
    connection_id: str | None = None,
) -> SessionRuntime | None:
    rt = await get_session(room_code)
    if rt is None:
        return None
    async with rt.lock:
        cp = rt.players.get(slot)
        if cp is None:
            return rt
        if connection_id is not None and cp.connection_id != connection_id:
            # A stale socket closed after the slot was replaced by a newer
            # connection. Do not mark the active replacement as disconnected.
            return rt
        cp.is_connected = False
        rt.connections.pop(slot, None)
        # If we were mid-session, pause.
        if rt.status not in (SessionStatus.LOBBY, SessionStatus.PAUSED, SessionStatus.ARCHIVED):
            rt.paused_status_before = rt.status
            rt.status = SessionStatus.PAUSED
            rt.paused_since = datetime.now(timezone.utc)
            await _persist_session_status(rt)
        rt.touch()
        return rt


async def _maybe_resume_from_pause(rt: SessionRuntime) -> None:
    """Restore status if paused and both players are now connected."""
    if rt.status != SessionStatus.PAUSED:
        return
    both_connected = (
        PlayerSlot.HOST in rt.players
        and PlayerSlot.GUEST in rt.players
        and rt.players[PlayerSlot.HOST].is_connected
        and rt.players[PlayerSlot.GUEST].is_connected
    )
    if not both_connected:
        return

    if rt.paused_status_before is not None:
        restored_status = rt.paused_status_before
    elif (
        rt.players[PlayerSlot.HOST].is_ready
        and rt.players[PlayerSlot.GUEST].is_ready
    ):
        restored_status = (
            SessionStatus.HOST_TURN
            if rt.starting_slot_this_round == PlayerSlot.HOST
            else SessionStatus.GUEST_TURN
        )
    else:
        restored_status = SessionStatus.LOBBY

    rt.status = restored_status
    rt.paused_status_before = None
    rt.paused_since = None
    await _persist_session_status(rt)


async def reconnect_window_expired(rt: SessionRuntime) -> bool:
    if rt.paused_since is None:
        return False
    elapsed = (datetime.now(timezone.utc) - rt.paused_since).total_seconds()
    return elapsed >= rt.reconnect_window_seconds


# ---------------------------------------------------------------------------
# Action submission and turn flow
# ---------------------------------------------------------------------------


async def submit_action(
    room_code: str, slot: PlayerSlot, text: str
) -> tuple[SessionRuntime, str]:
    """Record an action submission and advance the turn state machine.

    Returns the runtime and a status code:
        "ready_to_generate" — action recorded, caller should kick off the AI turn
    Raises ValueError if the submission is rejected (wrong slot, generating, etc.)
    """
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")

    text = (text or "").strip()
    if not text:
        raise ValueError("empty action text")
    if len(text) > MAX_ACTION_TEXT_LEN:
        raise ValueError("action text too long")

    async with rt.lock:
        if rt.status == SessionStatus.GENERATING:
            raise ValueError("generation in progress")
        if rt.status == SessionStatus.PAUSED:
            raise ValueError("session is paused; waiting for partner reconnect")
        if rt.status == SessionStatus.LOBBY:
            raise ValueError("not yet in play; both players must ready up")
        if rt.status == SessionStatus.ARCHIVED:
            raise ValueError("session is archived")
        if rt.kickoff_needed or rt.kickoff_in_progress:
            raise ValueError("opening scene in progress")

        active = _expected_active_slot(rt.status)
        if active is None or slot != active:
            raise ValueError("not your turn")

        # Multiplayer turns are sequential: one player submits, the GM responds,
        # then the floor passes to the other player.
        rt.pending_actions.clear()
        rt.pending_actions[slot] = PendingAction(
            slot=slot,
            text=text,
            submitted_at=datetime.now(timezone.utc),
        )
        rt.touch()

        rt.status = SessionStatus.GENERATING
        await _persist_session_status(rt)
        return rt, "ready_to_generate"


async def set_starting_slot(room_code: str, slot: PlayerSlot) -> SessionRuntime:
    """Set which player acts first before a lobby advances into play."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        if rt.status != SessionStatus.LOBBY:
            raise ValueError("starting slot can only be changed in the lobby")
        rt.starting_slot_this_round = slot
        await _persist_session_status(rt)
        rt.touch()
        return rt


async def begin_aux_generation(room_code: str) -> tuple[SessionRuntime, SessionStatus]:
    """Enter GENERATING for reroll/continue without consuming the current floor."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        if rt.status not in (SessionStatus.HOST_TURN, SessionStatus.GUEST_TURN):
            raise ValueError("session is not ready for generation")
        restore_status = rt.status
        rt.status = SessionStatus.GENERATING
        await _persist_session_status(rt)
        rt.touch()
        return rt, restore_status


async def finish_aux_generation(
    room_code: str,
    restore_status: SessionStatus,
) -> SessionRuntime | None:
    """Restore the current floor after a reroll/continue stream finishes."""
    rt = await get_session(room_code)
    if rt is None:
        return None
    async with rt.lock:
        if rt.status == SessionStatus.GENERATING:
            rt.status = restore_status
            await _persist_session_status(rt)
        rt.touch()
        return rt


def _expected_active_slot(status: SessionStatus) -> PlayerSlot | None:
    if status == SessionStatus.HOST_TURN:
        return PlayerSlot.HOST
    if status == SessionStatus.GUEST_TURN:
        return PlayerSlot.GUEST
    return None


def _turn_status_for_slot(slot: PlayerSlot) -> SessionStatus:
    return SessionStatus.HOST_TURN if slot == PlayerSlot.HOST else SessionStatus.GUEST_TURN


def current_active_slot(rt: SessionRuntime) -> PlayerSlot | None:
    """Public helper for callers that need to show whose floor it is."""
    return _expected_active_slot(rt.status)


async def consume_pending_actions(room_code: str) -> dict[PlayerSlot, str]:
    """Snapshot and clear the pending action for the current turn."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        snapshot = {slot: pa.text for slot, pa in rt.pending_actions.items()}
        rt.pending_actions.clear()
        rt.touch()
        return snapshot


async def begin_kickoff_if_needed(room_code: str) -> SessionRuntime | None:
    """Mark the room's opening-scene kickoff as in progress if one is pending."""
    rt = await get_session(room_code)
    if rt is None:
        return None
    async with rt.lock:
        if not rt.kickoff_needed or rt.kickoff_in_progress:
            return None
        rt.kickoff_needed = False
        rt.kickoff_in_progress = True
        rt.touch()
        return rt


async def finish_kickoff(room_code: str) -> SessionRuntime | None:
    """Clear the in-memory kickoff generation flag."""
    rt = await get_session(room_code)
    if rt is None:
        return None
    async with rt.lock:
        rt.kickoff_in_progress = False
        rt.touch()
        return rt


async def begin_next_round(room_code: str) -> SessionRuntime:
    """Called after generation completes — passes the floor to the other player."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        # Flip the active slot for the next turn.
        rt.turn_number += 1
        rt.starting_slot_this_round = (
            PlayerSlot.GUEST if rt.starting_slot_this_round == PlayerSlot.HOST else PlayerSlot.HOST
        )
        # If a player disconnected during generation, fall through to PAUSED.
        all_connected = all(p.is_connected for p in rt.players.values())
        if not all_connected:
            rt.paused_status_before = (
                SessionStatus.HOST_TURN
                if rt.starting_slot_this_round == PlayerSlot.HOST
                else SessionStatus.GUEST_TURN
            )
            rt.status = SessionStatus.PAUSED
            rt.paused_since = datetime.now(timezone.utc)
        else:
            rt.status = (
                SessionStatus.HOST_TURN
                if rt.starting_slot_this_round == PlayerSlot.HOST
                else SessionStatus.GUEST_TURN
            )
        await _persist_session_status(rt)
        rt.touch()
        return rt


# ---------------------------------------------------------------------------
# Host-only management
# ---------------------------------------------------------------------------


async def eject_guest(room_code: str) -> SessionRuntime:
    """Host removes the guest. Session becomes single-player going forward."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        rt.players.pop(PlayerSlot.GUEST, None)
        rt.connections.pop(PlayerSlot.GUEST, None)
        rt.pending_actions.pop(PlayerSlot.GUEST, None)
        rt.status = SessionStatus.LOBBY
        rt.paused_status_before = None
        rt.paused_since = None
        await _persist_session_status(rt)
        rt.touch()
        return rt


async def archive_session(room_code: str) -> SessionRuntime:
    """End the session but keep the campaign on disk."""
    rt = await get_session(room_code)
    if rt is None:
        raise ValueError("session not found")
    async with rt.lock:
        rt.status = SessionStatus.ARCHIVED
        rt.paused_status_before = None
        rt.paused_since = None
        await _persist_session_status(rt)
        rt.touch()
    async with _sessions_guard:
        _sessions.pop(rt.room_code, None)
    return rt


async def delete_session(room_code: str) -> bool:
    """Destructively remove the session AND its underlying campaign."""
    rt = await get_session(room_code)
    if rt is None:
        return False
    campaign_id = rt.campaign_id
    ooc_log_path = _ooc_log_path(rt.room_code)
    async with _sessions_guard:
        _sessions.pop(rt.room_code, None)
    await state_manager.delete_campaign(campaign_id)

    def _delete_ooc_log() -> None:
        try:
            ooc_log_path.unlink()
        except FileNotFoundError:
            pass

    async with _ooc_log_guard:
        await asyncio.to_thread(_delete_ooc_log)
    return True


async def _persist_session_status(rt: SessionRuntime) -> None:
    """Write the runtime's status fields back to the campaign's MultiplayerConfig."""

    async def _apply(st: CampaignState) -> CampaignState:
        if st.multiplayer is None:
            return st
        st.multiplayer.session_status = rt.status
        st.multiplayer.starting_slot_this_round = rt.starting_slot_this_round
        st.multiplayer.turn_number = rt.turn_number
        st.multiplayer.reconnect_window_seconds = rt.reconnect_window_seconds
        return st

    await state_manager.mutate_state(rt.campaign_id, _apply)


# ---------------------------------------------------------------------------
# Broadcasts
# ---------------------------------------------------------------------------


def _normalize_ooc_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    slot = str(raw.get("slot") or "").strip().lower()
    if slot not in {PlayerSlot.HOST.value, PlayerSlot.GUEST.value}:
        return None
    text = str(raw.get("text") or "").strip()[:MAX_OOC_MESSAGE_LEN]
    if not text:
        return None
    display_name = str(raw.get("display_name") or slot).strip()[:80] or slot
    ts = str(raw.get("ts") or "").strip()[:80]
    if not ts:
        ts = datetime.now(timezone.utc).isoformat()
    return {
        "slot": slot,
        "display_name": display_name,
        "text": text,
        "ts": ts,
    }


async def append_ooc(
    room_code: str,
    slot: PlayerSlot,
    display_name: str,
    text: str,
    ts: str,
) -> dict[str, Any]:
    """Append one out-of-character chat message to the room's JSONL log."""
    entry = _normalize_ooc_entry({
        "slot": slot.value,
        "display_name": display_name,
        "text": text,
        "ts": ts,
    })
    if entry is None:
        raise ValueError("invalid OOC message")

    path = _ooc_log_path(room_code)

    def _append() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True, separators=(",", ":")) + "\n")

    async with _ooc_log_guard:
        await asyncio.to_thread(_append)
    return entry


async def read_ooc_log(room_code: str, limit: int = 100) -> list[dict[str, Any]]:
    """Read the most recent OOC messages for a room."""
    try:
        normalized_limit = max(0, int(limit))
    except (TypeError, ValueError):
        normalized_limit = 100
    if normalized_limit == 0:
        return []

    path = _ooc_log_path(room_code)

    def _read() -> list[dict[str, Any]]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []

        entries: list[dict[str, Any]] = []
        for line in lines[-normalized_limit:]:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            entry = _normalize_ooc_entry(raw)
            if entry is not None:
                entries.append(entry)
        return entries

    async with _ooc_log_guard:
        return await asyncio.to_thread(_read)


async def broadcast(rt: SessionRuntime, message: dict[str, Any]) -> None:
    """Send a JSON message to every connected client in the session."""
    dead: list[tuple[PlayerSlot, str | None]] = []
    for slot, ws in list(rt.connections.items()):
        try:
            await ws.send_json(message)
        except Exception:
            log.warning("Failed to send to %s in room %s; dropping connection", slot.value, rt.room_code)
            cp = rt.players.get(slot)
            dead.append((slot, cp.connection_id if cp is not None else None))
    for slot, connection_id in dead:
        await mark_disconnected(rt.room_code, slot, connection_id=connection_id)


async def broadcast_to(rt: SessionRuntime, slot: PlayerSlot, message: dict[str, Any]) -> None:
    ws = rt.connections.get(slot)
    if ws is None:
        return
    try:
        await ws.send_json(message)
    except Exception:
        log.warning("Failed to send to %s in room %s", slot.value, rt.room_code)
        cp = rt.players.get(slot)
        await mark_disconnected(
            rt.room_code,
            slot,
            connection_id=cp.connection_id if cp is not None else None,
        )


async def broadcast_except(
    rt: SessionRuntime, exclude_slot: PlayerSlot, message: dict[str, Any]
) -> None:
    for slot in list(rt.connections.keys()):
        if slot == exclude_slot:
            continue
        await broadcast_to(rt, slot, message)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def cleanup_expired_sessions() -> int:
    """Remove sessions that have been paused or idle past the archive threshold."""
    now = datetime.now(timezone.utc)
    removed = 0
    async with _sessions_guard:
        codes = list(_sessions.keys())
    for code in codes:
        rt = await get_session(code)
        if rt is None:
            continue
        if rt.status == SessionStatus.PAUSED and rt.paused_since is not None:
            elapsed = (now - rt.paused_since).total_seconds()
            if elapsed >= SESSION_PAUSE_ARCHIVE_SECONDS:
                await archive_session(code)
                removed += 1
    return removed
