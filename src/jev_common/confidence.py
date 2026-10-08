"""Confidence, computed the way TypeSafe documents it (https://docs.typesafe.ai/confidence).

Confidence describes how concentrated a distribution is, not whether the answer is right.
The keyword baseline uses these formulas so its answers have the same shape as Jev's.
"""

from __future__ import annotations

from collections.abc import Sequence


def choice_confidence(probabilities: Sequence[float]) -> float:
    """(n * peak - 1) / (n - 1): 0 for a uniform distribution, 1 when one option has everything."""
    n = len(probabilities)
    if n < 2:
        return 1.0
    peak = max(probabilities)
    return max(0.0, min(1.0, (n * peak - 1) / (n - 1)))


def score_confidence(probabilities: Sequence[float]) -> float:
    """1 - (expected distance from the peak level) / (that distance for an even spread)."""
    n = len(probabilities)
    if n < 2:
        return 1.0
    total = sum(probabilities) or 1.0
    p = [value / total for value in probabilities]
    peak = p.index(max(p))
    spread = sum(value * abs(i - peak) for i, value in enumerate(p))
    even_spread = sum(abs(i - (n - 1) / 2) for i in range(n)) / n
    return max(0.0, min(1.0, 1 - spread / even_spread))


def expected_score(probabilities: Sequence[float]) -> float:
    """A Score answer's `score`: the probability-weighted level."""
    return sum(i * p for i, p in enumerate(probabilities))
