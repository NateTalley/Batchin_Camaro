"""Ollama agent using Ollama's native /api/chat tool-calling format."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from agent_base import SYSTEM_PROMPT, TOOL_DEFINITIONS, BaseArchiveAgent  # noqa: F401

__all__ = ["OllamaAgent", "SYSTEM_PROMPT", "TOOL_DEFINITIONS"]


class OllamaAgent(BaseArchiveAgent):
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.1",
        on_tool_call: Callable[[str, dict], Any] | None = None,
        max_rounds: int = 8,
    ):
        super().__init__(model=model, on_tool_call=on_tool_call, max_rounds=max_rounds)
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[str]:
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def _chat(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach Ollama at {self.base_url}: {e.reason}") from e

    def _extract_message(self, data: dict) -> dict:
        return data.get("message") or {}

    def _tool_message(self, tool_call: dict, name: str, result: str) -> dict:
        return {"role": "tool", "content": result, "tool_name": name}

    def _chat_stream(self, messages: list[dict], on_delta: Callable[[str], None]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": True,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    m = chunk.get("message") or {}
                    text = m.get("content")
                    if text:
                        content_parts.append(text)
                        on_delta(text)
                    if m.get("tool_calls"):
                        tool_calls.extend(m["tool_calls"])
                    if chunk.get("done"):
                        break
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach Ollama at {self.base_url}: {e.reason}") from e

        msg: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg
