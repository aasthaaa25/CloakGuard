# Controlled validation

This is a controlled-behavior check. It is not a real-world detection rate, and it is not a cloaking ROC-AUC. The pilot has no supported positive class, so ROC-AUC on those 30 pairs is undefined.

## What the old fixture files were

`testbed/captures/` was written by `testbed/run_local_captures.py` directly to disk. No crawler requested those files. They remain parser fixtures. They are not a validated live crawl.

## What was run this time

`testbed/local_app.py` served two template families on `127.0.0.1`. `detection/pipeline/crawl.py`'s httpx fetcher requested each scenario four times, in order H1, B1, H2, B2, using the Chrome and Googlebot User-Agents already in `VIEW_PROFILES`. Expectations were written in `testbed/expectations.csv` before the scores were read. Results are `testbed/results/captures.csv` and `testbed/results/predictions.csv`.

All 64 fetches returned HTTP 200 with a body. The method recorded on each fetch is `httpx`. No screenshot was taken, so visual features were not used. The URL model file is not on the path the scorer checks, and every prediction used `fixed_weight_heuristic`. No URL score was filled in.

`north_market` is the development family. `harbor_books` uses the same structure and different ordinary wording. No threshold or weight was changed after either family was scored, so the harbor results are a second template, not a tuned holdout.

## Cross-profile H1 versus B1

The H2 versus B2 scores match these to three digits. Threshold is 0.50. `alert` means the score reached that threshold.

| Scenario | North score | Harbor score | Alert | What the configuration says |
| --- | --- | --- | --- | --- |
| Identical clean | 0 | 0 | no | No selective modification |
| Promotional wording on both profiles | 0 | 0 | no | Not selective cloaking. The words are outside the six keyword lists |
| Bot-only casino/viagra injection | 0.480 | 0.482 | no | Known selective injection. The score moved and stayed under 0.50 |
| Human-only casino/pills injection | 0.192 | 0.193 | no | Reverse injection. Signed jargon density is −0.333; the bot-only case is +0.333 |
| Rotating counter | 0.003 | 0.003 | no | Not an attack. Within-profile H1–H2 text drift is 0.032 and the score is 0.003 |
| Hidden link on the bot view | 0.082 | 0.082 | no | `bot_only_link_count` is 1. Promotional score is 0 because `offer` is not in the keyword lists |
| Identical defacement | 0 | 0 | no | Both views are replaced. Cross-view drift does not show it |
| Bot challenge page | 0.066 | 0.079 | no | Access difference, not a cloaking label |

The implementation can separate a clean pair, a shared promotional sentence, a rotating counter, a hidden link, and a keyword injection by their feature values. At the frozen 0.50 threshold it does not alert on any of them, including the known bot-only injection. That threshold was not lowered to make the injection alert.

## Owner-side checks

`testbed/results/defense_checks.json` records 11 passing checks. They are injected-verdict and stubbed-DNS checks:

- An unseen fingerprint is allowed.
- One injected match rate-limits. Three block.
- An inert decoy is served, expires after the configured TTL, and rollback removes it.
- A forensic report with no screenshot says the screenshot is unavailable.
- Twelve concurrent consumes of a 10-token bucket do not all succeed.
- A documentation address claiming to be Googlebot fails closed.
- A stubbed resolver can pass the reverse-and-forward check, and a stubbed timeout fails closed. That is not a live Googlebot test.

The detector's own verdict on the bot-only injection is `no_alert`, so that verdict would not start a rate limit, block, or decoy. An injected verdict that forces a match does start those actions. Passing the injected checks does not mean the detector triggers the defense.

## Why the bot-only injection scored 0.480

`reports/score_path_audit.csv` recomputes every version 1 pair. For `north_market` H1 versus B1, the selective injection is:

| Piece | Value |
| --- | --- |
| Scoring path | `fixed_weight_heuristic` |
| URL-model probability | 0 |
| Weights | 0.40 drift + 0.35 jargon + 0.25 promo, summing to 1 |
| Human / bot tokens | 5 / 9 |
| Human / bot keyword hits | 0 / 3 |
| Signed density gap | 0.333 |
| Jensen–Shannon divergence | 1, in bits, not the square-root distance |
| Drift, promo, jargon scores | 0.194, 0.489, 0.800 |
| Contributions | 0.078 + 0.122 + 0.280 |
| Final score | 0.480, reconstruction error 0 |
| Version 1 threshold | 0.50, verdict `no_alert` |

A missing URL model selects this fallback. It does not keep the URL-assisted weights and set the URL term to zero. That other formula would have produced about 0.32, not 0.48. The pages are still mostly the same, so drift stays near 0.19. Three keyword hits do not fill the promotional scale, which divides hit count by 20. The jargon score stops at 0.80 because a density gap of 0.333 is divided by 0.50 before it is weighted. Human and bot order is H1 then B1. Visible text, not raw HTML, feeds the keyword counts. Drift also uses raw byte size. Those inputs are related and not identical. Seven arithmetic tests in `results/tests/test_score_arithmetic.py` pass. The 0.48 result is the formula, not an arithmetic bug, so the version 1 threshold was not moved to 0.47.

Version 1 is 2 template families, 8 scenario configurations, and 4 profile captures: 64 fetches and 16 cross-profile H1–B1 comparisons. It is an HTTP profile comparison. It is not a rendered-browser or visual evaluation.

## Heuristic version 2

The scope is a review alert for bot-directed promotional cloaking. It is not a block, not a human-only detector, and not an identical-defacement detector. `testbed/THRESHOLD_RULE.md` was written before the new scores. Calibration used `cedar_clinic` and `maple_archive`. Reserved families were `quartz_supply` and `linen_press`. Each family has 16 scenario configurations and 4 captures.

On calibration H1–B1 rows, the highest negative score was 0.240 and the lowest positive score was 0.299. The midpoint review threshold is 0.270. The version 1 threshold of 0.50 is unchanged in code and still misses the short few-term cases.

On the reserved families, every defined positive H1–B1 row alerted and every defined negative did not. The margin is small: a long human-only page scored 0.240 and a long in-list hidden link scored 0.299. Identical in-list wording on both profiles scored 0.113. A neutral hidden link stayed under 0.10. Identical defacement scored 0. A long substantial injection scored 0.443, which a 0.50 threshold would miss and the review threshold catches.

One reserved substantial injection, score 0.604, was then passed to the response code for the harness-designated subject `authorized-test-subject`. That subject was rate-limited, an inert decoy was served, and rollback cleared it. An unrelated client was not scored. A live lookup of `8.8.8.8` returned `dns.google` and failed closed. That is not a Googlebot test. The record is `testbed/results/detector_integration.json`.

`hostname_group` is the old hostname field. `registrable_domain_group` is the public-suffix registrable domain. The 300 historical rows have 300 hostnames and 290 registrable domains. Historical timestamps and final URLs were not invented. New captures store UTC time, requested and final URL, redirect chain, status, headers, and an artifact hash. Screenshots remain unsupported.

## Pilot status

In a randomly selected 30-pair pilot, the first reviewer identified no supported malicious cloaking. Independent review and adjudication are pending. Instructions for the second reviewer are `data/annotation/REVIEWER_2_INSTRUCTIONS.md`. The packet has no detector scores. Reviewer 1's labels were not copied into that packet.

`pair_complete` means the artifact and status check passed. Two of the 30 pilot pairs passed that check and were still unusable as content. `site_group` is the hostname with `www.` removed. It is not a registrable domain and not a template family.
