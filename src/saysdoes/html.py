"""HTML timeline (`--html`): one self-contained static file, no external assets.

Left column: what the agent says (reasoning / text / user / system steps), with commitment spans highlighted.
Right column: what it does (one row per classified sub-action), green when consistent with every active
commitment, red when it contradicts one. Red connectors link a contradicted span to its actions.

URL parameters (handled by the inline script):
  ?replay=1   start the replay automatically (also: the "Replay" button, or the `r` key)
  ?speed=N    replay speed multiplier (default 1; ~1.2 s per step / sub-command at speed 1)
  ?step=N     render statically up to step N, or up to sub-command N.M (e.g. ?step=4.8), for screenshots
  ?step=end   render everything statically with the final verdict panel open, for screenshots
"""
from __future__ import annotations

import html as _html
import os

from .analyze import Report
from .model import Action, Commitment, Finding, Step
from .report import summary_line, verb
from .rules import in_scope, is_high

KIND_LABEL = {
    "no_tools": "no tools",
    "read_only": "read-only",
    "no_network": "no network",
    "no_shell": "no shell",
    "only_file": "only {scope}",
    "file_negation": "won't change {scope}",
    "fuzzy_intent": "intent",
    "other": "stated limit",
}
STEP_LABEL = {"reasoning": "reasoning", "text": "assistant text", "user": "user", "system": "system"}
SOURCE_LABEL = {"reasoning": "reasoning", "text": "text"}  # where a commitment was stated
SYSTEM_PREVIEW = 160
RESULT_MAX = 4000


def esc(s) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


