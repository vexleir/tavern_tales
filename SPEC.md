# Tavern Tales — System Specification

> *"Every story begins with a door. Yours opens into The Ember & Ash."*

---

## 1. Concept & Vision

**Tavern Tales** is a multiplayer, text-based RPG powered by a local LLM acting as Game Master. Players create characters and enter a persistent, shared world — a dark fantasy realm where their choices ripple outward, shaping the world other players discover.

The GM is not a chatbot. It is a storyteller with memory, agenda, and consequence. NPCs are not mood boards — they are people with histories, secrets, and emotional ranges that respond authentically to player behavior over time.

### Core Pillars
- **Persistence**: The world exists between sessions. NPCs remember. Grudges linger.
- **Consequence**: Every action modifies world state. Lies erode trust. Kindness opens doors.
- **Tone**: Dark fantasy. Not grimdark for shock value — gritty, intimate, morally complex.
- **Flexibility**: Vanilla and adult content modes, toggled per world.
- **Immersion**: Second-person narration. The GM speaks to *you*.

---

## 2. Design Language

### Aesthetic
Dark fantasy tavern. Stone walls. Tallow candles guttering in draft. The smell of woodsmoke, spilled ale, and something older. Trade caravans pass through. Mercenaries drink in corners. The city of **Brindmoor** does not ask questions — it has too many of its own.

### Tone
- **GM Voice**: Literary, second-person present tense. Atmospheric. Never mechanical.
- **NPC Voice**: Each NPC has a distinct verbal register — Elena speaks differently than the barkeep.
- **Pacing**: Action → consequence → discovery. Don't rush beats.
- **Adult Content**: When enabled — tasteful, character-driven, never gratuitous. Fade to black for explicit moments.

### Color Palette (UI)
Deep slate, charcoal, amber accents. Serif font for story text, monospace for system info.

---

## 3. Three-Tier Memory System

### Tier 1 — Working Context (~2048 tokens)
The active scene window. Contains:
- Current location and description
- NPCs present and their current emotional states
- Last N player/GM message exchanges
- Immediate consequences from last turn

**Lifecycle**: Built fresh each turn from the database. Discarded after use.

### Tier 2 — Session Summary
A compressed narrative of everything that happened in the current session, regenerated every 20 turns by asking the LLM to summarize. Stored in the `messages` table as a special summary row.

**Format**: 200–400 word prose summary from the GM's perspective.  
**Trigger**: Auto-generated at turn 20, 40, 60, etc.

### Tier 3 — World Lore (Persistent)
Permanent world knowledge stored in the database:
- NPC long-term memories of specific players
- World history entries (major events)
- Quest state flags
- Faction reputation scores
- Location histories

**Queried**: Keyword/semantic search against current scene context to inject only relevant lore into the prompt. Prevents context bloat.

---

## 4. World State Schema (SQLite)

**Database location**: `~/.local/share/tavern_tales/<world_id>.db`

