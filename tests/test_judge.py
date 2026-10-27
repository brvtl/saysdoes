import json
import os
import subprocess

import pytest

from saysdoes import judge as J
from saysdoes.analyze import analyze
from saysdoes.cli import run
from saysdoes.html import render
from saysdoes.model import TraceBuilder
from saysdoes.report import format_text, to_dict

from conftest import fixture_path


def two_turn_trace():
    """Turn 1: a rule finding (read-only, then a scratch write). Turn 2: a commitment the regexes miss."""
    b = TraceBuilder("synthetic")
    b.add("user", "Please review a.py. Scratch files in /tmp are fine.", "t")              # s1
    b.add("reasoning", "Plan: I won't modify any files during this review.", "t")           # s2
    b.add_action("Bash", {"command": "cat a.py"}, "t", call_id="c1")                       # s3
    b.attach_result("c1", "print('hello world from a.py')")
    b.add_action("Bash", {"command": "echo notes > /tmp/scratch.txt"}, "t")                # s4
    b.add("text", "Done reviewing.", "t")                                                   # s5
    b.add("user", "Now fix the bug.", "t")                                                  # s6
    b.add("reasoning", "I'll keep the settings file exactly as it is and stick to code.", "t")  # s7
    b.add_action("Edit", {"file_path": "settings.toml", "old_string": "a", "new_string": "b"}, "t")  # s8
    b.add("text", "Fixed.", "t")                                                            # s9
    return b.build()


FIND_S7 = {"kind": "file_negation", "scope": "settings.toml",
           "commitment_quote": "keep the settings file exactly as it is", "commitment_step": "s7",
           "action_steps": ["s8"], "explanation": "It said it would keep the settings file unchanged, then edited it."}
DISMISS_F1 = {"finding_id": "f1", "evidence_quote": "Scratch files in /tmp are fine", "evidence_step": "s1",
              "reason": "not_a_violation", "explanation": "The write goes to a scratch file in /tmp."}


def cli_result(output, model="claude-haiku-5-5", cost=0.002, duration=1500, **extra):
    raw = {"type": "result", "subtype": "success", "is_error": False, "structured_output": output,
           "total_cost_usd": cost, "duration_ms": duration, "session_id": "sess", "uuid": "u",
           "modelUsage": {model: {"costUSD": cost, "canonicalModel": model}}}
    raw.update(extra)
    return raw


class FakeRunner:
    """Answers per turn: `by_step` maps a step ref that must appear in the prompt to the structured output."""

    def __init__(self, by_step=None, raw=None, stdout=None, exc=None, model="claude-haiku-5-5"):
        self.by_step, self.raw, self.stdout, self.exc, self.model = by_step or {}, raw, stdout, exc, model
        self.calls = []

    def __call__(self, argv, stdin, cwd, timeout):
        self.calls.append({"argv": argv, "stdin": stdin, "cwd": cwd, "timeout": timeout,
                           "cwd_files": os.listdir(cwd)})
        if self.exc:
            raise self.exc
        if self.stdout is not None:
            return 0, self.stdout, ""
        if self.raw is not None:
            return 0, json.dumps(self.raw), ""
        out = next((v for k, v in self.by_step.items() if f"\n{k} [" in stdin), {"findings": [], "dismissals": []})
        return 0, json.dumps(cli_result(out, self.model)), ""


def judge(tmp_path, runner, **kw):
    kw.setdefault("cache_dir", str(tmp_path / "cache"))
    return J.ClaudeJudge(runner=runner, binary="/fake/claude", **kw)


# ---------------------------------------------------------------- construction, CLI arguments


def test_make_judge():
    assert J.make_judge("none") is None and J.make_judge(None) is None
    j = J.make_judge("claude", cache_dir=None)
    assert isinstance(j, J.ClaudeJudge)
    assert (j.model, j.effort) == (J.DEFAULT_MODEL, J.DEFAULT_EFFORT)
    assert j.binary == "/nonexistent/claude-for-tests"  # $CLAUDE_BIN wins over PATH
    with pytest.raises(ValueError):
        J.make_judge("openai")


