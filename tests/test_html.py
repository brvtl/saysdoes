"""HTML timeline: structure, classes/ids the inline script relies on, alert content, self-containment."""
import os
import re

import pytest

from saysdoes import html
from saysdoes.analyze import analyze
from saysdoes.formats import load
from saysdoes.model import Commitment, Step, Trace

from conftest import REPO, fixture_path

COHERE = os.path.join(REPO, "fixtures", "cohere", "qwen-investigation.jsonl")
CLAUDE_CODE = os.path.join(REPO, "fixtures", "generated", "claude-code-readonly-review.jsonl")


def render(path):
    report = analyze(load(path))
    return report, html.render(report, path)


def test_self_contained():
    _, doc = render(fixture_path("cohere_pi_small.jsonl"))
    assert doc.startswith("<!doctype html>") and doc.rstrip().endswith("</html>")
    assert not re.search(r"<link\b|<img\b|@import|url\(\s*['\"]?(?:https?:)?//|\bsrc=", doc, re.I)
    assert "<script>" in doc and "<style>" in doc
    # neutral wording
    assert "contradiction between stated plan and actions" in doc
    assert not re.search(r"\blie|lying|liar", doc, re.I)


def test_contradiction_structure():
    report, doc = render(fixture_path("cohere_pi_small.jsonl"))
    (f,) = report.findings
    # commitment span highlighted with an id the connectors anchor to, marked as contradicted
    m = re.search(r'<mark class="commit final-bad"[^>]*id="commit-c1"[^>]*>([^<]*)</mark>', doc)
    assert m and m.group(1) == f.commitment.span_text == "without any tool calls"
    # every sub-command is its own row; all contradict no_tools
    rows = re.findall(r'<div class="act u st-(\w+)[^"]*" id="a(\d+-\d+)"', doc)
    assert [r for _, r in rows] == ["4-1", "4-2"] and {s for s, _ in rows} == {"bad"}
    # the alert fires on the high-severity action (metadata endpoint), not the first one
    assert re.search(r'id="a4-2" data-ref="4.2" data-findings="f1" data-cids="c1" data-alert="f1"', doc)
    assert 'data-alert' not in re.search(r'<div class="act[^>]*id="a4-1"[^>]*>', doc).group(0)
    tpl = re.search(r'<template id="alert-f1">(.*?)</template>', doc, re.S).group(1)
    assert "CONTRADICTION" in tpl and "<q>without any tool calls</q>" in tpl and "step 4.2" in tpl
    assert "metadata endpoint" in tpl
    assert 'id="verdict" class="verdict bad"' in doc
    assert 'id="final" class="final u bad"' in doc
    # replay controls and URL params
    assert 'id="replay"' in doc and "▶ Replay" in doc
    for param in ("'replay'", "'speed'", "'step'"):
        assert f"q.get({param})" in doc


def test_says_does_wording():
    _, doc = render(fixture_path("cohere_pi_small.jsonl"))
    tpl = re.search(r'<template id="alert-f1">(.*?)</template>', doc, re.S).group(1)
    assert "step 3 reasoning says <q>without any tool calls</q>" in tpl and "step 4.2 does <b>" in tpl
    final = re.search(r'<section id="final".*?</section>', doc, re.S).group(0)
    assert '<span class="lab">says · step 3 (reasoning)</span>' in final
    assert '<span class="lab">does · steps 4.1–4.2</span>' in final
    assert "What it <b>says</b>" in doc and "What it <b>does</b>" in doc
    assert "showFinal" in doc  # ?step=end opens the verdict panel statically


def test_visible_text_commitment_says_text():
    report = analyze(_synthetic(("user", "x"), ("text", "I won't use any tools for this."),
                                ("action", ("Bash", {"command": "ls"}))))
    (f,) = report.findings
    doc = html.render(report, "t")
    tpl = re.search(r'<template id="alert-f1">(.*?)</template>', doc, re.S).group(1)
    assert f"step {f.commitment.step_index} text says <q>" in tpl
    assert f"says · step {f.commitment.step_index} (text)" in doc


def test_consistent_trace_is_green():
    report, doc = render(fixture_path("clean_anthropic.json"))
    assert report.findings == []
    markup = doc.split("</style>", 1)[1].split("<script>", 1)[0]
    assert "st-bad" not in markup and "final-bad" not in markup and "<template" not in markup
    assert 'id="verdict" class="verdict ok"' in doc and 'class="final u ok"' in doc


def test_claude_code_readonly_fixture():
    report, doc = render(CLAUDE_CODE)
    assert report.findings == []
    assert re.findall(r'<mark class="commit final-ok low"[^>]*>([^<]*)</mark>', doc) == ["read-only", "offline"]
    assert len(re.findall(r'class="act u st-ok"', doc)) == 2
    assert "lower confidence" in doc  # commitments in visible text, not reasoning


