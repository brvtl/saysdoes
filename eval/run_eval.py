#!/usr/bin/env python3
"""Measure saysdoes against hand labels (stdlib only), rules-only and/or with the model judge.

A trace is predicted `contradiction` iff saysdoes reports >= 1 finding, i.e. iff
`saysdoes check --format <fmt>` would exit 1 (with the same --judge options).

    python eval/run_eval.py [--labels PATH] [--split dev|heldout|all] [--items] [--markdown] [--json OUT]
                            [--judge none|claude] [--judge-model M] [--judge-effort E] [--judge-cache DIR]
                            [--judge-offline] [--compare] [--jobs N]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

from saysdoes import judge as judge_mod  # noqa: E402
from saysdoes.analyze import analyze  # noqa: E402
from saysdoes.cli import add_judge_args  # noqa: E402
from saysdoes.formats import load  # noqa: E402
from saysdoes.model import COMMITMENT_KINDS  # noqa: E402

SPLITS = ("dev", "heldout", "all")
DEFAULT_LABELS = os.path.join(HERE, "labels.json")
EVAL_JUDGE_CACHE = os.path.join(HERE, "judge-cache")
MODE_TITLE = {"rules": "rules only", "judge": "rules + judge"}


# ---------------------------------------------------------------- labels

def resolve_path(path: str, labels_dir: str) -> str | None:
    """An item path relative to the repo root, else to the labels file's directory, else to eval/."""
    for base in (REPO, labels_dir, HERE):
        p = os.path.normpath(os.path.join(base, path))
        if os.path.exists(p):
            return p
    return None


def parser_format(fmt: str) -> str:
    """Label formats like `claude-code-session` / `claude-code-stream-json` use the claude-code parser."""
    return "claude-code" if fmt and fmt.startswith("claude-code") else fmt


def gold_of(item: dict) -> str:
    return (item.get("commitment_type") or "contradiction") if item["label"] == "contradiction" else "consistent"


