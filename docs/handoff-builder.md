# Handoff: implement `docs/plan-builder.md`

You are brendan's agent on the Dry Run team. This handoff turns `docs/plan-builder.md` into working code under
`builder/`. **Stay on task:** build only what that plan marks as the builder area or **[mine]**. Items marked **[team]**
are not yours to implement unless brendan says the team agreed. Never edit `CONTRACT.md`'s scope or demo sections.

**How to start (brendan types this):** `Run the handoff in docs/handoff-builder.md. Use a workflow.`
Saying "use a workflow" is the explicit opt-in to a multi-agent run.

## Read first (only these)

1. `.claude/CLAUDE.md` (team rules: channel, `Decided:` lines, the REAL/STUBBED/HARDCODED footer).
2. `docs/plan-builder.md` (the design; this handoff adds implementation detail and does not override it).
3. `CONTRACT.md` sections "How it works", "Demo", "Clock".
4. Skill `claude-api` **before** writing `builder/llm.py`. Confirm the model id, tool-use format and prompt-caching
   syntax there; don't rely on memory.
5. Skill `archil` only if you reach the 1:45 integration step.

## Approved by brendan

- Create `builder/`, `builder/tests/` and `scripts/flip.py`.
- **`./check` already exists (edan, e1ede98)**: it runs `python -m unittest discover -s . -t . -p 'test_*.py'` from the
  repo root, with no Archil and no API calls. Don't replace it. Name test files `test_*.py` and add `__init__.py` to
  `builder/` and `builder/tests/` so discovery finds them. The FakeLLM smoke run is a `test_*.py` too.
- **Standard library only.** HTTP goes through `urllib.request`, tests use `unittest`, and nothing is pip installed. A
  new dependency needs brendan's OK.
- Python 3.11+.

## Swarm plan

Agent budget: 5 coders (Opus 5.5) + 2 red-team reviewers (Fable 5.2) = 7. The lead (you) does Phase 0 and Phase 2
itself.

### Phase 0: lead, serial, ~10 min. Freeze the interfaces before fan-out.

Write `builder/types.py` with every shared dataclass and signature below, with `raise NotImplementedError` bodies in
the module stubs. Write `builder/tests/fixtures/toy/`:
- `spec.md`: 3 steps with `## Step k` headers.
- `rules/style.md`: one active rule.
- `heldout/` and `checks/`: deliberately outside the disk folder, used to prove they never leak.

Commit (no push). Every coder reads `types.py` and must not change it. If a coder needs a change, it reports back and
the lead decides.

```python
# builder/types.py (shape; finalize names here once)
@dataclass class Patch:      route: str; kind: Literal["spec_line","rule_off","control"]; step: int|None
                             old: str|None; new: str|None; rule: str|None; hypothesis: str
@dataclass class StepResult: step: int; commit: str; tool_calls: int; capped: bool
                             wall_s: float; model_calls: int
                             usage: dict   # summed API usage: input_tokens, output_tokens,
                                           # cache_creation_input_tokens, cache_read_input_tokens
@dataclass class State:      last_done: int; patch_id: str|None; patch_applied: bool
                             spec_sha_before: str|None; spec_sha_after: str|None
                             model: str; params: dict; steps: list[StepResult]
class LLM(Protocol):         def create(self, system: list[dict], messages: list[dict],
                                        tools: list[dict]|None) -> dict: ...   # raw Messages API response
class Exec(Protocol):        def read_file(self, p: str) -> str; def write_file(self, p: str, s: str) -> str
                             def list_files(self, p: str=".") -> str; def bash(self, cmd: str, timeout: int=30) -> str
class PatchError(Exception): ...
class ResumeError(Exception): ...
```

### Phase 1: five coders in parallel, disjoint files. Each writes its module and its tests. No one runs a real LLM.

