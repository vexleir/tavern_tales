"""
Tavern Tales — Gradio Web UI

A ChatGPT-style interface for the text RPG.
"""

import gradio as gr
import json
import uuid
import threading
import os
from typing import Optional

from models import init_db, get_connection, new_id, now_ts, CharacterSheet, World, Player, NPC, NPCRelationship, Scene, WorldEvent, WorldLore
from world import (
    create_lost_love_world, list_worlds, get_world, get_or_create_default_world,
    create_player, list_players, get_player, create_ember_and_ash, create_elena,
    create_starting_scene, add_lore, get_lore
)
from gm_engine import GMTurnProcessor


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_world: Optional[World] = None
        self.current_player: Optional[Player] = None
        self.current_scene: Optional[Scene] = None
        self.processor: Optional[GMTurnProcessor] = None
        self.elena_id: Optional[str] = None
        self._chat_history: list[dict] = []

    def reset(self):
        with self.lock:
            self.current_world = None
            self.current_player = None
            self.current_scene = None
            self.processor = None
            self.elena_id = None
            self._chat_history = []

    def chat_history(self) -> list[dict]:
        with self.lock:
            return list(self._chat_history)

    def add_to_history(self, role: str, content: str):
        with self.lock:
            self._chat_history.append({"role": role, "content": content})


state = AppState()


# ─────────────────────────────────────────────────────────────────────────────
# World / Login UI
# ─────────────────────────────────────────────────────────────────────────────

def load_worlds():
    """Load existing worlds for the world selector."""
    worlds = list_worlds()
    choices = [("— Select a world —", None)]
    choices += [(w.name, w.id) for w in worlds]
    return choices


def load_world_details(world_id: str) -> dict:
    """Return world metadata for the info panel."""
    w = get_world(world_id)
    if not w:
        return {"name": "—", "adult_mode": False, "model": ""}
    return {
        "name": w.name,
        "adult_mode": "Enabled" if w.adult_mode else "Disabled",
        "model": w.model_name
    }


def create_new_world(
    world_name: str,
    adult_mode: bool,
    model_name: str
) -> tuple[str, list]:
    """Create a new world and return (status_msg, updated_world_list)."""
    if not world_name.strip():
        return "World name cannot be empty.", load_worlds()

    world, player, elena, scene = create_lost_love_world(
        world_name=world_name,
        adult_mode=adult_mode,
        model_name=model_name or "qwen2.5-uncensored:14b"
    )

    state.current_world = world
    state.current_player = player
    state.current_scene = scene
    state.elena_id = elena.id

    # Initialize GM processor
    state.processor = GMTurnProcessor(world.id, player.id, world.model_name)

    return f"World '{world_name}' created and ready.", load_worlds()


