"""An offline keyword baseline that answers through the real TypeSafe SDK.

This is **not Jev**. It is the regex-and-keywords classifier a team typically has *before*
adopting a model, served behind an `httpx2.MockTransport` that speaks TypeSafe's
`POST /v1/systemone` wire format. The application code can't tell the difference, so:

- tests and CI exercise the real SDK (request building, response parsing, typed answers) for free;
- the evals have an honest **baseline column** to compare Jev against.

Every rule is keyed by the question's name; an unknown question gets a maximally uncertain
answer (Noul 0.5, uniform Choice/Score), which the application must treat as "don't know".
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx2

from jev_common.confidence import choice_confidence, expected_score, score_confidence

NoulRule = Callable[[str], float]
ChoiceRule = Callable[[str], Mapping[str, float]]
ScoreRule = Callable[[str], Sequence[float]]

SMOOTHING = 0.02


@dataclass
class KeywordBaseline:
    nouls: dict[str, NoulRule] = field(default_factory=dict)
    choices: dict[str, ChoiceRule] = field(default_factory=dict)
    scores: dict[str, ScoreRule] = field(default_factory=dict)
    model: str = "keyword-baseline"
    requests: list[dict[str, Any]] = field(default_factory=list)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET" and request.url.path.endswith("/v1/models"):
            models = [{"name": self.model, "description": "Offline keyword baseline", "release_date": "2026-10-07"}]
            return httpx2.Response(200, json={"models": models})
        body = json.loads(request.content)
        self.requests.append(body)
        text = _flatten(body["state"]).lower()
        answers = {name: self._answer(name, question, text) for name, question in body["questions"].items()}
        usage = {"input_tokens": max(1, len(request.content) // 4), "output_tokens": 0}
        return httpx2.Response(200, json={"model": self.model, "answers": answers, "usage": usage})

    def _answer(self, name: str, question: Mapping[str, Any], text: str) -> dict[str, Any]:
        kind = question["type"]
        if kind == "noul":
            rule = self.nouls.get(name)
            return {"type": "noul", "noul": float(rule(text)) if rule else 0.5}
        if kind == "choice":
            labels = list(question["criteria"])
            rule = self.choices.get(name)
            weights = rule(text) if rule else {}
            raw = [max(0.0, float(weights.get(label, 0.0))) + SMOOTHING for label in labels]
            total = sum(raw)
            probs = [value / total for value in raw]
            best = labels[probs.index(max(probs))]
            return {
                "type": "choice",
                "choice": best,
                "confidence": choice_confidence(probs),
                "probabilities": dict(zip(labels, probs, strict=True)),
            }
        if kind == "score":
            levels = list(question["criteria"])
            rule = self.scores.get(name)
            weights = list(rule(text)) if rule else [1.0] * len(levels)
            raw = [max(0.0, float(w)) + SMOOTHING for w in weights[: len(levels)]]
            raw += [SMOOTHING] * (len(levels) - len(raw))
            total = sum(raw)
            probs = [value / total for value in raw]
            return {
                "type": "score",
                "score": expected_score(probs),
                "confidence": score_confidence(probs),
                "legend": {
                    str(i): level if isinstance(level, str) else json.dumps(level) for i, level in enumerate(levels)
                },
                "probabilities": {str(i): p for i, p in enumerate(probs)},
            }
        raise ValueError(f"unknown question type {kind!r}")


def _flatten(state: Any) -> str:
    return state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)


def any_of(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def count_of(text: str, *needles: str) -> int:
    return sum(needle in text for needle in needles)
