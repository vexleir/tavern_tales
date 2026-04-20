# Tavern Tales 🍺

*A dark fantasy text RPG, Game Mastered by AI.*

Tavern Tales is a multiplayer text-based RPG where an LLM acts as Game Master, running a persistent world with deep memory and consequence. Players create characters, explore locations, and interact with NPCs whose responses, moods, and memories evolve based on what you do — and what you've done before.

---

## Features

- **LLM Game Master** — Runs on your local machine via Ollama. No cloud. No subscription.
- **Persistent World** — SQLite-backed. NPCs remember you. Grudges last. Kindness echoes.
- **Three-Tier Memory** — Working context (per turn), session summaries (every 20 turns), and persistent world lore.
- **Multiplayer-Ready** — Shared world state with per-player scenes. Async turn-based.
- **Adult Content Toggle** — Per-world setting. When enabled, the GM handles mature romantic scenarios tastefully with fade-to-black for explicit content.
- **Built-in Scenario** — "Lost Love" puts you face-to-face with Elena, a woman you abandoned three years ago, now found in a tavern in Brindmoor.
- **Gradio Web UI** — ChatGPT-style interface, runs at `http://localhost:7860`.

---

## Prerequisites

- **Python 3.11+**
- **Ollama** installed and running (`ollama serve`)
- **qwen2.5-uncensored:14b** model pulled (or another uncensored model)

### Install Ollama

```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Then pull the model
ollama pull qwen2.5-uncensored:14b
```

### Or use an alternative model

Any Ollama model works. Recommended for adult scenarios: `qwen2.5-uncensored:14b` or `llama3.1-uncensored:8b`.

---

## Quick Start

### 1. Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

Or install manually:

```bash
pip install gradio ollama
ollama pull qwen2.5-uncensored:14b
```

### 2. Start the server

```bash
cd ~/projects/tavern_tales
python3 server.py
```

### 3. Open in browser

```
http://localhost:7860
```

---

## How to Play

### Setup Tab
- **Select an existing world** from the dropdown, or create a new one
- **Join a world** with your character name
- New characters are auto-created if you haven't played before

### Game Tab
- The GM narrates the scene. Read what happens.
- Type your action or dialogue in the input box and press **Send** or hit Enter.
- Responses stream in real-time.
- Toggle **Adult Content** in the settings panel (per-world, requires logout/login to take effect on new scenes).

### World State Tab
- See all NPCs, their current moods, and relationship scores
- Browse world events and lore entries
- Useful for understanding what's happening in the world

### Memory Tab
- Inspect the exact context being sent to the GM each turn
- Useful for debugging or understanding GM behavior

---

## Project Structure

```
tavern_tales/
├── SPEC.md          # System specification and design document
├── models.py        # Data models (Player, NPC, Scene, Message, etc.)
├── memory.py        # Three-tier memory system
├── gm_engine.py     # GM system prompt, Ollama client, turn processor
├── world.py         # World initialization, Elena NPC, tavern setup
├── web.py           # Gradio web UI
├── server.py        # Entry point (runs on port 7860)
├── setup.sh         # Setup script
├── test.py          # Test suite
└── README.md        # This file
```

---

## The Lost Love Scenario

When you create a new world, you're dropped into **The Ember & Ash** — a tavern in Brindmoor, a trade city known for loose morals and loose tongues.

**Elena** is there. She was the person you loved three years ago in Thornwick. You left without a word. She spent months wondering what she did wrong.

She's guarded now. She's not the same person. But she's here — and she's watching the door.

Your relationship with Elena is tracked on four scales:
- **Love** — Does she still feel something? (-1.0 to 1.0)
- **Trust** — Does she believe you won't leave again? (-1.0 to 1.0)
- **Fear** — Is she scared of being hurt again? (0.0 to 1.0)
- **Anger** — Does she resent you? (0.0 to 1.0)

Actions have weight. Lies erode trust. Honesty builds it. There are things she wants to know that you've never told her.

---

## Database Location

All world state is stored in SQLite:

```
~/.local/share/tavern_tales/<world_id>.db
```

Each world gets its own database file. There's one database per world, shared by all players in that world.

---

## Git Setup

```bash
cd ~/projects/tavern_tales
git init
git add .
git commit -m "Initial commit: Tavern Tales RPG"

# Add your remote (replace with your repo URL)
git remote add origin https://github.com/yourusername/tavern-tales.git
git branch -M main
git push -u origin main
```

---

## Troubleshooting

### Ollama not running
```bash
ollama serve
# Keep this running in a separate terminal
```

### Model not found
```bash
ollama pull qwen2.5-uncensored:14b
```

### Port 7860 in use
Edit `server.py` and change `server_port=7860` to another port.

### Adult mode toggle not working
The toggle updates the database but doesn't affect the current session. Log out and back in, or start a new scene.

---

## Extending Tavern Tales

### Add new NPCs
See `world.py` — `create_elena()` as a template. Create a new function following the same pattern:
```python
def create_tavern_barkeep(world_id: str) -> NPC:
    personality = NPCPersonality(traits=["...", "..."], ...)
    npc = NPC(id=new_id(), world_id=world_id, name="...", ...)
    # save to DB
    return npc
```

### Add new world lore
```python
from world import add_lore
add_lore(world_id, category="history", keywords="keyword1 keyword2", content="...")
```

### Change the model
Edit the `model_name` field when creating a world, or update `new_model` in the web UI.

---

*Every story begins with a door. Yours opens into The Ember & Ash.*
