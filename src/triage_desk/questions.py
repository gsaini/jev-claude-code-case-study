"""The judgments Triage Desk asks for — all of them in one request per ticket.

Design rules, from TypeSafe's docs and Jev 1.13's documented weak spots:

- One narrow judgment per question; policy is combined in code (policy.py), not in a prompt.
- Every Choice has a no-match option (`other`), so the model is never forced into a wrong team.
- Speculative questions state their premise ("Assuming ... billing") and are only consumed when
  the premise holds — ignoring the unused answers costs a few input tokens, not a second request.
- No arithmetic and no dates: the urgency Score picks a described situation; the SLA clock is code.
- The state names its parts (`ticket.subject`, `ticket.body`) and carries nothing the questions don't need.
"""

from __future__ import annotations

from typing import Any

from typesafe_sdk import Choice, Noul, Score

DEPARTMENTS: dict[str, str] = {
    "billing": "Charges, invoices, payment methods, refunds, or the price of a plan the customer already has",
    "technical": "Something in the product is broken, erroring, slow, or an integration or API call fails",
    "account": "Signing in, passwords, two-factor, profile, team members and roles, or closing the account",
    "sales": "Buying, upgrading, quotes, discounts, or plans the customer does not have yet",
    "other": "None of the above, or not a support request at all (spam, thanks, auto-replies)",
}

URGENCY: list[str] = [
    "Can wait a week: a question, a suggestion, or a minor annoyance",
    "Within a few days: something is wrong, but the customer can keep working",
    "Today: the customer is blocked from doing their work",
    "Right now: the service is down for them, money is being lost, or data is at risk",
]

QUESTIONS: dict[str, Any] = {
    "department": Choice(
        instructions="Which team should handle the support ticket in `ticket`?",
        criteria=DEPARTMENTS,
    ),
    "urgency": Score(
        instructions="How urgent is the support ticket in `ticket` for the customer who wrote it?",
        criteria=URGENCY,
    ),
    "security": Noul(
        instructions=(
            "Does the ticket in `ticket` report a possible security problem: an account takeover, "
            "someone else accessing the account, leaked or exposed data, or a phishing message?"
        ),
    ),
    "legal": Noul(
        instructions="Does the ticket in `ticket` threaten legal action, or mention a lawyer, a court, or a regulator?",
    ),
    # Speculative: consumed only when the department answer is billing.
    "refund": Noul(
        instructions=(
            "Assuming the ticket in `ticket` is about billing: does the customer ask for a refund "
            "or for a charge to be reversed?"
        ),
    ),
    "churn": Noul(
        instructions="Does the customer in `ticket` say they will cancel, leave, or move to a competitor?",
    ),
}


def state_for(subject: str, body: str) -> dict[str, Any]:
    return {"ticket": {"subject": subject, "body": body}}