def test_cli_invocation_shape(tmp_path):
    r = FakeRunner()
    analyze(two_turn_trace(), judge(tmp_path, r, model="claude-sonnet-5-5", effort="medium", workers=1))
    assert len(r.calls) == 2  # one call per user turn with agent text
    call = r.calls[0]
    argv = call["argv"]
    assert argv[:4] == ["/fake/claude", "-p", "--output-format", "json"]
    flag = lambda name: argv[argv.index(name) + 1]  # noqa: E731
    assert flag("--model") == "claude-sonnet-5-5" and flag("--effort") == "medium"
    assert flag("--tools") == "" and flag("--system-prompt") == J.SYSTEM_PROMPT
    assert json.loads(flag("--json-schema")) == J.SCHEMA
    for f in ("--no-session-persistence", "--disable-slash-commands", "--strict-mcp-config"):
        assert f in argv
    assert "s2 [reasoning]" in call["stdin"]  # the user prompt goes to stdin, not argv
    assert call["cwd"] != os.getcwd() and call["cwd_files"] == [] and not os.path.exists(call["cwd"])
    assert call["timeout"] == J.DEFAULT_TIMEOUT


# ---------------------------------------------------------------- turns and rendering


def test_turn_units_skip_turns_without_agent_text():
    b = TraceBuilder("synthetic")
    b.add("system", "sys", "t")
    b.add("user", "one", "t")
    b.add_action("Bash", {"command": "ls"}, "t")
    b.add("user", "two", "t")
    b.add("text", "ok", "t")
    units = J.turn_units(b.build().steps)
    assert [[s.index for s in u] for u in units] == [[4, 5]]


def test_render_turn_refs_actions_findings_and_limits():
    r = analyze(two_turn_trace())
    (f1,) = r.findings
    assert f1.id == "f1" and f1.source == "rules" and f1.commitment.kind == "read_only"
    u1, u2 = J.turn_units(r.trace.steps)
    p = J.render_turn(u1, r.actions, [f1], 9, "synthetic")
    assert "Turn: steps s1-s5 of a 9-step trace" in p
    assert "s2 [reasoning] Plan: I won't modify any files" in p
    assert "s3 [action Bash/fs_read] cat a.py" in p and "result: print('hello world from a.py')" in p
    assert "s4 [action Bash/fs_write] echo notes > /tmp/scratch.txt (writes: /tmp/scratch.txt)" in p
    assert 'f1 [read_only] commitment at s2: "' in p and "-> contradicting actions: s4.1" in p
    assert f"over {J.LIMIT_AGENT} chars" in p and f"tool output over {J.LIMIT_RESULT} chars" in p
    p2 = J.render_turn(u2, r.actions, [], 9, "synthetic")
    assert "<deterministic_findings>\n(none)\n</deterministic_findings>" in p2
    assert "s1 [" not in p2  # only this turn's steps

    b = TraceBuilder("synthetic")
    b.add("user", "go", "t")
    b.add("reasoning", "A" * 5000 + "MIDDLE" + "B" * 5000, "t")
    b.add_action("Bash", {"command": "ls && cat x && " + "y" * 2000}, "t")
    r = analyze(b.build())
    p = J.render_turn(J.turn_units(r.trace.steps)[0], r.actions, [], 3, "synthetic")
    assert "MIDDLE" not in p and "chars omitted …]" in p
    assert "s3 [action Bash] ls && cat x" in p and "\n    s3.1 fs_list: ls" in p and "\n    s3.2 fs_read: cat x" in p


# ---------------------------------------------------------------- citation validation


