"""Code first, then Jev, then policy in code. The engine never returns "allow"."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from typesafe_sdk import TypeSafeClient, TypeSafeError

from jev_guard.questions import DECOMPOSED, DIMENSIONS, SINGLE, state_for
from jev_guard.rules import classify, redact

Decision = Literal["deny", "ask", "none"]
Source = Literal["rule", "fast-path", "model", "unavailable"]


@dataclass(frozen=True)
class Verdict:
    decision: Decision  # "none" means: no opinion — Claude Code's own permission rules decide
    reason: str
    source: Source
    command: str  # redacted
    probabilities: dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
    model: str = ""
    input_tokens: int = 0


def evaluate(
    command: str,
    client: TypeSafeClient | None,
    *,
    threshold: float = 0.5,
    single_question: bool = False,
) -> Verdict:
    redacted = redact(command)
    rule = classify(command)
    if rule.decision in ("deny", "ask"):
        return Verdict(rule.decision, rule.reason, "rule", redacted)
    if rule.decision == "none":
        return Verdict("none", rule.reason, "fast-path", redacted)
    if client is None:
        return Verdict("none", "no TypeSafe key: Claude Code's permission rules decide", "unavailable", redacted)

    questions = SINGLE if single_question else DECOMPOSED
    started = time.perf_counter()
    try:
        response = client.system_one(state=state_for(redacted), questions=questions)
    except TypeSafeError as exc:  # timeouts, rate limits, outages: fall back to Claude Code's own rules
        return Verdict("none", f"Jev unavailable ({type(exc).__name__})", "unavailable", redacted)
    latency_ms = (time.perf_counter() - started) * 1000
    probs = {name: answer.noul for name, answer in response.nouls.items()}
    meta = {
        "probabilities": probs,
        "latency_ms": latency_ms,
        "model": response.model,
        "input_tokens": response.usage.input_tokens or 0,
    }

    if single_question:
        if probs["risky"] >= threshold:
            return Verdict("ask", f"{response.model}: risky ({probs['risky']:.2f})", "model", redacted, **meta)
        return Verdict("none", f"{response.model}: not risky", "model", redacted, **meta)

    hits = [f"{dim[3]} ({probs[name]:.2f})" for name, dim in DIMENSIONS.items() if probs[name] >= threshold]
    if hits:
        return Verdict("ask", f"{response.model}: " + "; ".join(hits), "model", redacted, **meta)
    return Verdict("none", f"{response.model}: no risk dimension above threshold", "model", redacted, **meta)
