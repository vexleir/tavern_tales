# Tavern Tales Reborn

A local, private AI-driven text RPG. You write the actions; a locally-running language model writes the story. Everything runs on your own machine — no cloud, no subscriptions.

---

## Prerequisites

You need three things installed before you can run the game:

### 1. Ollama (the AI engine)

Ollama runs language models locally on your PC.

- Download: https://ollama.com/download
- Install it and make sure the Ollama service is running (it starts automatically on most systems).
- Verify it works by opening a terminal and running:
  ```
  ollama list
  ```
  If you see a list (even an empty one), Ollama is running.

### 2. Pull at least one language model

Ollama downloads models on demand. You need at least one model to use as the **Narrator** (the AI that writes your story). The same model can also serve as the **Utility** model.

Recommended models (pick at least one):

| Model | Command | Notes |
|---|---|---|
| Llama 3.1 8B Instruct | `ollama pull llama3.1:8b-instruct` | Best all-around choice for narrative quality |
| Qwen 2.5 7B | `ollama pull qwen2.5:7b` | Good alternative, fast on lower-end hardware |
| Mistral 7B | `ollama pull mistral` | Lightweight option |

Run the pull command in any terminal. The download may take a few minutes depending on your connection.

> **Tip:** If you have a more powerful PC (16 GB+ VRAM), try `ollama pull llama3.1:70b-instruct` for significantly richer narration.

### 3. Python 3.10 or newer

The backend is a Python server.

- Download: https://www.python.org/downloads/
- During installation on Windows, check **"Add Python to PATH"**.
- Verify: `python --version` (should show 3.10 or higher)

### 4. Node.js 18 or newer

The frontend is a React app built with Vite.

- Download: https://nodejs.org/en/download (choose the LTS version)
- Verify: `node --version` (should show v18 or higher)

---

## Installation

Clone or download this repository, then open a terminal in the project folder.

**Install backend dependencies:**
```bash
cd backend
pip install -r requirements.txt
cd ..
```

**Install frontend dependencies:**
```bash
cd frontend
npm install
cd ..
```

---

## Starting the Game

You need two terminal windows running at the same time.

**Terminal 1 — Backend server:**
```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Then open your browser at: **http://localhost:5173**

> **Windows shortcut:** Double-click `start_all.bat` in the project root to launch both servers at once.

---

## Quick Start: Your First Campaign

1. Open http://localhost:5173
2. Click **"+ Forge New World"**
3. **Models section** — The Narrator Model dropdown should already show your installed model. Leave Utility Model on auto (it will pick the right one automatically).
4. **Auto-Forge World** — Type a short world description (e.g. `"A fog-covered port city ruled by a merchant thieves' guild"`) and click **Generate World**. The AI will fill in the setting, NPCs, and starting scene for you. You can also fill these in manually.
5. **The Protagonist** — Give your character a name. Everything else is optional.
6. Click **Begin Adventure** at the bottom of the page.
7. The opening scene will appear. Type your first action in the box at the bottom and press **Enter** or click **Commit**.

---

## How to Play

### The basics

- **Type what your character does** in the input box at the bottom. Write in first or third person — the AI adapts.
  - Example: `"I approach the hooded figure at the bar and ask what they're drinking."`
- Press **Enter** or click **Commit** to send your action.
- The GM (AI) will respond with the next beat of the story.
- **Shift+Enter** adds a line break inside the input box without sending.

### When the AI rolls dice

If your action involves risk (attacking, sneaking, persuading, etc.), the game runs a d20 check automatically. The result appears as a badge in the header and shapes the GM's response — a critical success opens possibilities a partial success wouldn't.

You don't need to declare "I want to roll." Just describe the action and the system handles it.

### Post-turn buttons

| Button | What it does |
|---|---|
| **↻ Reroll** | Discards the GM's last response and generates a fresh one |
| **→ Continue** | Asks the GM to continue narrating without a new player action |

### Quick Actions bar

Click the **⚡ Actions** toggle above the input box to open a row of shortcut buttons. Each one pre-fills the input with an action template (Attack, Persuade, Search, Sneak, Rest, Roll). Edit the template and send it — or just use it as inspiration.

---

## Director Mode

Director Mode is a mid-game editor. Toggle it with the **Director Mode** button in the top-right of the story screen.

While active you can:

- **Edit protagonist stats, location, appearance, and inventory** directly in the sidebar.
- **Add, edit, or remove NPCs** and change their dispositions on the fly.
- **Edit the Lorebook** — add or remove world rules mid-story.
- **Undo** the last director edit (Ctrl+Z or the Undo button).
- **Fork Timeline** — duplicate the campaign at this exact moment and explore an alternate path without losing the original.
- **Inspect Prompt** — see the full system prompt being sent to the AI each turn (useful for debugging).
- **Debug Bundle** — export a full JSON snapshot of campaign state and memories.
- **Delete individual turns** — hover a message and click the red Delete button that appears.

---

## Glossary

| Term | Meaning |
|---|---|
| **Narrator Model (GM)** | The AI model that generates story narration and NPC dialogue. Larger = better quality, slower speed. |
| **Utility Model** | A smaller model used for background tasks: summarizing long sessions, extracting state changes (stat updates, NPC changes) from the GM's responses. Defaults to the best available small model automatically. |
| **Director Mode** | An in-session editor that lets you change world state, NPCs, and stats without ending the story. |
| **Lorebook** | A set of absolute rules the GM must always follow (e.g. "Magic requires a verbal component"). Included in every prompt. |
| **Cast** | Pre-defined NPCs with dispositions, secrets, and appearance. Each NPC's full profile is available to the GM every turn. |
| **Fork Timeline** | Duplicates the campaign at the current moment. You can explore "what if" paths without losing the original story. |
| **Preference Profiles** | An optional, consent-aware system for defining roleplay interests and boundaries. Profiles can seed campaign setup with tone and theme guidance. Fantasy preferences recorded here are not real-world consent. |
| **Fade to Black** | A preference setting that tells the GM to skip explicit content and cut to the aftermath instead. |
| **d20 Check** | An automatic dice roll triggered by risky player actions. The result (and your character's relevant stat) determines the outcome injected into the GM prompt. |

---

## Troubleshooting

**"No models found" or world generation fails with a 400 error**
- Make sure Ollama is running: open a terminal and type `ollama list`.
- Make sure you've pulled at least one model: `ollama pull llama3.1:8b-instruct`.

**The backend won't start**
- Make sure you're in the `backend/` folder and ran `pip install -r requirements.txt`.
- Check that port 8000 isn't already in use.

**The frontend shows a blank page or API errors**
- Make sure the backend is running on port 8000 before opening the frontend.
- Check the browser console (F12) for specific error messages.

**The GM ignores my protagonist's details**
- Make sure the Appearance and Details fields are filled in on the Forge Your World screen. The GM re-reads these every turn from the sidebar — edit them in Director Mode if needed.

**Running the test suite**
```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```
54 tests, all mocked (no live Ollama required).
