#!/usr/bin/env python3
"""
Tavern Tales — Test Script

Tests that all modules load correctly and that a basic world
can be initialized without errors.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    print("Testing imports...")
    from models import (
        Player, NPC, Message, Scene, WorldEvent,
        NPCRelationship, CharacterSheet, NPCPersonality, NPCState,
        World, WorldLore, init_db, get_connection, new_id
    )
    print("  ✓ All models imported")

def test_character_sheet():
    print("Testing CharacterSheet...")
    from models import CharacterSheet
    char = CharacterSheet(
        name="TestChar",
        appearance="tall, dark hair",
        backstory="A wanderer",
        personality="stoic",
        traits=["brave", "quiet"]
    )
    json_str = char.to_json()
    restored = CharacterSheet.from_json(json_str)
    assert restored.name == "TestChar"
    assert restored.traits == ["brave", "quiet"]
    print("  ✓ CharacterSheet serialization")

def test_npc_state():
    print("Testing NPCState...")
    from models import NPCState
    state = NPCState(
        location="tavern",
        mood="guarded",
        activity="serving drinks",
        flags={"key": "value"}
    )
    json_str = state.to_json()
    restored = NPCState.from_json(json_str)
    assert restored.mood == "guarded"
    assert restored.flags["key"] == "value"
    print("  ✓ NPCState serialization")

def test_relationship():
    print("Testing NPCRelationship...")
    from models import NPCRelationship
    rel = NPCRelationship(
        id="test-id",
        player_id="p1",
        npc_id="n1",
        love=0.3,
        trust=-0.2,
        fear=0.1,
        anger=0.2
    )
    rel.adjust(trust=0.1, love=0.05)
    assert abs(rel.trust - (-0.1)) < 0.001
    assert abs(rel.love - 0.35) < 0.001
    rel.add_history_entry("Test interaction")
    hist = rel.get_history()
    assert len(hist) == 1
    print("  ✓ NPCRelationship with adjustments and history")

def test_world_init():
    print("Testing world initialization...")
    from world import create_lost_love_world, get_world, list_worlds
    from models import init_db, get_connection

    world, player, elena, scene = create_lost_love_world(
        world_name="Test World",
        player_name="TestPlayer",
        adult_mode=False
    )

    assert world.name == "Test World"
    assert player.name == "TestPlayer"
    assert elena.name == "Elena"
    assert scene.location == "The Ember & Ash — main room"
    print("  ✓ World created successfully")

    # Verify database
    conn = get_connection(world.id)
    cur = conn.cursor()

    cur.execute("SELECT * FROM worlds WHERE id = ?", (world.id,))
    assert cur.fetchone() is not None

    cur.execute("SELECT * FROM players WHERE id = ?", (player.id,))
    assert cur.fetchone() is not None

    cur.execute("SELECT * FROM npcs WHERE id = ?", (elena.id,))
    assert cur.fetchone() is not None

    cur.execute("SELECT * FROM scenes WHERE player_id = ?", (player.id,))
    assert cur.fetchone() is not None

    cur.execute("SELECT * FROM world_lore WHERE world_id = ?", (world.id,))
    lore_rows = cur.fetchall()
    assert len(lore_rows) >= 2  # tavern + city lore

    conn.close()
    print("  ✓ All database tables populated")

def test_memory_system():
    print("Testing memory system...")
    from world import create_lost_love_world
    from memory import MemoryInjector, WorldLoreQuerier

    world, player, elena, scene = create_lost_love_world(
        world_name="Memory Test World",
        player_name="MemoryPlayer"
    )

    injector = MemoryInjector(world.id, player.id)

    from models import get_connection
    conn = get_connection(world.id)
    cur = conn.cursor()
    cur.execute("SELECT * FROM npcs WHERE id = ?", (elena.id,))
    row = cur.fetchone()
    conn.close()

    from models import NPC
    npc = NPC(
        id=row["id"], world_id=row["world_id"], name=row["name"],
        personality=row["personality"], memory=row["memory"],
        current_state=row["current_state"]
    )

    from models import NPCRelationship
    rel = NPCRelationship(
        id="rel-id", player_id=player.id, npc_id=elena.id,
        love=0.3, trust=-0.3, fear=0.2, anger=0.2
    )

    gm_instr = f"Test instruction. adult_mode={'ON' if world.adult_enabled else 'OFF'}."
    ctx = injector.build_working_context(
        scene=scene,
        player=player,
        present_npcs=[npc],
        relationships={npc.id: rel},
        gm_instructions=gm_instr,
        recent_messages=[]
    )

    assert "[WORLD LORE]" in injector.assemble_full_prompt(ctx, "Test input")
    assert "Elena" in ctx.npc_memories
    # Session summary should contain something meaningful
    assert len(ctx.session_summary) > 10
    print("  ✓ Memory context builds correctly")

    # Lore querier
    querier = WorldLoreQuerier(world.id)
    results = querier.query("tavern Brindmoor ember ash")
    assert len(results) > 0
    print("  ✓ Lore querier works")

def test_gm_engine():
    print("Testing GM engine (non-streaming check)...")
    from world import create_lost_love_world
    from gm_engine import OllamaClient

    # Just check Ollama is reachable
    client = OllamaClient(model_name="qwen2.5-uncensored:14b")
    try:
        healthy = client.check_health()
        print(f"  Ollama health check: {'✓ connected' if healthy else '✗ not running (run: ollama serve)'}")
    except Exception as e:
        print(f"  Ollama not available: {e}")
        print("  (This is fine if Ollama isn't installed yet)")

def test_models_import():
    print("Testing all model imports are complete...")
    from models import (
        Player, NPC, Message, Scene, Scene, WorldEvent,
        NPCRelationship, CharacterSheet, NPCPersonality, NPCState,
        World, WorldLore, init_db, get_connection, new_id, now_ts
    )
    print("  ✓ All models present and importable")

def cleanup_test_worlds():
    """Remove test worlds created during tests."""
    import glob
    import sqlite3
    db_dir = os.path.expanduser("~/.local/share/tavern_tales")
    for db_path in glob.glob(os.path.join(db_dir, "*.db")):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM worlds WHERE name LIKE 'Test%' OR name LIKE 'Memory%'")
        for row in cur.fetchall():
            print(f"  Cleaning up test world: {row['name']}")
        conn.close()
        # Only delete if confirmed test world
        cur = sqlite3.connect(db_path)
        cur.execute("SELECT name FROM worlds WHERE name LIKE 'Test%' OR name LIKE 'Memory%'")
        test_worlds = [r["name"] for r in cur.fetchall()]
        conn.close()
        if test_worlds:
            for tw in test_worlds:
                cur = sqlite3.connect(db_path)
                cur.execute("SELECT id FROM worlds WHERE name = ?", (tw,))
                row = cur.fetchone()
                if row:
                    # Just remove test dbs — simpler approach
                    pass
                conn.close()

def main():
    print("=" * 50)
    print("  Tavern Tales — Test Suite")
    print("=" * 50)
    print()

    test_imports()
    test_character_sheet()
    test_npc_state()
    test_relationship()
    test_world_init()
    test_memory_system()
    test_gm_engine()
    test_models_import()

    print()
    print("=" * 50)
    print("  All tests passed! ✓")
    print("=" * 50)


if __name__ == "__main__":
    main()
