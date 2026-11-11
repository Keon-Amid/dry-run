# v8: Banzai (formerly Dry Run; v7 + Brendan's four fixes)

*Same product as v7. What changed, and why:*
- *#4 "no disk": the agent's files and conversation now live on an Archil disk. Each step is a disk checkpoint;
  each fork is a disk branch mounted in a fresh sandbox. The disk is the product.*
- *#2 "fork budget": no paused sandboxes any more. Checkpoints are on the disk, so only running forks count (≤ 20).*
- *#1 "two culprits": each plant owns its own failing check, and the gate tests each one alone.*
- *#3 "real test last": the flip test moves to the 1:25 gate, as plain local builds before any orchestration.*

## The one line

**Your agent failed. Was it your spec, your harness, the model, or your test? We branch the agent's disk at the moment
it went wrong, prove which one it was, then send a swarm of branches to find the fix.**

## How it works

1. **BUILD.** A builder agent runs in a sandbox with an Archil disk mounted. Its workspace and its conversation log
   (`conversation.jsonl`) live on the disk. One spec step per turn; every turn it rereads `spec.md` and `rules/`. After
   each step: `git commit`, then a disk checkpoint `c_k`.
2. **GRADE.** The checks run (deterministic, never an LLM). Some fail.
3. **TRIAGE** each failing check:
   - fails on `golden/` → **your test is wrong**; the spec isn't touched
   - branch `c_{k-1}` 3 times, each in its own sandbox, rebuild that step: 0/3 fail → **the model slipped**;
     3/3 fail → a real problem
4. **LOCATE** with plain git: `git blame` gives the step where it surfaced, `git log -L` the step that first wrote those
   lines. The fork point is the checkpoint just before that.
5. **TEST SUSPECTS.** Branch the fork point 3 times per suspect (a spec line rewritten, or a harness rule switched off),
   plus 3 control branches. Each resumes from the saved conversation, runs to the end, and is graded. The culprit flips
   the check against the control (3/3 vs 0/3).
6. **FAN OUT FIXES (the swarm).** From the same checkpoint, ~5 rewrites of the culprit line × 3 branches = 15.
   - **Ambiguous line:** each reading gets its own branch; the card shows what each builds; the human picks.
   - **Spec defect:** a rewrite wins only if it passes 3/3, passes the **held-out checks** it never saw, and leaves the
     control untouched. All rewrites are shown, losers included.
7. **CONFIRM.** One fresh build from step 0 with the winning fix.

Every branch keeps its own `routes/<id>.md` (hypothesis, edit, result, verdict) and has a share link: anyone can open
the disk at that exact moment. Steps before the fork point are never rebuilt; only CONFIRM starts from step 0.

**Output, one card per failure:** *"Cause: spec step 2, 'codes are 6 digits'. Surfaced at step 5. Suspect test: 3/3 vs
control 0/3. Swarm: 15 branches tried 5 rewrites, 2 pass 3/3 + held-out."*

## Demo

"Shortlink": a URL-shortener API, ~150 lines, 7 spec steps, ~10 checks + 3–4 held-out checks, plus `golden/`.

| Plant | Expected verdict |
|---|---|
| Ambiguity: "links expire after 30 days" (checks want 30 days from the last click) | spec line; swarm shows both readings |
| ~~Contradiction: step 2 "codes are 6 digits" vs step 5 "users may pick an alias"~~ | **Dropped 20:50:** no flip with Haiku 5.5 (3/3 pass with the plant); see `demo/verdicts.md` |
| A bad harness rule (P2 picks it) | harness, not spec |
| Bad check (decoy): fails on `golden/` | your test is wrong |
| Control: one correct step + one good rule | untouched, stays green |

**Rule for plants:** each plant owns **its own** failing check, and no two plants touch the same check. Pre-register the
verdicts before the first run. Fallback `spec-b.md`: ambiguity + decoy + control only.

## Archil

- **The disk carries the agent:** its files and its conversation. A checkpoint per step (~15 ms) and a branch per fork
  (~35 ms, any disk size), per the docs. Each fork = its own disk branch + its own sandbox.
