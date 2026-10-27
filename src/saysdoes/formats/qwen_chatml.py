"""Raw Qwen ChatML text: <|im_start|>role ... <|im_end|> with <think> and <tool_call> blocks."""
from __future__ import annotations

import json
import re

from ..model import Trace, TraceBuilder
from .common import ParseError

_MSG = re.compile(r"<\|im_start\|>([^\n]*)\n?(.*?)(?:<\|im_end\|>|(?=<\|im_start\|>)|\Z)", re.S)
_BLOCK = re.compile(r"<think>(.*?)(?:</think>|\Z)|<tool_call>(.*?)(?:</tool_call>|\Z)", re.S)
_FUNC = re.compile(r"<function=([^>\s]+)>(.*?)(?:</function>|\Z)", re.S)
_PARAM = re.compile(r"<parameter=([^>\s]+)>\n?(.*?)\n?</parameter>", re.S)
_TOOL_RESPONSE = re.compile(r"<tool_response>(.*?)(?:</tool_response>|\Z)", re.S)


def _strip_nl(s: str) -> str:
    return s[1:] if s.startswith("\n") else s


def _parse_tool_call(body: str) -> list[tuple[str, object]]:
    calls = []
    for fm in _FUNC.finditer(body):
        params = {}
        for pm in _PARAM.finditer(fm.group(2)):
            val = pm.group(2)
            try:
                params[pm.group(1)] = json.loads(val) if val.strip()[:1] in ("{", "[") else val
            except json.JSONDecodeError:
                params[pm.group(1)] = val
        calls.append((fm.group(1), params))
    if not calls:
        try:
            obj = json.loads(body.strip())
            args = obj.get("arguments", obj.get("parameters", {}))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    pass
            calls.append((obj.get("name", "tool"), args))
        except (json.JSONDecodeError, AttributeError):
            calls.append(("tool", body.strip()))
    return calls


def parse(text: str, source: str = "") -> Trace:
    if "<|im_start|>" not in text:
        raise ParseError("no <|im_start|> markers found")
    b = TraceBuilder("qwen-chatml", source)
    for n, m in enumerate(_MSG.finditer(text), 1):
        role = m.group(1).strip()
        body = m.group(2)
        ref = f"message {n} ({role})"
        if role == "system":
            b.add("system", body.strip(), ref)
        elif role in ("user", "tool"):
            responses = _TOOL_RESPONSE.findall(body)
            rest = _TOOL_RESPONSE.sub("", body).strip()
            for r in responses:
                b.attach_result(None, r.strip())
            if role == "tool" and not responses:
                b.attach_result(None, body.strip())
            elif rest:
                b.add("user", rest, ref)
        elif role == "assistant":
            # Template may have emitted the opening <think> in the prompt: leading "...</think>".
            if "</think>" in body and "<think>" not in body.split("</think>", 1)[0]:
                head, body = body.split("</think>", 1)
                b.add("reasoning", head.strip("\n"), f"{ref} think")
            pos = 0
            for k, bm in enumerate(_BLOCK.finditer(body)):
                before = body[pos:bm.start()]
                b.add("text", before.strip("\n"), f"{ref} text")
                if bm.group(1) is not None:
                    b.add("reasoning", bm.group(1).strip("\n"), f"{ref} think")
                else:
                    for name, args in _parse_tool_call(bm.group(2)):
                        b.add_action(name, args, f"{ref} tool_call[{k}]")
                pos = bm.end()
            b.add("text", body[pos:].strip("\n"), f"{ref} text")
    return b.build()
