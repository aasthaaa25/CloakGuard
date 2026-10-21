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

## Pilot status

In a randomly selected 30-pair pilot, the first reviewer identified no supported malicious cloaking. Independent review and adjudication are pending. Instructions for the second reviewer are `data/annotation/REVIEWER_2_INSTRUCTIONS.md`. The packet has no detector scores. Reviewer 1's labels were not copied into that packet.

`pair_complete` means the artifact and status check passed. Two of the 30 pilot pairs passed that check and were still unusable as content. `site_group` is the hostname with `www.` removed. It is not a registrable domain and not a template family.
