# Dry Run

**Your agent failed. Was it your spec, your harness, the model, or your test?**

Dry Run forks the running agent at the moment it went wrong, proves which one it was, then sends a swarm of forks to find the fix.

Built at Archil's agent-builder hackathon, Casco SF, Nov 10 2026. Everything in this repository was written during the event.

> **Status:** in progress. This README describes the design we're building tonight. It will say plainly what works, what's stubbed and what we measured once those exist.

## How it works

1. **Build.** A builder agent runs inside an [Archil](https://archil.com) sandbox and builds a spec one step per turn, rereading the spec and its rules every turn. After each step it commits, and we fork the sandbox and pause the fork. Each step becomes a frozen copy of the agent: its memory, its files and its running processes.
2. **Grade.** Deterministic checks run against the build. No LLM decides pass or fail.
3. **Triage.** Each failing check gets sorted before anything else is spent on it:
   - it also fails on our reference implementation → **your test is wrong**, and the spec is left alone;
   - rebuilding that step on 3 forks passes every time → **the model slipped**;
   - it fails 3 out of 3 → a real problem in the spec or the harness.
4. **Locate.** Plain git, no LLM. `git blame` gives the step where the failure surfaced, and `git log -L` gives the step that first wrote those lines, which is where it started.
5. **Test suspects.** From the paused copy just before that step, fork 3 copies per suspect: a spec line rewritten, or a harness rule switched off, plus 3 control forks with nothing changed. The culprit is the change that flips the result against the control, reported as counts (3/3 vs 0/3), never a single run.
6. **Swarm the fix.** From the same paused copy, about 6 rewrites of the culprit line run in 3 forks each. A rewrite only wins if it passes 3/3, passes held-out checks the swarm never saw, and leaves the control untouched. Every rewrite is shown, losers included.
   - If the line is **ambiguous**, Dry Run doesn't guess what you meant. It shows what each reading builds and asks you to pick.
7. **Confirm.** One fresh build from step 0 with the winning fix.

Each fork writes down its hypothesis, the edit, the result and the verdict in `routes/<id>.md`.

The output is one card per failure:

> *Cause: spec step 2, "codes are 6 digits". Surfaced at step 5. Suspect test: 3/3 vs control 0/3. Swarm: 18 forks tried 6 rewrites, 2 passed 3/3 and the held-out checks. Best: "codes are 6-character alphanumeric".*

## Why Archil

Git can restore files, but not an agent in the middle of a build. An Archil fork carries the agent's context, its running processes and its files together, so Dry Run can reopen the exact moment something went wrong and try many changes from there in parallel, without rebuilding the steps before it.

## The demo

"Shortlink", a small URL-shortener API built from a 7-step spec, with planted problems whose expected verdicts we write down before the first run:

| Planted problem | Expected verdict |
|---|---|
| "Links expire after 30 days" (from creation, or from the last click?) | an ambiguous spec line; both readings shown |
| Step 2 says codes are 6 digits, step 5 lets users pick an alias | surfaced at step 5, started at step 2 |
| A harness rule: "never edit files written by earlier steps" | the harness, not the spec |
| A check that fails on the reference implementation | your test is wrong |
| One correct spec step and one good rule | left untouched |

## Team

Brendan, Edan, Keon.
