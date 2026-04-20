"""
Tavern Tales — World Initialization

Creates worlds, NPCs, scenes, and lore from scenario templates.
The Lost Love scenario is the built-in starting point.
"""

import json
import uuid
import sqlite3
from typing import Optional

from models import (
    init_db, get_connection, new_id, now_ts,
    World, Player, NPC, NPCRelationship, Scene,
    NPCPersonality, NPCState, WorldLore, CharacterSheet
)


# ─────────────────────────────────────────────────────────────────────────────
# World Initialization
# ─────────────────────────────────────────────────────────────────────────────

def create_world(
    name: str,
    description: str = "",
    adult_mode: bool = False,
    model_name: str = "qwen2.5-uncensored:14b"
) -> World:
    """Create a new world and initialize its database."""
    world = World(
        id=new_id(),
        name=name,
        description=description,
        adult_mode=1 if adult_mode else 0,
        model_name=model_name
    )

    init_db(world.id)

    conn = get_connection(world.id)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO worlds (id, name, description, adult_mode, model_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (world.id, world.name, world.description, world.adult_mode,
          world.model_name, world.created_at))
    conn.commit()
    conn.close()

    return world


def get_world(world_id: str) -> Optional[World]:
    if not world_id:
        return None
    try:
        conn = get_connection(world_id)
        cur = conn.cursor()
        cur.execute("SELECT * FROM worlds WHERE id = ?", (world_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return None
        return World(
            id=r["id"], name=r["name"], description=r["description"],
            adult_mode=r["adult_mode"], model_name=r["model_name"],
            created_at=r["created_at"]
        )
    except sqlite3.OperationalError:
        return None


def get_or_create_default_world() -> World:
    """Get the first world or create a default Lost Love world."""
    import os
    db_dir = os.path.expanduser("~/.local/share/tavern_tales")
    if os.path.exists(db_dir):
        import glob
        dbs = glob.glob(os.path.join(db_dir, "*.db"))
        if dbs:
            import sqlite3
            for db_path in dbs:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT id FROM worlds LIMIT 1")
                r = cur.fetchone()
                conn.close()
                if r:
                    return get_world(r["id"])

    # Create default
    return create_lost_love_world()


def list_worlds() -> list[World]:
    """List all worlds."""
    db_dir = os.path.expanduser("~/.local/share/tavern_tales")
    import glob
    import sqlite3
    worlds = []
    for db_path in glob.glob(f"{db_dir}/*.db"):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM worlds LIMIT 1")
            r = cur.fetchone()
            conn.close()
            if r:
                worlds.append(World(
                    id=r["id"], name=r["name"], description=r["description"],
                    adult_mode=r["adult_mode"], model_name=r["model_name"],
                    created_at=r["created_at"]
                ))
        except sqlite3.OperationalError:
            continue
    return worlds


# ─────────────────────────────────────────────────────────────────────────────
# Player Management
# ─────────────────────────────────────────────────────────────────────────────

def create_player(world_id: str, name: str, character_sheet: CharacterSheet) -> Player:
    """Create a player in a world."""
    player = Player(
        id=new_id(),
        world_id=world_id,
        name=name,
        character_sheet=character_sheet.to_json()
    )

    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO players (id, world_id, name, character_sheet, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (player.id, player.world_id, player.name,
          player.character_sheet, player.created_at))
    conn.commit()
    conn.close()

    return player


def get_player(player_id: str) -> Optional[Player]:
    conn = sqlite3.connect(get_world_db_path_from_player(player_id))
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    return Player(
        id=r["id"], world_id=r["world_id"], name=r["name"],
        character_sheet=r["character_sheet"], created_at=r["created_at"]
    )


def get_world_db_path_from_player(player_id: str) -> str:
    import sqlite3
    db_dir = os.path.expanduser("~/.local/share/tavern_tales")
    import glob
    for db_path in glob.glob(f"{db_dir}/*.db"):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT id FROM players WHERE id = ?", (player_id,))
        r = cur.fetchone()
        conn.close()
        if r:
            return db_path
    raise ValueError(f"Player {player_id} not found in any world")


def list_players(world_id: str) -> list[Player]:
    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE world_id = ?", (world_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        Player(id=r["id"], world_id=r["world_id"], name=r["name"],
               character_sheet=r["character_sheet"], created_at=r["created_at"])
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Lost Love Scenario — Elena NPC
# ─────────────────────────────────────────────────────────────────────────────

def create_elena(world_id: str, player_id: str, backstory: str = "") -> NPC:
    """
    Create Elena — the lost love NPC.

    Elena's emotional state is driven by:
    - How much the player hurt her (trust, anger)
    - Whether she still loves them (love)
    - Whether she's afraid of getting hurt again (fear)
    - Her guardedness based on all of the above
    """
    default_backstory = (
        "You met three years ago in the coastal town of Thornwick. "
        "She was a scholar's apprentice, curious and unguarded. You spent "
        "a summer together that felt like a lifetime. Then you left without "
        "explanation. She never knew why. She never forgave — but she never "
        "stopped wondering."
    )

    personality = NPCPersonality(
        traits=["guarded", "intelligent", "emotionally deep", "observant", "wounded"],
        speech_style=(
            "Elena speaks carefully, choosing words with precision. "
            "She has a scholar's vocabulary but a sailor's directness when she's angry. "
            "When she lets her guard down, she slips into the comfortable dialect of Thornwick. "
            "She doesn't repeat herself. She doesn't fill silences."
        ),
        goals=["understand why you left", "protect herself", "find peace"],
        fears=["being abandoned again", "not knowing the truth", "hoping for nothing"]
    )

    state = NPCState(
        location="The Ember & Ash tavern",
        mood="guarded",  # changes based on trust score
        activity="wiping down a table near the back",
        flags={
            "knows_player": True,
            "waiting_for_apology": True,
            "still_fancies_them": True  # relationship will determine this
        }
    )

    npc = NPC(
        id=new_id(),
        world_id=world_id,
        name="Elena",
        personality=personality.to_json(),
        memory=json.dumps([
            {
                "player_id": player_id,
                "entry": f"Met in Thornwick three years ago. Summer together. {backstory or default_backstory}",
                "timestamp": now_ts()
            },
            {
                "player_id": player_id,
                "entry": "Player left without saying goodbye. No explanation. She looked for them for months.",
                "timestamp": now_ts()
            }
        ]),
        current_state=state.to_json()
    )

    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO npcs (id, world_id, name, personality, memory, current_state)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (npc.id, npc.world_id, npc.name, npc.personality, npc.memory, npc.current_state))
    conn.commit()
    conn.close()

    # Create initial relationship with starting scores
    rel = NPCRelationship(
        id=new_id(),
        player_id=player_id,
        npc_id=npc.id,
        love=0.3,     # some residual feelings
        trust=-0.3,   # hurt by abandonment
        fear=0.2,     # scared of being hurt again
        anger=0.2     # some unresolved anger
    )

    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO npc_relationships (id, player_id, npc_id, love, trust, fear, anger, history)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (rel.id, rel.player_id, rel.npc_id, rel.love, rel.trust, rel.fear, rel.anger, rel.history))
    conn.commit()
    conn.close()

    return npc


