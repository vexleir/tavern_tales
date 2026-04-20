import httpx
import json
from typing import Dict, Any

OLLAMA_URL = "http://localhost:11434/api/generate"

async def extract_state_changes(user_action: str, gm_response: str, model: str = "llama3") -> Dict[str, Any]:
    """
    Asks Ollama to extract state changes and relationship updates into JSON format.
    """
    prompt = f"""
    Analyze the following roleplay exchange and extract any changes to the player's state (health, gold, location) 
    and any changes to NPC relationships or revealed secrets.

    Return the result strictly as a JSON object matching this schema:
    {{
        "player_state": {{"health_change": <int>, "gold_change": <int>, "location": "<str>"}},
        "npc_updates": [ {{"name": "<str>", "disposition_change": "<str>", "secret_revealed": "<str or null>"}} ]
    }}
    
    If there are no changes, return the defaults or empty arrays.

    Player Action: {user_action}
    GM Narrative: {gm_response}
    """
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json" # Forces JSON schema output in Ollama
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(OLLAMA_URL, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            if "response" in data:
                return json.loads(data["response"])
        except Exception as e:
            print(f"Extraction failed: {e}")
            
    return {}
