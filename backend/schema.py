"""
Campaign state schema (v2) for Tavern Tales Reborn.

All persistent campaign data is validated through these models. Other modules
(state_manager, extraction, prompt_builder, main) import from here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Disposition(str, Enum):
    FRIENDLY = "Friendly"
    NEUTRAL = "Neutral"
    SUSPICIOUS = "Suspicious"
    HOSTILE = "Hostile"


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Player(BaseModel):
    name: str = "Unknown"
    location: str = "The Ember & Ash Tavern"
    stats: dict[str, int] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)


class NPC(BaseModel):
    name: str
    disposition: Disposition = Disposition.NEUTRAL
    secrets_known: list[str] = Field(default_factory=list)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    role: Role
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_kickoff: bool = False
    partial: bool = False  # set True if generation was interrupted (C1)


class ChapterSummary(BaseModel):
    start_turn: int
    end_turn: int
    text: str


class Summaries(BaseModel):
    short: str = ""
    chapters: list[ChapterSummary] = Field(default_factory=list)
    arc: str = ""
    last_short_update_turn: int = 0
    last_chapter_rollup_turn: int = 0


class ModelConfig(BaseModel):
    gm: str = "llama3"
    utility: str = "llama3.1:8b-instruct"
    nsfw_world_gen: bool = False


class StatBound(BaseModel):
    min: int = 0
    max: int = 9999


class SamplingOverrides(BaseModel):
    """Per-campaign sampling overrides. Any None field inherits the ollama_client default."""

    temperature: float | None = None
    repeat_penalty: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    num_predict: int | None = None


class ReversalPatch(BaseModel):
    """Inverse of an extraction delta, used to roll back a message's side effects (B1/B2)."""

    stats_changes: dict[str, int] = Field(default_factory=dict)  # inverted deltas
    location_before: str | None = None
    inventory_to_remove: list[str] = Field(default_factory=list)
    inventory_to_restore: list[str] = Field(default_factory=list)
    npc_reversals: list[dict[str, Any]] = Field(default_factory=list)


class MessageSideEffects(BaseModel):
    memory_ids: list[str] = Field(default_factory=list)
    reversal: ReversalPatch = Field(default_factory=ReversalPatch)


# ---------------------------------------------------------------------------
# Top-level state
# ---------------------------------------------------------------------------


class CampaignState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = SCHEMA_VERSION
    campaign_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    models: ModelConfig = Field(default_factory=ModelConfig)

    player: Player = Field(default_factory=Player)
    npcs: list[NPC] = Field(default_factory=list)
    lorebook: dict[str, str] = Field(default_factory=dict)
    world_description: str = ""
    starting_scene: str = ""

    messages: list[Message] = Field(default_factory=list)
    summaries: Summaries = Field(default_factory=Summaries)

    side_effects: dict[str, MessageSideEffects] = Field(default_factory=dict)

    stat_bounds: dict[str, StatBound] = Field(default_factory=dict)
    sampling_overrides: SamplingOverrides = Field(default_factory=SamplingOverrides)


class CampaignSummary(BaseModel):
    """Lightweight listing shape for the menu screen."""

    id: str
    player: str
    created_at: str | None = None


# ---------------------------------------------------------------------------
# Extraction output
# ---------------------------------------------------------------------------


class NPCUpdate(BaseModel):
    name: str
    disposition_change: str | None = None  # free-form input; normalized downstream (B6)
    secret_revealed: str | None = None


class StateDelta(BaseModel):
    """Output schema for the state-extraction LLM call."""

    model_config = ConfigDict(extra="ignore")

    stats_changes: dict[str, int] = Field(default_factory=dict)
    location: str | None = None
    inventory_added: list[str] = Field(default_factory=list)
    inventory_removed: list[str] = Field(default_factory=list)
    npc_updates: list[NPCUpdate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt builder output
# ---------------------------------------------------------------------------


class BlockTokens(BaseModel):
    role_rules: int = 0
    world: int = 0
    scene: int = 0
    protagonist: int = 0
    cast: int = 0
    lorebook: int = 0
    arc_summary: int = 0
    chapter_summaries: int = 0
    short_summary: int = 0
    memories: int = 0


class PromptStats(BaseModel):
    blocks: BlockTokens = Field(default_factory=BlockTokens)
    system_tokens: int = 0
    history_tokens: int = 0
    response_budget: int = 512
    model_context_window: int = 8192
    total_used: int = 0


class BuiltPrompt(BaseModel):
    messages: list[dict[str, str]]
    stats: PromptStats
    system_prompt: str  # rendered system-prompt string for inspector (C4)
    retrieved_memories: list[dict[str, Any]] = Field(default_factory=list)