- **Why not git?** Git restores the code. The branch restores the whole workspace (dependencies, build output, data) and
  the agent's conversation, at any step, in 35 ms, mounted and ready for a new agent.
- **Facts that bite:**
  - checkpoints are made with the `archil` CLI on a mounted disk, so inside a sandbox (Linux), not on a Mac
  - branches and checkpoints **can't be deleted**
  - BYOB disks can't use them
  - ≤ 20 sandboxes at once (Developer plan); delete each sandbox in a `finally`
- **One swap point (so we can try the other approach):** all Archil code sits behind two calls in P1's area,
  `save(step) -> checkpoint_id` and `resume(checkpoint_id) -> worker`. Today: disk checkpoint + branch mounted in a fresh
  sandbox. Fallback (v7): fork + pause a sandbox per step. Nothing outside those two calls knows which one is used.
- **Sandbox count, worst case:**

| Wave | Running sandboxes |
|---|---|
| Build | 1 |
| Triage | 3 per failing check, ~3 checks = 9 |
| Suspects | ~4 suspects × 3 + 3 control = 15 |
| Swarm | 5 rewrites × 3 = 15 |

  Waves run one at a time, so the peak is 15–16. No paused sandboxes.

## Roles (TBD by the three of us)

- **P1 Archil & orchestrator:** disk + sandbox setup, checkpoint per step, branch + mount per fork, waves, run files.
- **P2 Spec & checks:** `spec.md`, `spec-b.md`, `rules/`, checks, held-out checks, `golden/`, git trace, the plants.
- **P3 Builder & page:** builder loop (conversation saved to disk), triage, swarm rewrite prompt, cards page, pitch.

Run files between areas: `run.json`, `triage.json`, `results.json`, `swarm.json`, `archil.json`. The page is built
against fakes first. `python -m orchestrator.pipeline [--local]` writes all five (plus `baseline.json`, `report.md`) to `orchestrator/runs/<stamp>/`
(P1); `orchestrator/runs/20261110-200432/` is a real Archil run with the stub builder and checks.

- **`run.json`** (the build): `{run_id, disk_id, store, builder, n_steps, model, simulated_slip, checkpoints{"k":
  checkpoint_id}, final_checks{name: bool}, steps[{step, wall_s, wrote[files], checks{name: bool},
  checks_hidden_during_build, checkpoint_ms}]}`. `wrote` = files changed on the disk by that step (hash diff).
  Optional per step, copied from the builder's RESULT `steps[]` when present: `tool_calls`, `commit`, `model_calls`, `usage` (the sum of the API's `usage` objects: `input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`); missing ones make the matching savings `"unknown"`.
- **`triage.json`**: `checks[{check, verdict: test_wrong|model_slip|real_problem|inconclusive, surfaced_step,
  origin_step, fails_on_golden, rebuild{checkpoint_id, step, fails: "3/3", errors, invalid, wave}|null, fork_checkpoint_id?,
  suspects{wave, control: "0/3", suspects[{route, kind, step, old, new, rule, score}]}?, culprit{...one suspect}|null?,
  swarm{branches, rewrites, winners}?, confirm{passed, text}?, card}]`. `card` is the one-line card text, built from these fields.
- **`results.json`** (every wave, appended): `waves[{wave, purpose: triage|suspects|swarm|confirm|smoke, check, targets,
  checkpoint_id, fork_step, to_step, n, wall_s, routes[{route, kind, edit, runs, graded, passed, errors, invalid,
  score: "passed/graded"}],
  copies[{id, route, kind, edit, branch, ok, invalid?, passed, checks{name: bool}, builder{...RESULT json + exit_code},
  wall_s, timings_ms{branch, sandbox, mount}, error?}]}]`.
- **`swarm.json`**: `swarms[{check, culprit, fork_checkpoint_id, wave, heldout_checks, n_branches, n_rewrites,
  rewrites[{route, text, visible: "3/3", heldout: "3/3", regressions[checks], errors, winner}], winners[routes],
  confirm{wave, route, text, ok, passed, regressions, checks, error}|null}]`. CONFIRM = one fresh build from `c0` with
  the shortest winner.
  A winner passes the visible check and its held-out checks 3/3 with no regression against the control.
