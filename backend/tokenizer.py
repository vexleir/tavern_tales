"""
Lightweight token counting.

Heuristic-based (~4 chars/token) by default. If tiktoken happens to be installed
we use it opportunistically for better accuracy. No required heavy deps — tiktoken
builds painfully on Windows without a compiler.
"""

from __future__ import annotations

from typing import Iterable

_TIKTOKEN_ENCODER = None
try:
    import tiktoken  # type: ignore

    _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover — optional dep
    _TIKTOKEN_ENCODER = None


# Per-model context windows. Conservative defaults; main.py / prompt_builder.py
# looks up by lowercased model name with substring fallback.
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "llama3": 8192,
    "llama3:8b": 8192,
    "llama3.1": 131072,
    "llama3.1:8b": 131072,
    "llama3.1:8b-instruct": 131072,
    "llama3.2": 131072,
    "llama3.2:3b": 131072,
    "qwen2.5": 32768,
    "qwen2.5:7b": 32768,
    "qwen2.5:7b-instruct": 32768,
    "mistral": 32768,
    "mistral-nemo": 128000,
    "fluffy/l3-8b-stheno": 8192,
    "stheno": 8192,
}


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _TIKTOKEN_ENCODER is not None:
        try:
            return len(_TIKTOKEN_ENCODER.encode(text))
        except Exception:
            pass
    # Heuristic: ~4 chars per token for English-ish text, with a small minimum.
    return max(1, (len(text) + 3) // 4)


def count_messages(messages: Iterable[dict]) -> int:
    """Count tokens across a list of {role, content} messages, accounting for per-message framing."""
    total = 0
    for m in messages:
        content = m.get("content", "") or ""
        role = m.get("role", "") or ""
        # +4 is a rough framing overhead (role tag, delimiters) matching common chat-template costs.
        total += count_tokens(content) + count_tokens(role) + 4
    return total


def lookup_context_window(model: str) -> int:
    """Best-effort lookup of a model's context window. Defaults to 8192."""
    if not model:
        return 8192
    name = model.lower()
    if name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[name]
    # Substring fallback — match the longest known prefix.
    best = (0, 8192)
    for key, ctx in MODEL_CONTEXT_WINDOWS.items():
        if key in name and len(key) > best[0]:
            best = (len(key), ctx)
    return best[1]
