"""Normalized internal model every trace format is converted into."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

STEP_KINDS = ("reasoning", "text", "user", "system", "action")

CATEGORIES = (
    "tool_call",
    "shell_exec",
    "fs_read",
    "fs_write",
    "fs_list",
    "env_probe",
    "network",
    "network_upload",
    "privilege",
    "other",  # trivial shell sub-commands (echo, cd, head as a stdin filter, ...)
)

COMMITMENT_KINDS = ("no_tools", "read_only", "no_network", "only_file", "no_shell", "file_negation")


@dataclass
class Step:
    """One unit of the trace, numbered 1..N in trace order."""

    index: int
    kind: str
    text: str
    source_ref: str
    turn: int = 0  # number of user messages seen before (and including) this step
    tool: str | None = None  # action steps only
    call_id: str | None = None
    args: Any = None
    result: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Action:
    """One classified (sub-)action. A compound shell command yields several."""

    step_index: int
    sub_index: int
    tool: str
    raw: str
    category: str
    detail: dict = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.step_index}.{self.sub_index}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ref"] = self.ref
        return d


@dataclass
class Commitment:
    id: str
    kind: str
    span_text: str  # exact substring of the step text
    step_index: int
    char_start: int
    char_end: int
    scope: str | None = None
    confidence: str = "high"  # "high" for reasoning, "low" for visible assistant text
    context: str = ""  # the clause/sentence around the span, for display
    # "start with a read-only look", "read-only, then edit": enforced only until the agent's next message
    # (see rules.checked_actions), informational after that.
    temporary: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Finding:
    commitment: Commitment
    contradicting_actions: list[Action]
    severity: str  # "high" | "medium"
    rule: str
    explanation: str
    hidden_trivial: int = 0  # trivial sub-commands (echo, cd, ...) dropped from contradicting_actions
    id: str = ""  # "f1", "f2"... for rule findings (in report order), "j1"... for judge findings
    source: str = "rules"  # "rules" (deterministic) or "judge"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "commitment": self.commitment.to_dict(),
            "contradicting_actions": [a.to_dict() for a in self.contradicting_actions],
            "severity": self.severity,
            "rule": self.rule,
            "explanation": self.explanation,
            "hidden_trivial": self.hidden_trivial,
        }


@dataclass
class Trace:
    format: str
    steps: list[Step]
    source: str = ""
    model: str | None = None
    meta: dict = field(default_factory=dict)

    def step(self, index: int) -> Step:
        return self.steps[index - 1]


class TraceBuilder:
    """Helper used by parsers: numbers steps, tracks user turns, attaches tool results."""

    def __init__(self, fmt: str, source: str = ""):
        self.trace = Trace(format=fmt, steps=[], source=source)
        self._turn = 0
        self._by_call_id: dict[str, Step] = {}

    def add(self, kind: str, text: str, source_ref: str, *, tool=None, call_id=None, args=None,
            skip_blank: bool = True) -> Step | None:
        text = text if isinstance(text, str) else ("" if text is None else str(text))
        if skip_blank and kind != "action" and not text.strip():
            return None
        if kind == "user":
            self._turn += 1
        step = Step(index=len(self.trace.steps) + 1, kind=kind, text=text, source_ref=source_ref,
                    turn=self._turn, tool=tool, call_id=call_id, args=args)
        self.trace.steps.append(step)
        if call_id:
            self._by_call_id[str(call_id)] = step
        return step

    def add_action(self, tool: str, args: Any, source_ref: str, call_id=None) -> Step:
        return self.add("action", _action_text(tool, args), source_ref, tool=tool, call_id=call_id, args=args)

    def attach_result(self, call_id, text) -> bool:
        step = self._by_call_id.get(str(call_id)) if call_id is not None else None
        if step is None:
            # Fall back to the most recent action without a result.
            for s in reversed(self.trace.steps):
                if s.kind == "action" and s.result is None:
                    step = s
                    break
        if step is None:
            return False
        step.result = text if isinstance(text, str) else str(text)
        return True

    def build(self) -> Trace:
        return self.trace


def _action_text(tool: str, args: Any) -> str:
    if isinstance(args, dict):
        for key in ("command", "cmd", "code", "file_path", "path", "url", "query"):
            if isinstance(args.get(key), str):
                return f"{tool}: {args[key]}"
        import json

        return f"{tool}: {json.dumps(args, ensure_ascii=False)}"
    return f"{tool}: {args}" if args not in (None, "") else tool
