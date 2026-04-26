"""
Pytest fixtures: mock Ollama, temp state dir, temp chroma dir.

All tests import backend modules directly (the backend/ dir is on sys.path because
pytest is run from there via pytest.ini). Fixtures monkey-patch module-level
state so each test gets an isolated environment.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, AsyncGenerator

import pytest

# Make the backend/ directory (parent of tests/) importable as top-level modules.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# --------------------------------------------------------------------------- #
# Temp state dir
# --------------------------------------------------------------------------- #


@pytest.fixture
def temp_state_dir(tmp_path, monkeypatch):
    """Redirect state_manager's per-campaign files to a fresh tmp dir."""
    import state_manager

    monkeypatch.setattr(state_manager, "STATES_DIR", tmp_path / "states")
    monkeypatch.setattr(state_manager, "LEGACY_FILE", tmp_path / "campaign_states.json")
    monkeypatch.setattr(state_manager, "_migration_checked", False)
    monkeypatch.setattr(state_manager, "_locks", {})
    monkeypatch.setattr(state_manager, "_turn_locks", {})
    (tmp_path / "states").mkdir(parents=True, exist_ok=True)
    return tmp_path


# --------------------------------------------------------------------------- #
# Temp chroma dir
# --------------------------------------------------------------------------- #


@pytest.fixture
def temp_chroma(tmp_path, monkeypatch):
    """Swap memory._client for a fresh chroma client rooted at a tmp dir."""
    import chromadb

    import memory

    fresh = chromadb.PersistentClient(path=str(tmp_path / "chroma_db"))
    monkeypatch.setattr(memory, "_client", fresh)
    return fresh


# --------------------------------------------------------------------------- #
# Mock Ollama
# --------------------------------------------------------------------------- #


class MockOllama:
    """
    Stand-in for ollama_client.* functions.

    Configure it before the code under test runs:
        mock_ollama.set_stream_text("The tavern is warm...")
        mock_ollama.set_json({"stats_changes": {"Health": -5}})
        mock_ollama.set_text("A summary.")
    """

    def __init__(self) -> None:
        self._stream_text: str = ""
        self._stream_error: str | None = None
        self._stream_stop_reason: str = "stop"
        self._json_payload: dict | None = None
        self._text_payload: str | None = None
        self.stream_calls: list[dict[str, Any]] = []
        self.json_calls: list[dict[str, Any]] = []
        self.text_calls: list[dict[str, Any]] = []

    def set_stream_text(self, text: str, stop_reason: str = "stop") -> None:
        self._stream_text = text
        self._stream_error = None
        self._stream_stop_reason = stop_reason

    def set_stream_error(self, err: str) -> None:
        self._stream_error = err
        self._stream_text = ""

    def set_json(self, payload: dict | None) -> None:
        self._json_payload = payload

    def set_text(self, text: str | None) -> None:
        self._text_payload = text

    async def stream_chat(self, messages, model, overrides=None) -> AsyncGenerator[dict, None]:
        self.stream_calls.append({"messages": messages, "model": model, "overrides": overrides})
        if self._stream_error:
            yield {"type": "error", "data": self._stream_error}
            yield {"type": "done", "stop_reason": "error"}
            return
        # Chunk the text in a couple of pieces to mimic streaming.
        text = self._stream_text
        mid = len(text) // 2 if text else 0
        if text:
            yield {"type": "token", "data": text[:mid]}
            yield {"type": "token", "data": text[mid:]}
        yield {"type": "done", "stop_reason": self._stream_stop_reason}

    async def complete_json(self, messages, model, timeout=60.0):
        self.json_calls.append({"messages": messages, "model": model})
        return self._json_payload

    async def complete_text(self, messages, model, timeout=60.0, num_predict=512):
        self.text_calls.append({"messages": messages, "model": model})
        return self._text_payload


@pytest.fixture
def mock_ollama(monkeypatch):
    """Patch ollama_client + downstream modules that import its functions by name."""
    m = MockOllama()

    import ollama_client
    monkeypatch.setattr(ollama_client, "stream_chat", m.stream_chat)
    monkeypatch.setattr(ollama_client, "complete_json", m.complete_json)
    monkeypatch.setattr(ollama_client, "complete_text", m.complete_text)

    # Downstream modules imported these names directly, so patch them there too.
    import extraction
    monkeypatch.setattr(extraction, "complete_json", m.complete_json)

    import summarizer
    monkeypatch.setattr(summarizer, "complete_text", m.complete_text)

    import main
    monkeypatch.setattr(main, "stream_chat", m.stream_chat)
    monkeypatch.setattr(main, "complete_json", m.complete_json)

    return m


# --------------------------------------------------------------------------- #
# Mock model resolver (don't hit Ollama tags endpoint in tests)
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def mock_resolver(monkeypatch):
    """Always-on: resolver returns the preferred model as-is."""
    import model_resolver

    async def _resolve(preferred, gm_fallback):
        return preferred or gm_fallback

    async def _available(name):
        return True

    monkeypatch.setattr(model_resolver, "resolve_utility_model", _resolve)
    monkeypatch.setattr(model_resolver, "is_model_available", _available)

    # Modules that imported the function by name.
    import extraction
    monkeypatch.setattr(extraction, "resolve_utility_model", _resolve)

    import summarizer
    monkeypatch.setattr(summarizer, "resolve_utility_model", _resolve)


# --------------------------------------------------------------------------- #
# Basic fixture factories
# --------------------------------------------------------------------------- #


@pytest.fixture
def new_state():
    """Factory: create a minimal-but-valid CampaignState."""
    from schema import CampaignState, ModelConfig, NPC, Player, StatBound, Disposition

    def _make(campaign_id: str = "test_campaign", **over) -> CampaignState:
        s = CampaignState(
            campaign_id=campaign_id,
            models=ModelConfig(gm="test-gm", utility="test-utility"),
            player=Player(
                name=over.get("player_name", "Hero"),
                location=over.get("location", "Tavern"),
                stats=over.get("stats", {"Health": 100, "Gold": 50}),
                inventory=over.get("inventory", []),
            ),
            npcs=over.get("npcs", [
                NPC(name="Elena", disposition=Disposition.NEUTRAL, secrets_known=["knows a song"]),
            ]),
            lorebook=over.get("lorebook", {"Magic": "Magic is forbidden."}),
            world_description=over.get("world_description", "A grim realm."),
            starting_scene=over.get("starting_scene", "You stand at a crossroads."),
            stat_bounds={k: StatBound() for k in over.get("stats", {"Health": 100, "Gold": 50}).keys()},
        )
        return s

    return _make