- **`archil.json`**: what branching saved. `waves[{wave, fork_step, wall_s, copies[{id, branch_ms, sandbox_ms,
  mount_ms, wall_s}], steps_reused, sum_copy_s, parallel_speedup, saved{steps, minutes, model_calls, usd,
  restore_minutes_vs_git}}]`, `totals_saved` (same keys plus `copies`), `per_step_avg` (from `run.json`),
  `restore_baseline` (git clone + install, from `spikes/disk_spike.json`), `spent{model, build, waves{name}, total}`
  (`{model_calls, usd}` each, from the builder's per-step usage), `stages_s` (wall seconds per pipeline stage).
- **`baseline.json`**: `baselines[{check, fixer, message, call{model_calls, usage, wall_s, stop_reason, usd}, diff,
  fixed_spec, error, prompt, reply, wave, n_builds, visible: "k/3", heldout: "k/3", regressions, errors, passes_all}]`.
  One plain Claude call (same model as the swarm, no tools) gets the original spec + the failing visible check's name
  and message and returns a whole fixed spec; it is built from `c0` three times. **`report.md`**: before / after /
  baseline pass rates side by side, generated from the run files. "Saved" = each copy would otherwise
  replay steps `1..fork_step`.

## Clock (0:00 = 7:00 PM)

| Time | Gate |
|---|---|
| 0:30 | Spike: sandbox mounts a disk, checkpoints from inside, branch mounted in a 2nd sandbox, `conversation.jsonl` intact; times printed. `golden/` passes all but the decoy |
| **1:25** | **Flip test, local, no Archil:** for each plant, 3 builds with it → its check fails 3/3; 3 builds with it removed → passes 3/3. Otherwise drop that plant or switch to `spec-b.md` |
| 1:45 | Full build on Archil with a checkpoint per step; trace prints `check → surfaced step → origin step` |
| 2:10 | Suspect wave from the fork point flips 3/3 vs control 0/3 |
| 2:25 | Swarm wave; winners chosen on held-out checks |
| 2:40 | Full run end to end; cards on the page |
| 2:50 | Recorded full run as a fallback video |
| 3:00 | Rehearse; one live suspect wave on stage |

**Cut first → last:** confirm build → swarm to 3 rewrites × 2 → harness-rule plant → share links →
live run (play the recording).
**Never cut:** Keon's game (the pixel-roguelike page that shows the run: each copy is a character that dies when its check fails), the 1:25 flip test, triage before suspects, control branches, held-out checks for swarm winners, counts.

## Pitch (90 s)

1. "Your agent failed. Whose fault was it: your spec, your harness, the model, or your test?"
2. The build runs; each step is a checkpoint of the agent's whole disk, files and conversation.
3. A check fails. Triage: *"your test is wrong, we didn't touch your spec"*, then a real one.
4. "Blame says step 5; the lines were first written at step 2." Branch step 2, one change per branch. Flip grid: 3/3 vs 0/3.
5. "Now a swarm." 15 branches light up, each a different rewrite. Winners pass checks they never saw.
6. "Every branch is a link: open the agent's disk at that exact moment."

## If asked

- **"Why not git?"** Git restores the code. A branch restores the whole workspace and the agent's conversation in 35 ms.
- **"Couldn't the swarm game your checks?"** Winners must pass held-out checks they never saw, 3/3, control untouched.
- **"You planted the bugs."** On purpose, as ground truth; the decoy, control and triage show it doesn't blame everything.
- **"Does it work on Claude Code?"** Not shown tonight. Claude Code keeps its conversation in files too, so the same
  branch-and-resume should apply. Untested; say so.

## Open questions

1. Who is P1, P2, P3?
2. Orchestrator language: Python (our Archil spikes) or TypeScript?
3. Which harness rule P2 plants (it must fail its own check, not the alias one).
4. Spike answer by 0:30: can a sandbox mount a branch and checkpoint from inside? If not, branch from the orchestrator.
