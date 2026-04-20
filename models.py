"""
Tavern Tales — Data Models
Core dataclasses for players, NPCs, world state, messages, scenes, and events.
"""

import uuid
import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from pathlib import Path

DB_DIR = Path.home() / ".local" / "share" / "tavern_tales"
DB_DIR.mkdir(parents=True, exist_ok=True)


def new_id() -> str:
    return str(uuid.uuid4())


def now_ts() -> str:
    return datetime.utcnow().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Character Sheet
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CharacterSheet:
    name: str
    appearance: str = ""
    backstory: str = ""
    personality: str = ""
    traits: list[str] = field(default_factory=list)
    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "CharacterSheet":
        d = json.loads(data)
        return cls(**d)


# ─────────────────────────────────────────────────────────────────────────────
# Player
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Player:
    id: str
    world_id: str
    name: str
    character_sheet: str  # JSON — CharacterSheet
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_ts()

    def get_character(self) -> CharacterSheet:
        return CharacterSheet.from_json(self.character_sheet)


# ─────────────────────────────────────────────────────────────────────────────
# NPC Personality / State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NPCPersonality:
    traits: list[str] = field(default_factory=list)
    speech_style: str = ""  # e.g., "formal", "sailor's tongue", "whispery"
    goals: list[str] = field(default_factory=list)
    fears: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "NPCPersonality":
        return cls(**json.loads(data))


@dataclass
class NPCState:
    location: str = ""
    mood: str = "neutral"  # neutral, happy, sad, angry, fearful, guarded, hopeful, etc.
    activity: str = ""     # what she's doing right now
    flags: dict = field(default_factory=dict)  # arbitrary state flags

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "NPCState":
        d = json.loads(data)
        if isinstance(d.get("flags"), str):
            d["flags"] = json.loads(d["flags"])
        return cls(**d)


# ─────────────────────────────────────────────────────────────────────────────
# NPC
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NPC:
    id: str
    world_id: str
    name: str
    personality: str  # JSON — NPCPersonality
    memory: str = "[]"  # JSON array of memory entries
    current_state: str = ""  # JSON — NPCState

    def get_personality(self) -> NPCPersonality:
        return NPCPersonality.from_json(self.personality)

    def get_state(self) -> NPCState:
        if not self.current_state:
            return NPCState()
        return NPCState.from_json(self.current_state)

    def get_memory(self) -> list[dict]:
        raw = json.loads(self.memory)
        return raw if isinstance(raw, list) else []

    def add_memory(self, player_id: str, entry: str):
        """Add a memory entry for a specific player."""
        mems = self.get_memory()
        mems.append({
            "player_id": player_id,
            "entry": entry,
            "timestamp": now_ts()
        })
        self.memory = json.dumps(mems)

    def get_memories_for_player(self, player_id: str) -> list[str]:
        """Return only memory entries relevant to a specific player."""
        return [
            m["entry"] for m in self.get_memory()
            if m.get("player_id") == player_id
        ]


# ─────────────────────────────────────────────────────────────────────────────
# NPC Relationship
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NPCRelationship:
    id: str
    player_id: str
    npc_id: str
    love: float = 0.0    # -1.0 to 1.0
    trust: float = 0.0   # -1.0 to 1.0
    fear: float = 0.0    # 0.0 to 1.0
    anger: float = 0.0   # 0.0 to 1.0
    history: str = "[]"  # JSON array of significant events

    def __post_init__(self):
        if not self.id:
            self.id = new_id()

    def get_history(self) -> list[dict]:
        return json.loads(self.history)

    def add_history_entry(self, entry: str):
        hist = self.get_history()
        hist.append({
            "entry": entry,
            "timestamp": now_ts(),
            "love": self.love,
            "trust": self.trust,
            "fear": self.fear,
            "anger": self.anger,
        })
        self.history = json.dumps(hist)

    def adjust(self, love=0.0, trust=0.0, fear=0.0, anger=0.0):
        self.love = max(-1.0, min(1.0, self.love + love))
        self.trust = max(-1.0, min(1.0, self.trust + trust))
        self.fear = max(0.0, min(1.0, self.fear + fear))
        self.anger = max(0.0, min(1.0, self.anger + anger))

    def mood_descriptor(self) -> str:
        """Return a prose descriptor of current mood based on scores."""
        if self.fear > 0.6:
            return "terrified"
        if self.anger > 0.6:
            return "furious"
        if self.love > 0.5 and self.trust > 0.3:
            return "affectionate"
        if self.trust < -0.3:
            return "cold and distant"
        if self.trust < 0.0:
            return "guarded"
        if self.love > 0.3:
            return "warm"
        return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# World
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class World:
    id: str
    name: str
    description: str = ""
    adult_mode: int = 0   # 0=off, 1=on
    model_name: str = "qwen2.5-uncensored:14b"
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_ts()

    @property
    def adult_enabled(self) -> bool:
        return bool(self.adult_mode)


