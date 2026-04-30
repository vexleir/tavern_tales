"""
Campaign state schema (v2) for Tavern Tales Reborn.

All persistent campaign data is validated through these models. Other modules
(state_manager, extraction, prompt_builder, main) import from here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
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


class PlayerSlot(str, Enum):
    HOST = "host"
    GUEST = "guest"


class SessionStatus(str, Enum):
    LOBBY = "lobby"
    HOST_TURN = "host_turn"
    GUEST_TURN = "guest_turn"
    GENERATING = "generating"
    PAUSED = "paused"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Player(BaseModel):
    name: str = "Unknown"
    location: str = "The Ember & Ash Tavern"
    gender: str = "Unspecified"  # M / F / NB / Unspecified (free-form to allow custom values)
    appearance: str = ""  # physical description — what others see
    description: str = ""  # personality, backstory, notable traits
    stats: dict[str, int] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)


class PlayerCharacter(BaseModel):
    """One player-controlled character in a multiplayer session.

    Mirrors `Player` but tagged with a slot so multiple characters can co-exist
    in the same campaign. Single-player campaigns continue to use `Player`.
    """

    slot: PlayerSlot
    name: str = "Unknown"
    location: str = ""
    gender: str = "Unspecified"
    appearance: str = ""
    description: str = ""
    stats: dict[str, int] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)


class NPC(BaseModel):
    name: str
    disposition: Disposition = Disposition.NEUTRAL
    gender: str = "Unspecified"
    appearance: str = ""
    description: str = ""
    secrets_known: list[str] = Field(default_factory=list)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    turn_id: str | None = None
    role: Role
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_kickoff: bool = False
    partial: bool = False  # set True if generation was interrupted (C1)
    player_slot: Literal["host", "guest"] | None = None  # multiplayer attribution


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


class RulesConfig(BaseModel):
    enabled: bool = True
    dice_mode: str = "d20"
    default_dc: int = 12
    tone: str = "dark fantasy"
    response_length: str = "concise"
    summary_short_interval: int = 5
    summary_chapter_interval: int = 20


class QuestObjective(BaseModel):
    text: str
    complete: bool = False


class Quest(BaseModel):
    id: str = Field(default_factory=lambda: f"quest_{uuid4().hex[:10]}")
    title: str
    status: str = "active"
    objectives: list[QuestObjective] = Field(default_factory=list)


class Condition(BaseModel):
    name: str
    severity: str = "minor"
    duration: str = "scene"
    source: str = ""


class ActionResolution(BaseModel):
    risky: bool = False
    stat: str = ""
    stat_value: int = 0
    modifier: int = 0
    roll: int = 0
    total: int = 0
    dc: int = 0
    outcome: str = "none"
    summary: str = ""


class CampaignEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:10]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    type: str
    message: str


class ReversalPatch(BaseModel):
    """Inverse of an extraction delta, used to roll back a message's side effects (B1/B2)."""

    player_slot: Literal["host", "guest"] | None = None  # multiplayer slot, None for single-player
    stats_changes: dict[str, int] = Field(default_factory=dict)  # inverted deltas
    location_before: str | None = None
    inventory_to_remove: list[str] = Field(default_factory=list)
    inventory_to_restore: list[str] = Field(default_factory=list)
    npc_reversals: list[dict[str, Any]] = Field(default_factory=list)


class MessageSideEffects(BaseModel):
    memory_ids: list[str] = Field(default_factory=list)
    reversal: ReversalPatch = Field(default_factory=ReversalPatch)
    # In multiplayer turns, character-specific reversals (one per slot) live here.
    # NPC reversals from the turn are stored on `reversal` (shared/global).
    extra_reversals: list[ReversalPatch] = Field(default_factory=list)
    status: str = "pending"
    error: str = ""


class MultiplayerConfig(BaseModel):
    """Multiplayer session configuration attached to a campaign.

    When `multiplayer` is None on a CampaignState, the campaign is single-player
    and the legacy `player` field is the source of truth. When present, both
    `host_character` and (eventually) `guest_character` carry per-slot state and
    `player` is left untouched for backwards compat.
    """

    room_code: str
    host_character: "PlayerCharacter"
    guest_character: "PlayerCharacter | None" = None
    merged_preference_context: "CampaignPreferenceContext | None" = None
    session_status: SessionStatus = SessionStatus.LOBBY
    starting_slot_this_round: PlayerSlot = PlayerSlot.HOST
    turn_number: int = 0
    reconnect_window_seconds: int = 300


class CampaignPreferenceContext(BaseModel):
    """Redacted preference metadata attached to a campaign.

    This is prompt-safe guidance only. It must not contain private comments,
    password-protected fantasy content, or reality-bridge private fields.
    """

    enabled: bool = False
    source: str = ""  # saved_fantasy, profile, comparison, etc.
    profile_id: str = ""
    profile_version: int | None = None
    draft_id: str = ""
    draft_title: str = ""
    selected_themes: list[dict[str, Any]] = Field(default_factory=list)
    fantasy_only_theme_ids: list[str] = Field(default_factory=list)
    real_world_hard_no_theme_ids: list[str] = Field(default_factory=list)
    global_context: dict[str, Any] = Field(default_factory=dict)
    safety_principle: str = "Fantasy interest is not real-world consent."


# ---------------------------------------------------------------------------
# Top-level state
# ---------------------------------------------------------------------------


class CampaignState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = SCHEMA_VERSION
    campaign_id: str
    title: str = ""  # user-editable display name; UI falls back to "{player}'s Tale" when empty
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    revision: int = 0

    models: ModelConfig = Field(default_factory=ModelConfig)

    player: Player = Field(default_factory=Player)
    npcs: list[NPC] = Field(default_factory=list)
    lorebook: dict[str, str] = Field(default_factory=dict)
    world_description: str = ""
    starting_scene: str = ""
    rules: RulesConfig = Field(default_factory=RulesConfig)
    quests: list[Quest] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    preference_context: CampaignPreferenceContext = Field(default_factory=CampaignPreferenceContext)

    messages: list[Message] = Field(default_factory=list)
    summaries: Summaries = Field(default_factory=Summaries)

    side_effects: dict[str, MessageSideEffects] = Field(default_factory=dict)
    events: list[CampaignEvent] = Field(default_factory=list)

    stat_bounds: dict[str, StatBound] = Field(default_factory=dict)
    sampling_overrides: SamplingOverrides = Field(default_factory=SamplingOverrides)

    # Multiplayer is opt-in. Single-player campaigns leave this as None and
    # continue using the legacy `player` field above.
    multiplayer: MultiplayerConfig | None = None


class CampaignSummary(BaseModel):
    """Lightweight listing shape for the menu screen."""

    id: str
    player: str
    title: str = ""
    created_at: str | None = None
    has_archived_multiplayer: bool = False


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


class MultiplayerStateDelta(BaseModel):
    """Per-slot extraction output for multiplayer turns.

    Stats / location / inventory updates are attributed per character.
    NPC updates are global (NPCs are shared across the campaign).
    """

    model_config = ConfigDict(extra="ignore")

    host: StateDelta = Field(default_factory=StateDelta)
    guest: StateDelta = Field(default_factory=StateDelta)
    npc_updates: list[NPCUpdate] = Field(default_factory=list)


# Resolve forward references on MultiplayerConfig now that PlayerCharacter and
# CampaignPreferenceContext exist as concrete classes.
MultiplayerConfig.model_rebuild()


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
    action_resolution: int = 0
    quests: int = 0
    conditions: int = 0
    preferences: int = 0
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
