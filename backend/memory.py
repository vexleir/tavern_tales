import os
import chromadb
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

# Initialize ChromaDB client
client = chromadb.PersistentClient(path=DB_PATH)

# Chroma uses a default embedding function (all-MiniLM-L6-v2) automatically if none provided.
collection_name = "tavern_tales_memories"
try:
    collection = client.get_collection(name=collection_name)
except Exception:
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"} # Good for semantic similarity
    )

def add_memory(campaign_id: str, character: str, content: str, turn: int):
    """
    Stores a piece of memory linked to a specific campaign and turn.
    """
    # Generating a deterministic ID
    import uuid
    mem_id = f"{campaign_id}_{turn}_{str(uuid.uuid4())[:8]}"
    
    collection.add(
        documents=[content],
        metadatas=[{"campaign": campaign_id, "character": character, "turn": turn}],
        ids=[mem_id]
    )
    return mem_id

def retrieve_relevant_memories(campaign_id: str, query: str, n_results: int = 3) -> List[str]:
    """
    Retrieves the most semantically relevant memories based on the user's action query.
    """
    if collection.count() == 0:
        return []
        
    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            where={"campaign": campaign_id}
        )
        
        if not results or not results['documents'] or len(results['documents'][0]) == 0:
            return []
            
        return results['documents'][0] # Returns list of retrieved text strings
    except Exception as e:
        print(f"Vector search failed: {e}")
        return []
