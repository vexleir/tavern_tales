from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict
from ollama_client import stream_chat
from memory import retrieve_relevant_memories, add_memory
from extraction import extract_state_changes
from state_manager import update_campaign_state, get_campaign_state
import asyncio

app = FastAPI(title="Tavern Tales Reborn GM Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    model: str = "llama3"
    campaign_id: str = "default_campaign"
    turn: int = 1

async def save_memory_background(campaign_id: str, turn: int, user_action: str, gm_response: str, model: str):
    """
    Background task to embed the interaction into the memory database and extract state.
    """
    content = f"Turn {turn}: Player acted: {user_action}\nGM narrated: {gm_response}"
    add_memory(campaign_id, "System", content, turn)
    print(f"[*] Saved vector memory for turn {turn}")
    
    # Extract state changes
    state = await extract_state_changes(user_action, gm_response, model)
    print(f"[*] Extracted state: {state}")
    
    # Update global state
    update_campaign_state(campaign_id, state)

async def stream_and_intercept(messages: List[Dict[str, str]], req: ChatRequest, background_tasks: BackgroundTasks):
    """
    Streams the response and also buffers it so we can save it to the memory DB afterwards.
    """
    full_response = []
    
    # Extract the user's latest action for memory saving
    user_action = "Unknown"
    for msg in reversed(req.messages):
        if msg["role"] == "user":
            user_action = msg["content"]
            break

    async for chunk in stream_chat(messages, model=req.model):
        full_response.append(chunk)
        yield chunk
        
    final_gm_text = "".join(full_response)
    
    # Fire off background task to save memory
    background_tasks.add_task(save_memory_background, req.campaign_id, req.turn, user_action, final_gm_text, req.model)

@app.get("/")
def read_root():
    return {"status": "Tavern Tales backend is running."}

@app.get("/api/state/{campaign_id}")
def get_state(campaign_id: str):
    """Retrieves the current persistent state for a campaign."""
    return get_campaign_state(campaign_id)

from state_manager import load_all_states, save_all_states
from typing import Any

class InitCampaignRequest(BaseModel):
    campaign_id: str
    player_name: str
    starting_health: int
    starting_gold: int
    starting_location: str
    npcs: List[Dict[str, Any]]

@app.post("/api/campaign/init")
def init_campaign(req: InitCampaignRequest):
    """Initializes a new campaign state with pre-defined characters/cast."""
    initial_state = {
        "player": {
            "name": req.player_name,
            "health": req.starting_health,
            "gold": req.starting_gold,
            "location": req.starting_location
        },
        "npcs": req.npcs
    }
    all_states = load_all_states()
    all_states[req.campaign_id] = initial_state
    save_all_states(all_states)
    
    # Optional: We could also inject these pre-defined NPC lore facts into Vector DB here.
    return {"status": "success"}

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, background_tasks: BackgroundTasks):
    """
    Expects messages array containing system prompt and chat history.
    """
    # 1. Identify the user query
    user_query = ""
    for msg in reversed(req.messages):
        if msg["role"] == "user":
            user_query = msg["content"]
            break
            
    # 2. Retrieve semantic memories based on the user's latest query
    memories = []
    if user_query:
        memories = retrieve_relevant_memories(req.campaign_id, user_query, n_results=3)
        
    # 3. Inject memories into the system prompt (which should be the first message)
    if memories and len(req.messages) > 0 and req.messages[0]["role"] == "system":
        memory_block = "\n\n[RELEVANT PAST MEMORIES/LORE]\n" + "\n".join(memories) + "\n[END MEMORIES]"
        req.messages[0]["content"] += memory_block

    return StreamingResponse(
        stream_and_intercept(req.messages, req, background_tasks),
        media_type="text/event-stream"
    )
