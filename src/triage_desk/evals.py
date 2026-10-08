"""Grade Triage Desk against the labeled tickets, and sweep the auto-route threshold for free.

The number that matters most is `wrong_auto`: tickets routed to the wrong team *without* a
person looking. A ticket sent to review costs a minute of someone's time; a wrong auto-route
costs the customer a day. The threshold sweep re-decides from the same answers — no new calls.
"""

from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Any

from jev_common.client import cost_usd
from triage_desk.app import Ticket
from triage_desk.policy import DEFAULT_THRESHOLDS, Decision, Thresholds, decide

SWEEP = (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9)


def expected_queue(labels: dict[str, Any]) -> str:
    if labels["security"]:
        return "security"
    if labels["department"] == "other":
        return "review"
    return labels["department"]


def grade(tickets: list[Ticket], decisions: list[Decision], flag: float = 0.5) -> dict[str, Any]:
    pairs = list(zip(tickets, decisions, strict=True))
    auto = [(t, d) for t, d in pairs if d.auto]
    sec = [(t, d) for t, d in pairs if t.labels["security"]]
    legal = [(t, d) for t, d in pairs if t.labels["legal"]]
    latencies = sorted(d.judgment.latency_ms for d in decisions)
    tokens = sum(d.judgment.input_tokens for d in decisions)
    return {
        "tickets": len(pairs),
        "model": decisions[0].judgment.model if decisions else "",
        "department_accuracy": _mean(d.judgment.department == t.labels["department"] for t, d in pairs),
        "auto_rate": len(auto) / len(pairs),
        "auto_accuracy": _mean(d.queue == expected_queue(t.labels) for t, d in auto),
        "wrong_auto": sum(d.queue != expected_queue(t.labels) for t, d in auto),
        "security_recall": _mean(d.judgment.security >= flag for _, d in sec),
        "security_false_alarms": sum(d.judgment.security >= flag for t, d in pairs if not t.labels["security"]),
        "legal_recall": _mean(d.judgment.legal >= flag for _, d in legal),
        "urgency_exact": _mean(_level(d) == t.labels["urgency"] for t, d in pairs),
        "urgency_within_1": _mean(abs(_level(d) - t.labels["urgency"]) <= 1 for t, d in pairs),
        "input_tokens": tokens,
        "cost_usd": cost_usd(tokens),
        "latency_p50_ms": statistics.median(latencies) if latencies else 0.0,
        "latency_p95_ms": latencies[max(0, round(0.95 * len(latencies)) - 1)] if latencies else 0.0,
    }


def sweep(
    tickets: list[Ticket], decisions: list[Decision], base: Thresholds = DEFAULT_THRESHOLDS
) -> list[dict[str, Any]]:
    rows = []
    for tau in SWEEP:
        t = replace(base, auto_route=tau)
        redecided = [decide(tk.id, tk.received_at, d.judgment, t) for tk, d in zip(tickets, decisions, strict=True)]
        auto = [(tk, d) for tk, d in zip(tickets, redecided, strict=True) if d.auto]
        rows.append(
            {
                "threshold": tau,
                "auto_rate": len(auto) / len(tickets),
                "wrong_auto": sum(d.queue != expected_queue(tk.labels) for tk, d in auto),
                "to_review": len(tickets) - len(auto),
            }
        )
    return rows


def markdown(name: str, g: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"### {name} (`{g['model']}`, {g['tickets']} tickets)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| department accuracy | {g['department_accuracy']:.0%} |",
        f"| auto-routed | {g['auto_rate']:.0%} |",
        f"| accuracy of auto-routed | {g['auto_accuracy']:.0%} |",
        f"| **wrong auto-routes** | **{g['wrong_auto']}** |",
        f"| security recall | {g['security_recall']:.0%} ({g['security_false_alarms']} false alarms) |",
        f"| legal recall | {g['legal_recall']:.0%} |",
        f"| urgency exact / within one level | {g['urgency_exact']:.0%} / {g['urgency_within_1']:.0%} |",
        f"| input tokens / cost at list price | {g['input_tokens']:,} / ${g['cost_usd']:.5f} |",
        f"| latency p50 / p95 | {g['latency_p50_ms']:.0f} ms / {g['latency_p95_ms']:.0f} ms |",
        "",
        "| auto-route threshold | auto-routed | wrong auto-routes | sent to review |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r['threshold']:.1f} | {r['auto_rate']:.0%} | {r['wrong_auto']} | {r['to_review']} |" for r in rows]
    return "\n".join(lines)


def _level(d: Decision) -> int:
    return min(3, max(0, int(d.judgment.urgency + 0.5)))


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
