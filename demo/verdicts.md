# Pre-registered verdicts (Shortlink)

Written and committed before the first real build. Each plant owns exactly one visible check and one held-out check;
no two plants share a check. `golden/` passes every check except the decoy.

| Plant | Where | Its check (held-out) | Flip test: with / without | Expected pipeline verdict |
|---|---|---|---|---|
| Ambiguity | spec step 4 "Links expire after 30 days." | `expiry_from_last_click` (`heldout_expiry_keeps_alive`) | fail 3/3 / pass 3/3 | real_problem; surfaced 4, origin 4; culprit spec step 4; swarm shows both readings |
| Contradiction | spec step 2 "Codes are 6 digits: ..." vs step 5 aliases | `alias_resolves` (`heldout_alias_digits_hyphens`) | fail 3/3 / pass 3/3 | real_problem; surfaced 5, origin 2; culprit spec step 2 |
| Bad harness rule | `rules/errors.md` "never raise, return None" | `rejects_bad_urls` (`heldout_shorten_rejects_bad_url`) | fail 3/3 / pass 3/3 | real_problem; culprit rule errors.md (harness, not spec); no swarm |
| Decoy (bad check) | `checks/stats_json.py` wants a JSON string, spec says dict | `stats_json` | fails in every arm | test_wrong (fails on golden/); spec untouched |
| Control | spec step 6 (clicks) + `rules/style.md` | `clicks_counted` | passes in every arm | green throughout; turning style.md off flips nothing |

Flip `--to-step` per plant = the step its check first becomes checkable: bad_rule 1, ambiguity 4, contradiction 5.
A plant that doesn't flip cleanly (anything other than 3/3 fail with vs 3/3 pass without) is dropped.

## Flip result (1:25 gate), claude-haiku-5-5, 3 runs per arm, from `demo/runs/flip-*.json`

| Plant | Check | with p/f/inv | without p/f/inv | Verdict | Kept |
|---|---|---|---|---|---|
| bad_rule | rejects_bad_urls | 0/3/0 | 3/0/0 | FLIP | yes |
| ambiguity | expiry_from_last_click | 0/3/0 | 3/0/0 | FLIP | yes |
| contradiction | alias_resolves | 3/0/0 | 3/0/0 | no flip | **dropped**: Haiku reconciles step 2 with step 5 itself |

The spec text is unchanged; the contradiction line stays in step 2, but it isn't a plant any more and has no
expected verdict. `codes_6_digits` timed out in 4 of 12 runs because the check passed a 333k-code `taken` set; it now
passes 1,000 codes (a check fix, not a plant change).
