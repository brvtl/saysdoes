"""Human-readable text report and machine-readable JSON."""
from __future__ import annotations

import json
import os

from . import __version__
from .analyze import Report
from .model import Action, Finding
from .shell import FS_WRITE

KIND_SAYS = {
    "no_tools": "says no tools",
    "read_only": "says read-only",
    "no_network": "says no network",
    "no_shell": "says no shell",
    "only_file": "says only {scope}",
    "file_negation": "says it won't change {scope}",
    "fuzzy_intent": "states an intent",
}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _host_label(a: Action) -> str | None:
    hosts = a.detail.get("hosts") or []
    if not hosts:
        return None
    clouds = a.detail.get("cloud_storage") or []
    if clouds:
        return "*." + clouds[0]
    return hosts[0]


def annotations(a: Action) -> str:
    notes = []
    if a.category in ("network", "network_upload") and a.detail.get("hosts"):
        method = a.detail.get("method")
        notes.append(f"{method} {a.detail['hosts'][0]}" if method else a.detail["hosts"][0])
    if a.detail.get("cloud_storage"):
        notes.append("cloud storage: " + ", ".join(a.detail["cloud_storage"]))
    if a.detail.get("metadata_hosts"):
        notes.append("metadata endpoint: " + ", ".join(a.detail["metadata_hosts"]))
    if a.detail.get("writes"):
        notes.append("writes " + ", ".join(a.detail["writes"]))
    if a.detail.get("sudo"):
        notes.append("sudo")
    return f"  [{'; '.join(notes)}]" if notes else ""


def verb(a: Action) -> str:
    d = a.detail
    argv0 = d.get("argv0") or a.tool
    if a.category == "network_upload":
        return f"{d.get('method', 'upload')} {_host_label(a) or argv0}"
    if a.category == "network":
        host = _host_label(a)
        return f"{argv0} {host}" if host else argv0
    if a.category == "fs_read" and d.get("reads") and not str(d["reads"][0]).startswith("("):
        return "read " + os.path.basename(d["reads"][0].rstrip("/")) if d["reads"][0] != "/" else "read /"
    if a.category == "fs_write" and d.get("writes"):
        target = os.path.basename(str(d["writes"][0]).rstrip("/"))
        if d.get("shell"):
            return f"{argv0 if argv0 in FS_WRITE else 'write'} {target}"
        return f"{a.tool} {target}"
    if a.category == "privilege":
        return f"sudo {argv0}" if d.get("sudo") else argv0
    return argv0


def _uniq(xs):
    return list(dict.fromkeys(xs))


def _truncate(s: str, n: int = 220) -> str:
    s = " ".join(s.split()) if "\n" in s else s
    return s if len(s) <= n else s[: n - 1] + "…"


def _quote(f: Finding) -> str:
    c = f.commitment
    ctx = c.context or c.span_text
    if len(ctx) > 200:
        i = ctx.find(c.span_text)
        start = max(0, i + len(c.span_text) - 180) if i >= 0 else 0
        ctx = ("…" if start else "") + ctx[start:start + 200]
    return " ".join(ctx.split())


def summary_line(f: Finding) -> str:
    c = f.commitment
    acts = f.contradicting_actions
    says = KIND_SAYS.get(c.kind, "states a plan").format(scope=c.scope)
    refs = acts[0].ref if len(acts) == 1 else f"{acts[0].ref}-{acts[-1].ref}"
    nontrivial = [a for a in acts if a.category != "other"] or acts
    did = ", ".join(_uniq(verb(a) for a in nontrivial))
    return f"step {c.step_index} {says}; {'step' if len(acts) == 1 else 'steps'} {refs} ran {did}"


def format_finding(f: Finding, report: Report) -> list[str]:
    c = f.commitment
    step = report.trace.step(c.step_index)
    where = "reasoning" if step.kind == "reasoning" else "assistant text, lower confidence"
    label = c.kind + (f"{' ' + c.scope if c.scope else ''} (judge)" if f.source == "judge" else "")
    lines = [f"✗ [{f.severity.upper()}] {label}  step {c.step_index} ({where}) says: \"{_quote(f)}\""]

    acts = f.contradicting_actions
    step_ids = _uniq(a.step_index for a in acts)
    tools = _uniq(report.trace.step(s).tool or "tool" for s in step_ids)
    in_steps = [a for a in report.actions if a.step_index in step_ids]
    steps_word = f"step {step_ids[0]}" if len(step_ids) == 1 else "steps " + ", ".join(map(str, step_ids))
    shellish = any(a.detail.get("shell") for a in in_steps)
    unit = "sub-command" if shellish else "action"
    count = _plural(len(in_steps), unit) if len(acts) == len(in_steps) else \
        f"{len(acts)} of {_plural(len(in_steps), unit)}"
    lines.append(f"    but {steps_word} ran {_plural(len(step_ids), 'tool call')} ({', '.join(tools)}) → {count}:")
    folded = []
    for a in acts:
        if a.category == "other":
            folded.append(f"{a.ref} {a.detail.get('argv0', a.tool)}")
            continue
        lines.append(f"      {a.ref:<5} {a.category:<15} {_truncate(a.raw)}{annotations(a)}")
    if folded:
        lines.append(f"      (folded {len(folded)} trivial: {', '.join(folded)})")
    if f.hidden_trivial:
        lines.append(f"      (+{_plural(f.hidden_trivial, 'trivial sub-command')} hidden)")
    lines.append(f"    {summary_line(f)}")
    if f.source == "judge":
        lines.append(f"    {f.explanation}")
    return lines


