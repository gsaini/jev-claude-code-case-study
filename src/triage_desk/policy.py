"""Policy lives in code: thresholds, escalation rules, priorities, and the SLA clock.

Jev answers narrow questions; this module decides what to *do* with the answers. Changing a
threshold here never needs a new model call, and every decision carries its reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from typesafe_sdk import SystemOneResponse

SLA_HOURS = (72, 24, 8, 1)  # by urgency level 0..3 — arithmetic on dates is code's job, not the model's


@dataclass(frozen=True)
class Thresholds:
    auto_route: float = 0.6  # department confidence needed to skip the human review queue
    flag: float = 0.5  # a Noul at or above this counts as "yes"


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class Judgment:
    """The typed answers for one ticket, lifted out of the SDK response."""

    department: str
    department_probabilities: dict[str, float]
    department_confidence: float
    urgency: float  # probability-weighted level, 0..3
    security: float
    legal: float
    refund: float
    churn: float
    model: str
    input_tokens: int
    latency_ms: float

    @classmethod
    def from_response(cls, response: SystemOneResponse, latency_ms: float) -> Judgment:
        department = response.choices["department"]
        return cls(
            department=department.choice,
            department_probabilities=dict(department.probabilities),
            department_confidence=department.confidence,
            urgency=response.scores["urgency"].score,
            security=response.nouls["security"].noul,
            legal=response.nouls["legal"].noul,
            refund=response.nouls["refund"].noul,
            churn=response.nouls["churn"].noul,
            model=response.model,
            input_tokens=response.usage.input_tokens or 0,
            latency_ms=latency_ms,
        )


@dataclass(frozen=True)
class Decision:
    ticket_id: str
    queue: str  # a department, "security", or "review"
    auto: bool  # routed without a person looking first
    priority: str  # P1 (now) .. P4 (this week)
    due: datetime
    tags: tuple[str, ...]
    reasons: tuple[str, ...]
    judgment: Judgment


def decide(ticket_id: str, received_at: datetime, j: Judgment, t: Thresholds = DEFAULT_THRESHOLDS) -> Decision:
    level = min(3, max(0, int(j.urgency + 0.5)))
    reasons: list[str] = []
    tags: list[str] = []

    if j.security >= t.flag:
        queue, auto, level = "security", False, 3
        reasons.append(f"possible security issue (p={j.security:.2f}) → security team, P1, a person reads it")
    elif j.department == "other":
        queue, auto = "review", False
        reasons.append(f"no team fits (other={j.department_probabilities.get('other', 0):.2f})")
    elif j.department_confidence < t.auto_route:
        queue, auto = "review", False
        top = sorted(j.department_probabilities.items(), key=lambda kv: kv[1], reverse=True)[:2]
        reasons.append(
            f"unsure: {top[0][0]} {top[0][1]:.2f} vs {top[1][0]} {top[1][1]:.2f} "
            f"(confidence {j.department_confidence:.2f} < {t.auto_route})"
        )
    else:
        queue, auto = j.department, True
        reasons.append(f"{j.department} (confidence {j.department_confidence:.2f})")

    if j.legal >= t.flag:
        tags.append("legal")
        if auto:
            auto = False
            reasons.append(f"legal language (p={j.legal:.2f}) → a person reads it before anyone replies")
    if queue == "billing" and j.refund >= t.flag:  # speculative answer, consumed only when its premise holds
        tags.append("refund")
    if j.churn >= t.flag:
        tags.append("churn-risk")

    return Decision(
        ticket_id=ticket_id,
        queue=queue,
        auto=auto,
        priority=f"P{4 - level}",
        due=received_at + timedelta(hours=SLA_HOURS[level]),
        tags=tuple(tags),
        reasons=tuple(reasons),
        judgment=j,
    )