def _clip(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def kind_label(c: Commitment) -> str:
    label = KIND_LABEL.get(c.kind, c.kind).format(scope=c.scope)
    return f"{label} (temporary)" if c.temporary else label


def finding_label(f: Finding) -> str:
    return kind_label(f.commitment) + (" · model judge" if f.source == "judge" else "")


def headline_action(f: Finding) -> Action:
    """The action the replay alert fires on: the first high-severity one, else the first contradiction."""
    return next((a for a in f.contradicting_actions if is_high(a)), f.contradicting_actions[0])


def describe(a: Action) -> str:
    """Short human description of an action, e.g. 'PUT to sanmaohe.oss-cn-beijing.aliyuncs.com'."""
    d = a.detail
    hosts = d.get("hosts") or []
    if a.category == "network_upload" and hosts:
        return f"{d.get('method') or 'upload'} to {hosts[0]}"
    if a.category == "network" and hosts:
        return f"{d.get('argv0') or a.tool} → {hosts[0]}"
    if d.get("shell") or d.get("code"):
        return _clip(a.raw, 70)
    return verb(a)


def _tags(a: Action) -> list[tuple[str, str]]:
    """(css class, text) chips shown under an action."""
    d = a.detail
    tags: list[tuple[str, str]] = []
    hosts = d.get("hosts") or []
    if a.category in ("network", "network_upload") and hosts:
        method = d.get("method")
        tags.append(("host", f"{method} {hosts[0]}" if method else hosts[0]))
    for c in d.get("cloud_storage") or []:
        tags.append(("hot", f"cloud storage · {c}"))
    for m in d.get("metadata_hosts") or []:
        tags.append(("hot", f"metadata endpoint · {m}"))
    for w in d.get("writes") or []:
        tags.append(("warn", f"writes {w}"))
    if d.get("sudo"):
        tags.append(("hot", "sudo"))
    return tags


def _action_display(a: Action, step: Step) -> str:
    if a.detail.get("shell") or a.detail.get("code"):
        return a.raw
    prefix = f"{step.tool}: "
    return step.text[len(prefix):] if step.text.startswith(prefix) else a.raw


class _Ctx:
    def __init__(self, report: Report):
        self.report = report
        self.steps = report.trace.steps
        self.findings = report.findings
        self.fid = {id(f): f"f{i + 1}" for i, f in enumerate(self.findings)}
        # action ref -> findings it contradicts
        self.bad: dict[str, list[Finding]] = {}
        for f in self.findings:
            for a in f.contradicting_actions:
                self.bad.setdefault(a.ref, []).append(f)
        self.headline: dict[str, list[Finding]] = {}
        for f in self.findings:
            self.headline.setdefault(headline_action(f).ref, []).append(f)
        # commitments to highlight: deterministic ones plus any (judge) commitments behind a finding
        commits = {c.id: c for c in report.commitments}
        for f in self.findings:
            commits.setdefault(f.commitment.id, f.commitment)
        self.commits = list(commits.values())
        self.contradicted = {f.commitment.id for f in self.findings}
        self.active: dict[str, list[Commitment]] = {}
        for c in self.commits:
            if c.temporary:  # informational only: never marks actions as kept
                continue
            for a in in_scope(c, report.actions, self.steps):
                self.active.setdefault(a.ref, []).append(c)
        self.kind_of = {s.index: s.kind for s in self.steps}
        self.by_step: dict[int, list[Action]] = {}
        for a in report.actions:
            self.by_step.setdefault(a.step_index, []).append(a)


# ---------------------------------------------------------------------------------------------------------
# Rendering pieces


def _highlight(text: str, commits: list[Commitment], contradicted: set[str]) -> str:
    """Escape `text`, wrapping commitment spans (which may overlap) in <mark> segments."""
    if not commits:
        return esc(text)
    cuts = sorted({0, len(text)} | {c.char_start for c in commits} | {c.char_end for c in commits})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if a == b:
            continue
        cover = [c for c in commits if c.char_start <= a and b <= c.char_end]
        if not cover:
            out.append(esc(text[a:b]))
            continue
        bad = any(c.id in contradicted for c in cover)
        final = "final-bad" if bad else ("final-temp" if all(c.temporary for c in cover) else "final-ok")
        attrs = [f'class="commit {final}'
                 f'{" low" if all(c.confidence == "low" for c in cover) else ""}"',
                 f'data-cids="{" ".join(c.id for c in cover)}"']
        first = [c for c in cover if c.char_start == a]
        if first:
            attrs.append(f'id="commit-{esc(first[0].id)}"')
        last = [c for c in cover if c.char_end == b]
        if last:
            attrs.append(f'data-label="{esc(" · ".join(kind_label(c) for c in last))}"')
        out.append(f"<mark {' '.join(attrs)}>{esc(text[a:b])}</mark>")
    return "".join(out)


def _spine(step: Step) -> str:
    return f'<div class="spine"><span class="dot k-{step.kind}">{step.index}</span></div>'


def _say_row(ctx: _Ctx, step: Step) -> str:
    kind = step.kind
    label = STEP_LABEL.get(kind, kind)
    commits = [c for c in ctx.commits if c.step_index == step.index]
    if kind == "system":
        text = step.text.strip()
        if len(text) > SYSTEM_PREVIEW:
            body = (f'<details class="sys"><summary><span class="preview">{esc(_clip(text, SYSTEM_PREVIEW))}</span>'
                    f'<span class="more">show full system prompt ({len(text):,} chars)</span></summary>'
                    f'<div class="full">{esc(text)}</div></details>')
        else:
            body = f'<div class="body">{esc(text)}</div>'
        cls = "card sys-card" + ("" if len(text) > SYSTEM_PREVIEW or "\n" in text else " slim")
    else:
        typ = " type" if kind in ("reasoning", "text") and len(step.text) <= 6000 else ""
        body = f'<div class="body{typ}">{_highlight(step.text.strip(chr(10)), _shift(commits, step.text), ctx.contradicted)}</div>'
        cls = f"card {kind}-card"
    note = ""
    if kind == "text" and commits:
        note = '<span class="lowconf" title="commitments in visible text are lower confidence">lower confidence</span>'
    return (f'<div class="{cls} u say" id="s{step.index}" data-ref="{step.index}" data-kind="{kind}">'
            f'<div class="meta"><span class="sn">step {step.index}</span>'
            f'<span class="kl">{esc(label)}</span>{note}</div>{body}</div>')


def _shift(commits: list[Commitment], text: str) -> list[Commitment]:
    """Commitment offsets are into the raw step text; we render it with leading newlines stripped."""
    lead = len(text) - len(text.lstrip("\n"))
    if not lead:
        return commits
    from dataclasses import replace

    return [replace(c, char_start=c.char_start - lead, char_end=c.char_end - lead) for c in commits]


def _act_row(ctx: _Ctx, a: Action, step: Step) -> str:
    bad = ctx.bad.get(a.ref, [])
    active = ctx.active.get(a.ref, [])
    trivial = a.category == "other"
    # A trivial sub-command is never shown as kept (it may be hidden from a no_tools finding it does violate).
    status = "bad" if bad else ("ok" if active and not trivial else "neutral")
    attrs = [f'class="act u st-{status}{" trivial" if trivial else ""}"', f'id="a{a.ref.replace(".", "-")}"',
             f'data-ref="{a.ref}"']
    if bad:
        attrs.append(f'data-findings="{" ".join(ctx.fid[id(f)] for f in bad)}"')
        attrs.append(f'data-cids="{" ".join(dict.fromkeys(f.commitment.id for f in bad))}"')
    heads = ctx.headline.get(a.ref, [])
    if heads:
        attrs[0] = attrs[0][:-1] + ' headline"'
        attrs.append(f'data-alert="{" ".join(ctx.fid[id(f)] for f in heads)}"')
    icon = {"bad": "✗", "ok": "✓", "neutral": "·"}[status]
    tags = "".join(f'<span class="tag {c}">{esc(t)}</span>' for c, t in _tags(a))
    why = ""
    if bad:
        seen = []
        for f in bad:
            c = f.commitment
            seen.append(f'contradicts step {c.step_index} “{esc(_clip(c.span_text, 60))}” '
                        f'<span class="rk">({esc(finding_label(f))})</span>')
        why = '<div class="why">✗ ' + "; ".join(dict.fromkeys(seen)) + "</div>"
    elif active:
        why = ('<div class="why okwhy">✓ consistent with '
               + ", ".join(f"“{esc(_clip(c.span_text, 40))}”" for c in active) + "</div>")
    code = esc(_action_display(a, step))
    return (f'<div {" ".join(attrs)}><span class="ref">{a.ref}</span>'
            f'<div class="ab"><div class="aline"><span class="cat c-{a.category}">{esc(a.category)}</span>'
            f'<code>{code}</code><span class="icon">{icon}</span></div>'
            f'{f"<div class=tags>{tags}</div>" if tags and not trivial else ""}{"" if trivial else why}</div></div>')


def _action_row(ctx: _Ctx, step: Step) -> str:
    acts = ctx.by_step.get(step.index, [])
    shellish = any(a.detail.get("shell") for a in acts)
    unit = "sub-command" if shellish else "action"
    n_bad = sum(1 for a in acts if a.ref in ctx.bad)
    count = _plural(len(acts), unit) if len(acts) != 1 or shellish else ""
    meta_bad = f'<span class="nbad">{n_bad} contradicting</span>' if n_bad else ""
    rows = "".join(_act_row(ctx, a, step) for a in acts)
    result = ""
    if step.result:
        r = step.result
        clipped = r if len(r) <= RESULT_MAX else r[:RESULT_MAX] + f"\n… ({len(r) - RESULT_MAX:,} more chars)"
        result = (f'<details class="result"><summary>tool output ({_plural(r.count(chr(10)) + 1, "line")})'
                  f'</summary><pre>{esc(clipped)}</pre></details>')
    return (f'<div class="card act-card u do" id="s{step.index}" data-ref="{step.index}" data-kind="action">'
            f'<div class="meta"><span class="sn">step {step.index}</span><span class="kl">tool call · '
            f'<b>{esc(step.tool or "tool")}</b></span>{f"<span class=cnt>{count}</span>" if count else ""}'
            f'{meta_bad}</div>{rows}{result}</div>')


def _blocks(steps: list[Step]) -> list[tuple[Step | None, list[Step]]]:
    """Group the timeline into rows: a reasoning/text step beside the action steps that directly follow it.

    Rows stay in trace order; within a row the left card precedes the right ones (the replay types the
    reasoning first, then reveals its actions), so a commitment and what contradicts it share one screen.
    """
    out: list[tuple[Step | None, list[Step]]] = []
    for step in steps:
        if step.kind == "action":
            if out and (out[-1][0] is None or out[-1][0].kind in ("reasoning", "text")):
                out[-1][1].append(step)
            else:
                out.append((None, [step]))
        else:
            out.append((step, []))
    return out


def _row(ctx: _Ctx, says: Step | None, does: list[Step]) -> str:
    first = says or does[0]
    left = _say_row(ctx, says) if says else ""
    right = "".join(_action_row(ctx, st) for st in does)
    return (f'<div class="row k-{first.kind}{" has-do" if does else ""}" data-row="{first.index}">'
            f'<div class="cell left">{left}</div>{_spine(first)}<div class="cell right">{right}</div></div>')


def _source(ctx: _Ctx, c: Commitment) -> str:
    """'reasoning' or 'text': the kind of step the commitment was stated in."""
    kind = ctx.kind_of.get(c.step_index, "")
    return SOURCE_LABEL.get(kind, kind or "text")


def _alert_template(ctx: _Ctx, f: Finding) -> str:
    c = f.commitment
    a = headline_action(f)
    hot = [t.split(" · ")[0] for cls, t in _tags(a) if cls == "hot"]
    others = len(f.contradicting_actions) - 1
    more = f'<span class="more">+{_plural(others, "other contradicting action")}</span>' if others else ""
    return (f'<template id="alert-{ctx.fid[id(f)]}"><div class="alert sev-{f.severity}">'
            f'<div class="a-title"><span class="warn">⚠</span> CONTRADICTION'
            f'<span class="sev">{esc(f.severity.upper())}</span><span class="rule">{esc(finding_label(f))}</span></div>'
            f'<div class="a-body">step {c.step_index} {esc(_source(ctx, c))} says <q>{esc(_clip(c.span_text, 90))}</q>'
            f' <span class="arrow">→</span> step {a.ref} does <b>{esc(describe(a))}</b>'
            + "".join(f' <span class="tag hot">{esc(t)}</span>' for t in hot)
            + f"{more}</div></div></template>")


def _rk(c: Commitment, judge: bool = False) -> str:
    label = kind_label(c) + (" · model judge" if judge else "")
    return "" if label.lower() == c.span_text.lower() else f' <span class="rk">({esc(label)})</span>'


def _says_does(ctx: _Ctx, f: Finding) -> str:
    c = f.commitment
    acts = f.contradicting_actions
    refs = acts[0].ref if len(acts) == 1 else f"{acts[0].ref}–{acts[-1].ref}"
    nontrivial = [a for a in acts if a.category != "other"] or acts
    did = list(dict.fromkeys(verb(a) for a in nontrivial))
    hot = {verb(a) for a in nontrivial if is_high(a)}
    did_html = ", ".join(f'<b class="hot">{esc(v)}</b>' if v in hot else esc(v) for v in did)
    return (f'<div class="fx"><span class="sev sev-{f.severity}">{esc(f.severity.upper())}</span>'
            f'<div class="said"><span class="lab">says · step {c.step_index} ({esc(_source(ctx, c))})</span>'
            f'<q>{esc(_clip(c.span_text, 90))}</q>{_rk(c, f.source == "judge")}</div>'
            f'<div class="arr">→</div><div class="did"><span class="lab">does · '
            f'{"step" if len(acts) == 1 else "steps"} {refs}</span>{did_html}</div></div>')


def _says_only(ctx: _Ctx, c: Commitment, sev: str, badge: str) -> str:
    return (f'<div class="fx"><span class="sev sev-{sev}">{badge}</span><div class="said">'
            f'<span class="lab">says · step {c.step_index} ({esc(_source(ctx, c))})</span><q>{esc(_clip(c.span_text, 80))}</q>'
            f'{_rk(c)}</div></div>')


def _final_panel(ctx: _Ctx) -> str:
    r = ctx.report
    n = len(r.findings)
    if n:
        high = sum(1 for f in r.findings if f.severity == "high")
        title = f"✗ {_plural(n, 'contradiction')} between stated plan and actions"
        sub = f"{high} high severity · exit code {r.exit_code}"
        items = "".join(_says_does(ctx, f) for f in r.findings)
        cls = "bad"
    else:
        title = "✓ Actions consistent with stated commitments"
        sub = (f"{_plural(sum(1 for c in r.commitments if not c.temporary), 'commitment')} checked against "
               f"{_plural(len(r.actions), 'action')} · exit code 0")
        items = "".join(_says_only(ctx, c, "ok", "kept") for c in r.commitments if not c.temporary)
        cls = "ok"
    items += "".join(_says_only(ctx, c, "temp", "temporary") for c in r.commitments
                     if c.temporary and c.id not in ctx.contradicted)
    hint = "saysdoes · deterministic check, no model judge"
    if r.judge:
        j = r.judge
        items += "".join(_says_only(ctx, _dismissed_commitment(d), "temp", "dismissed") for d in j["dismissed"])
        hint = (f"saysdoes · deterministic rules + model judge ({j['model']}, {j['effort']}): "
                f"{len(j['added'])} added, {len(j['dismissed'])} dismissed, {len(j['errors'])} errors")
    return (f'<section id="final" class="final u {cls}" data-ref="end"><div class="f-title">{title}</div>'
            f'<div class="f-sub">{esc(sub)}</div><div class="fxs">{items}</div>'
            f'<div class="f-hint">{esc(hint)}</div></section>')


def _dismissed_commitment(d: dict) -> Commitment:
    c = dict(d["finding"]["commitment"])
    return Commitment(**c)


def render(report: Report, path: str | None = None) -> str:
    ctx = _Ctx(report)
    t = report.trace
    path = path or t.source or "trace"
    rows = [_row(ctx, says, does) for says, does in _blocks(t.steps)]
    n = len(report.findings)
    verdict_cls = "bad" if n else "ok"
    verdict = (f"✗ {_plural(n, 'contradiction')}" if n else "✓ consistent")
    facts = [f'<span class="chip">{esc(t.format)}</span>']
    if t.model:
        facts.append(f'<span class="chip">{esc(t.model)}</span>')
    facts.append(f'<span class="facts">{_plural(len(t.steps), "step")} · {_plural(len(report.actions), "action")}'
                 f' · {_plural(len(report.commitments), "commitment")}</span>')
    templates = "".join(_alert_template(ctx, f) for f in report.findings)
    title = f"saysdoes — {os.path.basename(path)}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style></head>
<body class="static still">
<header id="hdr">
  <div class="brand"><span class="b1">says</span><span class="b2">does</span></div>
  <div class="file"><div class="fname" title="{esc(path)}">{esc(os.path.basename(path))}</div>
    <div class="fmeta">{"".join(facts)}</div></div>
  <div class="legend"><span class="lg ok">consistent</span><span class="lg bad">contradiction</span></div>
  <div id="verdict" class="verdict {verdict_cls}" data-final="{esc(verdict)}">{esc(verdict)}</div>
  <button id="replay" type="button" title="Replay (r)">▶ Replay</button>
</header>
<div id="banner" aria-live="assertive"></div>
<div id="flash"></div>
<div id="scrim"></div>
<div id="scroller"><main id="timeline">
  <svg id="links" aria-hidden="true"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
    markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#ff5d57"/></marker></defs></svg>
  <div class="colheads"><div class="ch left">What it <b>says</b> <span>reasoning &amp; text</span></div><div></div>
    <div class="ch right">What it <b>does</b> <span>tool calls, one row per sub-command</span></div></div>
  {"".join(rows)}
  {_final_panel(ctx)}
</main></div>
{templates}
<script>{JS}</script>
</body></html>
"""


def write(report: Report, path: str, source: str | None = None) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(report, source))


# ---------------------------------------------------------------------------------------------------------

CSS = r"""
:root{--bg:#0b0f14;--panel:#121820;--panel2:#171f29;--line:#263040;--text:#e7edf4;--muted:#8a98a8;
--green:#3ddc84;--green-bg:rgba(61,220,132,.10);--red:#ff5d57;--red-bg:rgba(255,93,87,.13);
--amber:#ffc24b;--blue:#6cb6ff;--violet:#b392f0;
--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono","Liberation Mono",monospace;
--sans:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:auto}
/* the document never scrolls (#scroller does), so plain `chrome --headless --screenshot` captures ?step=N views */
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:17px/1.5 var(--sans);-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;overflow:hidden}
#scroller{flex:1;min-height:0;overflow:auto;scrollbar-color:#2b3646 transparent}
header#hdr{flex:none;position:relative;z-index:30;display:flex;align-items:center;gap:22px;height:68px;padding:0 28px;
  background:rgba(11,15,20,.94);backdrop-filter:blur(6px);border-bottom:1px solid var(--line)}
