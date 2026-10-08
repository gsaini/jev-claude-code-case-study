"""Keyword versions of the guard's questions: the offline baseline. Not Jev — see jev_common.baseline."""

from __future__ import annotations

import re

from jev_common.baseline import KeywordBaseline


def _p(pattern: str):
    rx = re.compile(pattern)
    return lambda text: 0.9 if rx.search(text) else 0.05


DESTROYS = r"\brm\b|\bdelete\b|-delete\b|\bdrop\b|\btruncate\b|\bprune\b|\bdestroy\b|\bshred\b|\s>\s"
LEAVES = r"\bpush\b|\bpublish\b|\bdeploy\b|\bupload\b|\bscp\b|\brsync\b|-x\s*(post|put|patch|delete)\b|\bapply\b"
DISCARDS = r"--force\b|\s-f\b.*\bpush\b|\bpush\b.*\s-f\b|reset\s+--hard|\bclean\s+-\w*f|checkout\s+--\s|restore\s+\."
SYSTEM = r"\bsudo\b|\bbrew\s+install\b|npm\s+(i|install)\s+-g\b|pip\s+install\s+--user\b|>>\s*~/\.\w+rc|\bchsh\b"
SECRETS = r"\bsecret|\btoken\b|\bpassword\b|\bapi[_-]?key\b|\bcredential|\.env\b"


def keyword_baseline() -> KeywordBaseline:
    return KeywordBaseline(
        nouls={
            "destroys_data": _p(DESTROYS),
            "leaves_machine": _p(LEAVES),
            "discards_work": _p(DISCARDS),
            "system_wide": _p(SYSTEM),
            "exposes_secrets": _p(SECRETS),
            "risky": _p("|".join((DESTROYS, LEAVES, DISCARDS, SYSTEM, SECRETS))),
        }
    )
