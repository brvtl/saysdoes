from __future__ import annotations

import json
from typing import Any


class ParseError(Exception):
    """Input could not be parsed as the requested/detected trace format."""


def text_of(content: Any) -> str:
    """Flatten str / list-of-parts content into text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for k in ("text", "content", "output", "thinking"):
            if isinstance(content.get(k), (str, list)):
                return text_of(content[k])
        return ""
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") in (None, "text", "input_text", "output_text",
                                                                  "tool_result", "summary_text", "reasoning_text"):
                out.append(text_of(part.get("text", part.get("content"))))
        return "\n".join(x for x in out if x)
    return str(content)


def parse_args(arguments: Any) -> Any:
    """Tool arguments may be a JSON string; decode when possible."""
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
    return arguments
