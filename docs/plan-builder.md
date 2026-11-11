# Plan: builder loop and patch replay (brendan)

Status: proposal. Roles are still "TBD" in `CONTRACT.md`, and nothing here changes the contract until a human edits it.
Items marked **[team]** change the method or the demo and need edan and keon to agree. Items marked **[mine]** stay
inside the builder area.

Sources: `CONTRACT.md` v8, the Archil skill notes, and two review passes (harness design, adversarial spec review).
There are also lessons from the duck-bill blind-build retrospectives (Cleaning project, Nov 6–8). Nothing has been run
yet.

## Scope

| Area | Owns |
|---|---|
| brendan | `builder/`: step loop, tools, conversation log, patch apply, rewrite generator, local mode |
| P1 | `save`/`resume`, sandboxes, waves, grading calls, assembling `run.json` / `triage.json` / `results.json` / `swarm.json` |
| P2 | `spec.md`, `rules/`, checks, held-out checks, `golden/`, git trace, plants |

The worker writes no shared run file. It writes `state.json` and `routes/<id>.md` on the disk, and prints one JSON
result line that P1 copies into the run files.

## The worker

The same program is used by every wave: build, triage, suspects, swarm and confirm.

```
python -m builder.run --disk DIR --from-step K --to-step 7 --patch patch.json --route ID
```

