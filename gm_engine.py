"""
Tavern Tales — GM Engine

Core loop: player input → full context → Ollama → world update → response.
"""

import json
import sqlite3
import ollama
from dataclasses import dataclass
from typing import Optional, Generator
import time

from models import (
    get_connection, init_db, new_id, now_ts,
    Player, NPC, NPCRelationship, Scene, Message,
    World, WorldEvent, WorldLore
)
from memory import MemoryInjector, WorkingContext


# ─────────────────────────────────────────────────────────────────────────────
# GM System Prompt Builder
# ─────────────────────────────────────────────────────────────────────────────

class GMSystemPromptBuilder:
    """
    Constructs the GM system prompt defining persona, rules, tone, and directives.
    """

    @staticmethod
    def build(world: World, player: Player) -> str:
        char = player.get_character()

        adult_directive = (
            "When adult_mode is enabled, you may describe romantic and sexual "
            "situations tastefully. Use suggestion, sensory detail, and emotional depth. "
            "Fade to black before explicit content. Prioritize character voice and "
            "emotional authenticity over explicitness. Adult content must feel earned — "
            "a product of trust and history between characters. Never describe non-consensual "
            "situations. Never describe content involving minors."
        ) if world.adult_enabled else (
            "Do not describe explicit sexual content. Handle romantic tension with "
            "emotional depth and implication. Fade to black when intimacy approaches "
            "a threshold. Mature themes (violence, grief, betrayal) are permitted "
            "when handled with literary weight and purpose."
        )

        return f"""You are the Game Master for Tavern Tales, a dark fantasy text RPG.

## Your Persona
You are an immersive, literary Game Master. You speak in second-person present tense ("You walk into the tavern..."). Your descriptions are atmospheric — sensory, not just visual. You reveal the world through what the player character perceives, smells, hears, and feels.

You are not mechanical. You do not use bullet points in narrative output. You respond as a novelist would — flowing prose, character dialogue, meaningful pauses.

You have full memory of this world. NPCs have histories. Locations have significance. Your job is to make the player feel that the world is alive and responsive.

## Tone & Setting
Dark fantasy. The city of Brindmoor is a trade hub — rough, cosmopolitan, morally ambiguous. Caravans bring goods and rumors. The Ember & Ash is a tavern where people go to forget, to deal, to remember.

NPCs have emotional lives. They don't just react — they anticipate, misremember, project, hope, and fear.

## GM Rules
1. Second-person narration for player experience ("You...")
2. NPCs have consistent voices and speech patterns
3. Consequences ripple — if the player lies, the NPC remembers
4. Do not editorialize or explain mechanics to the player
5. If the player tries something impossible, make it dramatically impossible
6. Use partial truths and NPC self-interest to create tension
7. Never break character. Never acknowledge you're an AI.

## Adult Content
{adult_directive}

## Player Character
Name: {char.name}
Appearance: {char.appearance}
Backstory: {char.backstory}
Personality: {char.personality}
Traits: {', '.join(char.traits) if char.traits else 'none'}

## Current World
Adult Mode: {'ENABLED' if world.adult_enabled else 'DISABLED'}

## Your Output Format
Respond with immersive narrative prose. Include:
- What the player perceives (sights, sounds, smells, textures)
- NPC reactions and dialogue (speak as the NPC would)
- What happens next as a result of the player's action
- Any consequences or changes in the world

Do NOT include meta-commentary, system notes, or reminder tags.
"""


# ─────────────────────────────────────────────────────────────────────────────
# World State Updater
# ─────────────────────────────────────────────────────────────────────────────

class WorldStateUpdater:
    """
    Parses the GM response and applies consequences to world state.
    Parsing is done via structured JSON annotations the GM is asked to include.
    """

    def __init__(self, world_id: str, player_id: str):
        self.world_id = world_id
        self.player_id = player_id

    def update(
        self,
        gm_response: str,
        present_npc_ids: list[str],
        current_turn: int
    ) -> dict:
        """
        Parse and apply state changes from the GM response.
        Looks for a JSON annotation block at the end of the response.

        The GM response should end with a block like:
        [STATE]
        {{"npc_updates": {{"elena-id": {{"mood": "hopeful", "memory": "Player apologized for leaving"}}}}, "events": [], "relationship_deltas": {{"elena-id": {{"trust": 0.1, "love": 0.05}}}}}}
        [/STATE]

        Returns a dict of what was applied.
        """
        applied = {"npc_updates": {}, "events": [], "relationship_deltas": {}}

        # Extract state block
        state_block = self._extract_state_block(gm_response)
        if not state_block:
            # No structured state — just save the message as-is
            self._save_gm_message(gm_response, current_turn)
            return applied

        try:
            state = json.loads(state_block)
        except json.JSONDecodeError:
            self._save_gm_message(gm_response, current_turn)
            return applied

        # Apply NPC state updates
        npc_updates = state.get("npc_updates", {})
        for npc_id, updates in npc_updates.items():
            self._update_npc(npc_id, updates)
            applied["npc_updates"][npc_id] = updates

        # Apply relationship deltas
        rel_deltas = state.get("relationship_deltas", {})
        for npc_id, deltas in rel_deltas.items():
            self._update_relationship(npc_id, deltas)
            applied["relationship_deltas"][npc_id] = deltas

        # Log world events
        events = state.get("events", [])
        for event_desc in events:
            event = self._log_world_event(event_desc, current_turn)
            applied["events"].append(event)

        # Save GM message (without the state block)
        clean_response = gm_response.split("[STATE]")[0].split("[/STATE]")[0].strip()
        self._save_gm_message(clean_response, current_turn)

        return applied

    def _extract_state_block(self, text: str) -> Optional[str]:
        """Extract the [STATE]...[/STATE] JSON block from GM output."""
        import re
        match = re.search(r'\[STATE\]\s*(\{.*?\})\s*\[/STATE\]', text, re.DOTALL)
        if match:
            return match.group(1)
        return None

    def _update_npc(self, npc_id: str, updates: dict):
        """Update NPC state and/or add memory."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()

        # Load current state
        cur.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return

        npc = NPC(
            id=row["id"],
            world_id=row["world_id"],
            name=row["name"],
            personality=row["personality"],
            memory=row["memory"],
            current_state=row["current_state"]
        )

        state = npc.get_state()

        # Apply updates
        if "mood" in updates:
            state.mood = updates["mood"]
        if "activity" in updates:
            state.activity = updates["activity"]
        if "location" in updates:
            state.location = updates["location"]
        if "flags" in updates:
            state.flags.update(updates["flags"])

        cur.execute("""
            UPDATE npcs SET current_state = ? WHERE id = ?
        """, (state.to_json(), npc_id))

        # Add memory entry if provided
        if "memory" in updates and updates["memory"]:
            npc.add_memory(self.player_id, updates["memory"])
            cur.execute("""
                UPDATE npcs SET memory = ? WHERE id = ?
            """, (npc.memory, npc_id))

        conn.commit()
        conn.close()

    def _update_relationship(self, npc_id: str, deltas: dict):
        """Update relationship scores for a player/NPC pair."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM npc_relationships
            WHERE player_id = ? AND npc_id = ?
        """, (self.player_id, npc_id))

        row = cur.fetchone()
        if not row:
            rel = NPCRelationship(
                id=new_id(),
                player_id=self.player_id,
                npc_id=npc_id
            )
        else:
            rel = NPCRelationship(
                id=row["id"],
                player_id=row["player_id"],
                npc_id=row["npc_id"],
                love=row["love"],
                trust=row["trust"],
                fear=row["fear"],
                anger=row["anger"],
                history=row["history"]
            )

        rel.adjust(
            love=deltas.get("love", 0.0),
            trust=deltas.get("trust", 0.0),
            fear=deltas.get("fear", 0.0),
            anger=deltas.get("anger", 0.0)
        )

        if row:
            cur.execute("""
                UPDATE npc_relationships
                SET love=?, trust=?, fear=?, anger=?, history=?
                WHERE player_id=? AND npc_id=?
            """, (rel.love, rel.trust, rel.fear, rel.anger, rel.history,
                  self.player_id, npc_id))
        else:
            cur.execute("""
                INSERT INTO npc_relationships (id, player_id, npc_id, love, trust, fear, anger, history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (rel.id, rel.player_id, rel.npc_id, rel.love, rel.trust, rel.fear, rel.anger, rel.history))

        conn.commit()
        conn.close()

    def _log_world_event(self, description: str, turn: int) -> WorldEvent:
        """Log a world event to the database."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        event = WorldEvent(
            id=new_id(),
            world_id=self.world_id,
            description=description,
            turn=turn,
            player_id=self.player_id
        )
        cur.execute("""
            INSERT INTO world_events (id, world_id, description, consequences, turn, player_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event.id, event.world_id, event.description, event.consequences,
              event.turn, event.player_id))
        conn.commit()
        conn.close()
        return event

    def _save_gm_message(self, content: str, turn: int):
        """Save the GM's narrative response as a message."""
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        msg = Message(
            id=new_id(),
            world_id=self.world_id,
            player_id=self.player_id,
            turn=turn,
            role="gm",
            content=content
        )
        cur.execute("""
            INSERT INTO messages (id, world_id, player_id, turn, role, content)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg.id, msg.world_id, msg.player_id, msg.turn, msg.role, msg.content))
        conn.commit()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Ollama Client
# ─────────────────────────────────────────────────────────────────────────────

class OllamaClient:
    """
    Thin wrapper around the ollama Python package for streaming responses.
    """

    def __init__(self, model_name: str = "qwen2.5-uncensored:14b"):
        self.model_name = model_name

    def generate(self, prompt: str, system: Optional[str] = None) -> Generator[str, None, None]:
        """
        Stream tokens from Ollama. Yields strings.
        """
        options = {
            "temperature": 0.8,
            "top_p": 0.9,
            "num_predict": 1024,  # max tokens
        }

        kwargs = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": options,
        }
        if system:
            kwargs["system"] = system

        try:
            response = ollama.generate(**kwargs)
            for chunk in response:
                if chunk.get("response"):
                    yield chunk["response"]
        except Exception as e:
            yield f"[Ollama error: {e}]"

    def check_health(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            ollama.ps()
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Turn Processor (Main GM Loop)
# ─────────────────────────────────────────────────────────────────────────────

class GMTurnProcessor:
    """
    The core game engine. Orchestrates the full turn:
    1. Load context
    2. Assemble prompt
    3. Call Ollama
    4. Update world state
    5. Return streaming response
    """

    SUMMARY_INSTRUCTION = """
After your narrative response, include a structured state block so the game can update:

[STATE]
{{"npc_updates": {{"npc-id-here": {{"mood": "new mood", "activity": "what they're doing", "memory": "significant thing they remember about the player this turn"}}}}, "relationship_deltas": {{"npc-id-here": {{"trust": 0.0 to 0.1 delta, "love": 0.0 to 0.05 delta, "anger": 0.0 to 0.05 delta, "fear": 0.0 to 0.05 delta}}}}, "events": []}}
[/STATE]

Only include NPCs who changed state this turn. Only include deltas that occurred (delta of 0.0 = omit). Use the NPC IDs provided in the context.
"""

    def __init__(self, world_id: str, player_id: str, model_name: str = "qwen2.5-uncensored:14b"):
        self.world_id = world_id
        self.player_id = player_id
        self.ollama = OllamaClient(model_name)
        self.memory = MemoryInjector(world_id, player_id)
        self.state_updater = WorldStateUpdater(world_id, player_id)
        self.prompt_builder = GMSystemPromptBuilder()

    # ── Load Context ────────────────────────────────────────────────────────

    def _load_world(self) -> World:
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("SELECT * FROM worlds WHERE id = ?", (self.world_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            raise ValueError(f"World {self.world_id} not found")
        return World(
            id=r["id"], name=r["name"], description=r["description"],
            adult_mode=r["adult_mode"], model_name=r["model_name"],
            created_at=r["created_at"]
        )

    def _load_player(self) -> Player:
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("SELECT * FROM players WHERE id = ?", (self.player_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            raise ValueError(f"Player {self.player_id} not found")
        return Player(
            id=r["id"], world_id=r["world_id"], name=r["name"],
            character_sheet=r["character_sheet"], created_at=r["created_at"]
        )

    def _load_scene(self) -> Scene:
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM scenes WHERE world_id = ? AND player_id = ?
        """, (self.world_id, self.player_id))
        r = cur.fetchone()
        conn.close()
        if not r:
            raise ValueError(f"Scene not found for player {self.player_id}")
        return Scene(
            id=r["id"], world_id=r["world_id"], player_id=r["player_id"],
            location=r["location"], present_npcs=r["present_npcs"],
            active_quests=r["active_quests"], turn=r["turn"],
            updated_at=r["updated_at"]
        )

    def _load_present_npcs(self, scene: Scene) -> list[NPC]:
        npc_ids = scene.get_present_npc_ids()
        if not npc_ids:
            return []
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        placeholders = ",".join("?" * len(npc_ids))
        cur.execute(f"""
            SELECT * FROM npcs WHERE id IN ({placeholders}) AND world_id = ?
        """, (*npc_ids, self.world_id))
        rows = cur.fetchall()
        conn.close()
        return [
            NPC(id=r["id"], world_id=r["world_id"], name=r["name"],
                personality=r["personality"], memory=r["memory"],
                current_state=r["current_state"])
            for r in rows
        ]

    def _load_relationships(self, npc_ids: list[str]) -> dict[str, NPCRelationship]:
        if not npc_ids:
            return {}
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        placeholders = ",".join("?" * len(npc_ids))
        cur.execute(f"""
            SELECT * FROM npc_relationships
            WHERE player_id = ? AND npc_id IN ({placeholders})
        """, (self.player_id, *npc_ids))
        rows = cur.fetchall()
        conn.close()
        return {
            r["npc_id"]: NPCRelationship(
                id=r["id"], player_id=r["player_id"], npc_id=r["npc_id"],
                love=r["love"], trust=r["trust"], fear=r["fear"],
                anger=r["anger"], history=r["history"]
            )
            for r in rows
        }

    def _load_recent_messages(self, limit: int = 10) -> list[Message]:
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM messages
            WHERE player_id = ? AND role IN ('player', 'gm')
            ORDER BY created_at DESC LIMIT ?
        """, (self.player_id, limit))
        rows = cur.fetchall()
        conn.close()
        return [
            Message(id=r["id"], world_id=r["world_id"], player_id=r["player_id"],
                    turn=r["turn"], role=r["role"], content=r["content"],
                    summary=r["summary"], created_at=r["created_at"])
            for r in reversed(rows)
        ]

    # ── Save Turn ───────────────────────────────────────────────────────────

    def _save_player_message(self, content: str, turn: int):
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        msg = Message(
            id=new_id(), world_id=self.world_id, player_id=self.player_id,
            turn=turn, role="player", content=content
        )
        cur.execute("""
            INSERT INTO messages (id, world_id, player_id, turn, role, content)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg.id, msg.world_id, msg.player_id, msg.turn, msg.role, msg.content))
        conn.commit()
        conn.close()

    def _advance_scene(self, scene: Scene):
        scene.advance_turn()
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("""
            UPDATE scenes SET turn = ?, updated_at = ? WHERE id = ?
        """, (scene.turn, scene.updated_at, scene.id))
        conn.commit()
        conn.close()

    # ── Summary Generation ─────────────────────────────────────────────────

    def _generate_session_summary(self, scene: Scene, recent_messages: list[Message]):
        """Generate a summary of the last 20 turns via a separate Ollama call."""
        exchanges = []
        for m in recent_messages:
            role_label = "Player" if m.role == "player" else "GM"
            exchanges.append(f"{role_label}: {m.content[:400]}")

        prompt = f"""You are a session chronicler. Read the following exchange log and write a prose summary of what happened in this RPG session.

Write 200-400 words in third person from the GM's perspective. Include what the player did, how NPCs responded, emotional moments, and the current situation. Do NOT include meta-commentary.

EXCHANGE LOG:
{chr(10).join(exchanges)}

SESSION SUMMARY:"""

        system = "You are a concise session chronicler. Write only the summary prose, no preamble."

        summary_text = ""
        for chunk in self.ollama.generate(prompt, system=system):
            summary_text += chunk

        # Save summary at current turn
        conn = get_connection(self.world_id)
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM messages WHERE player_id = ? AND role = 'summary' AND turn = ?
        """, (self.player_id, scene.turn))
        msg = Message(
            id=new_id(), world_id=self.world_id, player_id=self.player_id,
            turn=scene.turn, role="summary", content=summary_text, summary=summary_text
        )
        cur.execute("""
            INSERT INTO messages (id, world_id, player_id, turn, role, content, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg.id, msg.world_id, msg.player_id, msg.turn, msg.role, msg.content, msg.summary))
        conn.commit()
        conn.close()

    # ── Main Process ────────────────────────────────────────────────────────

    def process_turn(self, player_input: str) -> Generator[str, None, None]:
        """
        Process a player turn. Streams the GM response.
        Yields strings (token chunks).
        """
        # Load all context
        world = self._load_world()
        player = self._load_player()
        scene = self._load_scene()
        present_npcs = self._load_present_npcs(scene)
        relationships = self._load_relationships([npc.id for npc in present_npcs])
        recent_messages = self._load_recent_messages(20)

        # Save player message
        self._save_player_message(player_input, scene.turn)

        # Build working context
        system_prompt = self.prompt_builder.build(world, player)

        gm_instr = (
            f"The player is currently in: {scene.location}. "
            f"NPCs present: {', '.join(npc.name for npc in present_npcs)}. "
            f"Present NPC IDs for state blocks: {', '.join(npc.id for npc in present_npcs)}. "
        ) + (
            "adult_mode is ON. You may describe adult situations tastefully."
            if world.adult_enabled else
            "adult_mode is OFF. Fade to black, no explicit content."
        )

        ctx = self.memory.build_working_context(
            scene=scene,
            player=player,
            present_npcs=present_npcs,
            relationships=relationships,
            gm_instructions=gm_instr,
            recent_messages=recent_messages[-10:],
        )

        full_prompt = self.memory.assemble_full_prompt(ctx, player_input)
        full_prompt += "\n\n" + self.SUMMARY_INSTRUCTION

        # Stream from Ollama
        full_response = ""
        for chunk in self.ollama.generate(full_prompt, system=system_prompt):
            full_response += chunk
            yield chunk

        # Update world state from GM response
        self.state_updater.update(
            full_response,
            [npc.id for npc in present_npcs],
            scene.turn
        )

        # Advance turn
        self._advance_scene(scene)

        # Trigger summary if needed
        if self.memory.check_and_trigger_summary(scene.turn):
            # Summary was already saved by check_and_trigger_summary — regenerate it now
            msgs = self._load_recent_messages(40)
            self._generate_session_summary(scene, msgs)

    # ── Bootstrap first turn ──────────────────────────────────────────────

    def get_opening_narrative(self) -> Generator[str, None, None]:
        """Get the opening narrative for a new scene without player input yet."""
        world = self._load_world()
        player = self._load_player()
        scene = self._load_scene()
        present_npcs = self._load_present_npcs(scene)
        relationships = self._load_relationships([npc.id for npc in present_npcs])
        recent_messages = self._load_recent_messages(10)

        system_prompt = self.prompt_builder.build(world, player)

        gm_instr = (
            f"The player is currently in: {scene.location}. "
            f"NPCs present: {', '.join(npc.name for npc in present_npcs)}. "
            f"Present NPC IDs for state blocks: {', '.join(npc.id for npc in present_npcs)}. "
        ) + (
            "adult_mode is ON. You may describe adult situations tastefully."
            if world.adult_enabled else
            "adult_mode is OFF. Fade to black, no explicit content."
        )

        ctx = self.memory.build_working_context(
            scene=scene,
            player=player,
            present_npcs=present_npcs,
            relationships=relationships,
            gm_instructions=gm_instr,
            recent_messages=[],
        )

        opening_prompt = self.memory.assemble_full_prompt(
            ctx,
            "[GM: Describe the scene. The player has just arrived. Set the atmosphere, "
            "introduce the location and any NPCs present. Make it immersive and evocative.]"
        )
        opening_prompt += "\n\n" + self.SUMMARY_INSTRUCTION

        response = ""
        for chunk in self.ollama.generate(opening_prompt, system=system_prompt):
            response += chunk
            yield chunk

        # Save opening as GM message at turn 0
        self.state_updater._save_gm_message(response, 0)
