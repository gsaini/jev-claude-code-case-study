"""`triage-desk demo | triage | eval | serve` — offline by default, Jev with --live."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from jev_common.client import MissingKey, cost_usd
from triage_desk.app import Ticket, as_dict, load_tickets, make_client, triage
from triage_desk.evals import grade, markdown, sweep

OFFLINE_NOTE = "Offline: the keyword baseline, not Jev. Numbers show the mechanics, not Jev's quality."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage-desk", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("demo", "triage", "eval", "serve"):
        p = sub.add_parser(name)
        p.add_argument("--live", action="store_true", help="call Jev (needs TYPESAFE_API_KEY)")
        if name == "triage":
            p.add_argument("subject")
            p.add_argument("body")
        if name == "demo":
            p.add_argument("-n", type=int, default=8, help="how many sample tickets")
        if name == "eval":
            p.add_argument("--yes", action="store_true", help="confirm a live run")
            p.add_argument("--out", type=Path, default=Path("runs"), help="where to write results")
        if name == "serve":
            p.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    try:
        client, _ = make_client(live=args.live)
    except MissingKey as exc:
        print(exc, file=sys.stderr)
        return 2
    label = "Jev (jev-latest)" if args.live else "keyword baseline"
    if not args.live:
        print(f"▸ {OFFLINE_NOTE}\n", file=sys.stderr)

    if args.cmd == "triage":
        ticket = Ticket(id="cli-1", subject=args.subject, body=args.body, received_at=datetime.now(UTC))
        print(json.dumps(as_dict(triage(client, ticket)), indent=2))
        return 0

    if args.cmd == "demo":
        for ticket in load_tickets()[: args.n]:
            d = triage(client, ticket)
            flag = "auto  " if d.auto else "REVIEW"
            tags = f" [{', '.join(d.tags)}]" if d.tags else ""
            print(
                f"{ticket.id} {flag} {d.queue:<9} {d.priority} {ticket.subject[:38]:<38}{tags}\n      ↳ {d.reasons[-1]}"
            )
        return 0

    if args.cmd == "eval":
        tickets = load_tickets()
        if args.live and not args.yes:
            est = sum(len(t.subject) + len(t.body) for t in tickets) // 4 + 600 * len(tickets)
            print(
                f"Live eval: {len(tickets)} requests to Jev, roughly {est:,} input tokens "
                f"(≈ ${cost_usd(est):.4f} at list price). Re-run with --yes.",
                file=sys.stderr,
            )
            return 2
        decisions = [triage(client, t) for t in tickets]
        g, rows = grade(tickets, decisions), sweep(tickets, decisions)
        report = markdown(label, g, rows)
        print(report)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out = args.out / f"triage-{'jev' if args.live else 'baseline'}-{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(report + "\n")
        (out / "decisions.jsonl").write_text("".join(json.dumps(as_dict(d)) + "\n" for d in decisions))
        (out / "summary.json").write_text(json.dumps({"grade": g, "sweep": rows}, indent=2) + "\n")
        print(f"\nSaved to {out}/", file=sys.stderr)
        return 0

    from triage_desk.web import serve

    serve(client, model_label=label, note="" if args.live else OFFLINE_NOTE, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
