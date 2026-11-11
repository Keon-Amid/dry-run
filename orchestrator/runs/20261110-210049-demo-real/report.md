# Banzai report: 20261110-210049-demo-real

Builder: builder/ (real) · model: claude-haiku-5-5 · disk: `dsk-000000000019172a`. Every number below is read from this folder's run files.

## Verdicts

| Failing check | Verdict | Surfaced / origin step | Card |
|---|---|---|---|
| `expiry_from_last_click` | real_problem | 4 / 4 | Cause: spec step 4, "Links expire after 30 days.". Surfaced at step 4, origin step 4. Suspect test: 3/3 vs control 0/3. Swarm: 15 branches tried 5 rewrites, 3 pass 3/3 + held-out. Confirmed: a fresh build from step 0 with it passes. |
| `rejects_bad_urls` | real_problem | 1 / 1 | Cause: rule errors.md. Surfaced at step 1, origin step 1. Suspect test: 3/3 vs control 0/3. |
| `stats_json` | test_wrong | 6 / 3 | stats_json: your test is wrong (it fails on golden/ too). The spec wasn't touched. |

## `expiry_from_last_click`

Held-out checks: `heldout_expiry_keeps_alive`.

| Arm | Visible check | Held-out | Cost |
|---|---|---|---|
| Before: the checkpointed build | 0/1 | 0/1 | build |
| Before: original spec, 3 fresh builds from step 0 | 0/3 | 0/3 | 43 calls, $0.0381 |
| Before: control branches (no change) | 0/3 | 0/3 | 74 calls, $0.0981 |
| After: the culprit's suspect edit (step 4 edit) | 3/3 | 3/3 | 74 calls, $0.0981 |
| After: swarm rw3 "Links expire after 30 days unused." | 3/3 | 3/3 | 125 calls, $0.1821 |
| After: swarm rw4 "Expiry is 30 days after the last click." | 3/3 | 3/3 | 125 calls, $0.1821 |
| After: swarm rw5 "Links expire 30 days after their last click." | 3/3 | 3/3 | 125 calls, $0.1821 |
| After: CONFIRM, fresh build from step 0 with rw3 | 1/1 | 1/1 | 15 calls, $0.0142 |
| After: both fixes, fresh build from step 0 with spec.fixed.md | 1/1 | 1/1 | 15 calls, $0.0167 |
| Baseline: one claude-haiku-5-5 call rewrites the spec, built from step 0 | 3/3 | 3/3 | 45 calls, $0.0463 + fix call $0.000771 |

All swarm rewrites (losers included):

| Rewrite | Visible | Held-out | Regressions | Winner |
|---|---|---|---|---|
| rw1 "" | 0/3 | 0/3 | - | no |
| rw2 "Links expire." | 0/3 | 0/3 | - | no |
| rw3 "Links expire after 30 days unused." | 3/3 | 3/3 | - | yes |
| rw4 "Expiry is 30 days after the last click." | 3/3 | 3/3 | - | yes |
| rw5 "Links expire 30 days after their last click." | 3/3 | 3/3 | - | yes |

<details><summary>Baseline's spec change</summary>

```diff
--- spec.md (original)
+++ spec.md (baseline fix)
@@ -21,8 +21,11 @@
   before looking it up.
 
 ## Step 4
-Links expire after 30 days. Put the expiry logic in `expiry.py` and use it in `Shortlink.resolve`: an expired link
-resolves to None.
+Links expire 30 days (2592000 seconds) after their last activity. A link's last activity is its creation time,
+or the time of its most recent successful `resolve` if it has been resolved since. Put the expiry logic in
+`expiry.py` and use it in `Shortlink.resolve`. A link is expired when `now` is 30 days or more after its last
+activity. An expired link resolves to None. A successful `resolve` of a live link sets its last activity to `now`,
+which extends its life by another 30 days from that click.
 
 ## Step 5
 Users may pick an alias instead of a generated code: `shorten(url, now=0, alias=None)`. An alias is 3 to 30
```
</details>

## `rejects_bad_urls`

Held-out checks: `heldout_shorten_rejects_bad_url`.

| Arm | Visible check | Held-out | Cost |
|---|---|---|---|
| Before: the checkpointed build | 0/1 | 0/1 | build |
| Before: original spec, 3 fresh builds from step 0 | 0/3 | 0/3 | 43 calls, $0.0381 |
| Before: control branches (no change) | 0/3 | 0/3 | 142 calls, $0.1315 |
| After: the culprit's suspect edit (rule errors.md off) | 3/3 | 3/3 | 142 calls, $0.1315 |
| After: both fixes, fresh build from step 0 with spec.fixed.md | 1/1 | 1/1 | 15 calls, $0.0167 |
| Baseline: one claude-haiku-5-5 call rewrites the spec, built from step 0 | 3/3 | 0/3 | 44 calls, $0.0454 + fix call $0.000553 |

<details><summary>Baseline's spec change</summary>

```diff
--- spec.md (original)
+++ spec.md (baseline fix)
@@ -6,8 +6,8 @@
 
 ## Step 1
 Create `urls.py` with `normalize(url: str) -> str`. Accept only `http://` and `https://` URLs that have a host.
-Lowercase the scheme and the host; keep the path, query and fragment exactly as given. Anything else is rejected
-with a `ValueError`.
+Lowercase the scheme and the host; keep the path, query and fragment exactly as given. Anything else, including
+URLs with other schemes such as `ftp://`, must raise a `ValueError`. Never return None for a rejected URL.
 
 ## Step 2
 Create `codes.py`. Codes are 6 digits: `is_valid_code(code)` is True only for a string of exactly 6 digits.
```
</details>

## After: both fixes (one fresh build from step 0, every check)

13/14 checks pass. Failing: `stats_json`.

## Cost and Archil

- Spent: 533 model calls, $0.601 (build {'model_calls': 14, 'usd': 0.017}; orchestrator calls {'model_calls': 3, 'usd': 0.0017}).
- Wall: 756.49 s; stages {'build': 107.009, 'natural': 64.748, 'triage': 43.192, 'suspects': 210.412, 'swarm': 104.115, 'confirm': 68.23, 'baseline': 158.768, 'total': 756.49}.
- Branching saved (archil.json totals): {'steps': 81, 'minutes': 14.92, 'model_calls': 162.0, 'usd': 0.1971, 'restore_minutes_vs_git': 7.7, 'copies': 50, 'wall_s': 709.612, 'sum_copy_s': 3082.508}.