def test_locate_normalises_whitespace_quotes_and_case():
    text = "Plan:  I’ll `only` edit\n  config.py and nothing else."
    s, e = J.locate("i'll only edit config.py", text)
    assert text[s:e] == "I’ll `only` edit\n  config.py"
    assert J.locate("…edit config.py and nothing else.", text) is not None
    assert J.locate("edit it", text) is None  # too short
    assert J.locate("edit settings.py", text) is None
    assert J.locate("only edit … nothing else", text) is None  # no ellipsis inside quotes


def test_validate_finding_accepts_and_rejects():
    r = analyze(two_turn_trace())
    u1, u2 = J.turn_units(r.trace.steps)
    c, acts = J.validate_finding(FIND_S7, u2, r)
    assert (c.step_index, c.kind, c.scope) == (7, "file_negation", "settings.toml")
    assert r.trace.step(7).text[c.char_start:c.char_end] == "keep the settings file exactly as it is"
    assert [a.ref for a in acts] == ["8.1"] and c.confidence == "high"
    bad = [
        ({"kind": "bogus"}, "unknown kind"),
        ({"commitment_quote": "keep the config untouched"}, "commitment_quote not found"),
        ({"commitment_quote": "keep it"}, "commitment_quote not found"),
        ({"commitment_step": "s8"}, "not agent text/reasoning"),
        ({"commitment_step": "s2"}, "not in this turn"),
        ({"commitment_step": "seven"}, "bad commitment_step"),
        ({"action_steps": []}, "no action_steps"),
        ({"action_steps": ["s9"]}, "not an action step"),
        ({"action_steps": ["s4"]}, "not an action step in this turn"),
        ({"action_steps": ["s8.3"]}, "no sub-action"),
    ]
    for patch, reason in bad:
        got = J.validate_finding({**FIND_S7, **patch}, u2, r)
        assert isinstance(got, str) and reason in got, (patch, got)
    # actions before the commitment never count, even in the same turn
    early = {**FIND_S7, "commitment_step": "s5", "commitment_quote": "Done reviewing.", "action_steps": ["s4"]}
    early_bad = J.validate_finding({**early, "commitment_quote": "Done reviewing"}, u1, r)
    assert isinstance(early_bad, str) and "not after the commitment" in early_bad


def test_validate_finding_narrows_whole_step_to_violating_sub_actions():
    b = TraceBuilder("synthetic")
    b.add("user", "go", "t")
    b.add("reasoning", "I am going to stay entirely offline for this one.", "t")
    b.add_action("Bash", {"command": "ls && echo hi && curl https://example.com"}, "t")
    r = analyze(b.build())
    item = {"kind": "no_network", "scope": "", "commitment_quote": "stay entirely offline for this one",
            "commitment_step": "s2", "action_steps": ["s3"], "explanation": "x"}
    _, acts = J.validate_finding(item, J.turn_units(r.trace.steps)[0], r)
    assert [a.ref for a in acts] == ["3.3"]
    _, acts = J.validate_finding({**item, "kind": "other"}, J.turn_units(r.trace.steps)[0], r)
    assert [a.ref for a in acts] == ["3.1", "3.3"]  # unknown kind: every non-trivial sub-action


def test_validate_dismissal():
    r = analyze(two_turn_trace())
    u1, u2 = J.turn_units(r.trace.steps)
    by_id = {"f1": r.findings[0]}
    assert J.validate_dismissal(DISMISS_F1, u1, by_id, r) is None
    in_result = {**DISMISS_F1, "evidence_step": "s3", "evidence_quote": "hello world from a.py"}
    assert J.validate_dismissal(in_result, u1, by_id, r) is None  # tool output is evidence too
    assert "not a deterministic finding" in J.validate_dismissal({**DISMISS_F1, "finding_id": "f9"}, u1, by_id, r)
    assert "not in this turn" in J.validate_dismissal({**DISMISS_F1, "evidence_step": "s7"}, u1, by_id, r)
    assert "evidence_quote not found" in J.validate_dismissal({**DISMISS_F1, "evidence_quote": "x" * 20}, u1,
                                                              by_id, r)
    assert "not a deterministic finding" in J.validate_dismissal(DISMISS_F1, u2, {}, r)


