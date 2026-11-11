# Banzai report: 20261110-211022-demo2-real

Builder: builder/ (real) · model: claude-sonnet-5-5 · disk: `dsk-00000000001919d8`. Every number below is read from this folder's run files.

## Verdicts

| Failing check | Verdict | Surfaced / origin step | Card |
|---|---|---|---|
| `cave_keeps_shape` | real_problem | 5 / 1 |  |
| `hero_is_yellow` | test_wrong | 3 / 2 |  |
| `hud_status_text` | real_problem | 6 / 6 |  |
| `torch_light_stops_at_walls` | real_problem | 4 / 4 |  |

## `cave_keeps_shape`

Held-out checks: `heldout_cave_ring`.

| Arm | Visible check | Held-out | Cost |
|---|---|---|---|
| Before: the checkpointed build | 0/1 | 0/1 | build |
| Before: original spec, 3 fresh builds from step 0 | 0/3 | 0/3 | None calls, $None |
| Before: control branches (no change) | 0/3 | 0/3 | None calls, $None |

## `hud_status_text`

Held-out checks: `heldout_hud_text_other`.

| Arm | Visible check | Held-out | Cost |
|---|---|---|---|
| Before: the checkpointed build | 0/1 | 0/1 | build |
| Before: original spec, 3 fresh builds from step 0 | 0/3 | 0/3 | None calls, $None |

## `torch_light_stops_at_walls`

Held-out checks: `heldout_torch_light_corner`.

| Arm | Visible check | Held-out | Cost |
|---|---|---|---|
| Before: the checkpointed build | 0/1 | 0/1 | build |
| Before: original spec, 3 fresh builds from step 0 | 1/3 | 1/3 | None calls, $None |

## Cost and Archil

- Spent: None model calls, $None (build None; orchestrator calls None).
- Wall: None s; stages {}.
- Branching saved (archil.json totals): {'steps': 36, 'minutes': 5.47, 'model_calls': 72.0, 'usd': 0.892, 'restore_minutes_vs_git': 3.9, 'copies': 27, 'wall_s': 216.209, 'sum_copy_s': 1403.33}.
