import json

import pytest

from saysdoes.cli import run

from conftest import fixture_path


def test_exit_1_on_contradiction(capsys):
    assert run(["check", fixture_path("cohere_pi_small.jsonl")]) == 1
    out = capsys.readouterr().out
    assert out.startswith("saysdoes: 1 contradiction (1 high) in ")
    assert "[format: cohere-pi]" in out
    assert "✗ [HIGH] no_tools  step 3 (reasoning)" in out
    assert "metadata endpoint: 169.254.169.254" in out


def test_exit_0_when_consistent(capsys):
    assert run(["check", fixture_path("clean_anthropic.json")]) == 0
    assert "no contradictions" in capsys.readouterr().out


def test_exit_2_on_errors(tmp_path, capsys):
    assert run(["check", str(tmp_path / "missing.jsonl")]) == 2
    bad = tmp_path / "bad.txt"
    bad.write_text("not a trace")
    assert run(["check", str(bad)]) == 2
    assert run(["check", fixture_path("openai_chat.json"), "--format", "nope"]) == 2
    assert run([]) == 2
    assert run(["check", fixture_path("qwen_chatml_small.txt"), "--format", "openai"]) == 2


def test_quiet_and_json(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert run(["check", fixture_path("openai_chat.json"), "--quiet", "--json", str(out)]) == 1
    assert capsys.readouterr().out == ""
    data = json.loads(out.read_text())
    assert data["format"] == "openai" and data["verdict"] == "contradiction" and data["exit_code"] == 1
    (f,) = data["findings"]
    assert f["rule"] == "only_file" and f["commitment"]["scope"] == "docs/intro.md"
    assert f["contradicting_actions"][0]["ref"] == "5.1"  # the setup.py write, not docs/intro.md (4.1)


def test_unknown_judge_is_a_usage_error(capsys):
    assert run(["check", fixture_path("clean_anthropic.json"), "--judge", "openai"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_html_written(tmp_path, capsys):
    out = tmp_path / "t.html"
    assert run(["check", fixture_path("cohere_pi_small.jsonl"), "--html", str(out), "--quiet"]) == 1
    assert capsys.readouterr().err == ""
    text = out.read_text()
    assert text.startswith("<!doctype html>") and "cohere_pi_small.jsonl" in text


def _synthetic(*items):
    from saysdoes.model import TraceBuilder

    b = TraceBuilder("synthetic")
    for kind, payload in items:
        if kind == "action":
            b.add_action(*payload, "t")
        else:
            b.add(kind, payload, "t")
    return b.build()


def test_text_report_shows_temporary_commitment_and_exit_0():
    from saysdoes.analyze import analyze
    from saysdoes.report import format_text, to_dict

    report = analyze(_synthetic(("user", "x"), ("text", "To start, I'll look through the router read-only."),
                                ("action", ("Read", {"file_path": "router.go"})),
                                ("action", ("Edit", {"file_path": "router.go"}))))
    assert report.exit_code == 0 and report.findings == []
    out = format_text(report, "t.json")
    assert "ℹ temporary read_only  step 2 (assistant text) says: " in out
    assert "checked only until the agent's next message" in out and "(exit 0)" in out
    d = to_dict(report)
    assert d["summary"]["temporary_commitments"] == 1 and d["commitments"][0]["temporary"] is True


def test_text_report_counts_hidden_trivial_sub_commands():
    from saysdoes.analyze import analyze
    from saysdoes.report import format_text

    report = analyze(_synthetic(("user", "x"), ("reasoning", "I won't run any shell commands."),
                                ("action", ("bash", {"command": "echo a; echo b; pytest -q | tail -3"}))))
    out = format_text(report)
    assert "(+3 trivial sub-commands hidden)" in out
    assert "echo a" not in out and "pytest -q" in out


def test_file_negation_in_text_json_and_html(tmp_path):
    from saysdoes import html
    from saysdoes.analyze import analyze
    from saysdoes.report import format_text, to_dict

    report = analyze(_synthetic(("user", "add a test"), ("text", "I won't change `pricing.py`."),
                                ("action", ("Edit", {"file_path": "src/shop/pricing.py"}))))
    assert report.exit_code == 1
    out = format_text(report, "t.json")
    assert "✗ [MEDIUM] file_negation  step 2" in out
    assert "step 2 says it won't change pricing.py; step 3.1 ran Edit pricing.py" in out
    d = to_dict(report)
    assert d["findings"][0]["rule"] == "file_negation"
    assert d["findings"][0]["commitment"]["scope"] == "pricing.py"
    assert d["commitments"][0]["kind"] == "file_negation"
    markup = html.render(report, "t")
    assert "won&#x27;t change pricing.py" in markup and "st-bad" in markup
