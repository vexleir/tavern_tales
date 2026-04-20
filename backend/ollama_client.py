import httpx
import json
from typing import AsyncGenerator, List, Dict, Any

OLLAMA_URL = "http://localhost:11434/api/chat"

async def stream_chat(messages: List[Dict[str, str]], model: str = "llama3") -> AsyncGenerator[str, None]:
    """Streams chat response from local Ollama via httpx."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0.8
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("POST", OLLAMA_URL, json=payload, timeout=60.0) as response:
                response.raise_for_status()
                async for chunk in response.aiter_lines():
                    if chunk:
                        try:
                            # Ollama streams one JSON object per line by default when stream=True
                            data = json.loads(chunk)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            yield "[[Error: Could not connect to local Ollama. Ensure Ollama is running.]]"