Disk layout (the agent's view):
```
DIR/
  workspace/            # app repo; commit "step k" + tag step-k per step; c_0 = before step 1
  spec.md  rules/       # read by the harness each turn; not readable as answers by the agent (see below)
  conversation.jsonl    # {"step":k,"msg":{...}} per line, Anthropic Messages format, fsynced per step
  state.json            # {last_done, patch_id, patch_applied, model, params, steps:[...]}
  routes/<id>.md        # hypothesis, edit, result, verdict
```

Checks, held-out checks, `golden/` and switched-off rules are **never** on the agent's disk; P1 grades from outside.
The agent's bash can read `../`. The duck build gamed the judge's tools when it was given them (it renamed a material
to dodge the bill detector).

### One step

1. Build a per-turn preamble from **spec steps 1..k only** plus the active `rules/`. It is sent as the system prompt
   and **never written to `conversation.jsonl`**. This way a spec edit at the fork point takes effect when the branch
   resumes, and the builder can't see step 5's text at step 2. Needs P2 to give `spec.md` `## Step k` headers.
2. Replay the history from `conversation.jsonl`, then send the user message "Do step k."
3. Run the tool loop: read_file, write_file, list_files, bash. Bash has a 30 s timeout, kills the process group and
   truncates output to about 4k characters.
4. Limit tool calls (~25 for build, ~12 for branches). At the limit, answer the pending tool calls with "budget
   reached", make one final call with tools disabled, then commit. The step is marked `capped`. A capped branch is
   reported as **invalid**, never as a fail.
5. `git add -A && git commit --allow-empty -m "step k"` and tag `step-k`. Then append the step's messages in one fsynced
   write, and atomically write `state.json` with `last_done=k`.
6. Exit (build wave), so P1 can call `save(k)` between turns. Branch waves run to the end in one process with no
   checkpoints, because checkpoints can't be deleted.

### Resume
- At `c_{k-1}`, the conversation ends at step k-1, HEAD is `step-(k-1)`, and `last_done=k-1`.
- On start, check all three. If they disagree, repair: drop log lines with step > `last_done`,
  `git reset --hard step-<last_done>` and `git clean -fd`.
- Then apply the patch once and loop to `--to-step`.

### Patches
```json
{"route":"s2-a1","kind":"spec_line|rule_off|control","step":2,"old":"…","new":"…","rule":null,"hypothesis":"…"}
```
- `spec_line`: exactly one match, or it fails loudly.
- `rule_off`: removes the rule from the disk (not into a readable `.off/`).
- `control`: goes through the same code path and rewrites identical text.
- **Every branch asserts its edit landed** (the spec hash changed, the rule file is gone) and records it in
  `state.json`. **[mine]**

### Rewrite generator (swarm)
- Input: the culprit line, that step's text, and the visible check's name and message. **Never** held-out checks; a
  test asserts this.
- Output: `rewrites.json` with 5 distinct rewrites, each different from the original.
- It includes **delete or shorten** rewrites and prefers the shortest winner. In the duck work every correction became
  a new constraint that bent the next run; the winning fix there was mostly removal. **[mine]**
- Ambiguity mode returns readings instead of fixes.

### Local mode
`DIR` is a plain folder, and `save` is a copytree. This runs the 1:25 flip test with no Archil.

### Model access
Whether a sandbox can reach api.anthropic.com is unknown. Tools sit behind one `Exec` interface, so the loop can run
on the laptop with tools executed in the sandbox if needed.

## Changes to the method [team]

A review found that, as written, only the decoy verdict comes out reliably.

| # | Change | Why |
|---|---|---|
| A | Run LOCATE before triage, then rebuild from `c_{origin-1}` to the end. Reuse those 3 runs as the control arm | Triage needs k. Rebuilding only the surfaced step inherits an earlier slip, so the spec gets blamed for a model error. Saves a wave |
| B | Only 3/3 vs 0/3 names a culprit; anything else is "inconclusive", shown with counts | 1/3 and 2/3 are undefined. An ambiguous line gives mixed results most of the time |
| C | Mechanical suspect list: spec lines of the origin and surfaced steps plus every rule. Edits are delete or minimal disambiguation only. Add one **placebo** branch (a meaning-preserving paraphrase) that must not flip | Today the list is either the plants (circular) or LLM edits that can make an innocent line flip |
| D | Fork at the suspect's own step − 1, and at `c_0` for rules | A rule acts from step 1; forking later means the edit is never acted on |
| E | Surfaced step = the first commit that fails the check. Run the checks on every commit. `git blame -w -M -C` is used for the origin only. Each check gets a "checkable from step N" tag | Blame breaks on reformatting and on bugs that are missing code. In the duck the origin was in parts that didn't look like the failure |
| F | At the 1:25 gate, test the full matrix: remove each plant alone and grade all checks. It must be diagonal | Shows plants don't interact; the control as written never enters the pipeline |
| G | Plant a labelled simulated model slip, or drop "model" from the pitch | One of the four verdicts is never shown |
| H | One held-out check per plant, testing the same intent on a different case | Otherwise swarm winners can fit the visible check |
| I | One **blind branch** (the same checkpoint files with `conversation.jsonl` dropped) on one suspect. If it disagrees with the resumed branch, the card says "conversation leak" | Old intent carries through history: the duck's baked shading "remembers the part you removed" |
| J | Unedited branches must reproduce the failure 3/3, or the wave is void | "A green control and an unperformed control look the same from output alone" |
| K | Label every card claim as confirmed (flip-tested), supported (blame says) or speculative | So git's guess isn't shown like a tested result |
| L | Move CONFIRM later in the cut order | The duck's winning move was a fresh blind rebuild, which is closest to CONFIRM |

**Be honest if asked:** "one culprit per check" holds only because we plant it that way; the duck's causes overlapped.
Dry Run diagnoses only what deterministic checks can see; the duck failure was caught by eye.

## Timeline

| Gate | Builder work | Stubbed | Proof |
|---|---|---|---|
| → 1:00 | convo, state, tools, patch, loop | LLM scripted, 2-step toy spec | pytest: write order, crash repair, patch on 0 or 2 matches, capped turn leaves a valid log |
| 1:25 | real LLM, local mode, `scripts/flip.py` (+ matrix F) | no Archil; P2 checks run as a subprocess | flip table printed from result files |
| 1:45 | worker behind P1's `resume()`, one step per process | remote `Exec` only if needed | 7 checkpoints, 7-step log, P2's trace reads the `step k` commits |
| 2:10 | patch + resume from the fork point | rewrites hand-written | culprit 3/3, placebo 0/3, good rule 0/3, control matches the build |
| 2:25 | `rewrite.py` live | none | `rewrites.json` validates; held-out text absent from the prompt (test) |
| 2:40 | hardening: backoff, timeouts, capped counts surfaced | none | one full run with no manual steps |

## Risks
- **Throughput (estimate, not measured).** 15 branches × ~6 steps × ~8 calls is about 700 requests per wave, roughly
  4–6 minutes. Mitigations: a fast model, prompt caching, 429 backoff, and a lower tool-call limit on branches.
- **New dependency.** An HTTP call from the standard library avoids adding the `anthropic` SDK; needs an OK either way.

## Open questions for brendan
1. Roles: is brendan P3? Who builds the cards page?
2. OK to create `builder/`? Standard library HTTP, or the `anthropic` SDK?
