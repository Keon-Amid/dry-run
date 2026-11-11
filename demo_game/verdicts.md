# Pre-registered verdicts (Dungeon)

Written and committed before the first real build. Each plant owns exactly one visible check and one held-out check;
no two plants share a check. `golden/` passes every check except the decoy.

| Plant | Where | Its check (held-out) | Flip test: with / without | Expected pipeline verdict |
|---|---|---|---|---|
| Ambiguity | spec step 4 "The pit costs a life." (does the player end up in the pit?) | `pit_stays_back` (`heldout_pit_from_above`) | fail 3/3 / pass 3/3 | real_problem; surfaced 4, origin 4; culprit spec step 4; swarm shows both readings |
| Bad harness rule | `rules/performance.md` "update the state in place, never copy" vs spec step 2 | `step_returns_new_state` (`heldout_branching_states`) | fail 3/3 / pass 3/3 | real_problem; culprit rule performance.md (harness, not spec); no swarm |
| Decoy (bad check) | `checks/actions_uppercase.py` wants `"E"`, spec says lowercase only | `actions_uppercase` | fails in every arm | test_wrong (fails on golden/); spec untouched |
| Control | spec step 3 (key + locked exit) + `rules/style.md` | `key_opens_exit` | passes in every arm | green throughout; turning style.md off flips nothing |

Flip `--to-step` per plant = the step its check first becomes checkable: bad_rule 2, ambiguity 4.
A plant that doesn't flip cleanly (anything other than 3/3 fail with vs 3/3 pass without) is dropped.

## Flip result (1:25 gate), claude-haiku-5-5, 3 runs per arm, from `demo_game/runs/flip-*.json`

| Plant | Check | with p/f/inv | without p/f/inv | Verdict | Kept |
|---|---|---|---|---|---|
| ambiguity | pit_stays_back | 0/3/0 | 3/0/0 | FLIP | yes (held-out `heldout_pit_from_above` also 0/3 vs 3/3) |
| bad_rule | step_returns_new_state | 3/0/0 | 3/0/0 | no flip | **dropped**: Haiku follows spec step 2 over the rule |

`rules/performance.md` stays on the disk unchanged (the template is pre-registered); it is no longer a plant.
Control `key_opens_exit` passed 3/3 in both ambiguity arms.