| Agent | Owns (only these files) | Must prove with tests |
|---|---|---|
| **C1 convo+state** | `builder/convo.py`, `builder/state.py`, `builder/gitops.py` | append is one fsynced write per step; truncate_after(k); state written atomically (tmp + `os.replace` + dir fsync); repair after a simulated crash (log ahead of state, HEAD ahead of tag); stale tags > last_done deleted |
| **C2 tools** | `builder/tools.py` | path escape rejected (`../`, absolute, symlink out); bash timeout kills the process group; output truncated to 4k with a marker; bash env has **no** `ANTHROPIC_API_KEY` or other `*_KEY`/`*_TOKEN`; cwd is `workspace/` |
| **C3 patch+local** | `builder/patch.py`, `builder/local.py` | spec_line fails on 0 or 2 matches; rule_off deletes the file (no `.off/`); control rewrites identical bytes via the same path; spec sha before/after recorded; landed-assert raises if the edit didn't take; `local.save` / `local.resume` copy a folder and keep git intact |
| **C4 llm+prompt** | `builder/llm.py`, `builder/prompt.py`, `builder/fake_llm.py` | prompt holds spec steps ≤ k only and active rules only; `cache_control` on the system block and the last history message; 429/529/overloaded retried with jittered backoff honouring `retry-after`; FakeLLM replays a script keyed by step, including a tool-use turn and an over-budget turn |
| **C5 rewrite+flip** | `builder/rewrite.py`, `scripts/flip.py` | the rewrite prompt contains no held-out or check-source text (test greps it against the fixture strings); output validated (5 distinct, all ≠ original, at least one delete/shorten); sorted shortest first; flip.py writes `flip.json` and prints its table **only from that file** |

Each coder finishes with: files changed, `python -m unittest discover builder/tests -v` output (tail), and
REAL/STUBBED/HARDCODED.

### Phase 2: lead, serial. Integrate.

1. `builder/loop.py` `run_step(disk, k, llm, ex, max_calls) -> StepResult`, and `builder/run.py` CLI (spec below).
2. End-to-end test with FakeLLM on the toy spec:
   - build steps 1..3 one process per step;
   - copy the disk at c_1, patch step 2, resume `--from-step 2`, and check the log, HEAD and state;
   - `--drop-conversation` (blind arm) starts with an empty history but the same files.
3. `./check` (edan's existing script) must pass, including `builder/tests/test_smoke.py` (a FakeLLM run of
   `builder.run`).
4. **One** real-LLM smoke run on the toy spec, steps 1..3, before the 1:25 gate. Print the token totals from
   `state.json`; don't type them.

### Phase 3: dual red team (Fable 5.2, parallel, read-only)

Give each reviewer the diff (`git diff origin/main`), `docs/plan-builder.md` and this file. Do **not** give them your
own assessment. Each returns findings as: file:line, failure scenario, wrong outcome, minimal fix, CONFIRMED (they ran
or traced it) or PLAUSIBLE.

- **R1: "Does the code do what the plan claims?"**
  - Resume invariants: log, HEAD and state agree after every crash point.
  - Capped turns leave a valid log.
  - Patches land or fail loudly.
  - Each step is one commit plus one tag.
  - Result line and exit codes.
  - Tests that pass without testing anything (`a-control-that-tests-nothing`).
- **R2: "Can the verdicts be wrong or gamed?"**
  - Can the builder read checks, held-out checks, `golden/` or removed rules via bash or path tricks?
  - Can old spec wording reach a resumed branch, through the log or the workspace files?
  - Can the rewrite prompt leak held-out content?
  - Can a capped or errored branch be counted as a fail?
  - Can flip.py print a number not read from a file?
  - Can the API key reach the agent?

The lead fixes every CONFIRMED finding and either fixes PLAUSIBLE ones or notes them in the report. Then run `./check`
again.

### Phase 4: ship

Use `/ship`. Show brendan the explain-back and **wait for brendan's OK** before pushing. Post `merged`; post `touched <owner>`
if you edited anything of P1's or P2's.

## Implementation detail (beyond the plan)

**`builder/run.py` CLI**
```
python -m builder.run --disk DIR --from-step K --to-step N [--patch patch.json] [--route ID]
                      [--max-calls 25] [--drop-conversation] [--fake-llm script.json]
```
- Logs go to stderr. The **last stdout line** is `RESULT {json}` (see the plan for the shape); P1 parses only that
  line.
