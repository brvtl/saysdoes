"""Pipeline: trace -> actions -> commitments -> findings (+ optional model judge)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from . import commitments as cm
from .model import Action, Commitment, Finding, Trace
from .rules import evaluate
from .tools import actions_for_trace

if TYPE_CHECKING:
    from .judge import ClaudeJudge


@dataclass
class Report:
    trace: Trace
    actions: list[Action]
    commitments: list[Commitment]
    findings: list[Finding]
    intents: list[Commitment] = field(default_factory=list)
    judge: dict | None = None  # the judge block (see judge.run_judge); None when the judge is off

    @property
    def exit_code(self) -> int:
        return 1 if self.findings else 0

    def action(self, ref: str) -> Action | None:
        return next((a for a in self.actions if a.ref == ref), None)


def analyze(trace: Trace, judge: ClaudeJudge | None = None, warn: Callable[[str], None] | None = None) -> Report:
    actions = actions_for_trace(trace.steps)
    commitments = cm.extract(trace.steps)
    findings = evaluate(trace.steps, actions, commitments)
    for i, f in enumerate(findings, 1):
        f.id = f"f{i}"
    report = Report(trace, actions, commitments, findings)
    report.intents = cm.extract_intents(trace.steps, commitments)
    if judge is not None:
        from .judge import run_judge

        report.judge = run_judge(report, judge, warn)
    return report
