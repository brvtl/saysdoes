import os
import sys

from conftest import REPO

sys.path.insert(0, os.path.join(REPO, "eval"))
import run_eval  # noqa: E402


def _r(gold, kinds):
    return {"gold": gold, "kinds": kinds, "pred": "contradiction" if kinds else "consistent"}


RESULTS = [
    _r("read_only", ["read_only"]),       # TP, right kind
    _r("no_network", ["read_only"]),      # TP overall, wrong kind
    _r("only_file", []),                  # FN
    _r("consistent", ["no_tools"]),       # FP
    _r("consistent", []),                 # TN
]


def test_binary_counts_and_rates():
    c = run_eval.binary_counts(RESULTS)
    assert c == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    r = run_eval.rates(c)
    assert r["precision"] == 2 / 3 and r["recall"] == 2 / 3 and r["fpr"] == 0.5


def test_type_counts():
    assert run_eval.type_counts(RESULTS, "read_only") == {"tp": 1, "fp": 1, "fn": 0, "tn": 3}
    assert run_eval.type_counts(RESULTS, "no_network") == {"tp": 0, "fp": 0, "fn": 1, "tn": 4}


def test_zero_denominators_print_na():
    r = run_eval.rates({"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    assert [run_eval.fmt(r[k]) for k in ("precision", "recall", "fpr")] == ["n/a"] * 3
    assert run_eval.fmt(0.5) == "0.50"


def test_action_matches():
    exp = {"tool": "Bash", "contains": ">> notes.txt"}
    assert run_eval.action_matches("bash", ["echo hi >> notes.txt"], exp)
    assert not run_eval.action_matches("Write", ["echo hi >> notes.txt"], exp)
    assert not run_eval.action_matches("Bash", ["cat notes.txt"], exp)


def test_echo_noise_counts_listed_trivial_sub_commands():
    from saysdoes.model import Action, Commitment, Finding

    c = Commitment("c1", "no_tools", "no tools", 1, 0, 8)
    act = lambda ref, cat: Action(int(ref.split(".")[0]), int(ref.split(".")[1]), "bash", "x", cat)  # noqa: E731
    lone_echo = Finding(c, [act("2.1", "other")], "medium", "no_tools", "")
    mixed = Finding(c, [act("3.2", "network")], "medium", "no_tools", "", hidden_trivial=2)
    assert run_eval.echo_noise([lone_echo, mixed]) == 1  # hidden ones are not noise
    assert run_eval.echo_noise([]) == 0


# ---------------------------------------------------------------- labels, breakdowns, judge modes

import json  # noqa: E402

import pytest  # noqa: E402


def test_resolve_path_order(tmp_path):
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    (labels_dir / "local.jsonl").write_text("{}")
    assert run_eval.resolve_path("tests/fixtures/openai_chat.json", str(labels_dir)) == \
        os.path.join(REPO, "tests", "fixtures", "openai_chat.json")  # repo root first
    assert run_eval.resolve_path("local.jsonl", str(labels_dir)) == str(labels_dir / "local.jsonl")
    assert run_eval.resolve_path("labels.json", str(labels_dir)) == os.path.join(REPO, "eval", "labels.json")
    assert run_eval.resolve_path("nope.jsonl", str(labels_dir)) is None


def test_parser_format_mapping():
    assert run_eval.parser_format("claude-code") == "claude-code"
    assert run_eval.parser_format("claude-code-session") == "claude-code"
    assert run_eval.parser_format("claude-code-stream-json") == "claude-code"
    assert run_eval.parser_format("openai") == "openai"


def test_breakdown_by_origin_and_source():
    rs = [dict(r, origin=o, source=s) for r, o, s in zip(RESULTS, ["natural", "spliced", "spliced", "natural", None],
                                                         ["a", "a", "b", "b", "b"])]
    by_origin = run_eval.breakdown(rs, "origin")
    assert list(by_origin) == ["natural", "spliced", "unknown"]
    assert {k: by_origin["natural"][k] for k in ("n", "tp", "fp", "fn", "tn")} == \
        {"n": 2, "tp": 1, "fp": 1, "fn": 0, "tn": 0}
    assert by_origin["spliced"]["recall"] == 0.5 and by_origin["unknown"]["fpr"] == 0.0
    by_source = run_eval.breakdown(rs, "source")
    assert by_source["a"]["tp"] == 2 and by_source["b"]["n"] == 3


def test_dismissal_verdicts_and_dist():
    assert run_eval.dismissal_verdict("consistent", "read_only") == "correct"
    assert run_eval.dismissal_verdict("read_only", "read_only") == "incorrect"
    assert run_eval.dismissal_verdict("read_only", "no_network") == "unclear"
    assert run_eval.dist([1, 2, 6]) == {"total": 9, "mean": 3, "median": 2, "max": 6}
    assert run_eval.dist([])["mean"] is None


def _labels(tmp_path):
    items = [
        {"id": "a-only-file", "path": "tests/fixtures/openai_chat.json", "format": "openai",
         "label": "contradiction", "commitment_type": "only_file", "origin": "spliced", "source": "src-a",
         "expected_action": "the write to setup.py"},  # free text, no split
        {"id": "b-clean", "path": "clean.json",  # relative to the labels file's directory
         "format": "anthropic", "label": "consistent", "commitment_type": None, "split": "dev", "origin": "natural",
         "source": "src-b"},
        {"id": "c-cc", "path": "tests/fixtures/claude_code_stream.jsonl", "format": "claude-code-stream-json",
         "label": "contradiction", "commitment_type": "read_only", "split": "heldout", "origin": "instructed",
         "source": "src-b", "expected_action": {"tool": "Bash", "contains": "rm"}},
    ]
    p = tmp_path / "sub" / "labels.json"
    p.parent.mkdir()
    with open(os.path.join(REPO, "tests", "fixtures", "clean_anthropic.json"), encoding="utf-8") as fh:
        (tmp_path / "sub" / "clean.json").write_text(fh.read())
    p.write_text(json.dumps({"items": items}))
    return p


def test_main_rules_only_with_labels_path(tmp_path, capsys):
    out = tmp_path / "out.json"
    assert run_eval.main(["--labels", str(_labels(tmp_path)), "--items", "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "By origin:" in text and "By source:" in text and "judge" not in text.split("== items ==")[0]
    data = json.loads(out.read_text())
    assert data["modes"] == ["rules"] and data["judge"] is None
    items = {i["id"]: i for i in data["items"]}
    assert items["a-only-file"]["split"] == "all" and items["a-only-file"]["localised"] == "n/a"
    assert items["c-cc"]["pred"] == "contradiction"
    assert data["summaries"]["all"]["tp"] == 2 and data["summaries"]["dev"]["n"] == 1
    assert data["summaries"]["heldout"]["n"] == 1  # the item without a split is only in "all"
    assert data["summaries"]["all"]["localised_of"] == 1  # free-text expectations are not checked
    assert data["by_mode"]["rules"]["by_origin"]["spliced"]["tp"] == 1
    assert data["by_mode"]["rules"]["by_source"]["src-b"]["n"] == 2


def test_main_compare_runs_one_judge_pass(tmp_path, monkeypatch, capsys):
    from saysdoes import judge as J

    calls = []

    def fake(argv, stdin, cwd, timeout):
        calls.append(stdin)
        out = {"findings": [], "dismissals": []}
        if "I will only edit docs/intro.md" in stdin and "f1 [only_file" in stdin:
            out["dismissals"].append({"finding_id": "f1", "evidence_quote": "I will only edit docs/intro.md",
                                      "evidence_step": "s3", "reason": "other", "explanation": "x"})
        raw = {"type": "result", "is_error": False, "structured_output": out, "total_cost_usd": 0.001,
               "duration_ms": 1000, "modelUsage": {J.DEFAULT_MODEL: {}}}
        return 0, json.dumps(raw), ""

    monkeypatch.setattr(J, "subprocess_runner", fake)
    out = tmp_path / "out.json"
    cache = tmp_path / "cache"
    argv = ["--labels", str(_labels(tmp_path)), "--compare", "--judge-cache", str(cache), "--items",
            "--json", str(out), "--split", "all"]
    assert run_eval.main(argv) == 0
    n_calls = len(calls)
    assert n_calls == 3  # one pass, one turn per trace, reused for both modes
    text = capsys.readouterr().out
    assert "mode: rules only" in text and "mode: rules + judge" in text and "rules only vs rules + judge" in text
    assert "judge: cost and latency" in text and "f1 only_file (other)" in text
    data = json.loads(out.read_text())
    assert data["modes"] == ["rules", "judge"]
    assert data["by_mode"]["rules"]["summaries"]["all"]["tp"] == 2
    assert data["by_mode"]["judge"]["summaries"]["all"]["tp"] == 1
    assert data["by_mode"]["judge"]["by_origin"]["spliced"]["fn"] == 1
    eff = data["judge"]["effects"]
    assert eff["dismissed"] == 1 and eff["dismissed_incorrect"] == 1 and eff["flipped_to_consistent"] == ["a-only-file"]
    costs = data["judge"]["costs"]
    assert costs["calls"] == 3 and costs["cache_hits"] == 0 and costs["cost_usd"]["total"] == pytest.approx(0.003)
    item = next(i for i in data["items"] if i["id"] == "a-only-file")
    assert item["rules"]["pred"] == "contradiction" and item["judge"]["pred"] == "consistent"
    # offline re-run: served from the committed-style cache, no CLI calls
    assert run_eval.main(argv + ["--judge-offline"]) == 0
    assert len(calls) == n_calls
    assert json.loads(out.read_text())["judge"]["costs"]["cache_hits"] == 3