def load_items(labels_path: str) -> list[dict]:
    with open(labels_path, encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    labels_dir = os.path.dirname(os.path.abspath(labels_path))
    for item in items:
        item["_path"] = resolve_path(item["path"], labels_dir)
        item.setdefault("split", "all")  # items without a split only count toward "all"
    return items


# ---------------------------------------------------------------- metric helpers (pure)

def ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def rates(c: dict) -> dict:
    """Precision, recall and false-positive rate from a {tp, fp, fn, tn} dict (None if undefined)."""
    return {"precision": ratio(c["tp"], c["tp"] + c["fp"]),
            "recall": ratio(c["tp"], c["tp"] + c["fn"]),
            "fpr": ratio(c["fp"], c["fp"] + c["tn"])}


def counts(pairs) -> dict:
    """Confusion counts from (gold_positive, predicted_positive) boolean pairs."""
    c = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for gold, pred in pairs:
        c[("t" if gold == pred else "f") + ("p" if pred else "n")] += 1
    return c


def binary_counts(results: list[dict]) -> dict:
    return counts((r["gold"] != "consistent", r["pred"] == "contradiction") for r in results)


def type_counts(results: list[dict], kind: str) -> dict:
    """Per-commitment-type counts: positives are contradictions labelled `kind`; a hit is a finding of `kind`."""
    return counts((r["gold"] == kind, kind in r["kinds"]) for r in results)


def action_matches(tool: str, texts: list[str], expected: dict) -> bool:
    return tool.lower() == expected["tool"].lower() and any(expected["contains"] in t for t in texts)


def echo_noise(findings) -> int:
    """Trivial sub-commands (category "other": echo, cd, head on stdin, ...) still listed in findings."""
    return sum(a.category == "other" for f in findings for a in f.contradicting_actions)


def fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def breakdown(results: list[dict], key: str) -> dict:
    """Binary counts and rates per value of `key` (e.g. origin, source); missing values are "unknown"."""
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(r.get(key) or "unknown", []).append(r)
    out = {}
    for value in sorted(groups):
        c = binary_counts(groups[value])
        out[value] = {"n": len(groups[value]), **c, **rates(c)}
    return out


def dist(xs: list[float]) -> dict:
    return {"total": sum(xs), "mean": statistics.mean(xs) if xs else None,
            "median": statistics.median(xs) if xs else None, "max": max(xs) if xs else None}


# ---------------------------------------------------------------- running saysdoes

def localise(report, gold: str, expected) -> bool | str | None:
    if not report.findings or gold == "consistent" or not expected:
        return None
    if not isinstance(expected, dict):
        return "n/a"  # free-text expectation: not checked automatically
    loc = False
    for f in report.findings:
        for a in f.contradicting_actions:
            step = report.trace.step(a.step_index)
            texts = [a.raw, step.text, json.dumps(step.args, ensure_ascii=False, sort_keys=True)]
            loc = loc or action_matches(a.tool, texts, expected)
    return loc


def mode_result(report, item: dict) -> dict:
    gold = gold_of(item)
    return {"pred": "contradiction" if report.findings else "consistent",
            "kinds": sorted({f.commitment.kind for f in report.findings}),
            "localised": localise(report, gold, item.get("expected_action")),
            "echo_noise": echo_noise(report.findings), "findings": [f.to_dict() for f in report.findings]}


def judge_meta(block: dict, report, gold: str) -> dict:
    added = [f for f in report.findings if f.source == "judge"]
    return {"added": [{"id": f.id, "kind": f.commitment.kind, "step": f.commitment.step_index,
                       "quote": f.commitment.span_text, "actions": [a.ref for a in f.contradicting_actions],
                       "explanation": f.explanation} for f in added],
            "dismissed": [{"id": d["finding_id"], "kind": d["finding"]["commitment"]["kind"], "reason": d["reason"],
                           "evidence_step": d["evidence_step"], "evidence_quote": d["evidence_quote"],
                           "explanation": d["explanation"],
                           "verdict": dismissal_verdict(gold, d["finding"]["commitment"]["kind"])}
                          for d in block["dismissed"]],
            "rejected": block["rejected"], "errors": block["errors"], "turns": block["turns"],
            "calls": block["calls"], "cache_hits": block["cache_hits"], "models_used": block["models_used"],
            "cost_usd": block["total_cost_usd"], "cost_usd_this_run": block["cost_usd_this_run"],
            "duration_ms": block["duration_ms_total"], "duration_ms_this_run": block["duration_ms_this_run"],
            "wall_clock_ms": block["wall_clock_ms"], "cache_keys": [t["key"] for t in block["per_turn"]]}


def dismissal_verdict(gold: str, kind: str) -> str:
    """Trace-level grading of one dismissal: on a consistent trace it removes a false finding (correct); on a
    contradiction it removes a finding of the labelled kind (incorrect) or of another kind (unclear)."""
    if gold == "consistent":
        return "correct"
    return "incorrect" if gold in (kind, "contradiction") else "unclear"


def run_item(item: dict, judge=None) -> dict:
    """Rules-only result, plus (with a judge) the rules+judge result from one judge pass over the same report."""
    report = analyze(load(item["_path"], parser_format(item["format"])))
    gold = gold_of(item)
    out = {"id": item["id"], "split": item["split"], "origin": item.get("origin"), "source": item.get("source"),
           "gold": gold, "note": item.get("note", ""), "rules": mode_result(report, item)}
    if judge is not None:
        warnings = []
        block = judge_mod.run_judge(report, judge, warnings.append)
        report.judge = block
        out["judge"] = mode_result(report, item)
        out["judge_meta"] = judge_meta(block, report, gold)
    return out


def view(results: list[dict], mode: str) -> list[dict]:
    """Flat per-item records for one mode (what the metric helpers take)."""
    return [{**{k: v for k, v in r.items() if k not in ("rules", "judge", "judge_meta")}, **r[mode]}
            for r in results]


def summarize(results: list[dict], types: list[str]) -> dict:
    c = binary_counts(results)
    tps = [r for r in results if r["gold"] != "consistent" and r["pred"] == "contradiction"]
    per_type = {}
    for t in types:
        tc = type_counts(results, t)
        per_type[t] = {**tc, **rates(tc)}
    golds = ["consistent"] + types + (["contradiction"] if any(r["gold"] == "contradiction" for r in results) else [])
    golds += sorted({r["gold"] for r in results} - set(golds))
    cols = ["none"] + types
    cols += sorted({k for r in results for k in r["kinds"]} - set(cols))
    confusion = {g: {k: 0 for k in cols} for g in golds}
    for r in results:
        for k in r["kinds"] or ["none"]:
            confusion[r["gold"]][k] += 1
    checked = [r for r in tps if r["localised"] != "n/a"]
    return {"n": len(results), **c, **rates(c),
            "localised": sum(1 for r in checked if r["localised"] is True), "localised_of": len(checked),
            "echo_noise": sum(r["echo_noise"] for r in results),
            "per_type": per_type, "confusion": confusion}


def judge_effects(results: list[dict]) -> dict:
    """What the judge changed, graded at trace level against the gold labels."""
    e = {"added": 0, "added_on_contradiction": 0, "added_on_consistent": 0, "added_new_tp": 0, "added_new_fp": 0,
         "dismissed": 0, "dismissed_correct": 0, "dismissed_incorrect": 0, "dismissed_unclear": 0,
         "rejected": 0, "errors": 0, "flipped_to_contradiction": [], "flipped_to_consistent": []}
    for r in results:
        m = r.get("judge_meta")
        if not m:
            continue
        positive = r["gold"] != "consistent"
        e["added"] += len(m["added"])
        e["added_on_contradiction" if positive else "added_on_consistent"] += len(m["added"])
        e["dismissed"] += len(m["dismissed"])
        for d in m["dismissed"]:
            e[f"dismissed_{d['verdict']}"] += 1
        e["rejected"] += len(m["rejected"])
        e["errors"] += len(m["errors"])
        before, after = r["rules"]["pred"], r["judge"]["pred"]
        if before != after:
            e["flipped_to_" + after].append(r["id"])
            if after == "contradiction":
                e["added_new_tp" if positive else "added_new_fp"] += 1
    return e


def judge_costs(results: list[dict], wall_clock_ms: float | None = None) -> dict:
    metas = [r["judge_meta"] for r in results if r.get("judge_meta")]
    return {"traces": len(metas), "turns": sum(m["turns"] for m in metas), "calls": sum(m["calls"] for m in metas),
            "cache_hits": sum(m["cache_hits"] for m in metas), "errors": sum(len(m["errors"]) for m in metas),
            "models_used": sorted({x for m in metas for x in m["models_used"]}),
            "cost_usd": dist([m["cost_usd"] for m in metas]),
            "cost_usd_this_run": sum(m["cost_usd_this_run"] for m in metas),
            "latency_ms": dist([m["duration_ms"] for m in metas]),
            "latency_ms_this_run": sum(m["duration_ms_this_run"] for m in metas),
            "wall_clock_ms": wall_clock_ms, "cost_note": judge_mod.COST_NOTE}


# ---------------------------------------------------------------- output

def table(headers: list[str], rows: list[list], markdown: bool) -> str:
    rows = [[str(x) for x in row] for row in rows]
    if markdown:
        lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()  # noqa: E731
    return "\n".join([line(headers), line(["-" * w for w in widths])] + [line(r) for r in rows])


def heading(text: str, md: bool, level: int = 3) -> str:
    return f"{'#' * level} {text}\n" if md else f"== {text} ==\n"


def rate_row(s: dict) -> list:
    return [s["tp"], s["fp"], s["fn"], s["tn"], fmt(s["precision"]), fmt(s["recall"]), fmt(s["fpr"])]


RATE_HEADERS = ["TP", "FP", "FN", "TN", "precision", "recall", "FPR"]


def print_summary(name: str, s: dict, md: bool) -> None:
    print(heading(f"split: {name} (n={s['n']})", md))
    print(table(RATE_HEADERS + ["localised", "echo-noise (trivial listed)"],
                [rate_row(s) + [f"{s['localised']}/{s['localised_of']}", s["echo_noise"]]], md))
    print("\nPer commitment type:\n")
    print(table(["type"] + RATE_HEADERS, [[t] + rate_row(v) for t, v in s["per_type"].items()], md))
    print("\nConfusion (rows = gold, columns = predicted finding kinds):\n")
    cols = list(next(iter(s["confusion"].values())))
    print(table(["gold \\ pred"] + cols, [[g] + [row[k] for k in cols] for g, row in s["confusion"].items()], md))
    print()


def print_breakdown(title: str, b: dict, md: bool) -> None:
    print(f"By {title}:\n")
    print(table([title, "n"] + RATE_HEADERS, [[k, v["n"]] + rate_row(v) for k, v in b.items()], md))
    print()


def _usd(x) -> str:
    return "n/a" if x is None else f"${x:.4f}"


def _secs(ms) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.1f}s"


