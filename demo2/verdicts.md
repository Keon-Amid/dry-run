# Pre-registered verdicts (Dungeon Painter, demo2)

Written before the first real build. Each real plant owns exactly one visible check and one held-out check; no two
plants share a check. `golden/workspace` passes every check except the decoy. `flawed/<plant>/` is golden with only
that plant's literal (flawed) reading; each fails exactly its own check + its held-out + the decoy (tested).

| Plant | Where | Its check (held-out) | Origin / surfaced | Flip: with / without | Expected pipeline verdict |
|---|---|---|---|---|---|
| Ambiguity | spec step 4 "Every torch lights the floor tiles within 3 steps of it." | `torch_light_stops_at_walls` (`heldout_torch_light_corner`) | 4 / 4 | fail 3/3 / pass 3/3 | real_problem; culprit spec step 4; swarm shows both readings (grid distance vs walking steps) |
| Contradiction (origin != surfaced) | spec step 1 "Each line is stripped of surrounding whitespace ..." vs step 5 "a space is void" | `cave_keeps_shape` (`heldout_cave_ring`) | 1 / 5 | fail 3/3 / pass 3/3 | real_problem; surfaced 5, origin 1; culprit spec step 1; fork at c0 |
| Bad harness rule | `rules/portable.md` "never emit `<text>` elements" vs step 6's status-bar label | `hud_status_text` (`heldout_hud_text_other`) | 6 / 6 (rule acts from step 1) | fail 3/3 / pass 3/3 | real_problem; culprit rule portable.md (harness, not spec); fork at c0; no swarm |
| Decoy (bad check) | `checks/hero_is_yellow.py` wants `#ffff00`; spec step 3 says the hero is `#ffffff` | `hero_is_yellow` | - | fails in every arm | test_wrong (fails on golden/); spec untouched |
| Control | spec step 2 (tile palette) + `rules/style.md` | `tiles_palette` | - | pass 3/3 / pass 3/3 | green throughout; the control patch (identical bytes) and turning style.md off flip nothing |
| Placebo | spec step 3 "Draw every sprite after all the tiles, so they sit on top." paraphrased | `sprites_on_top` | - | pass 3/3 / pass 3/3 | no flip (a meaning-preserving edit must not name a culprit) |

Flip `--to-step` per plant = the step its check first becomes checkable: control 2, placebo 3, ambiguity 4,
contradiction 5, bad_rule 6. One run of `scripts/flip.py --to-step 7` covers them all (and `render_demo()` needs 7).
A plant that doesn't flip cleanly (anything other than 3/3 fail with vs 3/3 pass without) is dropped.

## What a human sees (base run vs after Banzai, `python3 demo2/render.py --side-by-side BASE FIXED out.html`)

- **Ambiguity:** in the base image torchlight (gold tiles) leaks through the stone wall into the big water room and
  through the door into the cave; after the fix the light stays inside the torch's own little chamber.
- **Contradiction:** in the base image the round cave on the left is mangled: every indented row slid to the left
  edge, so the walls zig-zag and the cave is a lopsided blob; after the fix the cave is round again (the right-hand
  room, whose rows weren't indented, looks the same in both, which is why the cause is hard to spot by eye).
- **Bad harness rule:** in the base image the status bar under the map is a bare red bar with no words; after the
  rule is switched off it reads "HP 7/10  Gold 3".
- **Decoy / control / placebo:** the pictures are identical in every arm; only the decoy check is red, on golden too.

## Why this domain shows Banzai off

A dungeon map is a picture, so every planted flaw is something you can point at on a screen (light through a wall, a
broken cave, a missing label), while the checks still grade it exactly by parsing the SVG. Its seven steps build on
each other through real code (the parser from step 1 is silently reused by the void tiles of step 5 and the scene of
step 7), which is what makes "surfaced at step 5, caused at step 1" a true story that only git blame plus a branch
from checkpoint c0 can tell. And it is the team's roguelike theme: the same scene the page's characters walk through.
