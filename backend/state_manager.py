import json
import os
from typing import Dict, Any

STATE_FILE = os.path.join(os.path.dirname(__file__), "campaign_states.json")

def load_all_states() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_all_states(data: Dict[str, Any]):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_campaign_state(campaign_id: str) -> Dict[str, Any]:
    states = load_all_states()
    if campaign_id not in states:
        # Default starting state
        return {
            "player": {
                "health": 100,
                "gold": 50,
                "location": "The Ember & Ash Tavern"
            },
            "npcs": []
        }
    return states[campaign_id]

def update_campaign_state(campaign_id: str, new_extractions: Dict[str, Any]):
    """
    Merges newly extracted JSON data into the persistent campaign state.
    """
    states = load_all_states()
    current = get_campaign_state(campaign_id)
    
    # Update Player State
    if "player_state" in new_extractions and new_extractions["player_state"]:
        p_ext = new_extractions["player_state"]
        if "health_change" in p_ext and isinstance(p_ext["health_change"], (int, float)):
             current["player"]["health"] += p_ext["health_change"]
        if "gold_change" in p_ext and isinstance(p_ext["gold_change"], (int, float)):
             current["player"]["gold"] += p_ext["gold_change"]
        if "location" in p_ext and p_ext["location"]:
             current["player"]["location"] = p_ext["location"]
             
    # Update NPCs
    if "npc_updates" in new_extractions and isinstance(new_extractions["npc_updates"], list):
        for npc_update in new_extractions["npc_updates"]:
            name = npc_update.get("name")
            if not name: continue
            
            # Find existing NPC
            npc_record = next((n for n in current["npcs"] if n["name"] == name), None)
            if not npc_record:
                npc_record = {"name": name, "disposition": "Neutral", "secrets_known": []}
                current["npcs"].append(npc_record)
                
            if npc_update.get("disposition_change"):
                npc_record["disposition"] = npc_update["disposition_change"]
            
            secret = npc_update.get("secret_revealed")
            if secret and secret not in npc_record["secrets_known"]:
                npc_record["secrets_known"].append(secret)
                
    states[campaign_id] = current
    save_all_states(states)
