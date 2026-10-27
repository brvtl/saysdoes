"""Claude Code `--output-format stream-json --verbose` JSONL."""
from __future__ import annotations

from ..model import Trace, TraceBuilder
from .anthropic import add_blocks
from .common import ParseError

LINE_TYPES = ("system", "assistant", "user", "result")


def parse(objs: list[dict], source: str = "") -> Trace:
    b = TraceBuilder("claude-code", source)
    t = b.trace
    for lineno, obj in enumerate(objs, 1):
        if not isinstance(obj, dict):
            raise ParseError(f"line {lineno}: expected a JSON object")
        typ = obj.get("type")
        ref = f"line {lineno}"
        if typ == "system":
            if obj.get("model"):
                t.model = t.model or obj["model"]
            t.meta.setdefault("init", {k: obj.get(k) for k in ("session_id", "cwd", "model", "tools",
                                                                "permissionMode") if k in obj})
            desc = ", ".join(f"{k}={obj[k]}" for k in ("subtype", "model", "cwd") if obj.get(k))
            b.add("system", f"[claude-code {desc}]" if desc else "[claude-code system]", ref)
        elif typ in ("assistant", "user"):
            msg = obj.get("message") or {}
            if typ == "assistant" and msg.get("model") and not t.model:
                t.model = msg["model"]
            add_blocks(b, msg.get("role", typ), msg.get("content"), ref)
        elif typ == "result":
            t.meta["result"] = {k: obj.get(k) for k in ("subtype", "is_error", "num_turns", "result",
                                                        "total_cost_usd") if k in obj}
    return b.build()