def print_judge(costs: dict, effects: dict, md: bool) -> None:
    print(heading("judge: cost and latency", md))
    c, lat = costs["cost_usd"], costs["latency_ms"]
    print(table(["traces", "turns", "calls (this run)", "cache hits", "errors", "cost total", "cost/trace mean",
                 "median", "max", "latency total", "latency/trace mean", "median", "max"],
                [[costs["traces"], costs["turns"], costs["calls"], costs["cache_hits"], costs["errors"],
                  _usd(c["total"]), _usd(c["mean"]), _usd(c["median"]), _usd(c["max"]), _secs(lat["total"]),
                  _secs(lat["mean"]), _secs(lat["median"]), _secs(lat["max"])]], md))
    print(f"\nCost and latency are the stored values of each call (sum of the CLI's total_cost_usd and "
          f"duration_ms, cache hits included). This run: {_usd(costs['cost_usd_this_run'])} and "
          f"{_secs(costs['latency_ms_this_run'])} of CLI time in {costs['calls']} calls; judge phase wall clock "
          f"{_secs(costs['wall_clock_ms'])}. Models used: {', '.join(costs['models_used']) or '-'}. "
          f"Cost is the API-list-price equivalent; nothing is billed per call on a Claude subscription.\n")
    print(heading("judge: effects (trace-level)", md))
    print(table(["added", "on contradiction", "on consistent", "new TP", "new FP", "dismissed", "correct",
                 "incorrect", "unclear", "rejected citations", "errors"],
                [[effects["added"], effects["added_on_contradiction"], effects["added_on_consistent"],
                  effects["added_new_tp"], effects["added_new_fp"], effects["dismissed"],
                  effects["dismissed_correct"], effects["dismissed_incorrect"], effects["dismissed_unclear"],
                  effects["rejected"], effects["errors"]]], md))
    for k in ("flipped_to_contradiction", "flipped_to_consistent"):
        print(f"\n{k.replace('_', ' ')}: {', '.join(effects[k]) or '-'}")
    print()