# ─────────────────────────────────────────────────────────────────────────────
# Scene
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Scene:
    id: str
    world_id: str
    player_id: str
    location: str
    present_npcs: str = "[]"  # JSON list of NPC IDs
    active_quests: str = "[]"  # JSON list of quest flag keys
    turn: int = 0
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = now_ts()

    def get_present_npc_ids(self) -> list[str]:
        return json.loads(self.present_npcs)

    def get_active_quests(self) -> list[str]:
        return json.loads(self.active_quests)

    def add_npc(self, npc_id: str):
        npcs = self.get_present_npc_ids()
        if npc_id not in npcs:
            npcs.append(npc_id)
            self.present_npcs = json.dumps(npcs)

    def remove_npc(self, npc_id: str):
        npcs = self.get_present_npc_ids()
        if npc_id in npcs:
            npcs.remove(npc_id)
            self.present_npcs = json.dumps(npcs)

    def advance_turn(self):
        self.turn += 1
        self.updated_at = now_ts()


# ─────────────────────────────────────────────────────────────────────────────
# Message
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Message:
    id: str
    world_id: str
    player_id: str
    turn: int
    role: str  # 'player', 'gm', 'summary'
    content: str
    summary: Optional[str] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_ts()


# ─────────────────────────────────────────────────────────────────────────────
# World Event
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WorldEvent:
    id: str
    world_id: str
    description: str
    consequences: str = "{}"  # JSON dict of state changes
    turn: int = 0
    player_id: Optional[str] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_ts()

    def get_consequences(self) -> dict:
        return json.loads(self.consequences)


# ─────────────────────────────────────────────────────────────────────────────
# World Lore
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WorldLore:
    id: str
    world_id: str
    category: str  # 'history', 'faction', 'location', 'quest'
    keywords: str  # space-separated
    content: str
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_ts()

    def matches_keywords(self, text: str) -> bool:
        text_lower = text.lower()
        keywords = self.keywords.lower().split()
        return any(kw in text_lower for kw in keywords)


# ─────────────────────────────────────────────────────────────────────────────
# Database Helper
# ─────────────────────────────────────────────────────────────────────────────

def get_db_path(world_id: str) -> Path:
    return DB_DIR / f"{world_id}.db"


def get_connection(world_id: str) -> sqlite3.Connection:
    db_path = get_db_path(world_id)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(world_id: str):
    """Create all tables for a world."""
    path = get_db_path(world_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(world_id)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS worlds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            adult_mode INTEGER DEFAULT 0,
            model_name TEXT DEFAULT 'qwen2.5-uncensored:14b',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            name TEXT NOT NULL,
            character_sheet TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS npcs (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            name TEXT NOT NULL,
            personality TEXT NOT NULL,
            memory TEXT DEFAULT '[]',
            current_state TEXT DEFAULT '{}'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS npc_relationships (
            id TEXT PRIMARY KEY,
            player_id TEXT NOT NULL,
            npc_id TEXT NOT NULL,
            love REAL DEFAULT 0.0,
            trust REAL DEFAULT 0.0,
            fear REAL DEFAULT 0.0,
            anger REAL DEFAULT 0.0,
            history TEXT DEFAULT '[]',
            UNIQUE(player_id, npc_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS world_events (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            description TEXT NOT NULL,
            consequences TEXT DEFAULT '{}',
            turn INTEGER NOT NULL,
            player_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scenes (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            location TEXT NOT NULL,
            present_npcs TEXT DEFAULT '[]',
            active_quests TEXT DEFAULT '[]',
            turn INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(world_id, player_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS world_lore (
            id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            category TEXT NOT NULL,
            keywords TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
