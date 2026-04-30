"""
Per-campaign persistent state with atomic writes and per-campaign async locks.

Breaking change vs. v1: each campaign now lives in its own file under
`backend/states/{campaign_id}.json`. Legacy `campaign_states.json` is renamed
(not migrated) on first startup per the approved plan (decision D1).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from schema import (
    SCHEMA_VERSION,
    CampaignState,
    CampaignSummary,
    CampaignEvent,
    Disposition,
    Message,
    Player,
    PlayerCharacter,
    PlayerSlot,
    Role,
    StateDelta,
    StatBound,
    MultiplayerConfig,
)

log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
STATES_DIR = _BACKEND_DIR / "states"
LEGACY_FILE = _BACKEND_DIR / "campaign_states.json"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")

_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()
_turn_locks: dict[str, asyncio.Lock] = {}
_turn_locks_guard = asyncio.Lock()

_migration_checked = False


def _ensure_dir() -> None:
    STATES_DIR.mkdir(parents=True, exist_ok=True)


def _check_legacy_once() -> None:
    global _migration_checked
    if _migration_checked:
        return
    _migration_checked = True
    if LEGACY_FILE.exists():
        backup = _BACKEND_DIR / "campaign_states.json.legacy.bak"
        try:
            LEGACY_FILE.replace(backup)
            log.warning(
                "Legacy campaign_states.json detected; renamed to %s. "
                "Schema v2 does not migrate old data; create new campaigns to continue.",
                backup.name,
            )
        except OSError as e:
            log.error("Could not rename legacy state file: %s", e)


def _validate_id(campaign_id: str) -> None:
    if not campaign_id or not _SAFE_ID.match(campaign_id):
        raise ValueError(f"Invalid campaign_id: {campaign_id!r}")


def _path_for(campaign_id: str) -> Path:
    _validate_id(campaign_id)
    return STATES_DIR / f"{campaign_id}.json"


async def _get_lock(campaign_id: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _locks.get(campaign_id)
        if lock is None:
            lock = asyncio.Lock()
            _locks[campaign_id] = lock
        return lock


async def _get_turn_lock(campaign_id: str) -> asyncio.Lock:
    async with _turn_locks_guard:
        lock = _turn_locks.get(campaign_id)
        if lock is None:
            lock = asyncio.Lock()
            _turn_locks[campaign_id] = lock
        return lock


@asynccontextmanager
async def campaign_lock(campaign_id: str):
    lock = await _get_lock(campaign_id)
    async with lock:
        yield


@asynccontextmanager
async def turn_lock(campaign_id: str):
    """Serialize full chat/continue/regenerate turns for one campaign."""
    lock = await _get_turn_lock(campaign_id)
    async with lock:
        yield


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    try:
        os.replace(tmp, path)
    except PermissionError:
        # Some Windows sandbox/ACL setups allow creation and writes but deny
        # rename/delete. Keep the state payload intact and fall back to a direct
        # write so local tests and campaigns can continue.
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def initialize() -> None:
    """Called at app startup. Creates directories and handles legacy file rename."""
    _ensure_dir()
    _check_legacy_once()


async def load_state(campaign_id: str) -> CampaignState | None:
    _ensure_dir()
    path = _path_for(campaign_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return CampaignState.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as e:
        corrupt = path.with_suffix(f".corrupt-{int(time.time())}.bak")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        log.error("State file for %s was corrupt; renamed to %s. Reason: %s", campaign_id, corrupt.name, e)
        return None


async def save_state(state: CampaignState) -> None:
    _ensure_dir()
    _validate_id(state.campaign_id)
    # Ensure we always stamp the current schema version.
    state.schema_version = SCHEMA_VERSION
    state.revision += 1
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path = _path_for(state.campaign_id)
    _atomic_write(path, state.model_dump(mode="json"))


async def mutate_state(
    campaign_id: str,
    mutator: Callable[[CampaignState], Awaitable[CampaignState] | CampaignState],
) -> CampaignState | None:
    """Load → lock → call mutator(state) → save. Returns the new state (or None if missing)."""
    async with campaign_lock(campaign_id):
        state = await load_state(campaign_id)
        if state is None:
            return None
        maybe_coro = mutator(state)
        if asyncio.iscoroutine(maybe_coro):
            new_state = await maybe_coro
        else:
            new_state = maybe_coro  # type: ignore[assignment]
        if not isinstance(new_state, CampaignState):
            raise TypeError("mutator must return a CampaignState")
        await save_state(new_state)
        return new_state


async def list_campaigns() -> list[CampaignSummary]:
    _ensure_dir()
    out: list[CampaignSummary] = []
    for entry in sorted(STATES_DIR.glob("*.json")):
        if entry.name.endswith(".tmp") or entry.name.endswith(".bak"):
            continue
        try:
            with open(entry, "r", encoding="utf-8") as f:
                raw = json.load(f)
            mp = raw.get("multiplayer") or {}
            has_archived_mp = (
                mp.get("session_status") == "archived" and bool(mp)
            )
            out.append(
                CampaignSummary(
                    id=raw.get("campaign_id", entry.stem),
                    player=raw.get("player", {}).get("name", "Unknown"),
                    title=raw.get("title", "") or "",
                    created_at=raw.get("created_at"),
                    has_archived_multiplayer=has_archived_mp,
                )
            )
        except Exception as e:
            log.warning("Skipping unreadable state file %s: %s", entry.name, e)
    return out


async def delete_campaign(campaign_id: str) -> bool:
    path = _path_for(campaign_id)
    async with campaign_lock(campaign_id):
        removed = False
        candidates = {
            path,
            path.with_suffix(path.suffix + ".tmp"),
        }
        candidates.update(STATES_DIR.glob(f"{campaign_id}.corrupt-*.bak"))
        candidates.update(STATES_DIR.glob(f"{campaign_id}.json.corrupt-*.bak"))
        for candidate in candidates:
            try:
                if candidate.exists():
                    candidate.unlink()
                    removed = True
            except OSError as e:
                log.warning("Failed to delete campaign artifact %s: %s", candidate.name, e)
        return removed


# ---------------------------------------------------------------------------
# Extraction merge (used by A8 / B5 / B6 / B7)
# ---------------------------------------------------------------------------


def _normalize_disposition(value: str, previous: Disposition) -> Disposition:
    if not value:
        return previous
    v = value.lower()
    for disp in Disposition:
        if disp.value.lower() in v:
            return disp
    log.info("Disposition change %r did not match any enum; keeping %s", value, previous.value)
    return previous


def _clamp_stat(name: str, new_value: int, bounds: dict[str, StatBound]) -> int:
    b = bounds.get(name, StatBound())
    return max(b.min, min(b.max, new_value))


def _resolve_character_target(
    state: CampaignState,
    player_slot: PlayerSlot | str | None,
) -> Player | PlayerCharacter:
    """Resolve which Player / PlayerCharacter object a delta should be applied to.

    Single-player (slot=None): returns `state.player`.
    Multiplayer (slot=host/guest): returns the matching `PlayerCharacter`,
    falling back to `state.player` if the multiplayer config is absent.
    """
    if player_slot is None:
        return state.player
    slot_value = player_slot.value if isinstance(player_slot, PlayerSlot) else str(player_slot)
    if state.multiplayer is None:
        return state.player
    if slot_value == PlayerSlot.HOST.value:
        return state.multiplayer.host_character
    if slot_value == PlayerSlot.GUEST.value and state.multiplayer.guest_character is not None:
        return state.multiplayer.guest_character
    # Unknown slot or guest not yet joined — fall back gracefully.
    return state.player


def apply_state_delta(
    state: CampaignState,
    delta: StateDelta,
    player_slot: PlayerSlot | str | None = None,
) -> dict[str, Any]:
    """
    Apply an extraction delta to a CampaignState in place.
    Returns a ReversalPatch-compatible dict describing how to undo this change (B1/B2).

    `player_slot` is None for single-player (legacy `state.player`). When provided
    in multiplayer mode, stats / location / inventory updates target the matching
    `PlayerCharacter`. NPC updates are always global.
    """
    slot_value: str | None = None
    if player_slot is not None:
        slot_value = player_slot.value if isinstance(player_slot, PlayerSlot) else str(player_slot)

    reversal: dict[str, Any] = {
        "player_slot": slot_value,
        "stats_changes": {},
        "location_before": None,
        "inventory_to_remove": [],
        "inventory_to_restore": [],
        "npc_reversals": [],
    }

    target = _resolve_character_target(state, player_slot)

    # Stats
    for stat_name, raw_delta in delta.stats_changes.items():
        if not isinstance(raw_delta, (int, float)):
            continue
        d = int(raw_delta)
        if d == 0:
            continue

        current = target.stats.get(stat_name, 0)

        # Suspicious-delta guard (B5): huge deltas likely indicate the model
        # returned an absolute value rather than a delta. Halve with warning.
        if current > 0 and abs(d) > max(10, current * 10):
            log.warning(
                "Suspicious stat delta %+d on %s (current=%d); halving",
                d, stat_name, current,
            )
            d = d // 2

        # Dynamic stat: new stats get default bounds registered (B7).
        if stat_name not in target.stats:
            state.stat_bounds.setdefault(stat_name, StatBound())

        new_value = _clamp_stat(stat_name, current + d, state.stat_bounds)
        applied_delta = new_value - current  # may differ from d due to clamping
        if applied_delta == 0:
            continue
        target.stats[stat_name] = new_value
        reversal["stats_changes"][stat_name] = -applied_delta

    # Location
    if delta.location and delta.location.strip():
        reversal["location_before"] = target.location
        target.location = delta.location.strip()

    # Inventory
    for item in delta.inventory_added:
        if not isinstance(item, str) or not item.strip():
            continue
        item = item.strip()
        if item not in target.inventory:
            target.inventory.append(item)
            reversal["inventory_to_remove"].append(item)

    for item in delta.inventory_removed:
        if not isinstance(item, str) or not item.strip():
            continue
        item = item.strip()
        if item in target.inventory:
            target.inventory.remove(item)
            reversal["inventory_to_restore"].append(item)

    # NPCs (always global, regardless of slot)
    for upd in delta.npc_updates:
        if not upd.name:
            continue
        npc = next((n for n in state.npcs if n.name == upd.name), None)
        created = False
        if npc is None:
            from schema import NPC  # local import to avoid cycle at module load
            npc = NPC(name=upd.name)
            state.npcs.append(npc)
            created = True

        rev_entry: dict[str, Any] = {"name": upd.name, "created": created}
        if upd.disposition_change:
            prev_disp = npc.disposition
            new_disp = _normalize_disposition(upd.disposition_change, prev_disp)
            if new_disp != prev_disp:
                rev_entry["disposition_before"] = prev_disp.value
                npc.disposition = new_disp
        if upd.secret_revealed and upd.secret_revealed not in npc.secrets_known:
            npc.secrets_known.append(upd.secret_revealed)
            rev_entry["secret_added"] = upd.secret_revealed
        if rev_entry.keys() - {"name"}:
            reversal["npc_reversals"].append(rev_entry)

    return reversal


def apply_reversal(state: CampaignState, reversal: dict[str, Any]) -> None:
    """Undo the effects of `apply_state_delta` using the reversal patch (B2)."""
    slot_value = reversal.get("player_slot")
    target = _resolve_character_target(state, slot_value)

    for stat_name, inverse in reversal.get("stats_changes", {}).items():
        if not isinstance(inverse, (int, float)):
            continue
        current = target.stats.get(stat_name, 0)
        new_value = _clamp_stat(stat_name, current + int(inverse), state.stat_bounds)
        target.stats[stat_name] = new_value

    loc_before = reversal.get("location_before")
    if loc_before:
        target.location = loc_before

    for item in reversal.get("inventory_to_remove", []):
        if item in target.inventory:
            target.inventory.remove(item)

    for item in reversal.get("inventory_to_restore", []):
        if item not in target.inventory:
            target.inventory.append(item)

    for rev in reversal.get("npc_reversals", []):
        name = rev.get("name")
        if not name:
            continue
        if rev.get("created"):
            state.npcs = [n for n in state.npcs if n.name != name]
            continue
        npc = next((n for n in state.npcs if n.name == name), None)
        if npc is None:
            continue
        disp_before = rev.get("disposition_before")
        if disp_before:
            try:
                npc.disposition = Disposition(disp_before)
            except ValueError:
                pass
        secret = rev.get("secret_added")
        if secret and secret in npc.secrets_known:
            npc.secrets_known.remove(secret)


# ---------------------------------------------------------------------------
# Convenience helpers used by main.py
# ---------------------------------------------------------------------------


async def append_message(campaign_id: str, role: Role | str, content: str, **kwargs) -> Message | None:
    """Append a message to the campaign and persist. Returns the new Message (or None)."""
    role_enum = role if isinstance(role, Role) else Role(role)
    msg = Message(role=role_enum, content=content, **kwargs)

    async def _m(state: CampaignState) -> CampaignState:
        state.messages.append(msg)
        return state

    new_state = await mutate_state(campaign_id, _m)
    return msg if new_state else None


def touch_created(state: CampaignState) -> None:
    if not state.created_at:
        state.created_at = datetime.now(timezone.utc).isoformat()


def record_event(state: CampaignState, event_type: str, message: str) -> None:
    """Append a compact event-log entry, keeping only the most recent 100."""
    state.events.append(CampaignEvent(type=event_type, message=message))
    state.events = state.events[-100:]


def get_multiplayer_config(state: CampaignState) -> MultiplayerConfig | None:
    """Return the multiplayer config for callers that should not touch internals."""
    return state.multiplayer


async def update_multiplayer_config(
    campaign_id: str,
    updater: Callable[[MultiplayerConfig], Awaitable[MultiplayerConfig | None] | MultiplayerConfig | None],
) -> MultiplayerConfig | None:
    """Mutate and persist a campaign's MultiplayerConfig.

    The updater may edit the config in place and return None, or return a
    replacement config. Returns the saved config, or None if the campaign is
    missing or not multiplayer.
    """
    saved_config: MultiplayerConfig | None = None

    async def _apply(state: CampaignState) -> CampaignState:
        nonlocal saved_config
        if state.multiplayer is None:
            return state
        maybe_coro = updater(state.multiplayer)
        if asyncio.iscoroutine(maybe_coro):
            replacement = await maybe_coro
        else:
            replacement = maybe_coro
        if replacement is not None:
            state.multiplayer = replacement
        saved_config = state.multiplayer
        return state

    await mutate_state(campaign_id, _apply)
    return saved_config


async def set_guest_character(campaign_id: str, character: PlayerCharacter) -> MultiplayerConfig | None:
    """Set or replace the guest character on a multiplayer campaign."""
    character.slot = PlayerSlot.GUEST

    async def _update(config: MultiplayerConfig) -> MultiplayerConfig:
        config.guest_character = character
        return config

    return await update_multiplayer_config(campaign_id, _update)
