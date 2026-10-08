# Working in this repo

A case study of **TypeSafe's Jev with Claude Code**. Two programs share one rule: Jev answers narrow,
typed questions; code owns policy, arithmetic, dates, and every action.

- `src/triage_desk/` routes support tickets (one TypeSafe request per ticket, policy in `policy.py`).
- `src/jev_guard/` is the PreToolUse hook in `.claude/settings.json` that judges your Bash commands.

## Commands

```bash
uv sync                       # creates .venv — the hook runs from .venv/bin/python
uv run pytest -q              # offline: the keyword baseline answers through the real SDK
uv run ruff check . && uv run ruff format --check .
uv run triage-desk eval       # offline baseline eval; add --live --yes for Jev (needs TYPESAFE_API_KEY)
uv run jev-guard eval         # same for the guard
```

## Rules for changes

- **Use the TypeSafe skill** (`/typesafe:typesafe-ai`) and read the live docs before changing a question,
  the SDK usage, or the API shape. Don't write TypeSafe code from memory.
- **Never send Jev what code can compute.** Counting, math, date comparison, exact lookups: code.
- **One judgment per question.** New behavior that needs a new judgment gets a new question, not a longer one.
- **Every question change needs labeled cases** in `data/` and an eval run before and after. Report both.
- **The guard never returns `allow`.** It may only deny or force a prompt. `test_the_hook_never_says_allow` pins this.
- **The guard decides before it does anything else.** Logging and other side effects come after the answer is printed.
- **The judge never sees the agent's justification.** Only the redacted command goes into the guard's state.
- Offline numbers come from the keyword baseline. Never present them as Jev's results.
