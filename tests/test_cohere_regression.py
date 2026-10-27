"""Regression test on Cohere's published trace (fetched by scripts/fetch_cohere_trace.sh; not committed)."""
import json
import os

import pytest

from saysdoes.analyze import analyze
from saysdoes.cli import run
from saysdoes.formats import load

from conftest import REPO

TRACE = os.path.join(REPO, "fixtures", "cohere", "qwen-investigation.jsonl")

pytestmark = pytest.mark.skipif(not os.path.exists(TRACE),
                                reason="Cohere trace not present; run scripts/fetch_cohere_trace.sh")


def test_cohere_trace_report(tmp_path, capsys):
    trace = load(TRACE)
    assert trace.format == "cohere-pi"
    report = analyze(trace)

    no_tools = [f for f in report.findings if f.rule == "no_tools"]
    assert len(no_tools) == 1
    f = no_tools[0]
    assert "without tool calls" in f.commitment.span_text
    step = trace.step(f.commitment.step_index)
    assert step.kind == "reasoning"
    assert step.text[f.commitment.char_start:f.commitment.char_end] == f.commitment.span_text
    assert f.severity == "high"

    acts = f.contradicting_actions
    raws = [a.raw for a in acts]
    assert any(a.category == "fs_list" and a.raw.startswith("ls -la /tmp") for a in acts)
    assert any(a.category == "env_probe" and a.raw.startswith("which ") for a in acts)
    assert any(a.category == "fs_read" and "/etc/resolv.conf" in a.detail.get("reads", []) for a in acts)
    uploads = [a for a in acts if a.category == "network_upload"]
    assert len(uploads) == 1, raws
    up = uploads[0]
    assert up.detail["method"] == "PUT"
    assert "sanmaohe.oss-cn-beijing.aliyuncs.com" in up.detail["hosts"]
    assert up.detail["cloud_storage"] == ["aliyuncs.com"]

    out_json = tmp_path / "cohere.json"
    assert run(["check", TRACE, "--json", str(out_json)]) == 1
    out = capsys.readouterr().out
    assert "1 contradiction (1 high)" in out and "[format: cohere-pi]" in out
    assert "without tool calls" in out
    data = json.loads(out_json.read_text())
    assert data["format"] == "cohere-pi" and data["model"] == "Qwen-3.8-Flash-Next"
    assert data["summary"]["findings"] == 1 and data["summary"]["high"] == 1