def judge_line(j: dict) -> str:
    cost = f"${j['total_cost_usd']:.4f} API-equivalent"
    if j["cache_hits"]:
        cost += f" (${j['cost_usd_this_run']:.4f} this run)"
    parts = [f"judge: {j['backend']} {j['model']} ({j['effort']})", _plural(j["turns"], "turn"),
             f"{j['calls']} calls, {j['cache_hits']} cached", f"{len(j['added'])} added",
             f"{len(j['dismissed'])} dismissed", cost]
    if j["rejected"]:
        parts.append(f"{len(j['rejected'])} rejected citations")
    if j["errors"]:
        parts.append(_plural(len(j["errors"]), "error"))
    return " · ".join(parts)


def format_judge_notes(j: dict) -> list[str]:
    lines = []
    for d in j["dismissed"]:
        c = d["finding"]["commitment"]
        lines.append(f"– dismissed by judge: {d['finding_id']} {c['kind']}  step {c['step_index']} says: "
                     f"\"{' '.join((c['context'] or c['span_text']).split())}\"")
        lines.append(f"    {d['reason']}: {' '.join(str(d['explanation']).split())}")
        lines.append(f"    evidence, step {d['evidence_step']}: \"{' '.join(str(d['evidence_quote']).split())}\"")
        lines.append("")
    for e in j["errors"]:
        lines += [f"⚠ judge error, turn {e['turn']}: {e['error']} (rules-only for that turn)", ""]
    return lines


def format_text(report: Report, path: str | None = None) -> str:
    t = report.trace
    path = path or t.source or "<trace>"
    n = len(report.findings)
    high = sum(1 for f in report.findings if f.severity == "high")
    if n:
        head = f"saysdoes: {_plural(n, 'contradiction')} ({high} high) in {path}  [format: {t.format}]"
    else:
        head = f"saysdoes: no contradictions in {path}  [format: {t.format}]"
    facts = []
    if t.model:
        facts.append(f"model: {t.model}")
    facts += [_plural(len(t.steps), "step"), _plural(len(report.actions), "action"),
              _plural(len(report.commitments), "commitment")]
    lines = [head, "  " + " · ".join(facts)]
    if report.judge:
        lines.append("  " + judge_line(report.judge))
    lines.append("")
    for f in report.findings:
        lines += format_finding(f, report)
        lines.append("")
    if report.judge:
        lines += format_judge_notes(report.judge)
    contradicted = {f.commitment.id for f in report.findings}
    temporary = [c for c in report.commitments if c.temporary and c.id not in contradicted]
    for c in temporary:
        where = "reasoning" if t.step(c.step_index).kind == "reasoning" else "assistant text"
        lines.append(f"ℹ temporary {c.kind}  step {c.step_index} ({where}) says: "
                     f"\"{' '.join((c.context or c.span_text).split())}\"")
    if temporary:
        lines += ["    (stated as temporary or followed by a planned change; checked only until the agent's next "
                  "message, informational after that)", ""]
    if n:
        lines.append(f"verdict: contradiction between stated plan and actions (exit {report.exit_code})")
    else:
        lines.append("verdict: actions consistent with stated commitments (exit 0)")
    return "\n".join(lines) + "\n"


def to_dict(report: Report, path: str | None = None) -> dict:
    t = report.trace
    return {
        "tool": "saysdoes",
        "version": __version__,
        "file": path or t.source,
        "format": t.format,
        "model": t.model,
        "verdict": "contradiction" if report.findings else "consistent",
        "exit_code": report.exit_code,
        "summary": {
            "steps": len(t.steps),
            "actions": len(report.actions),
            "commitments": len(report.commitments),
            "temporary_commitments": sum(1 for c in report.commitments if c.temporary),
            "findings": len(report.findings),
            "high": sum(1 for f in report.findings if f.severity == "high"),
            "lines": [summary_line(f) for f in report.findings],
        },
        "meta": t.meta,
        "steps": [s.to_dict() for s in t.steps],
        "actions": [a.to_dict() for a in report.actions],
        "commitments": [c.to_dict() for c in report.commitments],
        "intents": [c.to_dict() for c in report.intents],
        "findings": [f.to_dict() for f in report.findings],
        "judge": report.judge or {"backend": "none"},
    }


def to_json(report: Report, path: str | None = None) -> str:
    return json.dumps(to_dict(report, path), indent=2, ensure_ascii=False)
