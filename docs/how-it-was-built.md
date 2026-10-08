# How this repo was built with Claude Code

Built in one Claude Code session with Claude Opus 5.5, from this request: *"There is buzz on the market around Jev + Claude Code. Can you do the research and create a case study to demonstrate using a sample app in a new GitHub repo?"*

## 1. Research before code

- Read TypeSafe's docs index (`llms.txt`) and the pages that matter: coding agents, models and pricing, confidence, fan-out, and **jaggedness** (the known weak spots).
- Read the official [skill](https://github.com/typesafe-ai/skills) and followed its rule that *"the live docs are the source of truth"*.
- Read the community integrations (jev-kit, jev-code, jev-mcp, and others) and grouped them into four patterns.
- Read the critical coverage as well as the launch posts: DataSci Ocean, beri.net, paddo.dev.
- Installed `typesafe-sdk` 0.7.2 and **read its source**, not just its docs: client options (`transport=`), answer types, retry policy, and environment variables. That's how the offline baseline could plug into the real SDK through `httpx2.MockTransport`.
- Read Claude Code's hooks and permissions docs for the exact `PreToolUse` output shape, and found the fact the guard is designed around: **a hook's `allow` skips the permission prompt**.

## 2. Decisions taken from the research

| Finding | Decision |
|---|---|
| Jev can't be Claude Code's model | Build pattern A (an app) and pattern B (a hook); describe C and D |
| One vague question scored 62.6%, five narrow ones 95% (beri.net) | The guard asks five questions; the eval compares five against one |
| Jev is weak at dates and math | SLA arithmetic is in code; urgency levels describe situations, not numbers |
| Jev reads literally | Boundary cases go in each Noul's criteria |
| Adversarial state can move answers | The agent's own description of its command is never sent |
| "When Jev is wrong, it is usually sure of itself" | Confidence gates the auto-route, and the threshold is chosen from a sweep over labeled data |
| No TypeSafe key on the build machine | A keyword baseline speaks the same API, so everything runs offline and the Jev results are left empty, not invented |

## 3. Build order

Policy and questions first, then the offline baseline, then the evals, then the tests (64, all offline), then a real end-to-end run of the hook with Claude Code-shaped JSON on stdin. **That run is where the logging bug appeared:** the hook crashed before printing its deny. It's now fixed and covered by a regression test. See [Jev Guard](jev-guard.md#the-bug-we-hit-building-it).

## 4. What wasn't done

- **No live Jev run.** There was no `TYPESAFE_API_KEY` on the machine. The live columns in the README stay empty until someone runs `--live`.
- **Patterns C and D aren't implemented here.** [Research](research.md#why-c-and-d-arent-built-here) explains why and links working implementations.
- **The labels are one person's judgment.** The ticket and command labels were written by the same author as the code. The triage baseline was written before the tickets; the guard baseline was written with the command list in mind, so treat it as an optimistic baseline.

## Prompt patterns that did the work

From [Claude Code prompt patterns](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/claude-code-prompt-patterns.md):

- "Read the live docs and the SDK source before writing integration code."
- "Write the failing test first" for each policy rule and hook guarantee.
- "Prove it works: pipe real hook JSON through it and show the output." This is how the logging bug was found.
- "What didn't you verify?" Section 4 above.
