import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from triage_desk.app import Ticket, load_tickets, make_client, triage
from triage_desk.evals import grade, sweep
from triage_desk.policy import Judgment, decide
from triage_desk.questions import QUESTIONS

T0 = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def judgment(**overrides) -> Judgment:
    base = dict(
        department="technical",
        department_probabilities={"technical": 0.9, "billing": 0.05, "account": 0.03, "sales": 0.01, "other": 0.01},
        department_confidence=0.88,
        urgency=1.0,
        security=0.02,
        legal=0.02,
        refund=0.1,
        churn=0.05,
        model="test",
        input_tokens=500,
        latency_ms=120.0,
    )
    return Judgment(**{**base, **overrides})


def test_one_request_per_ticket_carries_every_question():
    client, baseline = make_client(live=False)
    triage(client, Ticket(id="x", subject="Charged twice", body="Please refund the duplicate charge."))
    assert len(baseline.requests) == 1
    request = baseline.requests[0]
    assert set(request["questions"]) == set(QUESTIONS)  # speculative fan-out: one round trip
    assert request["state"] == {"ticket": {"subject": "Charged twice", "body": "Please refund the duplicate charge."}}


def test_confident_answer_is_auto_routed_with_the_sla_computed_in_code():
    d = decide("t", T0, judgment(urgency=2.2))
    assert (d.queue, d.auto, d.priority) == ("technical", True, "P2")
    assert d.due == T0 + timedelta(hours=8)


def test_security_overrides_everything_and_always_gets_a_person():
    d = decide("t", T0, judgment(security=0.8, department_confidence=0.99, urgency=0.0))
    assert (d.queue, d.auto, d.priority) == ("security", False, "P1")
    assert d.due == T0 + timedelta(hours=1)


def test_low_confidence_goes_to_review_with_the_two_candidates():
    d = decide("t", T0, judgment(department_confidence=0.4))
    assert (d.queue, d.auto) == ("review", False)
    assert "technical 0.90 vs billing 0.05" in d.reasons[0]


def test_no_match_goes_to_review():
    d = decide("t", T0, judgment(department="other", department_confidence=0.95))
    assert (d.queue, d.auto) == ("review", False)


def test_legal_language_keeps_the_team_but_needs_a_person():
    d = decide("t", T0, judgment(legal=0.9))
    assert (d.queue, d.auto) == ("technical", False) and "legal" in d.tags


def test_speculative_refund_answer_is_used_only_for_billing():
    assert "refund" not in decide("t", T0, judgment(refund=0.95)).tags
    billing = judgment(department="billing", department_probabilities={"billing": 0.95, "technical": 0.05}, refund=0.95)
    assert "refund" in decide("t", T0, billing).tags


def test_threshold_sweep_reuses_answers_without_new_calls():
    client, baseline = make_client(live=False)
    tickets = load_tickets()[:10]
    decisions = [triage(client, t) for t in tickets]
    calls = len(baseline.requests)
    rows = sweep(tickets, decisions)
    assert len(baseline.requests) == calls
    assert [r["auto_rate"] for r in rows] == sorted((r["auto_rate"] for r in rows), reverse=True)


def test_offline_eval_runs_end_to_end():
    client, _ = make_client(live=False)
    tickets = load_tickets()
    g = grade(tickets, [triage(client, t) for t in tickets])
    assert g["tickets"] == 40 and g["model"] == "keyword-baseline"
    assert 0 <= g["auto_accuracy"] <= 1 and g["cost_usd"] > 0


def test_eval_set_is_well_formed():
    tickets = load_tickets()
    assert len({t.id for t in tickets}) == len(tickets) == 40
    for t in tickets:
        assert t.labels["department"] in {"billing", "technical", "account", "sales", "other"}
        assert t.labels["urgency"] in {0, 1, 2, 3}
        assert t.received_at.tzinfo is not None


@pytest.fixture
def server():
    from triage_desk.web import make_server

    client, _ = make_client(live=False)
    srv = make_server(client, model_label="keyword baseline", note="offline", host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_web_api_and_page_escape_user_text(server):
    body = json.dumps({"subject": "<script>alert(1)</script>", "body": "My invoice is wrong."}).encode()
    request = urllib.request.Request(f"{server}/api/triage", data=body, headers={"Content-Type": "application/json"})
    decision = json.load(urllib.request.urlopen(request))
    assert decision["queue"] in {"billing", "review"}
    page = urllib.request.urlopen(f"{server}/").read().decode()
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_web_api_rejects_bad_input(server):
    request = urllib.request.Request(f"{server}/api/triage", data=b'{"subject": "x"}')
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(request)
    assert err.value.code == 400
