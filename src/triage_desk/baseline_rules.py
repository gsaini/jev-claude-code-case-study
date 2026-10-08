"""The keyword router a support team typically has before a model: the offline baseline.

Written before the eval set, and deliberately not tuned to it. It is here so the evals have an
honest "what we had before" column, and so tests and CI run the whole app with no key.
"""

from __future__ import annotations

from jev_common.baseline import KeywordBaseline, any_of, count_of

DEPARTMENT_WORDS = {
    "billing": ("charge", "invoice", "refund", "payment", "card", "billing", "receipt", "overcharg", "vat"),
    "technical": ("error", "broken", "bug", "crash", "fail", "timeout", "slow", "not working", "api", "webhook", "500"),
    "account": ("password", "log in", "login", "sign in", "2fa", "two-factor", "locked out", "invite", "role"),
    "sales": ("upgrade", "pricing", "quote", "enterprise", "discount", "demo", "trial", "seats", "annual plan"),
    "other": ("unsubscribe", "out of office", "auto-reply", "thank you so much"),
}
URGENT = (
    "asap",
    "urgent",
    "immediately",
    "right now",
    "down",
    "outage",
    "production",
    "losing",
    "can't work",
    "blocked",
)
CALM = ("no rush", "whenever", "suggestion", "curious", "just wondering", "feature request")


def _department(text: str) -> dict[str, float]:
    return {team: float(count_of(text, *words)) for team, words in DEPARTMENT_WORDS.items()}


def _urgency(text: str) -> list[float]:
    hot = count_of(text, *URGENT)
    calm = count_of(text, *CALM)
    return [0.6 + calm, 0.8, 0.9 * min(hot, 1), 0.9 * max(0, hot - 1)]


def keyword_baseline() -> KeywordBaseline:
    return KeywordBaseline(
        choices={"department": _department},
        scores={"urgency": _urgency},
        nouls={
            "security": lambda t: (
                0.9 if any_of(t, "hacked", "unauthori", "phishing", "breach", "compromised") else 0.05
            ),
            "legal": lambda t: (
                0.9 if any_of(t, "lawyer", "attorney", "legal action", "sue ", "court", "regulator") else 0.05
            ),
            "refund": lambda t: 0.85 if any_of(t, "refund", "money back", "chargeback", "reverse") else 0.1,
            "churn": lambda t: 0.85 if any_of(t, "cancel", "competitor", "switching to", "moving to") else 0.05,
        },
    )
