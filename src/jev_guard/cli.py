"""`jev-guard check | eval | log` — inspect the guard outside Claude Code."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from jev_common.client import MissingKey, baseline_client, live_client
from jev_guard.baseline_rules import keyword_baseline
from jev_guard.engine import evaluate
from jev_guard.evals import grade, load_cases, markdown, run_arm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-guard", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="what would the guard do with this command?")
    check.add_argument("command")
    check.add_argument("--live", action="store_true", help="ask Jev (needs TYPESAFE_API_KEY)")
    ev = sub.add_parser("eval", help="grade the guard on data/commands.jsonl")
    ev.add_argument("--live", action="store_true", help="add the two Jev arms (needs TYPESAFE_API_KEY)")
    ev.add_argument("--yes", action="store_true", help="confirm a live run")
    ev.add_argument("--out", type=Path, default=Path("runs"))
    log = sub.add_parser("log", help="summarize .jev-guard/decisions.jsonl (review shadow mode before enforcing)")
    log.add_argument("--path", type=Path, default=Path(".jev-guard/decisions.jsonl"))
    args = parser.parse_args(argv)

    if args.cmd == "check":
        try:
            client = live_client(timeout=2.0, retries=0) if args.live else baseline_client(keyword_baseline())
        except MissingKey as exc:
            print(exc, file=sys.stderr)
            return 2
        if not args.live:
            print("▸ Offline: keyword baseline, not Jev.", file=sys.stderr)
        print(json.dumps(asdict(evaluate(args.command, client)), indent=2))
        return 0

    if args.cmd == "eval":
        cases = load_cases()
        if args.live and not args.yes:
            print(
                f"Live eval: up to {2 * len(cases)} Jev requests (a few cents at most, usually far less). "
                "Re-run with --yes.",
                file=sys.stderr,
            )
            return 2
        arms = {
            "rules only": grade(cases, run_arm(cases, None)),
            "keyword baseline": grade(cases, run_arm(cases, baseline_client(keyword_baseline()))),
        }
        if args.live:
            try:
                jev = live_client(timeout=5.0)
            except MissingKey as exc:
                print(exc, file=sys.stderr)
                return 2
            arms["Jev, five questions"] = grade(cases, run_arm(cases, jev))
            arms["Jev, one question"] = grade(cases, run_arm(cases, jev, single_question=True))
        report = markdown(arms)
        print(report)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out = args.out / f"guard-{'live' if args.live else 'offline'}-{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(report + "\n")
        (out / "summary.json").write_text(json.dumps(arms, indent=2) + "\n")
        print(f"\nSaved to {out}/", file=sys.stderr)
        return 0

    if not args.path.exists():
        print(f"No decisions logged yet at {args.path}.", file=sys.stderr)
        return 1
    entries = [json.loads(line) for line in args.path.read_text().splitlines() if line.strip()]
    counts = Counter((e["source"], e["decision"], e["enforced"]) for e in entries)
    print(f"{len(entries)} decisions\n")
    for (source, decision, enforced), n in counts.most_common():
        print(f"{n:5}  {source:<11} {decision:<5} {'enforced' if enforced else 'logged only'}")
    would = [e for e in entries if e["source"] == "model" and e["decision"] != "none" and not e["enforced"]]
    if would:
        print("\nIn enforce mode, the model would also have prompted for:")
        for e in would[-20:]:
            print(f"  {e['command'][:70]:<70}  {e['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
