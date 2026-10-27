"""Anthropic Messages API JSON (content blocks: thinking, text, tool_use, tool_result)."""
from __future__ import annotations

from typing import Any

from ..model import Trace, TraceBuilder
from .common import ParseError, text_of

BLOCK_TYPES = {"thinking", "redacted_thinking", "tool_use", "tool_result", "server_tool_use",
               "web_search_tool_result"}


def looks_like(msgs: list) -> bool:
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if "tool_calls" in m or m.get("role") == "tool":
            return False
        c = m.get("content")
        if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") in BLOCK_TYPES for x in c):
            return True
    return False


def add_blocks(b: TraceBuilder, role: str, content: Any, ref: str) -> None:
    """Shared by the anthropic and claude-code parsers."""
    if isinstance(content, str):
        b.add("user" if role == "user" else "text", content, ref)
        return
    user_text = []
    for k, block in enumerate(content or []):
        if not isinstance(block, dict):
            continue
        bref = f"{ref}.content[{k}]"
        bt = block.get("type")
        if bt == "thinking":
            b.add("reasoning", block.get("thinking", ""), bref)
        elif bt == "text":
            if role == "user":
                user_text.append(block.get("text", ""))
            else:
                b.add("text", block.get("text", ""), bref)
        elif bt in ("tool_use", "server_tool_use"):
            b.add_action(block.get("name", "tool"), block.get("input", {}), bref, call_id=block.get("id"))
        elif bt in ("tool_result", "web_search_tool_result"):
            b.attach_result(block.get("tool_use_id"), text_of(block.get("content")))
    if user_text:
        # A user message carrying only tool_results is not a new user turn.
        b.add("user", "\n".join(user_text), ref)


def parse(data: Any, source: str = "") -> Trace:
    b = TraceBuilder("anthropic", source)
    msgs = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(msgs, list):
        raise ParseError("anthropic: expected a list of messages or {\"messages\": [...]}")
    if isinstance(data, dict):
        if data.get("model"):
            b.trace.model = data["model"]
        if data.get("system"):
            b.add("system", text_of(data["system"]), "system")
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            raise ParseError(f"anthropic: message {i} is not an object")
        role = m.get("role")
        if m.get("model") and not b.trace.model:
            b.trace.model = m["model"]
        if role == "system":
            b.add("system", text_of(m.get("content")), f"messages[{i}]")
        else:
            add_blocks(b, role, m.get("content"), f"messages[{i}]")
    return b.build()
