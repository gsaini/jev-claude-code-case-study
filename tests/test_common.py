"""The keyword baseline must look exactly like Jev to the official SDK."""

import pytest
from typesafe_sdk import Choice, ChoiceAnswer, Noul, NoulAnswer, Score, ScoreAnswer

from jev_common.baseline import KeywordBaseline
from jev_common.client import MissingKey, baseline_client, cost_usd, live_client
from jev_common.confidence import choice_confidence, expected_score, score_confidence


def test_confidence_matches_the_documented_example():
    # docs.typesafe.ai quick start: technical 0.85, billing 0.15, sales 0.0 → confidence 0.78
    assert choice_confidence([0.85, 0.15, 0.0]) == pytest.approx(0.775)
    assert choice_confidence([1 / 3] * 3) == pytest.approx(0.0)
    assert score_confidence([0.0, 1.0, 0.0]) == pytest.approx(1.0)
    assert expected_score([0.0, 1.0, 0.0]) == pytest.approx(1.0)


def test_baseline_answers_through_the_real_sdk():
    baseline = KeywordBaseline(
        nouls={"billing": lambda t: 0.9 if "charged" in t else 0.1},
        choices={"tone": lambda t: {"angry": 3.0} if "asap" in t else {}},
        scores={"urgency": lambda t: [0.0, 0.0, 1.0]},
    )
    with baseline_client(baseline) as client:
        response = client.system_one(
            state={"ticket": "I was charged twice. Fix it ASAP."},
            questions={
                "billing": Noul(instructions="Is this about billing?"),
                "tone": Choice(instructions="Tone?", criteria={"calm": None, "angry": None}),
                "urgency": Score(instructions="How urgent?", criteria=["later", "soon", "now"]),
            },
        )
    assert isinstance(response.answers["billing"], NoulAnswer) and response.nouls["billing"].noul == 0.9
    assert isinstance(response.answers["tone"], ChoiceAnswer) and response.choices["tone"].choice == "angry"
    assert isinstance(response.answers["urgency"], ScoreAnswer) and response.scores["urgency"].score > 1.8
    assert response.model == "keyword-baseline" and response.usage.input_tokens > 0
    assert len(baseline.requests) == 1


def test_unknown_questions_get_maximally_uncertain_answers():
    with baseline_client(KeywordBaseline()) as client:
        response = client.system_one(
            state="anything",
            questions={"x": Noul(instructions="?"), "y": Choice(instructions="?", criteria={"a": None, "b": None})},
        )
    assert response.nouls["x"].noul == 0.5
    assert response.choices["y"].confidence == pytest.approx(0.0)


def test_live_client_refuses_without_a_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(MissingKey):
        live_client()


def test_cost_uses_the_list_price():
    assert cost_usd(1_000_000) == pytest.approx(0.042)
