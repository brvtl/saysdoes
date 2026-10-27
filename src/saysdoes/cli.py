"""Command-line interface. Exit codes: 0 = consistent, 1 = contradictions, 2 = usage/parse error."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from . import html as html_mod
from . import judge as judge_mod
from .analyze import analyze
from .formats import FORMATS, ParseError, load
from .report import format_text, to_json

EXIT_OK, EXIT_FOUND, EXIT_ERROR = 0, 1, 2


def add_judge_args(p: argparse.ArgumentParser) -> None:
    """--judge and its options (shared with eval/run_eval.py)."""
    p.add_argument("--judge", default="none", choices=judge_mod.BACKENDS,
                   help="optional model judge run after the rules (default: none). 'claude' runs headless Claude "
                        "Code with your local login; it adds missed commitments and dismisses false findings, "
                        "with every quote checked against the trace")
    p.add_argument("--judge-model", default=judge_mod.DEFAULT_MODEL, metavar="MODEL",
                   help=f"model for --judge claude (default: {judge_mod.DEFAULT_MODEL})")
    p.add_argument("--judge-effort", default=judge_mod.DEFAULT_EFFORT, choices=judge_mod.EFFORTS,
                   help=f"effort for --judge claude (default: {judge_mod.DEFAULT_EFFORT})")
    p.add_argument("--judge-cache", default=judge_mod.DEFAULT_CACHE_DIR, metavar="DIR",
                   help=f"judge result cache (default: {judge_mod.DEFAULT_CACHE_DIR}/)")
    p.add_argument("--judge-offline", action="store_true",
                   help="use cached judge results only; a cache miss is recorded as a judge error")


def make_judge_from_args(args: argparse.Namespace):
    return judge_mod.make_judge(args.judge, args.judge_model, args.judge_effort, args.judge_cache,
                                args.judge_offline)


JUDGE_EPILOG = ("Judge cost: the report's total_cost_usd is the Claude Code CLI's API-list-price equivalent. "
                "On a Claude subscription the calls are not billed per token. Set CLAUDE_BIN to use a "
                "claude binary that is not on PATH.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="saysdoes", description=__doc__)
    p.add_argument("--version", action="version", version=f"saysdoes {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="check a trace for contradictions between stated plan and actions",
                       epilog=JUDGE_EPILOG)
    c.add_argument("trace", help="path to the trace file")
    c.add_argument("--format", default="auto", choices=("auto",) + FORMATS)
    c.add_argument("--html", metavar="OUT.html", help="write a self-contained HTML timeline")
    c.add_argument("--json", metavar="OUT.json", help="write the machine-readable report")
    add_judge_args(c)
    c.add_argument("--quiet", action="store_true", help="no stdout report; rely on the exit code")
    return p


def _err(msg: str) -> None:
    print(f"saysdoes: error: {msg}", file=sys.stderr)


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse: --help/--version exit 0, usage errors exit 2
        return int(e.code) if isinstance(e.code, int) else EXIT_ERROR
    try:
        trace = load(args.trace, args.format)
    except FileNotFoundError:
        _err(f"no such file: {args.trace}")
        return EXIT_ERROR
    except (ParseError, OSError, UnicodeError) as e:
        _err(f"could not parse {args.trace}: {e}")
        return EXIT_ERROR

    report = analyze(trace, make_judge_from_args(args))

    if not args.quiet:
        sys.stdout.write(format_text(report, args.trace))
    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as fh:
                fh.write(to_json(report, args.trace) + "\n")
        except OSError as e:
            _err(f"could not write {args.json}: {e}")
            return EXIT_ERROR
    if args.html:
        try:
            html_mod.write(report, args.html, args.trace)
        except OSError as e:
            _err(f"could not write {args.html}: {e}")
            return EXIT_ERROR
    return report.exit_code


def main(argv: list[str] | None = None) -> None:
    sys.exit(run(argv))