# ---------------------------------------------------------------- applying results


def test_judge_adds_and_dismisses_findings(tmp_path):
    trace = two_turn_trace()
    assert analyze(trace).exit_code == 1  # rules: the scratch write contradicts "won't modify any files"
    runner = FakeRunner({"s2": {"findings": [], "dismissals": [DISMISS_F1]},
                         "s7": {"findings": [FIND_S7], "dismissals": []}})
    r = analyze(trace, judge(tmp_path, runner))
    (f,) = r.findings
    assert (f.id, f.source, f.rule, f.commitment.kind) == ("j1", "judge", "judge:claude", "file_negation")
    assert f.severity == "medium" and f.explanation.startswith("Model judge (claude): It said")
    assert r.exit_code == 1
    j = r.judge
    assert j["added"] == ["j1"] and [d["finding_id"] for d in j["dismissed"]] == ["f1"]
    d = j["dismissed"][0]
    assert d["reason"] == "not_a_violation" and d["evidence_step"] == 1 and d["finding"]["source"] == "rules"
    data = to_dict(r)
    assert data["findings"][0]["source"] == "judge" and data["judge"]["dismissed"][0]["finding_id"] == "f1"
    text = format_text(r)
    assert "file_negation settings.toml (judge)" in text and "Model judge (claude)" in text
    assert "– dismissed by judge: f1 read_only" in text and "judge: claude claude-haiku-5-5 (low)" in text
    html = render(r)
    assert "model judge" in html and "dismissed" in html


def test_dismissal_alone_changes_exit_code(tmp_path):
    runner = FakeRunner({"s2": {"findings": [], "dismissals": [DISMISS_F1]}})
    r = analyze(two_turn_trace(), judge(tmp_path, runner))
    assert r.findings == [] and r.exit_code == 0


def test_invalid_items_are_rejected_and_recorded(tmp_path):
    bad_find = {**FIND_S7, "commitment_quote": "a sentence that is not there"}
    dup = {**FIND_S7, "kind": "read_only", "scope": "", "commitment_step": "s2",
           "commitment_quote": "I won't modify any files", "action_steps": ["s4"]}
    runner = FakeRunner({"s2": {"findings": [dup], "dismissals": [{**DISMISS_F1, "finding_id": "f7"},
                                                                    DISMISS_F1, DISMISS_F1]},
                         "s7": {"findings": [bad_find], "dismissals": []}})
    r = analyze(two_turn_trace(), judge(tmp_path, runner))
    reasons = sorted(x["reason"] for x in r.judge["rejected"])
    assert any("duplicates finding f1" in x for x in reasons)
    assert any("'f7' is not a deterministic finding" in x for x in reasons)
    assert any("f1 already dismissed" in x for x in reasons)
    assert any("commitment_quote not found in s7" in x for x in reasons)
    assert len(r.judge["rejected"]) == 4 and r.judge["added"] == [] and len(r.judge["dismissed"]) == 1


# ---------------------------------------------------------------- cache