def test_reasoning_and_actions_share_a_row():
    _, doc = render(fixture_path("cohere_pi_small.jsonl"))
    row = re.search(r'<div class="row k-reasoning has-do" data-row="3">.*?<div class="cell right">(.*?)</div></div></div>',
                    doc, re.S)
    assert row and 'id="s4"' in row.group(0)


def test_escaping():
    steps = [Step(1, "reasoning", "<script>alert(1)</script> I won't use any tools & stuff", "t"),
             Step(2, "action", "bash: echo '<b>'", "t", tool="bash", args={"command": "echo '<b>'"})]
    report = analyze(Trace("anthropic", steps, source="x<y>.json"))
    doc = html.render(report)
    assert "<script>alert(1)</script>" not in doc and "&lt;script&gt;alert(1)&lt;/script&gt;" in doc
    assert "echo &#x27;&lt;b&gt;&#x27;" in doc and "x&lt;y&gt;.json" in doc


def test_overlapping_spans_are_segmented():
    text = "I won't modify any files or use the network."
    cs = [Commitment("c1", "read_only", "won't modify any files", 1, 2, 24),
          Commitment("c2", "no_network", "won't modify any files or use the network", 1, 2, 43)]
    out = html._highlight(text, cs, {"c2"})
    assert out.count("<mark") == 2
    assert 'data-cids="c1 c2" id="commit-c1"' in out
    assert re.sub(r"<[^>]+>", "", out) == html.esc(text)


def test_describe_and_headline():
    report = analyze(load(fixture_path("cohere_pi_small.jsonl")))
    (f,) = report.findings
    assert html.headline_action(f).ref == "4.2"
    assert html.describe(report.action("4.2")).startswith("curl")  # GET -> network; shown as the command


def test_step_and_final_units_ordered():
    _, doc = render(fixture_path("cohere_pi_small.jsonl"))
    refs = re.findall(r'class="[^"]*\bu\b[^"]*"[^>]*data-ref="([\d.]+|end)"', doc)
    assert refs == ["1", "2", "3", "4", "4.1", "4.2", "5", "end"]


@pytest.mark.skipif(not os.path.exists(COHERE), reason="Cohere trace not present; run scripts/fetch_cohere_trace.sh")
def test_cohere_alert_names_quote_and_put():
    report, doc = render(COHERE)
    (f,) = report.findings
    assert html.headline_action(f).ref == "4.8"
    assert re.search(r'id="a4-8" data-ref="4.8"[^>]*data-alert="f1"', doc)
    tpl = re.search(r'<template id="alert-f1">(.*?)</template>', doc, re.S).group(1)
    assert "step 3 reasoning says <q>without tool calls</q>" in tpl
    assert "step 4.8 does <b>PUT to sanmaohe.oss-cn-beijing.aliyuncs.com</b>" in tpl
    assert "cloud storage" in tpl and "HIGH" in tpl
    assert "show full system prompt" in doc  # long system prompt collapsed


def _synthetic(*items):
    from saysdoes.model import TraceBuilder

    b = TraceBuilder("synthetic")
    for kind, payload in items:
        if kind == "action":
            b.add_action(*payload, "t")
        else:
            b.add(kind, payload, "t")
    return b.build()


def test_temporary_commitment_is_informational():
    report = analyze(_synthetic(("user", "x"), ("reasoning", "For now this is read-only while I profile the cache."),
                                ("action", ("Read", {"file_path": "cache.rs"})),
                                ("action", ("Edit", {"file_path": "cache.rs"}))))
    doc = html.render(report, "t")
    markup = doc.split("</style>", 1)[1].split("<script>", 1)[0]
    assert 'class="commit final-temp"' in markup and "read-only (temporary)" in markup
    assert 'class="sev sev-temp">temporary<' in markup
    assert "st-bad" not in markup and "st-ok" not in markup  # the edit is neither contradicted nor "kept"
    assert "0 commitments checked" in markup


def test_temporary_commitment_contradicted_within_its_phase():
    report = analyze(_synthetic(("user", "x"), ("reasoning", "For now this is read-only while I profile the cache."),
                                ("action", ("Edit", {"file_path": "cache.rs"}))))
    markup = html.render(report, "t").split("</style>", 1)[1].split("<script>", 1)[0]
    assert "st-bad" in markup and "read-only (temporary)" in markup
    assert 'class="sev sev-temp">temporary<' not in markup  # listed as a contradiction, not as informational


def test_hidden_trivial_action_not_marked_kept():
    report = analyze(_synthetic(("user", "x"), ("reasoning", "No tool calls are needed."),
                                ("action", ("bash", {"command": "cd /w && cargo build"}))))
    (f,) = report.findings
    assert f.hidden_trivial == 1
    markup = html.render(report, "t").split("</style>", 1)[1].split("<script>", 1)[0]
    row = re.search(r'<div class="act u st-(\w+) trivial"[^>]*data-ref="3.1"', markup)
    assert row and row.group(1) == "neutral"
