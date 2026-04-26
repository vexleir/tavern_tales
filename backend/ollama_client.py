"""
Streaming Ollama chat client.

Emits a stream of StreamEvent dicts — callers route tokens to the frontend and
handle errors via a distinguished channel so error messages never leak into the
narrative buffer.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator

import httpx

from schema import SamplingOverrides

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"

# Defaults tuned to prevent runaway repetition. repeat_penalty 1.15 is well above
# the 1.05 that caused the original `…………` tail; min_p adds a tail-trim floor.
DEFAULT_SAMPLING: dict[str, Any] = {
    "temperature": 0.8,
    "repeat_penalty": 1.15,
    "top_p": 0.9,
    "top_k": 40,
    "min_p": 0.05,
    "num_predict": 1024,
    "stop": ["\nUser:", "\nPlayer:", "User:", "[END]"],
}


def _build_options(overrides: SamplingOverrides | None) -> dict[str, Any]:
    opts = dict(DEFAULT_SAMPLING)
    if overrides is None:
        return opts
    for field in ("temperature", "repeat_penalty", "top_p", "top_k", "min_p", "num_predict"):
        val = getattr(overrides, field, None)
        if val is not None:
            opts[field] = val
    return opts


async def stream_chat(
    messages: list[dict[str, str]],
    model: str,
    overrides: SamplingOverrides | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream a chat completion from Ollama.

    Yields events of the form:
        {"type": "token", "data": "..."}        — narrative token
        {"type": "error", "data": "..."}        — transport / connection error
        {"type": "done", "stop_reason": "...", "prompt_eval_count": int, "eval_count": int}
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": _build_options(overrides),
    }

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", OLLAMA_URL, json=payload, timeout=120.0) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    yield {
                        "type": "error",
                        "data": f"Ollama returned HTTP {response.status_code}: {body[:500]}",
                    }
                    return

                last_done_meta: dict[str, Any] = {}
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("done"):
                        last_done_meta = {
                            "stop_reason": data.get("done_reason", "stop"),
                            "prompt_eval_count": data.get("prompt_eval_count", 0),
                            "eval_count": data.get("eval_count", 0),
                        }
                        break

                    msg = data.get("message") or {}
                    content = msg.get("content")
                    if content:
                        yield {"type": "token", "data": content}

                yield {"type": "done", **last_done_meta}

    except httpx.ConnectError as e:
        log.error("Ollama connect error: %s", e)
        yield {
            "type": "error",
            "data": "Could not connect to local Ollama. Ensure Ollama is running on localhost:11434.",
        }
    except httpx.ReadTimeout as e:
        log.error("Ollama read timeout: %s", e)
        yield {"type": "error", "data": "Ollama response timed out."}
    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected Ollama streaming failure")
        yield {"type": "error", "data": f"Unexpected streaming error: {e}"}


_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def _coerce_json(content: str) -> tuple[dict[str, Any] | None, str | None]:
    """Try to parse `content` as JSON, with light tolerance for common LLM quirks
    (markdown code fences, leading/trailing prose). Returns (result, error)."""
    raw = content.strip()
    if not raw:
        return None, "empty content"

    fenced = _JSON_FENCE_RE.match(raw)
    if fenced:
        raw = fenced.group(1).strip()

    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        # Last-ditch: extract the first {...} block.
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1]), None
            except json.JSONDecodeError as e2:
                snippet = raw[:200].replace("\n", " ")
                return None, f"JSON parse failure after fence/brace recovery: {e2} (raw starts: {snippet!r})"
        snippet = raw[:200].replace("\n", " ")
        return None, f"output is not valid JSON (raw starts: {snippet!r})"


async def complete_json_detail(
    messages: list[dict[str, str]],
    model: str,
    timeout: float = 60.0,
    num_predict: int = 768,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Non-streaming JSON-mode completion. Returns (parsed_dict, None) on success,
    (None, error_message) on any failure — caller decides whether to log/surface.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(OLLAMA_URL, json=payload, timeout=timeout)
            if res.status_code >= 400:
                body = res.text[:300]
                return None, f"Ollama HTTP {res.status_code} from {model}: {body}"
            data = res.json()
            content = data.get("message", {}).get("content", "")
            result, parse_err = _coerce_json(content)
            if result is not None:
                return result, None
            log.warning("complete_json: %s from %s", parse_err, model)
            return None, parse_err
    except httpx.ConnectError:
        return None, "could not connect to Ollama on localhost:11434 — is it running?"
    except httpx.ReadTimeout:
        return None, f"Ollama timed out after {timeout:.0f}s on {model}"
    except Exception as e:  # noqa: BLE001
        log.exception("complete_json: unexpected failure from %s", model)
        return None, f"{type(e).__name__}: {e}"


async def complete_json(
    messages: list[dict[str, str]],
    model: str,
    timeout: float = 60.0,
    num_predict: int = 768,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper — returns just the dict, or None on any failure."""
    result, _ = await complete_json_detail(messages, model, timeout=timeout, num_predict=num_predict)
    return result


async def complete_text(
    messages: list[dict[str, str]],
    model: str,
    timeout: float = 60.0,
    num_predict: int = 512,
) -> str | None:
    """Non-streaming text completion for utility tasks (summarization)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": num_predict},
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(OLLAMA_URL, json=payload, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            return data.get("message", {}).get("content")
    except Exception as e:
        log.warning("complete_text: call to %s failed: %s", model, e)
        return None
