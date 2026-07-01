"""Shared agent scaffolding: system prompt, tool schema, and the tool-call loop.

Provider-specific agents (Ollama native, OpenAI-compatible) subclass
``BaseArchiveAgent`` and implement the three transport hooks:

- ``_chat``           -> POST the messages and return the raw JSON response
- ``_extract_message``-> pull the assistant message dict out of that response
- ``_tool_message``   -> build the ``role: tool`` reply for one tool call
"""

from __future__ import annotations

import json
from typing import Any, Callable

import ia_service

SYSTEM_PROMPT = """You are an Internet Archive assistant for Batchin' Camaro.
Use the provided tools to search archive.org, inspect item metadata, and start downloads.
Always use tools instead of guessing item IDs or file names.
For large batch downloads (more than 5 items), ask the user to confirm first.
Be concise and helpful."""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_archive",
            "description": "Search Internet Archive items by keyword query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"},
                    "mediatype": {
                        "type": "string",
                        "enum": ["texts", "audio", "movies", "image", "software", "data"],
                        "description": "Optional mediatype filter",
                    },
                    "rows": {"type": "integer", "description": "Max results (1-100)", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_item_metadata",
            "description": "Get metadata and downloadable file list for an archive.org item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "Archive.org identifier"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_download",
            "description": "Queue Internet Archive items for download to the configured output directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of item identifiers",
                    },
                    "want_text": {"type": "boolean", "default": True},
                    "want_pdf": {"type": "boolean", "default": True},
                },
                "required": ["item_ids"],
            },
        },
    },
]


class BaseArchiveAgent:
    """Provider-agnostic tool-calling loop over the Internet Archive tools."""

    def __init__(
        self,
        model: str,
        on_tool_call: Callable[[str, dict], Any] | None = None,
        max_rounds: int = 8,
    ):
        self.model = model
        self.on_tool_call = on_tool_call
        self.max_rounds = max_rounds
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # --- transport hooks (implemented per provider) ---------------------------

    def _chat(self, messages: list[dict]) -> dict:
        raise NotImplementedError

    def _extract_message(self, data: dict) -> dict:
        raise NotImplementedError

    def _tool_message(self, tool_call: dict, name: str, result: str) -> dict:
        raise NotImplementedError

    def _chat_stream(self, messages: list[dict], on_delta: Callable[[str], None]) -> dict:
        """Stream a completion, emitting text via ``on_delta``, return the full message.

        Default: no real streaming — fetch normally and emit the content once.
        Providers override this to stream token deltas.
        """
        msg = self._extract_message(self._chat(messages))
        if msg.get("content"):
            on_delta(msg["content"])
        return msg

    # --- shared logic ---------------------------------------------------------

    @staticmethod
    def _parse_args(raw_args: Any) -> dict:
        if isinstance(raw_args, dict):
            return raw_args
        try:
            return json.loads(raw_args or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    def _execute_tool(self, name: str, args: dict) -> str:
        if self.on_tool_call:
            result = self.on_tool_call(name, args)
            if result is not None:
                return json.dumps(result) if not isinstance(result, str) else result

        if name == "search_archive":
            results = ia_service.search_items(
                args.get("query", ""),
                mediatype=args.get("mediatype"),
                rows=int(args.get("rows") or 10),
            )
            return json.dumps({"count": len(results), "results": results})
        if name == "get_item_metadata":
            item_id = args.get("item_id", "").strip()
            meta = ia_service.get_metadata(item_id)
            return json.dumps(ia_service.summarize_metadata(meta))
        if name == "start_download":
            return json.dumps({
                "status": "queued",
                "item_ids": args.get("item_ids", []),
                "note": "Download handler not configured",
            })
        return json.dumps({"error": f"Unknown tool: {name}"})

    def run_turn(
        self,
        user_message: str,
        on_delta: Callable[[str], None] | None = None,
        on_tool: Callable[[str], None] | None = None,
    ) -> tuple[str, list[str]]:
        """Send user message, run the tool loop, return (assistant_text, tool_log).

        If ``on_delta`` is given, the assistant text is streamed to it as it
        arrives. If ``on_tool`` is given, each tool invocation is reported live.
        """
        self.messages.append({"role": "user", "content": user_message})
        tool_log: list[str] = []

        for _ in range(self.max_rounds):
            if on_delta is not None:
                msg = self._chat_stream(self.messages, on_delta)
            else:
                msg = self._extract_message(self._chat(self.messages))
            self.messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return msg.get("content") or "", tool_log

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                args = self._parse_args(fn.get("arguments"))
                entry = f"{name}({json.dumps(args)})"
                tool_log.append(entry)
                if on_tool is not None:
                    on_tool(entry)
                result = self._execute_tool(name, args)
                self.messages.append(self._tool_message(tc, name, result))

        return "Reached maximum tool rounds. Try a simpler request.", tool_log
