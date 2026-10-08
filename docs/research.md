# Research: what "Jev + Claude Code" actually is

*Researched 2026-10-07. Jev, its SDK, and the integrations around it are weeks old and changing fast; re-check anything you rely on.*

## What Jev is

**Jev** is the first model from **TypeSafe** that TypeSafe calls a *System One* model ([docs](https://docs.typesafe.ai/introduction)). It doesn't write text. You send a **state** (text or JSON) and a set of typed **questions**, and it returns typed answers with probabilities:

| Primitive | Asks | Returns |
|---|---|---|
| **Choice** | pick one option from a defined set | the option, a probability per option, `confidence` |
| **Score** | where the state sits on ordered, described levels | an expected level, a probability per level, `confidence` |
| **Noul** | is this statement true? | a probability of "yes" |

All the questions in a request are evaluated **in parallel against the same state**, so asking ten questions costs about the same latency as asking one ([speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)). The current model is `jev-1.13.0` ([models](https://docs.typesafe.ai/models)): **$42 per billion input tokens; output tokens are free**. The context limit is 64K tokens per request (32K for the state plus the longest question), and the input is text only. Rate limits are listed at 100K tokens/s and 80 requests/s, but TypeSafe warns that they are "adjusting dynamically". TypeSafe quotes 70–500 ms end to end, with most requests around 100 ms.

TypeSafe publishes a page of **known weak spots** for Jev 1.13 ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)), which shaped every design decision in this repo:

- it reads instructions **literally**, so boundary cases have to be spelled out in the criteria;
- it is unreliable at counting, math, and **date comparison** (keep those in code);
- it is weak on indirection and double negatives;
- accuracy drops when the state carries irrelevant detail;
- **adversarial content** in the state can move the answer;
- it leans toward the **first option** of a Choice;
- it can't generate text.

## What it is *not*

TypeSafe answers the obvious misunderstanding directly ([Jev with coding agents](https://docs.typesafe.ai/introduction/coding-agents)): Jev **cannot be the model behind Claude Code**. There is no `model: "jev-latest"` that turns a coding agent into a Jev agent, because a coding agent needs a model that writes text, calls tools, and edits files.

So "Jev + Claude Code" means using **both models together**, in one of four ways.

## The four integration patterns found in the wild

| Pattern | What happens | Examples | In this repo |
|---|---|---|---|
| **A. Claude Code builds with Jev** | Claude Code writes the application; the application calls Jev for its typed decisions | The official [TypeSafe skill](https://github.com/typesafe-ai/skills) (`claude plugin install typesafe@typesafe-ai`); [Charlie Hills' setup guide](https://charliehills.substack.com/p/jev-claude-code-the-setup-guide) (email triage) | ✅ **Triage Desk** |
| **B. Jev guards Claude Code's loop** | A Claude Code hook asks Jev about each tool call before it runs | [jev-kit](https://github.com/jonathanavis96/jev-kit)'s *Airlock* (`PreToolUse`) and *tier guard* (subagent dispatch) | ✅ **Jev Guard** |
| **C. Jev as a tool Claude Code calls** | An MCP server or CLI exposes classify, check, score, and rank, so the agent hands repetitive judgments to Jev | [jev-code](https://github.com/FrancoisChastel/jev-code) (`jev_classify`, `jev_check`, `jev_score`, `jev_rank`, `jev_ask`) | described below |
| **D. Jev drives the browser for Claude Code** | Claude delegates a browser task; [Jev Ultrafast](https://github.com/browser-use/jev-ultrafast) picks each click from an indexed menu of what's on the page | [jev-mcp](https://github.com/SAITS-Swiss-AI-Tech-Services/jev-mcp), [jev-reflex](https://github.com/MSalvalaggio/jev-reflex) ("Claude thinks, Jev reacts"), [jev-browser-skill](https://github.com/zurfyx/jev-browser-skill), [jev-browser-use](https://github.com/damian87x/jev-browser-use) | described below |

These all follow the same idea, from Kahneman by way of TypeSafe's naming. **Claude is System Two**: slow, generative, and in charge of planning and exceptions. **Jev is System One**: fast and typed, for the repetitive, bounded calls inside the loop. As [Flavio Copes' deep dive](https://flaviocopes.com/jev/) puts it, a coding agent can ask Jev whether a shell command is read-only, reversible, or destructive, but Jev never runs anything itself.

### Why C and D aren't built here

- **C (Jev as a tool)** is pattern A's question design exposed over MCP. The design work is the same: narrow questions, decisions in code, and thresholds checked against labeled data. `jev-code` already does this well, and it returns a `decision: auto | review` field derived from confidence, which matches Triage Desk's review queue.
- **D (browser)** needs Chrome, `jev-ultrafast`, and a second text model for typing, so it can't run offline in CI. The architecture is covered in the [Jev Ultrafast study note](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/jev-ultrafast.md). jev-kit reports **9/9 successes for Jev, 9/9 for Sonnet, and 4/9 for Haiku** on 3 goals × 3 repetitions, at **$0.0008 vs $0.1868** in Claude cost per run. Those are the project's own numbers on a very small sample.

## The claims, and what independent tests found

TypeSafe's headline is **"193.6× faster, 444.6× cheaper"**, and its own post says these figures are "on the higher end of real world gains". Independent write-ups agree on two caveats:

1. **The benchmark scores agreement, not correctness.** The reference answer is the average answer of two frontier models, not a human label ([DataSci Ocean](https://datasciocean.com/en/ai-concept/jev-overview/)). Third-party tests compiled there report roughly **5×–25× faster**, much smaller cost multiples, and accuracy "on par or slightly worse" than frontier models.
2. **Decomposition matters more than the model.** In a pre-registered phishing benchmark ([beri.net, 2026-09-20](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval)), Jev scored **62.6%** when asked a single "is this phishing?" question, against 81.3% for Claude Haiku 4.5. With the question split into **five narrow signals** combined by a logistic regression, it scored **95.0%** against Haiku's 93.2%. The same piece reports **miscalibration out of distribution**: an ECE of 0.107, and on one ticket-priority question Jev was right 44.7% of the time while giving an average probability of 0.74.

A production-style report ([paddo.dev, 2026-09-30](https://paddo.dev/blog/thirty-cent-judge)) judged 9,081 product-matching pairs for **$0.32 in 13 minutes**, and the share of correct published matches went from 78% to 90%. Its warning: *"When Jev is wrong, it is usually sure of itself."*

**What we took from this:** treat Jev as a cheap, fast, typed judgment that you **decompose**, **gate on confidence**, and **verify against labeled data**. Don't use it as an oracle. Its price is what makes the verification affordable: this repo's whole live eval costs a fraction of a cent.

## Sources

Official: [TypeSafe docs](https://docs.typesafe.ai/llms.txt) · [Jev with coding agents](https://docs.typesafe.ai/introduction/coding-agents) · [Models & pricing](https://docs.typesafe.ai/models) · [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) · [Confidence](https://docs.typesafe.ai/confidence) · [Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out) · [Agent skill](https://github.com/typesafe-ai/skills) · [Python SDK](https://docs.typesafe.ai/sdk/python) (`typesafe-sdk` 0.7.2) · [Claude Code hooks](https://code.claude.com/docs/en/hooks)

Community integrations: [jev-kit](https://github.com/jonathanavis96/jev-kit) · [jev-code](https://github.com/FrancoisChastel/jev-code) · [jev-mcp](https://github.com/SAITS-Swiss-AI-Tech-Services/jev-mcp) · [jev-reflex](https://github.com/MSalvalaggio/jev-reflex) · [jev-browser-skill](https://github.com/zurfyx/jev-browser-skill) · [jev-browser-use](https://github.com/damian87x/jev-browser-use) · [jev-ultrafast](https://github.com/browser-use/jev-ultrafast)

Coverage and evaluations: [Flavio Copes](https://flaviocopes.com/jev/) · [Charlie Hills](https://charliehills.substack.com/p/jev-claude-code-the-setup-guide) · [DataSci Ocean](https://datasciocean.com/en/ai-concept/jev-overview/) · [beri.net](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval) · [paddo.dev](https://paddo.dev/blog/thirty-cent-judge)

Numbers from community projects and third-party articles are **as reported by their authors**; this repo didn't reproduce them.