- Exit codes: 0 ok, 2 capped (invalid branch), 1 error. A `PatchError` or `ResumeError` is exit 1 with a reason in
  RESULT.
- Model from env `DRYRUN_MODEL` (default: the fast current Sonnet id confirmed via `claude-api`). Key from
  `ANTHROPIC_API_KEY`, read only in `llm.py`. Temperature left at the API default, and logged.

**Turn construction (C4 plus the lead)**
- System = `[{"type":"text","text": preamble(disk,k), "cache_control": {"type":"ephemeral"}}]`. The preamble is the
  harness instructions, spec steps 1..k, and the active rules.
- History = messages from `conversation.jsonl` (the `msg` field only), then `{"role":"user","content":"Do step k."}`.
  Put `cache_control` on the last history block so each tool-loop call reuses the prefix.
- Tool schemas: `read_file{path}`, `write_file{path,content}`, `list_files{path?}`, `bash{command}`. Each tool result is
  a `tool_result` block with `is_error` set on exceptions. Never raise out of the loop for a tool error.
- Stop when `stop_reason == "end_turn"`. At the limit, send `tool_result` "budget reached, finish now" for every pending
  `tool_use`, make one final call with `tools=None`, then mark the step capped.

**Disk and git (C1)**
- Commit with a fixed identity: `git -c user.name=builder -c user.email=builder@dryrun.local commit --allow-empty -m
  "step k"`, then `git tag -f step-k`.
- `c_0` = a `git init` workspace with an empty commit tagged `step-0`, made by `run.py` on first use.
- Resume check: `from_step == state.last_done + 1`, max log step == last_done, `HEAD == step-<last_done>`. On a
  mismatch, repair (truncate the log, `reset --hard`, `clean -fdx`, delete tags > last_done). Any repair is logged to
  stderr and recorded in RESULT.

**Isolation (C2)**
- Resolve every path against `workspace/`, reject it if it's outside after `realpath`, and refuse to follow symlinks
  out.
- bash: `subprocess.run(..., cwd=workspace, start_new_session=True, timeout=t, env=clean_env)`. On timeout,
  `os.killpg`. `clean_env` keeps only `PATH`, `HOME`, `LANG` and `TMPDIR`.
- Known limit, stated in the report: bash can still `cd /` and read any file on the box. Real isolation is the sandbox,
  where checks are not mounted. Locally, keep checks outside the disk folder.

**Patches (C3)**
- `spec_line` edits only inside the named `## Step k` section.
- Record `spec_sha_before`/`spec_sha_after`. The landed-assert is: spec_line changes the sha; rule_off leaves the file
  absent; control keeps the sha the same with `patch_applied=true`.
- Patch file and hypothesis go into `routes/<route>.md`.

**flip.py (C5)**
- Inputs: `--plants plants.json` (stub until P2 delivers: `[{"id","patch":{...},"check":"name"}]`), `--runs 3`, and env
  `DRYRUN_CHECK_CMD` (P2's grader, called with the workspace path, JSON on stdout).
- For each plant: 3 disks with the plant, 3 with it removed via its patch, run to the last step, grade, append to
  `flip.json`.
- Capped runs are counted separately as invalid, never as passes or fails.
- Option `--matrix` grades **all** checks per run (team item F; build the flag, it's cheap).

**What not to build** (team items, not approved): changes to the triage order, the suspect-list generator, placebo
waves, card labels. Leave a `TODO(team: A..L)` only where code would plug in.

## Checklist before reporting done

- [ ] `./check` green; output tail pasted.
- [ ] `state.json` steps carry `wall_s`, `model_calls` and `usage` (all four token fields), plus top-level `model`, so
      P1 can copy them straight into `run.json` (CONTRACT.md > Roles, edan's contract change).
- [ ] FakeLLM end-to-end: build, patch, resume, blind arm.
- [ ] One real toy run; numbers printed from `state.json`.
- [ ] Both red-team reports received; every CONFIRMED finding fixed or explained.
- [ ] Commit messages carry `Decided:` lines for every judgment call.
- [ ] Report ends with REAL / STUBBED / HARDCODED.
