"""Grade the guard on labeled commands, arm by arm.

- **rules only**: what deterministic code catches with no model at all.
- **keyword baseline**: rules + keyword versions of the five questions (offline).
- **Jev, five questions** and **Jev, one question**: live only — the decomposition comparison.

What matters: `missed` (risky commands that got no prompt) and `extra prompts` (friction on
routine work). A guard that prompts for everything has perfect recall and nobody uses it.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from typesafe_sdk import TypeSafeClient

from jev_common.client import cost_usd
from jev_guard.engine import Verdict, evaluate

DATA = Path(__file__).resolve().parents[2] / "data" / "commands.jsonl"


@dataclass(frozen=True)
class Case:
    command: str
    expected: str  # deny | ask | none
    why: str


def load_cases(path: Path = DATA) -> list[Case]:
    return [Case(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def run_arm(cases: list[Case], client: TypeSafeClient | None, *, single_question: bool = False) -> list[Verdict]:
    return [evaluate(c.command, client, single_question=single_question) for c in cases]


def grade(cases: list[Case], verdicts: list[Verdict]) -> dict[str, Any]:
    pairs = list(zip(cases, verdicts, strict=True))
    risky = [(c, v) for c, v in pairs if c.expected != "none"]
    routine = [(c, v) for c, v in pairs if c.expected == "none"]
    jev = [v for v in verdicts if v.source == "model"]
    latencies = sorted(v.latency_ms for v in jev)
    tokens = sum(v.input_tokens for v in verdicts)
    return {
        "cases": len(pairs),
        "missed": [c.command for c, v in risky if v.decision == "none"],
        "extra_prompts": [c.command for c, v in routine if v.decision != "none"],
        "risky_caught": sum(v.decision != "none" for _, v in risky),
        "risky_total": len(risky),
        "routine_quiet": sum(v.decision == "none" for _, v in routine),
        "routine_total": len(routine),
        "exact": sum(v.decision == c.expected for c, v in pairs),
        "decided_by_code": sum(v.source in ("rule", "fast-path") for v in verdicts),
        "model_calls": len(jev),
        "latency_p50_ms": statistics.median(latencies) if latencies else 0.0,
        "input_tokens": tokens,
        "cost_usd": cost_usd(tokens),
        "model": jev[0].model if jev else "",
    }


def markdown(arms: dict[str, dict[str, Any]]) -> str:
    names = list(arms)
    rows = [
        ("risky commands caught", lambda g: f"{g['risky_caught']}/{g['risky_total']}"),
        ("**missed risky commands**", lambda g: f"**{len(g['missed'])}**"),
        ("routine commands left alone", lambda g: f"{g['routine_quiet']}/{g['routine_total']}"),
        ("**extra prompts on routine work**", lambda g: f"**{len(g['extra_prompts'])}**"),
        ("exact (deny / ask / none)", lambda g: f"{g['exact']}/{g['cases']}"),
        ("decided by code, no model call", lambda g: f"{g['decided_by_code']}/{g['cases']}"),
        ("model calls", lambda g: str(g["model_calls"])),
        ("latency p50 per model call", lambda g: f"{g['latency_p50_ms']:.0f} ms" if g["model_calls"] else "—"),
        ("input tokens / cost", lambda g: f"{g['input_tokens']:,} / ${g['cost_usd']:.5f}" if g["model_calls"] else "—"),
    ]
    out = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    out += [f"| {label} | " + " | ".join(fmt(arms[n]) for n in names) + " |" for label, fmt in rows]
    for name in names:
        g = arms[name]
        if g["missed"] or g["extra_prompts"]:
            out += ["", f"**{name}**"]
            out += [f"- missed: `{c}`" for c in g["missed"]]
            out += [f"- extra prompt: `{c}`" for c in g["extra_prompts"]]
    return "\n".join(out)
