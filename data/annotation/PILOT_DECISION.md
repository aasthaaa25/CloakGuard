# Capture inventory and annotation-pilot decision

## What the two counts are

| Count | Meaning | Verified |
| --- | --- | --- |
| 300 | One attempted capture per `*_meta.json` in `results/data/crawl_sample/` | 300 rows in `data/manifests/capture_inventory.csv` |
| 204 | `pair_complete=yes`: both HTML files exist, both are non-empty, both recorded statuses are HTTP 200 | 204 rows |

The other 96 rows stay in the inventory. They are crawler outcomes, not detector examples. No screenshot file exists for any row. The source meta files do not contain a final URL after redirects or a capture timestamp, so those three columns are empty rather than guessed.

Among all 300 attempts, and among the 204 complete pairs:

- 300 distinct requested URLs, 0 duplicate URLs
- 300 distinct site groups, using the hostname with a leading `www.` removed
- 0 site groups with more than one capture

A later split does not have to separate repeated observations of the same site. There are no repeats. There is also no positive class yet, so a stratified group split is not available.

## Pilot

Seed `20261021` drew 30 of the 204 complete pairs. The draw is `data/annotation/pilot_30_ids.txt`. The review packet, `data/annotation/pilot_30_packet.jsonl`, contains titles, visible-text excerpts, link differences, and body hashes. It does not contain fusion scores, jargon scores, or model predictions.

Reviewer 1 inspected that packet and `data/annotation/pilot_diff_notes.txt` as static text. The saved HTML was not opened in a browser. Reviewer 2 has not labeled; `data/annotation/pilot_30_reviewer_2_blank.csv` is empty on purpose. One reviewer cannot measure agreement.

| Reviewer 1 label | Pairs |
| --- | --- |
| `no_suspicious_difference_observed` | 25 |
| `benign_profile_dependent_difference` | 3 |
| `unusable` | 2 |
| `supported_malicious_cloaking` | 0 |
| `bot_challenge_or_access_difference` | 0 |
| `uncertain` | 0 |

The three benign differences are two Cloudflare email-token link changes with identical visible text, and one game-promotion page whose boilerplate paragraph and related links change while the title and article stay the same. One identical pair is an Indonesian lottery page served to both profiles. That is promotional content, not selective cloaking. Two pairs are unusable: an empty 114-byte body, and a redirect stub whose destination was not stored.

In a randomly selected 30-pair pilot, the first reviewer identified no supported malicious cloaking. Independent review and adjudication are pending. This does not establish that all 204 artifact-complete pairs are negative. `pair_complete` means the file and status check passed, not that the pair is a usable annotation. `site_group` is a hostname with `www.` removed, not a registrable domain.

## Branch

**Branch B for a training benchmark.** This pilot does not contain a defensible positive cloaking example. The 204 pairs should not be turned into a model-training set on the basis of this pass.

A separate visible-text triage, which is not annotation, found 113 byte-identical complete pairs, 176 with identical visible text, and 28 with some visible-text difference. The windows in `data/annotation/visible_text_triage.json` are counters, cookie lines, related products, related posts, and form-field labels. They are candidates for a second human reviewer. They are not labels.

The right next collection is a new capture with repeated profiles and a known configuration, not another model run on these files. A local scenario set for that purpose is under `testbed/`. It is controlled behavior, not a real incident.

## What this pilot could answer

Static inspection works. The rubric can keep a shared gambling page and a rotating paragraph out of the positive class. The saved pairs are enough to say that these 30 do not show selective cloaking, and not enough to prove any site is clean. Reviewer agreement is unmeasured. No credible selective positive appeared in the pilot.
