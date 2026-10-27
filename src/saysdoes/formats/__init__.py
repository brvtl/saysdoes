"""Trace format parsers and auto-detection."""
from __future__ import annotations

import json
from typing import Any

from ..model import Trace
from . import anthropic, claude_code, cohere_pi, openai, qwen_chatml
from .common import ParseError

FORMATS = ("cohere-pi", "qwen-chatml", "openai", "anthropic", "claude-code")
_PARSERS = {
    "cohere-pi": cohere_pi.parse,
    "qwen-chatml": qwen_chatml.parse,
    "openai": openai.parse,
    "anthropic": anthropic.parse,
    "claude-code": claude_code.parse,
}

__all__ = ["FORMATS", "ParseError", "detect", "load", "load_text", "decode"]


def decode(text: str) -> tuple[str, Any]:
    """Return ("json", obj) | ("jsonl", [obj, ...]) | ("text", str)."""
    stripped = text.strip()
    if not stripped:
        raise ParseError("empty input")
    try:
        return "json", json.loads(stripped)
    except json.JSONDecodeError:
        pass
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    objs = []
    try:
        for ln in lines:
            objs.append(json.loads(ln))
    except json.JSONDecodeError:
        objs = []
    if objs and all(isinstance(o, dict) for o in objs):
        return "jsonl", objs
    return "text", text


def detect(kind: str, data: Any) -> str:
    if kind == "text":
        if "<|im_start|>" in data:
            return "qwen-chatml"
        raise ParseError("could not detect trace format (not JSON, JSONL, or ChatML)")
    if kind == "json":
        if isinstance(data, str) and "<|im_start|>" in data:
            return "qwen-chatml"
        if isinstance(data, dict):
            if isinstance(data.get("trace"), str) and "<|im_start|>" in data["trace"]:
                return "qwen-chatml"
            if data.get("type") in ("session", "message") and ("message" in data or "version" in data):
                return "cohere-pi"
            if data.get("type") in claude_code.LINE_TYPES and ("session_id" in data or "subtype" in data):
                return "claude-code"
        objs = [data] if isinstance(data, dict) and "type" in data else None
        if objs is None:
            if openai.is_responses(data):
                return "openai"
            msgs = data.get("messages") if isinstance(data, dict) else data
            if isinstance(msgs, list):
                return "anthropic" if anthropic.looks_like(msgs) else "openai"
            raise ParseError("could not detect trace format of JSON document")
        data = objs
        kind = "jsonl"
    if kind == "jsonl":
        if any(o.get("type") == "session" for o in data[:3]) or any(
                o.get("type") == "message" and isinstance(o.get("message"), dict)
                and o["message"].get("role") in cohere_pi.ROLES for o in data):
            return "cohere-pi"
        if any(o.get("type") in claude_code.LINE_TYPES and ("message" in o or "subtype" in o) for o in data):
            return "claude-code"
        if all("role" in o for o in data):  # JSONL of chat messages
            return "anthropic" if anthropic.looks_like(data) else "openai"
        if openai.is_responses(data):
            return "openai"
    raise ParseError("could not detect trace format")


def load_text(text: str, fmt: str = "auto", source: str = "") -> Trace:
    kind, data = decode(text)
    if fmt == "auto":
        fmt = detect(kind, data)
    if fmt not in _PARSERS:
        raise ParseError(f"unknown format: {fmt}")
    if fmt == "qwen-chatml":
        if kind == "json" and isinstance(data, dict):
            data = data.get("trace", "")
        elif kind != "text" and not isinstance(data, str):
            raise ParseError("qwen-chatml expects raw ChatML text")
        trace = _PARSERS[fmt](data if isinstance(data, str) else text, source)
    else:
        if kind == "text":
            raise ParseError(f"{fmt} expects JSON or JSONL input")
        if fmt in ("cohere-pi", "claude-code"):
            data = data if kind == "jsonl" else ([data] if isinstance(data, dict) else data)
            if not isinstance(data, list):
                raise ParseError(f"{fmt} expects JSONL")
        trace = _PARSERS[fmt](data, source)
    if not trace.steps:
        raise ParseError(f"no messages found for format {fmt}")
    return trace


def load(path: str, fmt: str = "auto") -> Trace:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return load_text(text, fmt, source=path)
