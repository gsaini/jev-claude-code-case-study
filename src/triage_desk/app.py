"""The application: one TypeSafe request per ticket, then code decides."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from typesafe_sdk import TypeSafeClient

from jev_common.baseline import KeywordBaseline
from jev_common.client import baseline_client, live_client
from triage_desk.baseline_rules import keyword_baseline
from triage_desk.policy import DEFAULT_THRESHOLDS, Decision, Judgment, Thresholds, decide
from triage_desk.questions import QUESTIONS, state_for

DATA = Path(__file__).resolve().parents[2] / "data" / "tickets.jsonl"


@dataclass(frozen=True)
class Ticket:
    id: str
    subject: str
    body: str
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    labels: dict[str, Any] = field(default_factory=dict)  # only in the eval set


def triage(client: TypeSafeClient, ticket: Ticket, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> Decision:
    started = time.perf_counter()
    response = client.system_one(state=state_for(ticket.subject, ticket.body), questions=QUESTIONS)
    latency_ms = (time.perf_counter() - started) * 1000
    return decide(ticket.id, ticket.received_at, Judgment.from_response(response, latency_ms), thresholds)


def make_client(*, live: bool) -> tuple[TypeSafeClient, KeywordBaseline | None]:
    if live:
        return live_client(), None
    baseline = keyword_baseline()
    return baseline_client(baseline), baseline


def load_tickets(path: Path = DATA) -> list[Ticket]:
    tickets = []
    for line in path.read_text().splitlines():
        if line.strip():
            raw = json.loads(line)
            tickets.append(
                Ticket(
                    id=raw["id"],
                    subject=raw["subject"],
                    body=raw["body"],
                    received_at=datetime.fromisoformat(raw["received_at"]),
                    labels=raw.get("labels", {}),
                )
            )
    return tickets


def as_dict(d: Decision) -> dict[str, Any]:
    j = d.judgment
    return {
        "ticket_id": d.ticket_id,
        "queue": d.queue,
        "auto": d.auto,
        "priority": d.priority,
        "due": d.due.isoformat(),
        "tags": list(d.tags),
        "reasons": list(d.reasons),
        "judgment": {
            "department": j.department,
            "department_confidence": round(j.department_confidence, 3),
            "department_probabilities": {k: round(v, 3) for k, v in j.department_probabilities.items()},
            "urgency": round(j.urgency, 2),
            "security": round(j.security, 3),
            "legal": round(j.legal, 3),
            "refund": round(j.refund, 3),
            "churn": round(j.churn, 3),
            "model": j.model,
            "input_tokens": j.input_tokens,
            "latency_ms": round(j.latency_ms, 1),
        },
    }
