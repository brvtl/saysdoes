"""OpenAI Chat Completions messages and Responses API output items."""
from __future__ import annotations

from typing import Any

from ..model import Trace, TraceBuilder
from .common import ParseError, parse_args, text_of

RESPONSES_ITEM_TYPES = {"reasoning", "function_call", "function_call_output", "web_search_call",
                        "local_shell_call", "custom_tool_call", "computer_call", "file_search_call",
                        "code_interpreter_call", "mcp_call"}


def is_responses(data: Any) -> bool:
    if isinstance(data, dict):
        if isinstance(data.get("output"), list):
            return True
        data = data.get("input") if isinstance(data.get("input"), list) else None
    if isinstance(data, list):
        return any(isinstance(o, dict) and o.get("type") in RESPONSES_ITEM_TYPES for o in data)
    return False


def parse(data: Any, source: str = "") -> Trace:
    b = TraceBuilder("openai", source)
    if is_responses(data):
        _parse_responses(b, data)
    else:
        msgs = data.get("messages") if isinstance(data, dict) else data
        if not isinstance(msgs, list):
            raise ParseError("openai: expected a list of messages or {\"messages\": [...]}")
        if isinstance(data, dict) and data.get("model"):
            b.trace.model = data["model"]
        _parse_chat(b, msgs)
    return b.build()


def _reasoning_text(r: Any) -> str:
    if isinstance(r, str):
        return r
    if isinstance(r, dict):
        if r.get("summary"):
            return text_of(r["summary"])
        return text_of(r.get("content") or r.get("text"))
    return text_of(r)


def _parse_chat(b: TraceBuilder, msgs: list) -> None:
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            raise ParseError(f"openai: message {i} is not an object")
        role = m.get("role")
        ref = f"messages[{i}]"
        if role in ("system", "developer"):
            b.add("system", text_of(m.get("content")), ref)
        elif role == "user":
            b.add("user", text_of(m.get("content")), ref)
        elif role in ("tool", "function"):
            b.attach_result(m.get("tool_call_id"), text_of(m.get("content")))
        elif role == "assistant":
            if m.get("model") and not b.trace.model:
                b.trace.model = m["model"]
            for key in ("reasoning_content", "reasoning", "thinking"):
                if m.get(key):
                    b.add("reasoning", _reasoning_text(m[key]), f"{ref}.{key}")
                    break
            b.add("text", text_of(m.get("content")), f"{ref}.content")
            for k, tc in enumerate(m.get("tool_calls") or []):
                fn = tc.get("function") or {}
                b.add_action(fn.get("name", "tool"), parse_args(fn.get("arguments", {})),
                             f"{ref}.tool_calls[{k}]", call_id=tc.get("id"))
            if m.get("function_call"):
                fc = m["function_call"]
                b.add_action(fc.get("name", "tool"), parse_args(fc.get("arguments", {})), f"{ref}.function_call")


def _parse_responses(b: TraceBuilder, data: Any) -> None:
    items: list = []
    if isinstance(data, dict):
        if data.get("model"):
            b.trace.model = data["model"]
        if data.get("instructions"):
            b.add("system", text_of(data["instructions"]), "instructions")
        inp = data.get("input")
        if isinstance(inp, str):
            b.add("user", inp, "input")
        elif isinstance(inp, list):
            items += [("input", i, x) for i, x in enumerate(inp)]
        items += [("output", i, x) for i, x in enumerate(data.get("output") or [])]
    else:
        items = [("items", i, x) for i, x in enumerate(data)]
    for where, i, it in items:
        if not isinstance(it, dict):
            continue
        ref = f"{where}[{i}]"
        typ = it.get("type", "message" if "role" in it else None)
        if typ == "message":
            role = it.get("role")
            kind = {"user": "user", "system": "system", "developer": "system"}.get(role, "text")
            b.add(kind, text_of(it.get("content")), ref)
        elif typ == "reasoning":
            txt = text_of(it.get("summary")) or text_of(it.get("content"))
            b.add("reasoning", txt, ref)
        elif typ in ("function_call", "custom_tool_call", "mcp_call"):
            args = parse_args(it.get("arguments", it.get("input", {})))
            b.add_action(it.get("name", "tool"), args, ref, call_id=it.get("call_id") or it.get("id"))
        elif typ == "local_shell_call":
            action = it.get("action") or {}
            b.add_action("local_shell", {"command": action.get("command", [])}, ref,
                         call_id=it.get("call_id") or it.get("id"))
        elif typ == "web_search_call":
            action = it.get("action") or {}
            b.add_action("web_search", {"query": action.get("query", "")} if action else {}, ref,
                         call_id=it.get("id"))
        elif typ in ("computer_call", "file_search_call", "code_interpreter_call"):
            args = {k: v for k, v in it.items() if k not in ("type", "id", "status")}
            name = {"code_interpreter_call": "code_interpreter"}.get(typ, typ.replace("_call", ""))
            b.add_action(name, args, ref, call_id=it.get("call_id") or it.get("id"))
        elif typ in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
            b.attach_result(it.get("call_id"), text_of(it.get("output")))