def test_cache_hit_miss_and_key(tmp_path):
    runner = FakeRunner({"s7": {"findings": [FIND_S7], "dismissals": []}})
    j = judge(tmp_path, runner)
    r1 = analyze(two_turn_trace(), j)
    assert len(runner.calls) == 2 and r1.judge["calls"] == 2 and r1.judge["cache_hits"] == 0
    keys = [t["key"] for t in r1.judge["per_turn"]]
    for k in keys:
        path = tmp_path / "cache" / k[:2] / f"{k}.json"
        stored = json.loads(path.read_text())
        assert stored["type"] == "result" and "session_id" not in stored and "uuid" not in stored
    r2 = analyze(two_turn_trace(), judge(tmp_path, runner))
    assert len(runner.calls) == 2  # no new CLI calls
    assert r2.judge["calls"] == 0 and r2.judge["cache_hits"] == 2
    assert [f.id for f in r2.findings] == [f.id for f in r1.findings]
    # every input of the key matters
    base = ("claude", "m", "low", "v1", "sys", "prompt")
    k0 = J.cache_key(*base)
    for i in range(len(base)):
        changed = list(base)
        changed[i] += "x"
        assert J.cache_key(*changed) != k0
    assert set(keys) == {J.cache_key("claude", J.DEFAULT_MODEL, J.DEFAULT_EFFORT, J.PROMPT_VERSION, J.SYSTEM_PROMPT,
                                     c["stdin"]) for c in runner.calls}
    # a different model or effort misses the cache
    analyze(two_turn_trace(), judge(tmp_path, FakeRunner(model="claude-sonnet-5-5"), model="claude-sonnet-5-5"))
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 4


def test_offline_uses_cache_and_records_misses(tmp_path):
    runner = FakeRunner({"s7": {"findings": [FIND_S7], "dismissals": []}})
    analyze(two_turn_trace(), judge(tmp_path, runner))
    offline = FakeRunner()
    r = analyze(two_turn_trace(), judge(tmp_path, offline, offline=True))
    assert offline.calls == [] and r.judge["cache_hits"] == 2 and r.judge["added"] == ["j1"]
    warnings = []
    r = analyze(two_turn_trace(), judge(tmp_path, offline, offline=True, cache_dir=str(tmp_path / "empty")),
                warnings.append)
    assert offline.calls == [] and r.judge["calls"] == 0
    assert [e["error"] for e in r.judge["errors"]] == ["cache miss with --judge-offline"] * 2
    assert len(warnings) == 2 and "rules-only" in warnings[0]
    assert [f.id for f in r.findings] == ["f1"] and r.exit_code == 1  # rules-only result kept


# ---------------------------------------------------------------- failures fall back to rules-only


@pytest.mark.parametrize("runner, error", [
    (FakeRunner(exc=subprocess.TimeoutExpired("claude", 5)), "timed out"),
    (FakeRunner(stdout="not json at all"), "not JSON"),
    (FakeRunner(raw={"type": "result", "is_error": True, "result": "rate limited", "modelUsage": {}}),
     "rate limited"),
    (FakeRunner(raw=cli_result({"findings": []})), "no valid structured_output"),
    (FakeRunner(model="claude-opus-5-5"), "requested model claude-haiku-5-5 but the CLI used claude-opus-5-5"),
    (FakeRunner(raw={**cli_result({"findings": [], "dismissals": []}), "modelUsage": {}}), "no modelUsage"),
    (FakeRunner(exc=OSError("exec format error")), "OSError"),
])
def test_failures_fall_back_to_rules(tmp_path, runner, error):
    warnings = []
    r = analyze(two_turn_trace(), judge(tmp_path, runner), warnings.append)
    assert [f.id for f in r.findings] == ["f1"] and r.exit_code == 1
    assert len(r.judge["errors"]) == 2 and error in r.judge["errors"][0]["error"]
    assert warnings and r.judge["added"] == [] and r.judge["total_cost_usd"] == 0
    assert not (tmp_path / "cache").exists()  # failed results are not cached


def test_missing_binary(tmp_path):
    j = J.ClaudeJudge(cache_dir=str(tmp_path / "c"), env={}, runner=FakeRunner())
    j.binary = None
    r = analyze(two_turn_trace(), j, lambda m: None)
    assert "claude CLI not found" in r.judge["errors"][0]["error"] and r.exit_code == 1


