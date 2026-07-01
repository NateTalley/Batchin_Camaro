"""OpenAI-compatible agent using the /v1/chat/completions tool-calling format.

Works with the OpenAI API and any server that speaks the same wire format:
LM Studio, llama.cpp server, OpenRouter, groq, Together, and Ollama's own
/v1 endpoint. Point ``base_url`` at the provider and set an ``api_key``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from agent_base import TOOL_DEFINITIONS, BaseArchiveAgent

_DONE = "[DONE]"

__all__ = ["OpenAIAgent"]


class OpenAIAgent(BaseArchiveAgent):
    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        on_tool_call: Callable[[str, dict], Any] | None = None,
        max_rounds: int = 8,
    ):
        super().__init__(model=model, on_tool_call=on_tool_call, max_rounds=max_rounds)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            # Some providers sit behind a WAF that 403s the default
            # "Python-urllib/x.y" agent, so send an explicit one.
            "User-Agent": "BatchinCamaro/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def list_models(self) -> list[str]:
        req = urllib.request.Request(f"{self.base_url}/models", headers=self._headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        return sorted(models)

    def _chat(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI HTTP {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach API at {self.base_url}: {e.reason}") from e

    def _extract_message(self, data: dict) -> dict:
        if data.get("error"):
            raise RuntimeError(f"API error: {data['error']}")
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"No choices in response: {json.dumps(data)[:400]}")
        m = choices[0].get("message") or {}
        # Normalize to only the fields the API accepts back on the next turn;
        # strips extras like `refusal`/`annotations` that strict servers reject.
        out: dict[str, Any] = {"role": m.get("role", "assistant"), "content": m.get("content")}
        tool_calls = m.get("tool_calls")
        if tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": (tc.get("function") or {}).get("name", ""),
                        "arguments": (tc.get("function") or {}).get("arguments", "{}"),
                    },
                }
                for tc in tool_calls
            ]
        return out

    def _tool_message(self, tool_call: dict, name: str, result: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call.get("id"),
            "name": name,
            "content": result,
        }

    def _chat_stream(self, messages: list[dict], on_delta: Callable[[str], None]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "stream": True,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == _DONE:
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        content_parts.append(text)
                        on_delta(text)
                    for tcd in delta.get("tool_calls") or []:
                        idx = tcd.get("index", 0)
                        slot = tool_calls.setdefault(
                            idx, {"id": None, "type": "function",
                                  "function": {"name": "", "arguments": ""}})
                        if tcd.get("id"):
                            slot["id"] = tcd["id"]
                        fn = tcd.get("function") or {}
                        if fn.get("name"):
                            slot["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            slot["function"]["arguments"] += fn["arguments"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI HTTP {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach API at {self.base_url}: {e.reason}") from e

        msg: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
        if tool_calls:
            msg["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
        return msg