# ─────────────────────────────────────────────────────────────────────────────
# The Ember & Ash Tavern
# ─────────────────────────────────────────────────────────────────────────────

def create_ember_and_ash(world_id: str) -> dict:
    """
    Create the tavern location and atmospheric lore.
    Returns a dict with location details and lore entries.
    """
    tavern_description = """
The Ember & Ash sits on the corner of Dockside and Copper Street in Brindmoor's
old quarter. The building leans slightly, as if it has learned to endure the salt
wind off the harbor. Inside: dark wood worn smooth by generations of elbows,
candles in iron sconces, a hearth that hasn't fully died in forty years.

The tavern draws caravans, mercenaries, merchants, and people who need to be
forgotten. The barkeep, a broad woman named Marta, asks no questions.
The ale is strong. The secrets are cheap.
"""

    # Add location lore
    add_lore(
        world_id=world_id,
        category="location",
        keywords="tavern ember ash Brindmoor Dockside Copper Street Marta barkeep",
        content=tavern_description.strip()
    )

    # City lore
    add_lore(
        world_id=world_id,
        category="location",
        keywords="Brindmoor city trade caravans harbor docks",
        content=(
            "Brindmoor is a trade city on the eastern coast. It has no ruler — "
            "only a council of merchant houses that agree on very little. "
            "The docks never sleep. The taverns never run dry. "
            "Rumors here travel faster than ships."
        )
    )

    return {"location": "The Ember & Ash", "description": tavern_description}