### `players`
```sql
CREATE TABLE players (
    id          TEXT PRIMARY KEY,   -- UUID
    world_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    character_sheet TEXT NOT NULL,  -- JSON: class, traits, backstory, appearance
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `npcs`
```sql
CREATE TABLE npcs (
    id          TEXT PRIMARY KEY,   -- UUID
    world_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    personality TEXT NOT NULL,      -- JSON: traits, speech style, goals
    memory      TEXT NOT NULL,      -- JSON: array of memory entries per player
    current_state TEXT NOT NULL     -- JSON: location, mood, activity
);
```

### `npc_relationships`
```sql
CREATE TABLE npc_relationships (
    id          TEXT PRIMARY KEY,   -- UUID
    player_id   TEXT NOT NULL,
    npc_id      TEXT NOT NULL,
    love        REAL DEFAULT 0.0,   -- -1.0 to 1.0
    trust       REAL DEFAULT 0.0,   -- -1.0 to 1.0
    fear        REAL DEFAULT 0.0,   -- 0.0 to 1.0
    anger       REAL DEFAULT 0.0,   -- 0.0 to 1.0
    history     TEXT DEFAULT '[]',  -- JSON: array of significant interaction entries
    UNIQUE(player_id, npc_id)
);
```

### `world_events`
```sql
CREATE TABLE world_events (
    id          TEXT PRIMARY KEY,   -- UUID
    world_id    TEXT NOT NULL,
    description TEXT NOT NULL,
    consequences TEXT DEFAULT '{}', -- JSON: flags, NPC state changes applied
    turn        INTEGER NOT NULL,
    player_id   TEXT,               -- who triggered it (null = world event)
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `scenes`
```sql
CREATE TABLE scenes (
    id          TEXT PRIMARY KEY,   -- UUID
    world_id    TEXT NOT NULL,
    player_id   TEXT NOT NULL,      -- scenes are per-player
    location    TEXT NOT NULL,      -- location key
    present_npcs TEXT DEFAULT '[]', -- JSON: list of NPC ids
    active_quests TEXT DEFAULT '[]',-- JSON: list of quest flag keys
    turn        INTEGER DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `messages`
```sql
CREATE TABLE messages (
    id          TEXT PRIMARY KEY,   -- UUID
    world_id    TEXT NOT NULL,
    player_id   TEXT NOT NULL,
    turn        INTEGER NOT NULL,
    role        TEXT NOT NULL,      -- 'player', 'gm', 'summary'
    content     TEXT NOT NULL,
    summary     TEXT,               -- populated for 'summary' role rows
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `world_lore`
```sql
CREATE TABLE world_lore (
    id          TEXT PRIMARY KEY,   -- UUID
    world_id    TEXT NOT NULL,
    category    TEXT NOT NULL,      -- 'history', 'faction', 'location', 'quest'
    keywords    TEXT NOT NULL,      -- space-separated for keyword search
    content     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `worlds`
```sql
CREATE TABLE worlds (
    id          TEXT PRIMARY KEY,   -- UUID
    name        TEXT NOT NULL,
    description TEXT,
    adult_mode  INTEGER DEFAULT 0,  -- 0=off, 1=on
    model_name  TEXT DEFAULT 'qwen2.5-uncensored:14b',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. GM Engine — Core Loop

```
Player Input
    │
    ▼
Build Working Context
    ├── Query World Lore (keyword match against scene)
    ├── Load Session Summary (last summary row)
    ├── Load recent messages (last 10 exchanges)
    ├── Load current scene (location, NPCs, quests)
    ├── Load player character sheet
    └── Load NPC memories/relationships for present NPCs
    │
    ▼
Assemble Prompt (Memory Injection Format — see §7)
    │
    ▼
Send to Ollama (streaming)
    │
    ▼
Parse GM Response
    ├── Extract NPC state changes (mood, location, memory updates)
    ├── Extract world events (if any)
    └── Extract relationship score deltas
    │
    ▼
Update World State (SQLite)
    ├── Save GM response as message
    ├── Update NPC states and memories
    ├── Log world events
    └── Trigger summary if turn % 20 == 0
    │
    ▼
Return streaming response to UI
```

---

## 6. Adult Content Handling

**Per-world toggle**: `worlds.adult_mode` (0 or 1)

**When OFF** (default):
- Mature themes present but implied
- Romance fades to black before anything explicit
- Violence described but not gratuitous
- System prompt instructs GM to handle with implication

**When ON**:
- GM may describe adult situations with tasteful detail
- Explicit moments handled as "fade to black" — intimate, evocative, not pornographic
- System prompt addition: *"When adult_mode is enabled, you may describe romantic and sexual situations tastefully. Use suggestion, sensory detail, and emotional depth. Fade to black before explicit content. Prioritize character voice and emotional authenticity over explicitness."*

**NPC consent modeling**: Adult content triggers only when NPC relationship score supports it (love > 0.5, trust > 0.3).

---

## 7. Multiplayer Design

- **Shared world**: All players share one SQLite database per world
- **Independent scenes**: Each player has their own scene record — they only see their own story thread
- **World event propagation**: When Player A does something that creates a world event, Player B's GM prompt includes that event in World Lore on their next turn
- **NPC state sharing**: NPCs are global — if Player A angers Elena, Player B finds her in a worse mood
- **No real-time sync**: Turn-based async. Each player's turn is processed independently
- **Session lock**: Advisory locks prevent simultaneous writes to the same NPC record

---

## 8. Memory Injection Format

Every Ollama prompt follows this structure:

```
[WORLD LORE]
<relevant lore entries, keyword-matched to current scene>

[SESSION SUMMARY]
<200-400 word compressed summary of this session so far>

[WORKING CONTEXT]
<current location, atmosphere, present NPCs and their states>

[PLAYER CHARACTER]
<character sheet: name, class, appearance, backstory, traits>

[NPC MEMORIES]
<what each present NPC specifically remembers about this player>

[GM INSTRUCTIONS]
<persona, world rules, tone directives, adult mode flag>

[PLAYER INPUT]
<the player's action or dialogue this turn>
```

---

## 9. The Lost Love Scenario — Built-In

**NPC: Elena**

A woman the player once loved. She is in Brindmoor now, far from where they met. She works the evenings at The Ember & Ash, waiting tables, asking no questions. She is guarded. She is not over it.

Her emotional state shifts with the relationship score:
- `trust < -0.3`: Cold, distant, won't make eye contact
- `trust 0.0`: Careful, measured, watching you
- `trust > 0.3`: Warmer, allows herself to remember
- `love > 0.5 + trust > 0.3`: Allows closeness, old intimacy resurfaces
- `anger > 0.5`: Confrontational, brings up the past
- `fear > 0.3`: Wants you to leave, won't say why

Her memory includes:
- How you met, where
- Why you parted (player-configurable backstory)
- Something she never said
- Something she can't forgive — yet

---

*Last updated: Initial spec*