def _item_row(r: dict, modes: list[str]) -> list:
    loc = {None: "-", True: "yes", False: "NO", "n/a": "n/a"}
    last = r[modes[-1]]
    row = [r["id"], r["split"], r.get("origin") or "-", r["gold"]]
    row += [r[m]["pred"] for m in modes]
    row += [",".join(last["kinds"]) or "-", loc[last["localised"]]]
    m = r.get("judge_meta")
    if m is not None:
        row.append("; ".join(f"{a['id']} {a['kind']}@s{a['step']}" for a in m["added"]) or "-")
        row.append("; ".join(f"{d['id']} {d['kind']} ({d['reason']})" for d in m["dismissed"]) or "-")
        problems = (len(m["rejected"]), len(m["errors"]))
        row.append(f"{problems[0]}r/{problems[1]}e" if any(problems) else "-")
    return row + [r["note"]]


def item_headers(modes: list[str], judged: bool) -> list[str]:
    h = ["id", "split", "origin", "gold"] + [f"{m} pred" for m in modes] + ["finding kinds", "localised"]
    if judged:
        h += ["judge added", "judge dismissed", "rejected/errors"]
    return h + ["note"]


def evaluate(items: list[dict], judge=None, jobs: int = 4) -> tuple[list[dict], float | None]:
    start = time.monotonic()
    if judge is not None and jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(lambda it: run_item(it, judge), items))
    else:
        results = [run_item(it, judge) for it in items]
    return results, ((time.monotonic() - start) * 1000 if judge is not None else None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--labels", default=DEFAULT_LABELS, metavar="PATH", help="labels file (default: eval/labels.json)")
    p.add_argument("--split", choices=SPLITS, help="only report this split (default: dev, heldout and all)")
    p.add_argument("--items", action="store_true", help="print the per-item table")
    p.add_argument("--json", metavar="OUT", help="write a machine-readable dump")
    p.add_argument("--markdown", action="store_true", help="print tables as GitHub markdown")
    add_judge_args(p)
    p.set_defaults(judge_cache=EVAL_JUDGE_CACHE)
    p.add_argument("--compare", action="store_true",
                   help="report rules-only and rules+judge from one judge pass (implies --judge claude)")
    p.add_argument("--jobs", type=int, default=4, help="traces judged concurrently (default: 4)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.compare and args.judge == "none":
        args.judge = "claude"
    judge = judge_mod.make_judge(args.judge, args.judge_model, args.judge_effort, args.judge_cache,
                                 args.judge_offline)
    modes = (["rules", "judge"] if args.compare else ["judge"]) if judge else ["rules"]

    try:
        items = load_items(args.labels)
    except (OSError, ValueError, KeyError) as e:
        print(f"run_eval: error: could not read labels {args.labels}: {e}", file=sys.stderr)
        return 2
    present, skipped = [], []
    for item in items:
        if item["_path"] is None:
            if not item.get("optional"):
                print(f"run_eval: error: missing trace for {item['id']}: {item['path']}", file=sys.stderr)
                return 2
            print(f"note: skipping optional item {item['id']} (missing {item['path']})")
            skipped.append(item["id"])
            continue
        present.append(item)
    results, wall_ms = evaluate(present, judge, args.jobs)

    types = list(COMMITMENT_KINDS) + sorted({i["commitment_type"] for i in items if i.get("commitment_type")
                                             and i["commitment_type"] not in COMMITMENT_KINDS})
    splits = [args.split] if args.split else list(SPLITS)
    selected = {s: [r for r in results if s == "all" or r["split"] == s] for s in splits}
    shown = selected["all"] if "all" in selected else selected[splits[0]]
    md = args.markdown
    by_mode = {}
    for mode in modes:
        if len(modes) > 1 or mode != "rules":
            print(heading(f"mode: {MODE_TITLE[mode]}", md, 2))
        summaries = {s: summarize(view(rs, mode), types) for s, rs in selected.items()}
        for s in splits:
            print_summary(s, summaries[s], md)
        flat = view(shown, mode)
        by_mode[mode] = {"summaries": summaries, "by_origin": breakdown(flat, "origin"),
                         "by_source": breakdown(flat, "source")}
        print_breakdown("origin", by_mode[mode]["by_origin"], md)
        print_breakdown("source", by_mode[mode]["by_source"], md)

    judge_out = None
    if judge:
        judge_out = {"backend": judge.name, "model": judge.model, "effort": judge.effort,
                     "prompt_version": judge_mod.PROMPT_VERSION, "costs": judge_costs(shown, wall_ms),
                     "effects": judge_effects(shown)}
        print_judge(judge_out["costs"], judge_out["effects"], md)
    if len(modes) > 1:
        print(heading("rules only vs rules + judge", md))
        print(table(["split", "mode"] + RATE_HEADERS,
                    [[s, MODE_TITLE[m]] + rate_row(by_mode[m]["summaries"][s]) for s in splits for m in modes], md))
        print()

    if args.items:
        print(heading("Items", md) if md else "== items ==\n")
        print(table(item_headers(modes, bool(judge)), [_item_row(r, modes) for r in shown], md))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"labels": os.path.relpath(os.path.abspath(args.labels), REPO), "skipped": skipped,
                       "types": types, "modes": modes, "summaries": by_mode[modes[-1]]["summaries"],
                       "by_mode": by_mode, "judge": judge_out,
                       "items": [{**view([r], modes[-1])[0], **{m: r[m] for m in modes},
                                  **({"judge_meta": r["judge_meta"]} if "judge_meta" in r else {})}
                                 for r in shown]},
                      fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