.brand{font-weight:800;font-size:24px;letter-spacing:-.5px;white-space:nowrap}
.brand .b1{color:var(--text)}.brand .b2{color:var(--muted)}
.brand::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:9px;
  background:linear-gradient(135deg,var(--green) 50%,var(--red) 50%);vertical-align:1px}
.file{min-width:0;flex:1}
.fname{font:600 17px/1.2 var(--mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fmeta{display:flex;gap:8px;align-items:center;margin-top:4px;font-size:13px;color:var(--muted);white-space:nowrap}
.chip{border:1px solid var(--line);border-radius:6px;padding:0 7px;color:#c2cdd9;font-family:var(--mono);font-size:12.5px}
.legend{display:flex;gap:14px;font-size:13.5px;color:var(--muted);white-space:nowrap}
.lg::before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:0}
.lg.ok::before{background:var(--green)}.lg.bad::before{background:var(--red)}
.verdict{font-weight:800;font-size:17px;padding:7px 14px;border-radius:9px;white-space:nowrap;letter-spacing:.2px}
.verdict.bad{background:var(--red);color:#1a0505}.verdict.ok{background:var(--green);color:#03170b}
.verdict.pending{background:var(--panel2);color:var(--muted);border:1px solid var(--line);font-weight:600}
#replay{font:700 15px var(--sans);color:var(--text);background:var(--panel2);border:1px solid #3a475a;border-radius:9px;
  padding:8px 14px;cursor:pointer}
#replay:hover{border-color:var(--blue)}
main#timeline{position:relative;max-width:1260px;margin:0 auto;padding:6px 24px 120px}
svg#links{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:5;overflow:visible}
svg#links path.link{fill:none;stroke:var(--red);stroke-width:1.6;opacity:.42}
svg#links path.link.head{stroke-width:3;opacity:.95;filter:drop-shadow(0 0 4px rgba(255,93,87,.6))}
svg#links path.link.fresh{stroke-dasharray:var(--len);stroke-dashoffset:var(--len);animation:draw .7s ease-out forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.colheads{position:sticky;top:0;z-index:20;display:grid;grid-template-columns:minmax(0,1fr) 56px minmax(0,1fr);
  background:linear-gradient(var(--bg) 78%,rgba(11,15,20,0));padding:12px 0 10px}
.ch{font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:1.4px;font-weight:600}
.ch b{color:var(--text)}.ch span{text-transform:none;letter-spacing:0;font-weight:400;margin-left:8px;font-size:13.5px}
.row{display:grid;grid-template-columns:minmax(0,1fr) 56px minmax(0,1fr);align-items:start}
.spine{position:relative;align-self:stretch;display:flex;justify-content:center}
.spine::before{content:"";position:absolute;top:0;bottom:0;left:50%;width:2px;margin-left:-1px;background:var(--line)}
.dot{position:relative;margin-top:14px;width:30px;height:30px;border-radius:50%;background:var(--panel2);
  border:2px solid var(--line);font:700 13px/26px var(--mono);text-align:center;color:var(--muted)}
.dot.k-reasoning{border-color:var(--violet);color:var(--violet)}.dot.k-action{border-color:var(--blue);color:var(--blue)}
.dot.k-user{border-color:#d0d7de;color:#d0d7de}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px 14px;margin:8px 0}
.meta{display:flex;gap:10px;align-items:baseline;font-size:13px;color:var(--muted);margin-bottom:6px;
  text-transform:uppercase;letter-spacing:1px;font-weight:600}
.meta .sn{font-family:var(--mono);color:#c2cdd9;letter-spacing:0}
.meta b{color:var(--blue);text-transform:none;letter-spacing:0;font-family:var(--mono);font-size:14px}
.meta .cnt{text-transform:none;letter-spacing:0;font-weight:400}
.meta .nbad{margin-left:auto;color:var(--red);text-transform:none;letter-spacing:0}
body.replaying .meta .nbad{visibility:hidden}
.lowconf{margin-left:auto;text-transform:none;letter-spacing:0;font-weight:500;color:var(--amber);font-size:12.5px}
.body{white-space:pre-wrap;overflow-wrap:anywhere}
.reasoning-card{border-left:4px solid var(--violet)}
.reasoning-card .body{font-size:19.5px;line-height:1.55;color:#dfe6ee}
.text-card{border-left:4px solid #5b6b80}.text-card .body{font-size:17px;color:#cfd8e2}
.user-card{border-left:4px solid #d0d7de;background:var(--panel2)}.user-card .body{font-size:16.5px;color:#d7dee6}
.sys-card{padding:8px 14px;background:transparent;border-style:dashed}
.sys-card .meta{margin-bottom:2px}
.sys-card.slim{display:flex;gap:12px;align-items:baseline;padding:5px 14px;margin:5px 0}
.sys-card.slim .meta{margin:0;flex:none}.sys-card.slim .body{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row.k-system .dot{margin-top:6px;width:22px;height:22px;font-size:11px;line-height:18px}
.sys-card .body,.sys .preview{font:13.5px/1.45 var(--mono);color:var(--muted)}
.sys summary{cursor:pointer;list-style:none}.sys summary::-webkit-details-marker{display:none}
.sys .more{display:block;margin-top:4px;font-size:12.5px;color:var(--blue)}
.sys[open] .preview{display:none}
.sys .full{white-space:pre-wrap;font:13px/1.45 var(--mono);color:#aab6c3;max-height:360px;overflow:auto;margin-top:8px}
mark.commit{color:inherit;background:rgba(255,194,75,.22);box-shadow:inset 0 -2px 0 var(--amber);border-radius:3px;padding:1px 0}
mark.commit.low{background:rgba(255,194,75,.14)}
mark.commit.final-temp{background:rgba(150,170,190,.16);box-shadow:inset 0 -2px 0 #7d8fa3}
mark.commit[data-label]::after{content:attr(data-label);display:none;margin-left:4px;padding:0 5px;border-radius:4px;
  font:800 10.5px/15px var(--sans);text-transform:uppercase;letter-spacing:.5px;vertical-align:super;white-space:nowrap;
  background:var(--amber);color:#211700}
mark.commit.lit[data-label]::after{display:inline-block}
mark.commit.lit{animation:lit 1.1s ease-out}
@keyframes lit{0%{box-shadow:0 0 0 0 rgba(255,194,75,.9),inset 0 -2px 0 var(--amber)}100%{box-shadow:0 0 0 12px rgba(255,194,75,0),inset 0 -2px 0 var(--amber)}}
mark.commit.broken{background:var(--red-bg);box-shadow:inset 0 -3px 0 var(--red);background:rgba(255,93,87,.28)}
mark.commit.broken[data-label]::after{background:var(--red);color:#1a0505}
mark.commit.broken.flare{animation:flare 1.2s ease-out 2}
@keyframes flare{0%{box-shadow:0 0 0 0 rgba(255,93,87,.95),inset 0 -3px 0 var(--red)}100%{box-shadow:0 0 0 16px rgba(255,93,87,0),inset 0 -3px 0 var(--red)}}
mark.commit.settled{background:var(--green-bg);box-shadow:inset 0 -3px 0 var(--green);background:rgba(61,220,132,.2)}
mark.commit.settled[data-label]::after{background:var(--green);color:#03170b}
.act-card{border-left:4px solid var(--blue);padding-bottom:10px}
.row.has-do .cell.right{padding-top:30px;align-self:end}.row.k-action .cell.right{padding-top:0}
.act.st-bad.headline{border-width:2px;border-left-width:6px;border-color:var(--red);box-shadow:0 0 22px rgba(255,93,87,.28)}
.act{display:grid;grid-template-columns:46px minmax(0,1fr);gap:8px;margin:7px 0;padding:8px 10px 8px 8px;border-radius:9px;
  border:1px solid var(--line);border-left:5px solid #4b5869;background:var(--panel2)}
.act .ref{font:700 15px/26px var(--mono);color:#c2cdd9}
.aline{display:flex;gap:10px;align-items:flex-start}
.act code{flex:1;min-width:0;font:15px/1.45 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;color:#e7edf4;padding-top:2px}
.cat{flex:none;font:700 11.5px/22px var(--mono);padding:0 7px;border-radius:5px;background:#223044;color:#a9c7ec;margin-top:2px;
  text-transform:uppercase;letter-spacing:.3px}
.c-network,.c-network_upload{background:#3a2a17;color:#ffc68a}.c-privilege{background:#3a1730;color:#ff9be0}
.c-fs_write{background:#33301a;color:#ffe08a}.c-other{background:#1d242e;color:var(--muted)}
.icon{flex:none;width:26px;height:26px;border-radius:50%;text-align:center;font:800 15px/26px var(--sans)}
.st-ok{border-left-color:var(--green)}.st-ok .icon{background:var(--green-bg);color:var(--green)}
.st-bad{border-left-color:var(--red);background:var(--red-bg);border-color:rgba(255,93,87,.45)}
.st-bad .icon{background:var(--red);color:#1a0505}
.st-neutral .icon{color:var(--muted)}
.act.trivial{padding:3px 10px 3px 8px;margin:4px 0;opacity:.78}
.act.trivial .ref,.act.trivial code{font-size:13.5px;line-height:22px}.act.trivial code{padding-top:0;color:#b8c3cf}
.act.trivial .icon{width:20px;height:20px;font-size:11.5px;line-height:20px;margin-top:1px}
.act.trivial .cat{margin-top:0;line-height:20px;font-size:10.5px}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.tag{font:600 12.5px/20px var(--mono);padding:0 7px;border-radius:5px;background:#1d2633;color:#aebbc9;border:1px solid var(--line)}
.tag.host{color:#ffc68a;border-color:#5a4122}.tag.hot{background:var(--red);color:#1a0505;border-color:var(--red)}
.tag.warn{color:#ffe08a;border-color:#4d4520}
.why{margin-top:6px;font-size:14.5px;font-weight:600;color:#ff8f8a}.why .rk{color:#d1847f;font-weight:500}
.why.okwhy{color:#7fe3aa;font-weight:500}
.result{margin-top:8px;font-size:13.5px;color:var(--muted)}
.result summary{cursor:pointer}.result pre{max-height:260px;overflow:auto;font:12.5px/1.4 var(--mono);color:#aab6c3;
  background:#0d1218;border:1px solid var(--line);border-radius:8px;padding:8px 10px;white-space:pre-wrap}
.final{margin:26px auto 0;max-width:900px;border-radius:16px;padding:24px 30px;border:2px solid}
.final.bad{border-color:var(--red);background:linear-gradient(180deg,rgba(255,93,87,.16),rgba(255,93,87,.05))}
.final.ok{border-color:var(--green);background:linear-gradient(180deg,rgba(61,220,132,.14),rgba(61,220,132,.04))}
.f-title{font-size:28px;font-weight:800;letter-spacing:-.3px}.final.bad .f-title{color:#ff8f8a}.final.ok .f-title{color:#7fe3aa}
.f-sub{color:var(--muted);margin-top:2px}
.fxs{margin-top:16px;display:flex;flex-direction:column;gap:12px}
.fx{display:flex;align-items:flex-start;gap:14px;font-size:19px}.fx .sev{margin-top:5px}
.fx .lab{display:block;font-size:12.5px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);font-weight:700}
.fx .said{flex:0 1 44%}.fx .did{flex:1}.fx .arr{font-size:28px;font-weight:900;color:var(--red);padding-top:10px}
.fx q{quotes:"“" "”";font-weight:700}.final.bad .fx q{color:#ffb3af}.final.ok .fx q{color:#a8f0c6}
.fx .rk{color:var(--muted);font-size:15px}.fx .did .hot{color:#fff;background:rgba(255,93,87,.3);padding:0 5px;border-radius:4px;font-weight:700}
.f-hint{margin-top:18px;font-size:13px;color:var(--muted)}
#final.modal{position:fixed;left:50%;top:50%;z-index:50;margin:0;width:min(980px,calc(100vw - 80px));transform:translate(-50%,-50%);
  background:#150d10;box-shadow:0 30px 90px rgba(0,0,0,.75);animation:pop .5s cubic-bezier(.2,1.3,.4,1)}
#final.modal.ok{background:#0c1611}
@keyframes pop{from{opacity:0;transform:translate(-50%,-46%) scale(.96)}to{opacity:1;transform:translate(-50%,-50%)}}
#scrim{position:fixed;inset:0;z-index:45;background:rgba(5,8,12,.62);opacity:0;pointer-events:none;transition:opacity .5s}
#scrim.on{opacity:1;pointer-events:auto;cursor:pointer}
.sev{font:800 12px/20px var(--sans);padding:1px 7px;border-radius:5px;margin-right:8px;letter-spacing:.6px;vertical-align:1px}
.sev-high{background:var(--red);color:#1a0505}.sev-medium{background:var(--amber);color:#211700}
.sev-ok{background:var(--green);color:#03170b;text-transform:uppercase}
.sev-temp{background:#5b6b7c;color:#e8eef5;text-transform:uppercase}
#banner{position:fixed;left:50%;bottom:16px;z-index:40;transform:translate(-50%,30px);opacity:0;pointer-events:none;
  width:min(1180px,calc(100vw - 40px));transition:opacity .25s,transform .35s cubic-bezier(.2,1.4,.4,1)}
#banner.show{opacity:1;transform:translate(-50%,0)}
.alert{background:#2a0b0b;border:2px solid var(--red);border-radius:14px;padding:12px 22px 14px;margin-top:8px;
  box-shadow:0 18px 50px rgba(0,0,0,.6),0 0 0 0 rgba(255,93,87,.7)}
#banner.show .alert{animation:pulse 1.1s ease-out 3}
@keyframes pulse{0%{box-shadow:0 18px 50px rgba(0,0,0,.6),0 0 0 0 rgba(255,93,87,.75)}100%{box-shadow:0 18px 50px rgba(0,0,0,.6),0 0 0 26px rgba(255,93,87,0)}}
.a-title{display:flex;align-items:center;gap:12px;font-weight:900;font-size:25px;letter-spacing:1px;color:#ff6f69}
.a-title .warn{font-size:28px}
.a-title .sev{background:var(--red);color:#1a0505;font-size:13px;padding:2px 9px;border-radius:6px;letter-spacing:.8px}
.a-title .rule{font:700 13px var(--mono);color:#ffb3af;border:1px solid #7a2a27;padding:1px 8px;border-radius:6px;letter-spacing:0}
.a-body{margin-top:6px;font-size:21px;line-height:1.45;color:#ffe9e8}
.a-body q{font-weight:700;color:#fff;background:rgba(255,93,87,.25);padding:0 4px;border-radius:4px;quotes:"“" "”"}
.a-body b{font-family:var(--mono);font-size:19px;color:#fff;overflow-wrap:anywhere}
.a-body .arrow{color:var(--red);font-weight:900;margin:0 4px}
.a-body .tag{font-size:13px;vertical-align:2px}
.a-body .more{display:block;font-size:14px;color:#d1847f;margin-top:2px}
#flash{position:fixed;inset:0;z-index:35;pointer-events:none;opacity:0;
  background:radial-gradient(ellipse at center,rgba(255,93,87,.05) 30%,rgba(255,40,40,.45) 100%)}
#flash.go{animation:flash 1.3s ease-out}
@keyframes flash{0%{opacity:0}12%{opacity:1}35%{opacity:.25}50%{opacity:.8}100%{opacity:0}}
body.hide-pending .u:not(.act):not(.shown),body.hide-pending .row:not(.shown){display:none}
body.hide-pending .act:not(.shown){visibility:hidden}
body.still *,body.still *::after{transition:none!important;animation:none!important}  /* placeholders keep the card's layout stable */
.u.shown.enter{animation:enter .45s ease-out}
@keyframes enter{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.act.st-bad.hit{animation:hit .5s ease-out}
@keyframes hit{0%{transform:translateX(0);background:rgba(255,93,87,.5)}20%{transform:translateX(-6px)}40%{transform:translateX(5px)}
  60%{transform:translateX(-3px)}100%{transform:none}}
.act.cur{outline:2px solid rgba(108,182,255,.55);outline-offset:2px}
.type.typing::after{content:"▋";color:var(--violet);animation:blink .8s steps(1) infinite;margin-left:1px}
@keyframes blink{50%{opacity:0}}
"""

JS = r"""
(function(){
  var q = new URLSearchParams(location.search);
  var speed = Math.min(20, Math.max(0.1, parseFloat(q.get('speed')) || 1));
  var BASE = 1200;
  var body = document.body, tl = document.getElementById('timeline'), svg = document.getElementById('links');
  var banner = document.getElementById('banner'), flash = document.getElementById('flash');
  var scrim = document.getElementById('scrim'), scroller = document.getElementById('scroller');
  var verdict = document.getElementById('verdict'), btn = document.getElementById('replay');
  var units = Array.prototype.slice.call(document.querySelectorAll('.u'));
  var rows = Array.prototype.slice.call(document.querySelectorAll('.row'));
  var run = 0;

  function syncRows(){ rows.forEach(function(r){ r.classList.toggle('shown', !!r.querySelector('.u.shown')); }); }

  function $$(sel, root){ return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function sleep(ms, token){ return new Promise(function(res, rej){ setTimeout(function(){ token === run ? res() : rej('stop'); }, ms / speed); }); }

  function refKey(ref){ if (ref === 'end') return [1e9, 0]; var p = String(ref).split('.'); return [parseInt(p[0], 10), p.length > 1 ? parseInt(p[1], 10) : 0]; }
  function upTo(ref, limit){  // is unit `ref` within ?step=limit
    var a = refKey(ref), b = refKey(limit);
    if (String(limit).indexOf('.') < 0) return a[0] <= b[0];
    return a[0] < b[0] || (a[0] === b[0] && a[1] <= b[1]);
  }

  // ---- connectors from a contradicted commitment span to each revealed contradicting action
  function drawLinks(fresh){
    var keep = {};
    $$('path.link', svg).forEach(function(p){ keep[p.getAttribute('data-k')] = p; });
    var t = tl.getBoundingClientRect();
    svg.setAttribute('viewBox', '0 0 ' + t.width + ' ' + tl.scrollHeight);
    svg.style.height = tl.scrollHeight + 'px';
    var seen = {};
    $$('.act.st-bad').forEach(function(act){
      if (!visible(act)) return;
      (act.getAttribute('data-cids') || '').split(' ').forEach(function(cid){
        var m = document.getElementById('commit-' + cid);
        if (!m || !visible(m)) return;
        var k = cid + '>' + act.id; seen[k] = 1;
        var mr = m.getClientRects(); var r0 = mr[mr.length - 1] || m.getBoundingClientRect();
        var ar = act.getBoundingClientRect();
        var x1 = r0.right - t.left + 2, y1 = r0.top - t.top + r0.height / 2;
        var x2 = ar.left - t.left - 3, y2 = ar.top - t.top + Math.min(ar.height / 2, 20);
        // run along the text line to the edge of the reasoning card, then curve across the gutter
        var card = m.closest('.card'), xe = card ? card.getBoundingClientRect().right - t.left + 6 : x1;
        xe = Math.max(x1, Math.min(xe, x2 - 50));
        var dx = Math.max(24, (x2 - xe) * 0.5);
        var d = 'M' + x1 + ',' + y1 + ' L' + xe + ',' + y1 + ' C' + (xe + dx) + ',' + y1 + ' ' + (x2 - dx) + ',' + y2 + ' ' + x2 + ',' + y2;
        var p = keep[k];
        if (!p){
          p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          p.setAttribute('class', 'link' + (act.hasAttribute('data-alert') ? ' head' : ''));
          p.setAttribute('data-k', k); p.setAttribute('marker-end', 'url(#arrow)');
          svg.appendChild(p);
          if (fresh){ p.setAttribute('d', d); var L = p.getTotalLength(); p.style.setProperty('--len', L); p.classList.add('fresh'); }
        }
        p.setAttribute('d', d);
      });
    });
    Object.keys(keep).forEach(function(k){ if (!seen[k]) keep[k].remove(); });
  }
  function visible(el){ return el.offsetParent !== null && getComputedStyle(el).visibility !== 'hidden'; }

  function brk(act, animate){
    (act.getAttribute('data-cids') || '').split(' ').forEach(function(cid){
      $$('mark.commit').forEach(function(m){
        if ((' ' + m.getAttribute('data-cids') + ' ').indexOf(' ' + cid + ' ') < 0) return;
        if (animate && !m.classList.contains('broken')){ m.classList.remove('flare'); void m.offsetWidth; m.classList.add('flare'); }
        m.classList.add('broken', 'lit');
      });
    });
  }
  function showAlert(act, animate){
    banner.innerHTML = '';
    act.getAttribute('data-alert').split(' ').forEach(function(fid){
      var t = document.getElementById('alert-' + fid); if (t) banner.appendChild(t.content.cloneNode(true));
    });
    banner.classList.remove('show'); void banner.offsetWidth; banner.classList.add('show');
    if (animate){ flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go'); }
  }
  function settle(){ $$('mark.commit.final-ok').forEach(function(m){ m.classList.add('settled', 'lit'); }); }

  function follow(el, smooth){
    var sr = scroller.getBoundingClientRect(), r = el.getBoundingClientRect(), y = scroller.scrollTop;
    var top = r.top - sr.top, bottom = r.bottom - sr.top, h = scroller.clientHeight, hdr = 56;
    var pad = banner.classList.contains('show') ? banner.offsetHeight + 40 : 40;
    var target = y + bottom - h + pad;
    if (r.height > h - hdr - pad) target = Math.min(target, y + top - hdr);
    if (target > y + 1 || top < hdr) scroller.scrollTo({top: Math.max(0, target), behavior: smooth ? 'smooth' : 'auto'});
  }

  // ---- static view (default, ?step=N, or ?step=end with the verdict panel open)
  function renderStatic(limit){
    var showFinal = limit === 'end';
    if (showFinal) limit = null;
    var last = null, lastAlert = null;
    units.forEach(function(u){
      var show = limit == null || upTo(u.getAttribute('data-ref'), limit);
      u.classList.toggle('shown', show);
      if (!show) return;
      last = u;
      if (u.classList.contains('act') && u.classList.contains('st-bad')) brk(u, false);
      if (u.hasAttribute('data-alert')) lastAlert = u;
    });
    syncRows();
    var done = units[units.length - 1].classList.contains('shown');
    if (limit == null){ $$('mark.commit').forEach(function(m){ m.classList.add('lit'); }); }
    else { $$('.say.shown mark.commit').forEach(function(m){ m.classList.add('lit'); }); }
    if (done) settle();
    if (limit != null){
      body.classList.add('hide-pending', 'still');
      if (!done){ verdict.className = 'verdict pending'; verdict.textContent = 'up to step ' + limit; }
      if (lastAlert) showAlert(lastAlert, false);
      if (last) requestAnimationFrame(function(){ follow(last, false); drawLinks(false); });
    }
    drawLinks(false);
    if (showFinal){
      body.classList.add('still');
      var acts = $$('.act.shown'), lastAct = acts[acts.length - 1];
      if (lastAct) requestAnimationFrame(function(){ follow(lastAct, false); drawLinks(false); });
      document.getElementById('final').classList.add('modal'); scrim.classList.add('on');
    }
  }

  // ---- replay
  function typewrite(el, token){
    var nodes = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), n;
    while ((n = w.nextNode())) nodes.push([n, n.nodeValue]);
    var total = nodes.reduce(function(s, x){ return s + x[1].length; }, 0);
    nodes.forEach(function(x){ x[0].nodeValue = ''; });
    var dur = Math.min(4200, Math.max(700, total * 14)) / speed, t0 = performance.now();
    el.classList.add('typing');
    return new Promise(function(res, rej){
      function frame(now){
        if (token !== run){ nodes.forEach(function(x){ x[0].nodeValue = x[1]; }); el.classList.remove('typing'); return rej('stop'); }
        var k = Math.min(total, Math.ceil(total * (now - t0) / dur)), left = k;
        nodes.forEach(function(x){ var c = Math.max(0, Math.min(x[1].length, left)); x[0].nodeValue = x[1].slice(0, c); left -= c; });
        follow(el, false);
        if (k < total) requestAnimationFrame(frame); else { el.classList.remove('typing'); res(); }
      }
      requestAnimationFrame(frame);
    });
  }

  function reset(){
    run++;
    body.classList.add('hide-pending', 'replaying'); body.classList.remove('static', 'still');
    units.forEach(function(u){ u.classList.remove('shown', 'enter', 'hit', 'cur'); });
    syncRows();
    $$('mark.commit').forEach(function(m){ m.classList.remove('lit', 'broken', 'settled', 'flare'); });
    $$('details[open]').forEach(function(d){ d.open = false; });
    $$('path.link', svg).forEach(function(p){ p.remove(); });
    banner.classList.remove('show'); banner.innerHTML = '';
    document.getElementById('final').classList.remove('modal'); scrim.classList.remove('on');
    verdict.className = 'verdict pending'; verdict.textContent = 'replaying…';
    btn.textContent = '↺ Restart';
    scroller.scrollTop = 0;
  }

  async function replay(){
    reset();
    var token = run;
    try {
      await sleep(500, token);
      for (var i = 0; i < units.length; i++){
        var u = units[i], kind = u.getAttribute('data-kind'), isAct = u.classList.contains('act');
        $$('.act.cur').forEach(function(a){ a.classList.remove('cur'); });
        u.classList.add('shown', 'enter');
        syncRows();
        if (u.id === 'final'){
          banner.classList.remove('show'); settle();
          u.classList.add('modal'); scrim.classList.add('on'); body.classList.remove('replaying');
          verdict.className = 'verdict ' + (u.classList.contains('bad') ? 'bad' : 'ok');
          verdict.textContent = verdict.getAttribute('data-final');
          btn.textContent = '↺ Replay';
          drawLinks(false);
          return;
        }
        if (isAct){
          u.classList.add('cur');
          if (u.classList.contains('st-bad')){ u.classList.add('hit'); brk(u, true); }
          follow(u, true); drawLinks(true);
          if (u.hasAttribute('data-alert')){ showAlert(u, true); follow(u, true); await sleep(BASE + 3000, token); }
          else await sleep(u.classList.contains('trivial') ? BASE * 0.55 : BASE, token);
        } else if (kind === 'action'){
          follow(u, true); await sleep(BASE * 0.35, token);
        } else {
          var tw = u.querySelector('.type');
          follow(u, true);
          if (tw) await typewrite(tw, token);
          var marks = $$('mark.commit', u);
          marks.forEach(function(m){ m.classList.add('lit'); });
          drawLinks(false);
          await sleep(kind === 'system' ? BASE * 0.5 : (marks.length ? BASE + 900 : BASE), token);
        }
      }
    } catch (e) { if (e !== 'stop') throw e; }
  }

  btn.addEventListener('click', function(){ replay(); });
  scrim.addEventListener('click', function(){ document.getElementById('final').classList.remove('modal'); scrim.classList.remove('on'); });
  document.addEventListener('keydown', function(e){ if ((e.key === 'r' || e.key === 'R') && !e.metaKey && !e.ctrlKey) replay(); });
  window.addEventListener('resize', function(){ drawLinks(false); });
  document.addEventListener('toggle', function(){ drawLinks(false); }, true);

  if (q.get('replay') === '1') replay();
  else renderStatic(q.get('step'));
})();
"""
