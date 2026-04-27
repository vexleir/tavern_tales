"""Encrypted persistence for preference profiles and saved fantasies."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from preference_defaults import default_categories, merge_default_categories
from preference_schema import (
    FantasySummary,
    GeneratedFantasy,
    PreferenceProfileSummary,
    ProfileStatus,
    UserPreferenceProfile,
    now_iso,
    pref_id,
)
from secure_storage import decrypt_json, encrypt_json, password_decrypt_text, password_encrypt_text

log = logging.getLogger(__name__)


_BACKEND_DIR = Path(__file__).resolve().parent
PREFERENCES_DIR = _BACKEND_DIR / "preferences"
FANTASIES_DIR = _BACKEND_DIR / "fantasies"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")

_profile_locks: dict[str, asyncio.Lock] = {}
_fantasy_locks: dict[str, asyncio.Lock] = {}
_profile_guard = asyncio.Lock()
_fantasy_guard = asyncio.Lock()


def _ensure_dirs() -> None:
    PREFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    FANTASIES_DIR.mkdir(parents=True, exist_ok=True)


async def initialize() -> None:
    _ensure_dirs()


def _validate_id(value: str, label: str = "id") -> None:
    if not value or not _SAFE_ID.match(value):
        raise ValueError(f"Invalid {label}: {value!r}")


def _profile_path(profile_id: str) -> Path:
    _validate_id(profile_id, "profile_id")
    return PREFERENCES_DIR / f"{profile_id}.json"


def _fantasy_path(fantasy_id: str) -> Path:
    _validate_id(fantasy_id, "fantasy_id")
    return FANTASIES_DIR / f"{fantasy_id}.json"


async def _get_profile_lock(profile_id: str) -> asyncio.Lock:
    async with _profile_guard:
        lock = _profile_locks.get(profile_id)
        if lock is None:
            lock = asyncio.Lock()
            _profile_locks[profile_id] = lock
        return lock


async def _get_fantasy_lock(fantasy_id: str) -> asyncio.Lock:
    async with _fantasy_guard:
        lock = _fantasy_locks.get(fantasy_id)
        if lock is None:
            lock = asyncio.Lock()
            _fantasy_locks[fantasy_id] = lock
        return lock


@asynccontextmanager
async def profile_lock(profile_id: str):
    lock = await _get_profile_lock(profile_id)
    async with lock:
        yield


@asynccontextmanager
async def fantasy_lock(fantasy_id: str):
    lock = await _get_fantasy_lock(fantasy_id)
    async with lock:
        yield


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dirs()
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
        # Some Windows sandbox/ACL combinations allow file creation and writes
        # but deny rename/delete in newly-created sensitive-data directories.
        # Keep the payload encrypted and fall back to a direct write so profile
        # creation still works for local users.
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass


def new_profile(display_name: str, user_id: str = "local_default") -> UserPreferenceProfile:
    now = now_iso()
    profile = UserPreferenceProfile(
        profileId=pref_id("profile"),
        userId=user_id or "local_default",
        displayName=display_name.strip() or "Default Profile",
        createdAt=now,
        updatedAt=now,
        lastReviewedAt=now,
        categories=default_categories(),
    )
    return profile


async def save_profile(profile: UserPreferenceProfile, bump_version: bool = True) -> UserPreferenceProfile:
    _ensure_dirs()
    async with profile_lock(profile.profileId):
        existing = await load_profile(profile.profileId)
        if existing and bump_version:
            profile.profileVersion = max(profile.profileVersion, existing.profileVersion + 1)
        profile.updatedAt = now_iso()
        profile.schemaVersion = "1.0.0"
        _atomic_write(_profile_path(profile.profileId), encrypt_json(profile.model_dump(mode="json")))
        return profile


async def create_profile(display_name: str, user_id: str = "local_default") -> UserPreferenceProfile:
    profile = new_profile(display_name, user_id=user_id)
    return await save_profile(profile, bump_version=False)


async def load_profile(profile_id: str) -> UserPreferenceProfile | None:
    _ensure_dirs()
    path = _profile_path(profile_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = decrypt_json(raw)
        return merge_default_categories(UserPreferenceProfile.model_validate(data))
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        corrupt = path.with_suffix(f".corrupt-{int(time.time())}.bak")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        raise RuntimeError(f"Preference profile {profile_id!r} could not be read: {e}") from e


async def list_profiles(include_archived: bool = False) -> list[PreferenceProfileSummary]:
    _ensure_dirs()
    summaries: list[PreferenceProfileSummary] = []
    for entry in sorted(PREFERENCES_DIR.glob("*.json")):
        if entry.name.endswith(".tmp"):
            continue
        try:
            raw = json.loads(entry.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or raw.get("encrypted") is not True:
            continue
        try:
            profile = await load_profile(entry.stem)
        except Exception as e:  # noqa: BLE001
            log.warning("Skipping unreadable preference profile %s: %s", entry.name, e)
            continue
        if profile is None:
            continue
        if profile.status == ProfileStatus.ARCHIVED and not include_archived:
            continue
        summaries.append(PreferenceProfileSummary(
            profileId=profile.profileId,
            userId=profile.userId,
            displayName=profile.displayName,
            profileVersion=profile.profileVersion,
            schemaVersion=profile.schemaVersion,
            status=profile.status,
            updatedAt=profile.updatedAt,
            onboardingCompleted=bool(profile.onboardingCompletedAt),
        ))
    return summaries


async def import_profile(payload: dict[str, Any], user_id: str = "local_default") -> UserPreferenceProfile:
    profile = UserPreferenceProfile.model_validate(payload)
    profile.profileId = pref_id("profile")
    profile.userId = user_id or profile.userId or "local_default"
    profile.displayName = f"{profile.displayName} (Imported)"
    profile.profileVersion = 1
    now = now_iso()
    profile.createdAt = now
    profile.updatedAt = now
    return await save_profile(profile, bump_version=False)


async def save_fantasy(fantasy: GeneratedFantasy) -> GeneratedFantasy:
    _ensure_dirs()
    async with fantasy_lock(fantasy.id):
        fantasy.updatedAt = now_iso()
        _write_fantasy_unlocked(fantasy)
        return fantasy


def _write_fantasy_unlocked(fantasy: GeneratedFantasy) -> None:
    _atomic_write(_fantasy_path(fantasy.id), encrypt_json(fantasy.model_dump(mode="json")))


async def load_fantasy(fantasy_id: str) -> GeneratedFantasy | None:
    _ensure_dirs()
    path = _fantasy_path(fantasy_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = decrypt_json(raw)
        return GeneratedFantasy.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        corrupt = path.with_suffix(f".corrupt-{int(time.time())}.bak")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        raise RuntimeError(f"Fantasy {fantasy_id!r} could not be read: {e}") from e


async def list_fantasies(profile_id: str | None = None) -> list[FantasySummary]:
    _ensure_dirs()
    out: list[FantasySummary] = []
    for entry in sorted(FANTASIES_DIR.glob("*.json")):
        if entry.name.endswith(".tmp"):
            continue
        fantasy = await load_fantasy(entry.stem)
        if fantasy is None:
            continue
        if profile_id and fantasy.ownerProfileId != profile_id:
            continue
        out.append(FantasySummary(
            id=fantasy.id,
            ownerProfileId=fantasy.ownerProfileId,
            title=fantasy.title,
            createdAt=fantasy.createdAt,
            updatedAt=fantasy.updatedAt,
            createdFromProfileVersion=fantasy.createdFromProfileVersion,
            sharingMode=fantasy.sharingMode,
            passwordProtected=bool(fantasy.passwordProtection.enabled),
        ))
    return out


async def protect_fantasy(fantasy_id: str, password: str, hint: str = "") -> GeneratedFantasy | None:
    async with fantasy_lock(fantasy_id):
        fantasy = await load_fantasy(fantasy_id)
        if fantasy is None:
            return None
        if fantasy.passwordProtection.enabled:
            return fantasy
        fantasy.protectedContent = password_encrypt_text(fantasy.content, password)
        fantasy.content = ""
        fantasy.passwordProtection.enabled = True
        fantasy.passwordProtection.hint = hint
        fantasy.passwordProtection.protectedAt = now_iso()
        fantasy.updatedAt = now_iso()
        _write_fantasy_unlocked(fantasy)
        return fantasy


def unlock_fantasy_content(fantasy: GeneratedFantasy, password: str) -> str:
    if not fantasy.passwordProtection.enabled:
        return fantasy.content
    if not fantasy.protectedContent:
        return ""
    return password_decrypt_text(fantasy.protectedContent, password)
