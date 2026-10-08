"""Claude Code PreToolUse hook: `.venv/bin/python -m jev_guard.hook` (see .claude/settings.json).

Protocol (https://code.claude.com/docs/en/hooks): the tool call arrives as JSON on stdin; to deny or
force a permission prompt, print `hookSpecificOutput` with `permissionDecision` and exit 0. Printing
nothing leaves the decision to Claude Code's own permission rules.

This hook prints only "deny" or "ask", never "allow" — an "allow" would skip the permission prompt,
and a probabilistic judge should never be the thing that waves a command through.

Environment:
- JEV_GUARD_MODE       `shadow` (default): Jev's opinions are logged, not enforced. `enforce`: they are.
                       Code rules (hard deny, secrets) are deterministic and always enforced.
- JEV_GUARD_THRESHOLD  Noul probability that counts as "yes" (default 0.5).
- JEV_GUARD_BASELINE   `1` to use the offline keyword baseline instead of Jev (demos only).
- TYPESAFE_API_KEY     Or, better, the file ~/.config/jev-guard/key (chmod 600), so the key isn't in the
                       environment of the agent being judged. With neither, ambiguous commands get no
                       opinion and Claude Code decides.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any

from jev_common.client import baseline_client, live_client
from jev_guard.baseline_rules import keyword_baseline
from jev_guard.engine import Verdict, evaluate

BUDGET_SECONDS = 2.0  # Jev usually answers in ~100-500 ms; past this, Claude Code's rules decide
KEY_FILE = Path.home() / ".config" / "jev-guard" / "key"


def main(stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout, env: Mapping[str, str] = os.environ) -> int:
    payload = json.load(stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = str(payload.get("tool_input", {}).get("command", ""))
    mode = env.get("JEV_GUARD_MODE", "shadow")
    threshold = float(env.get("JEV_GUARD_THRESHOLD", "0.5"))

    if env.get("JEV_GUARD_BASELINE") == "1":
        client = baseline_client(keyword_baseline())
    elif key := _api_key(env):
        client = live_client(api_key=key, timeout=BUDGET_SECONDS, retries=0)
    else:
        client = None

    verdict = evaluate(command, client, threshold=threshold)
    enforced = verdict.decision != "none" and (verdict.source == "rule" or mode == "enforce")
    if enforced:  # decide and answer first: nothing after this line may cost us the decision
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": verdict.decision,
                    "permissionDecisionReason": f"jev-guard: {verdict.reason}",
                }
            },
            stdout,
        )
        stdout.flush()
    _log(env, payload, verdict, mode, enforced)
    return 0


def _api_key(env: Mapping[str, str]) -> str | None:
    if key := env.get("TYPESAFE_API_KEY", "").strip():
        return key
    key_file = Path(env.get("JEV_GUARD_KEY_FILE") or KEY_FILE)
    try:
        return key_file.read_text().strip() or None
    except OSError:
        return None


def _log(env: Mapping[str, str], payload: dict[str, Any], v: Verdict, mode: str, enforced: bool) -> None:
    """One JSON line per decision. Commands are logged redacted, never raw."""
    root = Path(env.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    log = root / ".jev-guard" / "decisions.jsonl"
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "session": payload.get("session_id", ""),
        "command": v.command,
        "decision": v.decision,
        "source": v.source,
        "reason": v.reason,
        "mode": mode,
        "enforced": enforced,
        "probabilities": {k: round(p, 3) for k, p in v.probabilities.items()},
        "latency_ms": round(v.latency_ms, 1),
        "model": v.model,
    }
    try:  # best effort: a full disk or a missing directory must never undo a decision
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"jev-guard: could not write {log}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
