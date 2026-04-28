"""Encrypted JSON storage helpers for sensitive local data.

Preference profiles and saved fantasies are sensitive enough that plaintext
JSON files would be the wrong default. This module provides a small envelope
format around Fernet encryption and password-derived Fernet keys.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ModuleNotFoundError as e:  # pragma: no cover - exercised only in misconfigured envs
    Fernet = None  # type: ignore[assignment]
    InvalidToken = ValueError  # type: ignore[assignment]
    PBKDF2HMAC = None  # type: ignore[assignment]
    hashes = None  # type: ignore[assignment]
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


_BACKEND_DIR = Path(__file__).resolve().parent
SECURE_DIR = _BACKEND_DIR / "secure"
KEY_FILE = SECURE_DIR / "local_profile_storage.key"
KEY_ENV = "TAVERN_TALES_PROFILE_KEY"

ENVELOPE_VERSION = 1
ALGORITHM = "fernet"
PASSWORD_KDF = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390_000


class SecureStorageError(RuntimeError):
    pass


def _require_crypto() -> None:
    if _IMPORT_ERROR is not None:
        raise SecureStorageError(
            "Encrypted storage requires the 'cryptography' package. "
            "Install backend requirements before using preference profiles."
        ) from _IMPORT_ERROR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_secure_dir() -> None:
    SECURE_DIR.mkdir(parents=True, exist_ok=True)


def _read_or_create_local_key() -> bytes:
    _require_crypto()
    configured = os.environ.get(KEY_ENV, "").strip()
    if configured:
        return configured.encode("utf-8")

    _ensure_secure_dir()
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()  # type: ignore[union-attr]
    KEY_FILE.write_bytes(key)
    if os.name != "nt":
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            pass
    return key


def export_local_key_backup() -> dict[str, Any]:
    """Return a user-controlled backup payload for the local encryption key."""
    _require_crypto()
    configured = os.environ.get(KEY_ENV, "").strip()
    key = configured.encode("utf-8") if configured else _read_or_create_local_key()
    source = "env" if configured else "local"
    return {
        "backupType": "tavern_tales_local_encryption_key",
        "keySource": source,
        "keyEnvVar": KEY_ENV,
        "algorithm": ALGORITHM,
        "exportedAt": _now(),
        "key": key.decode("utf-8"),
        "warning": (
            "Keep this key private. Anyone with this key and your encrypted local preference/fantasy files "
            "can decrypt them. Losing this key can make encrypted local data unrecoverable."
        ),
    }


def _fernet_from_key(key: bytes):
    _require_crypto()
    try:
        return Fernet(key)  # type: ignore[misc]
    except Exception as e:  # noqa: BLE001
        raise SecureStorageError(
            f"Invalid {KEY_ENV} value. Expected a urlsafe base64 Fernet key."
        ) from e


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def encrypt_json(payload: dict[str, Any]) -> dict[str, Any]:
    f = _fernet_from_key(_read_or_create_local_key())
    token = f.encrypt(_json_bytes(payload)).decode("utf-8")
    return {
        "encrypted": True,
        "envelopeVersion": ENVELOPE_VERSION,
        "algorithm": ALGORITHM,
        "keySource": "env" if os.environ.get(KEY_ENV, "").strip() else "local",
        "createdAt": _now(),
        "ciphertext": token,
    }


def decrypt_json(envelope: dict[str, Any]) -> dict[str, Any]:
    if not envelope.get("encrypted"):
        raise SecureStorageError("Refusing to read unencrypted sensitive payload.")
    if envelope.get("algorithm") != ALGORITHM:
        raise SecureStorageError(f"Unsupported encrypted payload algorithm: {envelope.get('algorithm')!r}")
    token = str(envelope.get("ciphertext") or "").encode("utf-8")
    f = _fernet_from_key(_read_or_create_local_key())
    try:
        raw = f.decrypt(token)
    except InvalidToken as e:
        raise SecureStorageError("Could not decrypt sensitive payload with the configured key.") from e
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise SecureStorageError("Encrypted payload did not contain a JSON object.")
    return data


def derive_password_key(password: str, salt: bytes, iterations: int = PASSWORD_ITERATIONS) -> bytes:
    _require_crypto()
    if not password:
        raise SecureStorageError("Password cannot be empty.")
    kdf = PBKDF2HMAC(  # type: ignore[misc]
        algorithm=hashes.SHA256(),  # type: ignore[union-attr]
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def password_encrypt_text(text: str, password: str) -> dict[str, Any]:
    salt = os.urandom(16)
    key = derive_password_key(password, salt)
    token = _fernet_from_key(key).encrypt(text.encode("utf-8")).decode("utf-8")
    return {
        "algorithm": ALGORITHM,
        "kdf": PASSWORD_KDF,
        "iterations": PASSWORD_ITERATIONS,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "ciphertext": token,
        "protectedAt": _now(),
    }


def password_decrypt_text(protected: dict[str, Any], password: str) -> str:
    if protected.get("algorithm") != ALGORITHM or protected.get("kdf") != PASSWORD_KDF:
        raise SecureStorageError("Unsupported password-protected payload.")
    salt = base64.urlsafe_b64decode(str(protected.get("salt") or "").encode("ascii"))
    iterations = int(protected.get("iterations") or PASSWORD_ITERATIONS)
    key = derive_password_key(password, salt, iterations=iterations)
    try:
        raw = _fernet_from_key(key).decrypt(str(protected.get("ciphertext") or "").encode("utf-8"))
    except InvalidToken as e:
        raise SecureStorageError("Password did not unlock this fantasy.") from e
    return raw.decode("utf-8")
