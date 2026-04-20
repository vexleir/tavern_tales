"""
Tavern Tales — Three-Tier Memory System

Tier 1: Working Context — built fresh each turn, ~2048 tokens
Tier 2: Session Summary — compressed every 20 turns
Tier 3: World Lore — persistent NPC memories, world history, quest flags
"""

import json
import sqlite3
from typing import Optional
from dataclasses import dataclass

from models import (
    get_connection, Scene, Message, NPC, NPCRelationship,
    WorldEvent, WorldLore, World, Player
)


# ─────────────────────────────────────────────────────────────────────────────
# Working Context
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WorkingContext:
    """
    The complete context assembled and passed to Ollama each turn.
    """
    world_lore: str          # Relevant lore entries
    session_summary: str     # What happened this session so far
    working_scene: str       # Current location, atmosphere, NPCs present
    player_character: str    # The active player's sheet
    npc_memories: str        # What present NPCs remember about the player
    gm_instructions: str     # Persona, rules, tone, adult mode flag
    # player_input is prepended by the GM engine when assembling the full prompt


# ─────────────────────────────────────────────────────────────────────────────
# Session Summarizer
# ─────────────────────────────────────────────────────────────────────────────

class SessionSummarizer:
    """
    Compresses the last N turns into a prose session summary.
    Triggers every 20 turns to prevent context bloat.
    """

    SUMMARY_TURNS = 20

    def __init__(self, world_id: str, player_id: str):
        self.world_id = world_id
        self.player_id = player_id

    def needs_summary(self, current_turn: int) -> bool:
        """Return True if it's time to generate a summary."""
        return current_turn > 0 and current_turn % self.SUMMARY_TURNS == 0

    def get_recent_messages(self, limit: int = 40) -> list[Message]:
        """Fetch the most recent player/GM messages for summarization."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM messages
            WHERE player_id = ?
              AND role IN ('player', 'gm')
              AND summary IS NULL
            ORDER BY turn DESC, created_at DESC
            LIMIT ?
        """, (self.player_id, limit))
        rows = cur.fetchall()
        conn.close()

        messages = []
        for r in reversed(rows):  # oldest first for summarization
            messages.append(Message(
                id=r["id"],
                world_id=r["world_id"],
                player_id=r["player_id"],
                turn=r["turn"],
                role=r["role"],
                content=r["content"],
                summary=r["summary"],
                created_at=r["created_at"]
            ))
        return messages

    def build_summary_prompt(self, messages: list[Message]) -> str:
        """
        Build a prompt instructing the LLM to summarize the session.
        Returns only the instruction portion — the LLM generates the summary.
        """
        exchange_lines = []
        for m in messages:
            role_label = "Player" if m.role == "player" else "GM"
            exchange_lines.append(f"{role_label}: {m.content[:500]}")

        exchanges = "\n".join(exchange_lines)

        return f"""You are a session chronicler. Read the following exchange log and write a prose summary of what happened in this RPG session.

Write 200-400 words. Write in third person from the GM's perspective, as if narrating to a reader. Include:
- What the player character did and discovered
- How NPCs responded and what was revealed
- Any significant emotional moments or decisions
- The current situation the player finds themselves in

Do NOT include system notes, tone directives, or meta-commentary. Only write the story so far.

EXCHANGE LOG:
{exchanges}

SESSION SUMMARY:"""

    def generate_summary(self, messages: list[Message]) -> str:
        """
        Placeholder — actual generation happens in gm_engine via Ollama.
        This method returns the raw summary text once the LLM returns it.
        """
        # The GM engine calls Ollama with build_summary_prompt().
        # This method stores the result.
        pass

    def save_summary(self, summary_text: str, turn: int):
        """Store a generated summary as a special 'summary' role message."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()

        # Delete any existing summary for this summary checkpoint
        cur.execute("""
            DELETE FROM messages
            WHERE player_id = ? AND role = 'summary' AND turn = ?
        """, (self.player_id, turn))

        msg = Message(
            id=str(uuid.uuid4()),
            world_id=self.world_id,
            player_id=self.player_id,
            turn=turn,
            role="summary",
            content=summary_text,
            summary=summary_text
        )

        cur.execute("""
            INSERT INTO messages (id, world_id, player_id, turn, role, content, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg.id, msg.id, msg.player_id, msg.turn, msg.role, msg.content, msg.summary))

        conn.commit()
        conn.close()