def test_model_alias_matches_model_usage():
    usage = {"claude-haiku-5-5": {"canonicalModel": "claude-haiku-5-5"}}
    assert J._model_matches("haiku", usage) == ["claude-haiku-5-5"]
    assert J._model_matches("claude-haiku-5-5", usage) == ["claude-haiku-5-5"]
    assert J._model_matches("sonnet", usage) == []


# ---------------------------------------------------------------- cost and latency


def test_cost_aggregation_separates_cached_and_this_run(tmp_path):
    analyze(two_turn_trace(), judge(tmp_path, FakeRunner(), workers=1))  # fills the cache for both turns
    # Drop one cached entry so the second run has one hit and one fresh call with a different cost.
    first = sorted((tmp_path / "cache").rglob("*.json"))[0]
    hit_cost = json.loads(first.read_text())["total_cost_usd"]
    other = [p for p in (tmp_path / "cache").rglob("*.json") if p != first][0]
    other.unlink()

    class Pricier(FakeRunner):
        def __call__(self, argv, stdin, cwd, timeout):
            self.calls.append(stdin)
            return 0, json.dumps(cli_result({"findings": [], "dismissals": []}, cost=0.01, duration=4000)), ""

    r = analyze(two_turn_trace(), judge(tmp_path, Pricier()))
    j = r.judge
    assert j["calls"] == 1 and j["cache_hits"] == 1
    assert j["total_cost_usd"] == pytest.approx(hit_cost + 0.01)
    assert j["cost_usd_this_run"] == pytest.approx(0.01)
    assert j["duration_ms_total"] == 1500 + 4000 and j["duration_ms_this_run"] == 4000
    assert j["wall_clock_ms"] >= 0 and j["models_used"] == ["claude-haiku-5-5"]
    assert "API-list-price equivalent" in j["cost_note"]
    assert sorted(t["cached"] for t in j["per_turn"]) == [False, True]


# ---------------------------------------------------------------- CLI


def test_cli_judge_flags_and_exit_codes(tmp_path, monkeypatch, capsys):
    trace = fixture_path("clean_anthropic.json")
    assert run(["check", trace]) == 0
    # offline with an empty cache: warns, keeps the rules-only result
    out = tmp_path / "r.json"
    assert run(["check", trace, "--judge", "claude", "--judge-offline", "--judge-cache", str(tmp_path / "c"),
                "--json", str(out), "--quiet"]) == 0
    assert "cache miss with --judge-offline" in capsys.readouterr().err
    j = json.loads(out.read_text())["judge"]
    assert j["backend"] == "claude" and j["errors"] and j["offline"] is True
    assert json.loads(open(out).read())["findings"] == []
    # without --judge the JSON says so
    run(["check", trace, "--json", str(out), "--quiet"])
    assert json.loads(out.read_text())["judge"] == {"backend": "none"}
    # a fake CLI that adds a finding flips the exit code; model/effort flags reach the CLI
    r = analyze(__import__("saysdoes.formats", fromlist=["load"]).load(trace))
    step = next(s for s in r.trace.steps if s.kind in ("reasoning", "text"))
    act = next((s for s in r.trace.steps if s.kind == "action" and s.index > step.index), None)
    if act is None:
        pytest.skip("fixture has no action after agent text")
    quote = step.text.strip()[:40]
    runner = FakeRunner({f"s{step.index}": {"findings": [{"kind": "other", "scope": "", "commitment_quote": quote,
                                                           "commitment_step": f"s{step.index}",
                                                           "action_steps": [f"s{act.index}"],
                                                           "explanation": "x"}], "dismissals": []}},
                        model="claude-sonnet-5-5")
    monkeypatch.setattr(J, "subprocess_runner", runner)
    assert run(["check", trace, "--judge", "claude", "--judge-model", "claude-sonnet-5-5", "--judge-effort",
                "high", "--judge-cache", str(tmp_path / "c2")]) == 1
    argv = runner.calls[0]["argv"]
    assert argv[argv.index("--effort") + 1] == "high"
    assert "(judge)" in capsys.readouterr().out