def select_world_and_login(world_id: str, player_name: str, password: str) -> tuple[str, str]:
    """Select a world and log in as a player (password unused for now)."""
    if not world_id:
        return "Please select a world.", gr.update()

    if not player_name.strip():
        return "Please enter your character name.", gr.update()

    world = get_world(world_id)
    if not world:
        return f"World not found: {world_id}", gr.update()

    # Check if player exists
    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ? LIMIT 1", (player_name,))
    existing = cur.fetchone()
    conn.close()

    if existing:
        player = Player(
            id=existing["id"], world_id=existing["world_id"],
            name=existing["name"], character_sheet=existing["character_sheet"],
            created_at=existing["created_at"]
        )
        msg = f"Welcome back, {player.name}."
    else:
        # Create new character
        char_sheet = CharacterSheet(
            name=player_name,
            appearance="A weary traveler with dust on their boots.",
            backstory=f"{player_name} arrived in Brindmoor seeking answers — or perhaps escape.",
            personality="Cautious. Curious. Carrying secrets.",
            traits=["observant", "quiet"]
        )
        player = create_player(world_id, player_name, char_sheet)

        # Create Elena for new players
        elena = create_elena(world_id, player.id)
        create_starting_scene(world_id, player.id, elena.id)
        state.elena_id = elena.id

        msg = f"Character '{player_name}' created."

    state.current_world = world
    state.current_player = player

    # Load or create scene
    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM scenes WHERE world_id = ? AND player_id = ?
    """, (world_id, player.id))
    row = cur.fetchone()
    conn.close()

    if row:
        state.current_scene = Scene(
            id=row["id"], world_id=row["world_id"], player_id=row["player_id"],
            location=row["location"], present_npcs=row["present_npcs"],
            active_quests=row["active_quests"], turn=row["turn"],
            updated_at=row["updated_at"]
        )
    else:
        # Should not happen normally
        elena = create_elena(world_id, player.id)
        scene = create_starting_scene(world_id, player.id, elena.id)
        state.current_scene = scene
        state.elena_id = elena.id

    state.processor = GMTurnProcessor(world.id, player.id, world.model_name)
    state._chat_history = []

    return msg


def send_message(message: str) -> tuple[str, str]:
    """Process a player message and return (response, updated_history)."""
    if not state.processor:
        return "No active game. Please log in first.", ""

    if not message.strip():
        return "", ""

    state.add_to_history("player", message)

    # Process turn and stream response
    response_parts = []

    def collect(chunks):
        for chunk in chunks:
            response_parts.append(chunk)
            yield chunk

    try:
        # For Gradio, we need to collect the full response first
        full_response = ""
        for chunk in state.processor.process_turn(message):
            full_response += chunk

        state.add_to_history("assistant", full_response)

        # Build chat history for display
        history = state.chat_history()
        return "", history

    except Exception as e:
        error_msg = f"[Error: {e}]"
        return error_msg, state.chat_history()


def get_opening_narrative() -> str:
    """Get the opening narrative when a player first enters."""
    if not state.processor:
        return ""

    try:
        opening = ""
        for chunk in state.processor.get_opening_narrative():
            opening += chunk
        state.add_to_history("assistant", opening)
        return opening
    except Exception as e:
        return f"[Error loading scene: {e}]"


# ─────────────────────────────────────────────────────────────────────────────
# World State Viewer
# ─────────────────────────────────────────────────────────────────────────────

def get_npc_states() -> str:
    """Return formatted NPC states for the world viewer."""
    if not state.current_world or not state.current_player:
        return "No active world."

    conn = get_connection(state.current_world.id)
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM npcs WHERE world_id = ?
    """, (state.current_world.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "No NPCs in this world."

    lines = []
    for r in rows:
        npc = NPC(
            id=r["id"], world_id=r["world_id"], name=r["name"],
            personality=r["personality"], memory=r["memory"],
            current_state=r["current_state"]
        )
        state_npc = npc.get_state()

        # Get relationship for current player
        conn = get_connection(state.current_world.id)
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM npc_relationships WHERE player_id = ? AND npc_id = ?
        """, (state.current_player.id, npc.id))
        rel_row = cur.fetchone()
        conn.close()

        lines.append(f"**{npc.name}**")
        lines.append(f"  Mood: {state_npc.mood}")
        lines.append(f"  Activity: {state_npc.activity}")
        lines.append(f"  Location: {state_npc.location}")
        if rel_row:
            rel = NPCRelationship(
                id=rel_row["id"], player_id=rel_row["player_id"], npc_id=rel_row["npc_id"],
                love=rel_row["love"], trust=rel_row["trust"],
                fear=rel_row["fear"], anger=rel_row["anger"],
                history=rel_row["history"]
            )
            lines.append(f"  Love: {rel.love:.2f} | Trust: {rel.trust:.2f} | Fear: {rel.fear:.2f} | Anger: {rel.anger:.2f}")
            lines.append(f"  Relationship: {rel.mood_descriptor()}")
        mems = npc.get_memories_for_player(state.current_player.id)
        if mems:
            lines.append("  Memories:")
            for m in mems:
                lines.append(f"    - {m}")
        lines.append("")

    return "\n".join(lines) if lines else "No NPCs."


def get_world_events() -> str:
    """Return recent world events."""
    if not state.current_world:
        return "No active world."

    conn = get_connection(state.current_world.id)
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM world_events
        WHERE world_id = ?
        ORDER BY created_at DESC LIMIT 20
    """, (state.current_world.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "No world events yet."

    lines = []
    for r in rows:
        event = WorldEvent(
            id=r["id"], world_id=r["world_id"], description=r["description"],
            consequences=r["consequences"], turn=r["turn"],
            player_id=r["player_id"], created_at=r["created_at"]
        )
        lines.append(f"[Turn {event.turn}] {event.description}")

    return "\n".join(lines)


def get_memory_inspector() -> str:
    """Show the current working context."""
    if not state.processor:
        return "No active game."

    from memory import MemoryInjector

    world = state.current_world
    player = state.current_player
    scene = state.current_scene

    injector = MemoryInjector(world.id, player.id)

    present_npc_ids = scene.get_present_npc_ids()
    conn = get_connection(world.id)
    cur = conn.cursor()
    placeholders = ",".join("?" * len(present_npc_ids)) if present_npc_ids else "''"
    cur.execute(f"SELECT * FROM npcs WHERE id IN ({placeholders})", present_npc_ids)
    npc_rows = cur.fetchall()
    conn.close()

    present_npcs = [
        NPC(id=r["id"], world_id=r["world_id"], name=r["name"],
            personality=r["personality"], memory=r["memory"],
            current_state=r["current_state"])
        for r in npc_rows
    ]

    rel_ids = {npc.id for npc in present_npcs}
    conn = get_connection(world.id)
    cur = conn.cursor()
    rel_placeholders = ",".join("?" * len(rel_ids)) if rel_ids else "''"
    cur.execute(f"""
        SELECT * FROM npc_relationships WHERE player_id = ? AND npc_id IN ({rel_placeholders})
    """, (player.id, *rel_ids))
    rel_rows = cur.fetchall()
    conn.close()

    relationships = {
        r["npc_id"]: NPCRelationship(
            id=r["id"], player_id=r["player_id"], npc_id=r["npc_id"],
            love=r["love"], trust=r["trust"], fear=r["fear"],
            anger=r["anger"], history=r["history"]
        )
        for r in rel_rows
    }

    gm_instr = f"Location: {scene.location}. adult_mode={'ON' if world.adult_enabled else 'OFF'}."
    ctx = injector.build_working_context(
        scene=scene, player=player, present_npcs=present_npcs,
        relationships=relationships, gm_instructions=gm_instr,
        recent_messages=[]
    )

    sections = [
        "=== WORLD LORE ===",
        ctx.world_lore or "(none)",
        "",
        "=== SESSION SUMMARY ===",
        ctx.session_summary,
        "",
        "=== WORKING CONTEXT ===",
        ctx.working_scene,
        "",
        "=== PLAYER CHARACTER ===",
        ctx.player_character,
        "",
        "=== NPC MEMORIES ===",
        ctx.npc_memories,
    ]

    return "\n".join(sections)


def get_lore_browser(category: str) -> str:
    """Get lore entries filtered by category."""
    if not state.current_world:
        return "No active world."

    cat = category if category != "all" else None
    entries = get_lore(state.current_world.id, category=cat)

    if not entries:
        return "No lore entries."

    lines = []
    for e in entries:
        lines.append(f"[{e.category.upper()}] {e.content[:200]}...")
        lines.append(f"  Keywords: {e.keywords}")
        lines.append("")

    return "\n".join(lines)


def update_adult_mode(world_id: str, enabled: bool) -> str:
    """Toggle adult mode for a world."""
    if not world_id:
        return "No world selected."

    conn = get_connection(world_id)
    cur = conn.cursor()
    cur.execute("UPDATE worlds SET adult_mode = ? WHERE id = ?", (1 if enabled else 0, world_id))
    conn.commit()
    conn.close()

    if state.current_world and state.current_world.id == world_id:
        state.current_world.adult_mode = 1 if enabled else 0

    return f"Adult mode {'enabled' if enabled else 'disabled'}."


# ─────────────────────────────────────────────────────────────────────────────
# Gradio UI Layout
# ─────────────────────────────────────────────────────────────────────────────

def build_ui():
    theme = gr.themes.Soft(
        primary_hue="amber",
        secondary_hue="slate",
        neutral_hue="gray",
    )
    with gr.Blocks(title="Tavern Tales") as app:

        gr.Markdown("""
        # 🍺 Tavern Tales
        *A dark fantasy RPG, Game Mastered by AI*
        """)

        with gr.Tabs() as tabs_container:
            # ── Setup Tab ──────────────────────────────────────────────────
            with gr.Tab("⚙️ Setup", id="setup"):
                gr.Markdown("## World Setup")

                # Both dropdowns defined early so create_new_world can update both
                gr.Markdown("### Select or Create a World")
                with gr.Row():
                    world_selector = gr.Dropdown(
                        label="Select World",
                        choices=[],
                        value=None,
                        allow_custom_value=True
                    )
                    login_world = gr.Dropdown(
                        label="Or Join World",
                        choices=[],
                        allow_custom_value=True
                    )

                world_info = gr.JSON(label="World Details")

                def on_world_select(world_id):
                    if not world_id:
                        return {}
                    return load_world_details(world_id)

                world_selector.change(
                    on_world_select,
                    inputs=[world_selector],
                    outputs=[world_info]
                )

                gr.Markdown("---")
                gr.Markdown("### Create New World")

                with gr.Row():
                    with gr.Column(scale=1):
                        new_world_name = gr.Textbox(label="World Name", placeholder="Brindmoor — Lost Love")
                        new_model = gr.Textbox(
                            label="Ollama Model",
                            value="qwen2.5-uncensored:14b",
                            placeholder="qwen2.5-uncensored:14b"
                        )
                        new_adult_mode = gr.Checkbox(label="Adult Content Mode", value=False)

                    with gr.Column(scale=1):
                        create_btn = gr.Button("Create World", variant="primary")
                        create_status = gr.Textbox(label="Status")

                        def do_create(name, adult, model):
                            status, choices = create_new_world(name, adult, model)
                            # Return status and same choices for both dropdowns
                            return status, choices, choices

                        create_btn.click(
                            do_create,
                            inputs=[new_world_name, new_adult_mode, new_model],
                            outputs=[create_status, world_selector, login_world]
                        )

                gr.Markdown("---")
                gr.Markdown("## Join World")

                with gr.Row():
                    login_name = gr.Textbox(
                        label="Character Name",
                        placeholder="Your character's name"
                    )
                    login_password = gr.Textbox(
                        label="Password (optional)",
                        type="password",
                        placeholder="Ignored for now — future auth"
                    )
                    login_btn = gr.Button("Enter the Tavern", variant="primary")

                login_msg = gr.Textbox(label="Status", lines=1)

                login_btn.click(
                    select_world_and_login,
                    inputs=[login_world, login_name, login_password],
                    outputs=[login_msg]
                )

            # ── Game Tab ───────────────────────────────────────────────────
            with gr.Tab("🎭 The Game", id="game") as game_tab:
                gr.Markdown("### Your Story")

                with gr.Row():
                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(
                            label="Tavern Tales",
                            height=550,

                            avatar_images=("🧑", "🍺")
                        )

                        msg_input = gr.Textbox(
                            label="What do you do?",
                            placeholder="Describe your action or dialogue...",
                            lines=3
                        )

                        with gr.Row():
                            send_btn = gr.Button("Send", variant="primary")
                            clear_btn = gr.Button("Clear")
                            new_scene_btn = gr.Button("New Scene")

                        gr.Markdown("*GM responses stream in real-time. Your choices shape the world.*")

                    with gr.Column(scale=1):
                        gr.Markdown("### GM Settings")
                        adult_toggle = gr.Checkbox(
                            label="Adult Content",
                            value=False,
                            info="Allow mature romantic content"
                        )
                        adult_status = gr.Textbox(
                            label="Status",
                            lines=1
                        )

                        def toggle_adult(enabled):
                            if state.current_world:
                                return update_adult_mode(state.current_world.id, enabled)
                            return "No active world."

                        adult_toggle.change(
                            toggle_adult,
                            inputs=[adult_toggle],
                            outputs=[adult_status]
                        )

                        gr.Markdown("### Scene Info")
                        scene_info = gr.JSON(label="Current Scene")

                        def update_scene_info():
                            if state.current_scene and state.current_world:
                                return {
                                    "location": state.current_scene.location,
                                    "turn": state.current_scene.turn,
                                    "world": state.current_world.name
                                }
                            return {}

                        game_tab.select(
                            update_scene_info,
                            outputs=[scene_info]
                        )

                        gr.Markdown("### Openings")
                        open_btn = gr.Button("Get Opening Narrative", variant="secondary")
                        open_output = gr.Textbox(label="Opening", lines=5)

                        open_btn.click(
                            get_opening_narrative,
                            outputs=[open_output]
                        )

                def handle_send(message, history):
                    """Gradio Chatbot callback — returns (response, history)."""
                    if not message.strip():
                        return "", history

                    history = history or []
                    history.append({"role": "user", "content": message})

                    if not state.processor:
                        assistant_msg = "No active game. Please log in via the Setup tab."
                        history.append({"role": "assistant", "content": assistant_msg})
                        return "", history

                    try:
                        full_response = ""
                        for chunk in state.processor.process_turn(message):
                            full_response += chunk

                        state.add_to_history("player", message)
                        state.add_to_history("assistant", full_response)
                        history.append({"role": "assistant", "content": full_response})
                        return "", history

                    except Exception as e:
                        error_msg = f"[Error: {e}]"
                        history.append({"role": "assistant", "content": error_msg})
                        return "", history

                def clear_history():
                    state._chat_history = []
                    return None, []

                send_btn.click(
                    handle_send,
                    inputs=[msg_input, chatbot],
                    outputs=[msg_input, chatbot]
                )

                msg_input.submit(
                    handle_send,
                    inputs=[msg_input, chatbot],
                    outputs=[msg_input, chatbot]
                )

                clear_btn.click(
                    clear_history,
                    outputs=[chatbot, msg_input]
                )

                def handle_new_scene():
                    """Reset the scene and return opening narrative."""
                    if not state.current_world or not state.current_player:
                        return "", "No active game."

                    # Reload scene
                    conn = get_connection(state.current_world.id)
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT * FROM scenes WHERE world_id = ? AND player_id = ?
                    """, (state.current_world.id, state.current_player.id))
                    row = cur.fetchone()
                    conn.close()

                    if row:
                        state.current_scene = Scene(
                            id=row["id"], world_id=row["world_id"], player_id=row["player_id"],
                            location=row["location"], present_npcs=row["present_npcs"],
                            active_quests=row["active_quests"], turn=row["turn"],
                            updated_at=row["updated_at"]
                        )

                    state.processor = GMTurnProcessor(
                        state.current_world.id, state.current_player.id,
                        state.current_world.model_name
                    )
                    state._chat_history = []

                    opening = ""
                    for chunk in state.processor.get_opening_narrative():
                        opening += chunk

                    return "", [("assistant", opening)]

                new_scene_btn.click(
                    handle_new_scene,
                    outputs=[msg_input, chatbot]
                )

            # ── World State Tab ─────────────────────────────────────────────
            with gr.Tab("🗺️ World State"):
                gr.Markdown("## World State Viewer")

                with gr.Row():
                    with gr.Tab("NPCs"):
                        npc_viewer = gr.Markdown(value=get_npc_states)
                        refresh_npcs = gr.Button("Refresh NPCs")
                        refresh_npcs.click(get_npc_states, outputs=[npc_viewer])

                    with gr.Tab("Events"):
                        events_viewer = gr.Markdown(value=get_world_events)
                        refresh_events = gr.Button("Refresh Events")
                        refresh_events.click(get_world_events, outputs=[events_viewer])

                    with gr.Tab("Lore"):
                        lore_category = gr.Dropdown(
                            label="Category",
                            choices=["all", "history", "faction", "location", "quest"],
                            value="all"
                        )
                        lore_viewer = gr.Markdown(value=get_lore_browser("all"))
                        lore_category.change(
                            lambda c: get_lore_browser(c),
                            inputs=[lore_category],
                            outputs=[lore_viewer]
                        )
                        refresh_lore = gr.Button("Refresh Lore")
                        refresh_lore.click(
                            lambda c: get_lore_browser(c),
                            inputs=[lore_category],
                            outputs=[lore_viewer]
                        )

            # ── Memory Inspector Tab ────────────────────────────────────────
            with gr.Tab("🧠 Memory"):
                gr.Markdown("## Memory Inspector")
                gr.Markdown("*Current working context sent to the GM each turn*")

                memory_viewer = gr.Markdown(value=get_memory_inspector)
                refresh_memory = gr.Button("Refresh Memory")
                refresh_memory.click(get_memory_inspector, outputs=[memory_viewer])

                gr.Markdown("""
                **Three-Tier Memory System:**
                - **Working Context**: Current scene, present NPCs, recent exchanges (~2048 tokens)
                - **Session Summary**: Compressed narrative of this session (refreshes every 20 turns)
                - **World Lore**: Persistent NPC memories, world history, quest flags
                """)

    return app


def main():
    app = build_ui()
    app.launch(
        server_port=7860,
        server_name="0.0.0.0",
        share=False,
    )


if __name__ == "__main__":
    main()