import uuid  # moved here to keep imports together


# ─────────────────────────────────────────────────────────────────────────────
# World Lore Querier
# ─────────────────────────────────────────────────────────────────────────────

class WorldLoreQuerier:
    """
    Queries persistent world lore entries by keyword relevance to current scene.
    """

    def __init__(self, world_id: str):
        self.world_id = world_id

    def query(self, scene_text: str, category: Optional[str] = None, limit: int = 5) -> list[WorldLore]:
        """
        Find lore entries whose keywords match words in scene_text.
        Returns up to `limit` entries.
        """
        conn = get_connection(self.world_id)
        cur = conn.cursor()

        if category:
            cur.execute("""
                SELECT * FROM world_lore
                WHERE world_id = ? AND category = ?
                ORDER BY created_at DESC
                LIMIT 100
            """, (self.world_id, category))
        else:
            cur.execute("""
                SELECT * FROM world_lore
                WHERE world_id = ?
                ORDER BY created_at DESC
                LIMIT 100
            """, (self.world_id,))

        all_rows = cur.fetchall()
        conn.close()

        matched = []
        for r in all_rows:
            lore = WorldLore(
                id=r["id"],
                world_id=r["world_id"],
                category=r["category"],
                keywords=r["keywords"],
                content=r["content"],
                created_at=r["created_at"]
            )
            if lore.matches_keywords(scene_text):
                matched.append(lore)
                if len(matched) >= limit:
                    break

        return matched

    def format_for_prompt(self, lore_entries: list[WorldLore]) -> str:
        """Format lore entries into a readable string for the GM prompt."""
        if not lore_entries:
            return "(No relevant world lore found.)"

        sections = []
        for lore in lore_entries:
            sections.append(f"[{lore.category.upper()}] {lore.content}")

        return "\n\n".join(sections)

    def add_lore(self, category: str, keywords: str, content: str):
        """Add a new lore entry to the world."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        lore = WorldLore(
            id=str(uuid.uuid4()),
            world_id=self.world_id,
            category=category,
            keywords=keywords,
            content=content
        )
        cur.execute("""
            INSERT INTO world_lore (id, world_id, category, keywords, content)
            VALUES (?, ?, ?, ?, ?)
        """, (lore.id, lore.world_id, lore.category, lore.keywords, lore.content))
        conn.commit()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Memory Injector
# ─────────────────────────────────────────────────────────────────────────────

class MemoryInjector:
    """
    Assembles the full three-tier memory context for each turn.
    This is the primary interface the GM engine uses.
    """

    def __init__(self, world_id: str, player_id: str):
        self.world_id = world_id
        self.player_id = player_id
        self.lore_querier = WorldLoreQuerier(world_id)
        self.summarizer = SessionSummarizer(world_id, player_id)

    # ── Tier 1: Working Context ──────────────────────────────────────────────

    def build_working_context(
        self,
        scene: Scene,
        player: Player,
        present_npcs: list[NPC],
        relationships: dict[str, NPCRelationship],
        gm_instructions: str,
        recent_messages: list[Message],
    ) -> WorkingContext:
        """
        Build the complete WorkingContext by querying all three tiers.
        """
        # Tier 1a: Current scene
        scene_text = self._format_scene(scene, present_npcs)
        scene_keywords = f"{scene.location} {' '.join(n.name for n in present_npcs)}"
        working_scene = scene_text

        # Tier 3: World Lore — keyword-matched to scene
        lore_entries = self.lore_querier.query(scene_keywords, limit=5)
        world_lore = self.lore_querier.format_for_prompt(lore_entries)

        # Tier 2: Session Summary — get last summary + recent messages
        session_summary = self._get_session_summary(scene.turn)
        if recent_messages:
            session_summary += "\n\n[RECENT EXCHANGE]\n" + "\n".join(
                f"{'Player' if m.role == 'player' else 'GM'}: {m.content[:300]}"
                for m in recent_messages[-6:]
            )

        # NPC Memories — what present NPCs remember about this player
        npc_memories = self._format_npc_memories(present_npcs, relationships)

        # Player character sheet
        char = player.get_character()
        player_character = self._format_character(char, relationships, present_npcs)

        return WorkingContext(
            world_lore=world_lore,
            session_summary=session_summary,
            working_scene=working_scene,
            player_character=player_character,
            npc_memories=npc_memories,
            gm_instructions=gm_instructions,
        )

    def _format_scene(self, scene: Scene, present_npcs: list[NPC]) -> str:
        """Format the current scene description."""
        lines = [f"**Location: {scene.location}**"]
        lines.append("")

        if present_npcs:
            lines.append("Present NPCs:")
            for npc in present_npcs:
                state = npc.get_state()
                lines.append(f"  - {npc.name}: {state.mood}, {state.activity}")
                if state.flags:
                    lines.append(f"    ({', '.join(f'{k}: {v}' for k, v in state.flags.items())})")

        quests = scene.get_active_quests()
        if quests:
            lines.append(f"\nActive quests: {', '.join(quests)}")

        lines.append(f"\nCurrent turn: {scene.turn}")
        return "\n".join(lines)

    def _format_npc_memories(
        self,
        present_npcs: list[NPC],
        relationships: dict[str, NPCRelationship]
    ) -> str:
        """Format what each present NPC remembers about the player."""
        lines = []
        for npc in present_npcs:
            rel = relationships.get(npc.id)
            memories = npc.get_memories_for_player(self.player_id)
            lines.append(f"\n**{npc.name}**")
            if rel:
                lines.append(f"  Relationship: {rel.mood_descriptor()}")
                lines.append(f"  love={rel.love:.2f}, trust={rel.trust:.2f}, fear={rel.fear:.2f}, anger={rel.anger:.2f}")
            if memories:
                lines.append("  Memories:")
                for mem in memories:
                    lines.append(f"    - {mem}")
            else:
                lines.append("  (No significant memories yet)")

        return "\n".join(lines) if lines else "(No NPCs present)"

    def _format_character(
        self,
        char,
        relationships: dict[str, NPCRelationship],
        present_npcs: list[NPC]
    ) -> str:
        """Format the player character sheet for the prompt."""
        lines = [
            f"Name: {char.name}",
            f"Appearance: {char.appearance}",
            f"Personality: {char.personality}",
            f"Backstory: {char.backstory}",
            f"Traits: {', '.join(char.traits) if char.traits else 'none'}",
        ]
        return "\n".join(lines)

    def _get_session_summary(self, current_turn: int) -> str:
        """
        Find the most recent session summary that predates current turn.
        """
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("""
            SELECT content FROM messages
            WHERE player_id = ? AND role = 'summary' AND turn < ?
            ORDER BY turn DESC LIMIT 1
        """, (self.player_id, current_turn))
        row = cur.fetchone()
        conn.close()

        if row:
            return f"[SESSION SUMMARY — from earlier this session]\n{row['content']}"

        return "[No prior session summary — this is the beginning of the session.]"

    # ── Assemble Full Prompt ─────────────────────────────────────────────────

    def assemble_full_prompt(
        self,
        ctx: WorkingContext,
        player_input: str
    ) -> str:
        """
        Assemble the complete prompt in the required memory injection order.
        """
        parts = [
            "[WORLD LORE]",
            ctx.world_lore,
            "",
            "[SESSION SUMMARY]",
            ctx.session_summary,
            "",
            "[WORKING CONTEXT]",
            ctx.working_scene,
            "",
            "[PLAYER CHARACTER]",
            ctx.player_character,
            "",
            "[NPC MEMORIES]",
            ctx.npc_memories,
            "",
            "[GM INSTRUCTIONS]",
            ctx.gm_instructions,
            "",
            "[PLAYER INPUT]",
            player_input,
        ]
        return "\n".join(parts)

    # ── Summary Trigger ─────────────────────────────────────────────────────

    def check_and_trigger_summary(self, current_turn: int) -> bool:
        """
        Called after a turn is processed. Returns True if a summary was triggered.
        The actual generation is done in gm_engine.
        """
        return self.summarizer.needs_summary(current_turn)