# ─────────────────────────────────────────────────────────────────────────────
# Starting Scene Builder
# ─────────────────────────────────────────────────────────────────────────────

def create_starting_scene(
    world_id: str,
    player_id: str,
    elena_id: str
) -> Scene:
    """Create the player's opening scene in the tavern."""
    scene = Scene(
        id=new_id(),
        world_id=world_id,
        player_id=player_id,
        location="The Ember & Ash — main room",
        present_npcs=json.dumps([elena_id]),
        active_quests=json.dumps([
            "find_elena",
            "discover_why_shes_here",
            "earn_her_trust"
        ]),
        turn=0
    )

    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO scenes (id, world_id, player_id, location, present_npcs, active_quests, turn, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (scene.id, scene.world_id, scene.player_id, scene.location,
          scene.present_npcs, scene.active_quests, scene.turn, scene.updated_at))
    conn.commit()
    conn.close()

    return scene


# ─────────────────────────────────────────────────────────────────────────────
# Lore Management
# ─────────────────────────────────────────────────────────────────────────────

def add_lore(world_id: str, category: str, keywords: str, content: str):
    """Add a world lore entry."""
    lore = WorldLore(
        id=new_id(),
        world_id=world_id,
        category=category,
        keywords=keywords,
        content=content
    )

    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO world_lore (id, world_id, category, keywords, content)
        VALUES (?, ?, ?, ?, ?)
    """, (lore.id, lore.world_id, lore.category, lore.keywords, lore.content))
    conn.commit()
    conn.close()


def get_lore(world_id: str, category: Optional[str] = None) -> list[WorldLore]:
    conn = get_connection(world_id)
    cur = conn.cursor()
    if category:
        cur.execute("""
            SELECT * FROM world_lore WHERE world_id = ? AND category = ?
            ORDER BY created_at DESC
        """, (world_id, category))
    else:
        cur.execute("SELECT * FROM world_lore WHERE world_id = ? ORDER BY created_at DESC", (world_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        WorldLore(id=r["id"], world_id=r["world_id"], category=r["category"],
                  keywords=r["keywords"], content=r["content"], created_at=r["created_at"])
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Full Scenario Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def create_lost_love_world(
    world_name: str = "Brindmoor — Lost Love",
    player_name: str = "Traveler",
    character_sheet: Optional[CharacterSheet] = None,
    adult_mode: bool = False,
    model_name: str = "qwen2.5-uncensored:14b"
) -> tuple[World, Player, NPC, Scene]:
    """
    Bootstrap a complete Lost Love scenario world.
    Returns (world, player, elena, scene).
    """
    if character_sheet is None:
        character_sheet = CharacterSheet(
            name=player_name,
            appearance="Road-worn, tired eyes, carrying the dust of three cities.",
            backstory=(
                "You left Thornwick three years ago, leaving everything behind — "
                "including someone you loved. You've been running ever since. "
                "Now a rumor has brought you to Brindmoor: she's here."
            ),
            personality="Ridden with guilt. Searching. Afraid of what you'll find.",
            traits=["haunted", "determined", "conflicted"]
        )

    # 1. Create world
    world = create_world(
        name=world_name,
        description="A chance reunion in a tavern in Brindmoor. Old love. Old wounds.",
        adult_mode=adult_mode,
        model_name=model_name
    )

    # 2. Create player
    player = create_player(world.id, player_name, character_sheet)

    # 3. Create tavern and lore
    create_ember_and_ash(world.id)

    # 4. Create Elena
    elena = create_elena(world.id, player.id)

    # 5. Create starting scene
    scene = create_starting_scene(world.id, player.id, elena.id)

    return world, player, elena, scene


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

import os


def get_world_db_path(world_id: str) -> str:
    return os.path.expanduser(f"~/.local/share/tavern_tales/{world_id}.db")
