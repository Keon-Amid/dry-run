# Dry Run

**Your agent failed. Was it your spec, your harness, the model, or your test?**

Dry Run branches the agent's disk at the moment it went wrong, proves which one it was, then sends a swarm of branches to find the fix.

Built at Archil's agent-builder hackathon, Casco SF, Nov 10 2026. Everything in this repository was written during the event.

> **Status:** in progress. This README describes the design we're building tonight ([CONTRACT.md](CONTRACT.md) is the full spec). It will say plainly what works, what's stubbed and what we measured once those exist.

## How it works

The builder agent's whole world lives on an [Archil](https://archil.com) disk: its code, its dependencies, its build output, and its conversation so far. That means any step of a build can be saved and reopened later, exactly as it was.

1. **Build.** A builder agent works through a spec one step per turn, rereading the spec and its rules every turn. After each step it commits, and we take a checkpoint of the disk: a saved moment of the agent's files and conversation.
2. **Grade.** Deterministic checks run against the build. No LLM decides pass or fail.
3. **Triage.** Each failing check gets sorted before anything else is spent on it:
   - it also fails on our reference implementation → **your test is wrong**, and the spec is left alone;
   - three fresh copies rebuild that step from the checkpoint before it, and all pass → **the model slipped**;
   - all three fail → a real problem in the spec or the harness.
4. **Locate.** Plain git, no LLM. `git blame` gives the step where the failure surfaced, and `git log -L` gives the step that first wrote those lines, which is where it started.
5. **Test suspects.** From the checkpoint just before that step, branch the disk 3 times per suspect: a spec line rewritten, or a harness rule switched off, plus 3 control branches with nothing changed. Each branch resumes the agent from its saved conversation and runs to the end. The culprit is the change that flips the result against the control, reported as counts (3/3 vs 0/3), never a single run.
6. **Swarm the fix.** From the same checkpoint, about 5 rewrites of the culprit line run on 3 branches each. A rewrite only wins if it passes 3/3, passes held-out checks the swarm never saw, and leaves the control untouched. Every rewrite is shown, losers included.
   - If the line is **ambiguous**, Dry Run doesn't guess what you meant. It shows what each reading builds and asks you to pick.
7. **Confirm.** One fresh build from step 0 with the winning fix.

Steps before the branch point are never rebuilt. Every branch writes down its hypothesis, the edit, the result and the verdict, and has its own share link, so anyone can open the agent's disk at that exact moment.

The output is one card per failure:

> *Cause: spec step 2, "codes are 6 digits". Surfaced at step 5. Suspect test: 3/3 vs control 0/3. Swarm: 15 branches tried 5 rewrites, 2 passed 3/3 and the held-out checks.*

## Why Archil

Git can restore the code. An Archil branch restores the agent's whole workspace (dependencies, build output, data) and its conversation, at any step, mounted and ready for a new agent to pick up. Branches share everything with the original and only store what changes, so making one doesn't depend on how big the disk is. That's what makes it affordable to go back to an earlier step and try many changes from there in parallel.

## The demo

"Shortlink", a small URL-shortener API built from a 7-step spec, with planted problems whose expected verdicts we write down before the first run. Each planted problem has its own failing check.

| Planted problem | Expected verdict |
|---|---|
| "Links expire after 30 days" (from creation, or from the last click?) | an ambiguous spec line; both readings shown |
| Step 2 says codes are 6 digits, step 5 lets users pick an alias | surfaced at step 5, started at step 2 |
| A bad harness rule | the harness, not the spec |
| A check that fails on the reference implementation | your test is wrong |
| One correct spec step and one good rule | left untouched |

## Team

Brendan, Edan, Keon.
