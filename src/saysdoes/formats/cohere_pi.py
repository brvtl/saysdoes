"""Pi-session JSONL (as published in CohereLabs/10-2026-qwen-investigation-traces)."""
from __future__ import annotations

from ..model import Trace, TraceBuilder
from .common import ParseError, parse_args, text_of

ROLES = ("custom", "user", "assistant", "toolResult", "tool_result", "tool", "system")


def parse(objs: list[dict], source: str = "") -> Trace:
    b = TraceBuilder("cohere-pi", source)
    t = b.trace
    for lineno, obj in enumerate(objs, 1):
        if not isinstance(obj, dict):
            raise ParseError(f"line {lineno}: expected a JSON object")
        typ = obj.get("type")
        if typ == "session":
            t.meta["session"] = {k: obj.get(k) for k in ("id", "version", "cwd", "timestamp") if k in obj}
            if isinstance(obj.get("source"), dict):
                t.meta["session"]["source"] = obj["source"]
            continue
        if typ != "message":
            continue  # model_change, thinking_level_change, compaction, ... are not steps
        msg = obj.get("message") or {}
        role = msg.get("role")
        mid = obj.get("id", "")
        ref = f"line {lineno} ({mid})" if mid else f"line {lineno}"
        content = msg.get("content")
        if role in ("custom", "system"):
            b.add("system", text_of(content), ref)
        elif role == "user":
            b.add("user", text_of(content), ref)
        elif role in ("toolResult", "tool_result", "tool"):
            b.attach_result(msg.get("toolCallId") or msg.get("tool_call_id"), text_of(content))
        elif role == "assistant":
            if msg.get("model") and not t.model:
                t.model = msg["model"]
            if isinstance(content, str):
                b.add("text", content, ref)
                continue
            for k, block in enumerate(content or []):
                if not isinstance(block, dict):
                    continue
                bref = f"{ref} content[{k}]"
                bt = block.get("type")
                if bt == "thinking":
                    b.add("reasoning", block.get("thinking", ""), bref)
                elif bt == "text":
                    b.add("text", block.get("text", ""), bref)
                elif bt in ("toolCall", "tool_call", "tool_use"):
                    args = parse_args(block.get("arguments", block.get("input", {})))
                    b.add_action(block.get("name", "tool"), args, bref, call_id=block.get("id"))
    return b.build()
