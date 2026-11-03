# Annotation rubric

A row receives one of these labels only when the evidence named in the definition is present. Otherwise the label is `uncertain`. Do not collapse uncertain rows into a binary class.

| Label | Required evidence |
| --- | --- |
| `confirmed_malicious_cloaking` | The same site, URL, and time window was fetched under at least two profiles, and an annotator can point to content that is promotional or harmful in one profile and absent from the other, with the difference not explained by consent dialogs, localization, ads, or rotation. A model score is not this evidence. |
| `legitimate_profile_dependent` | The views differ, and the difference is an intended function of the client profile, such as a mobile layout, a logged-in state, or a language negotiated by the client. |
| `ordinary_dynamic` | The views differ by timestamps, counters, shuffled modules, or other changes that also appear between two captures of the same profile. |
| `overt_unauthorized_modification` | The page is visibly replaced or vandalized in the profile a normal visitor receives, without a requirement that a second profile see something else. |
| `benign` | Both views render the same non-harmful page, including pages that promote a lawful product. |
| `failed_capture` | A view is missing, empty, an error status, a challenge page, or otherwise not the destination document. Record the reason. |
| `uncertain` | The artifacts are insufficient, the annotators disagree, or the only “label” is a detector score. |

The 300 crawl records in `results/data/crawl_sample/` do not contain an annotator decision. The audit assigns every one of them `uncertain` unless the capture itself failed, in which case the observation also carries failure reasons. The column `drift_score` in the missing 160,000-URL CSV is not one of the labels above.

## Pilot labels

The 30-pair pilot uses the categories below. A difference by itself is not a positive. Cloaking, in Google's published description, involves showing different content to users and search engines with deceptive intent. These labels are not detector outputs.

| Label | Meaning |
| --- | --- |
| `supported_malicious_cloaking` | The saved artifacts support selective deceptive or promotional content. |
| `benign_profile_dependent_difference` | The views differ, and a legitimate explanation is available from the artifacts. |
| `no_suspicious_difference_observed` | This saved pair does not show a supported suspicious difference. It does not prove the site is clean. |
| `bot_challenge_or_access_difference` | A challenge, denial, or access policy blocks a meaningful comparison. |
| `uncertain` | The artifacts do not support a reliable decision. |
| `unusable` | The capture is broken, incomplete, or not the destination document. |

Reviewers must not see fusion scores, jargon scores, model predictions, or a suggested detector label. The review packet is `data/annotation/pilot_30_packet.jsonl`. Reviewer 1's labels are `data/annotation/pilot_30_reviewer_1.csv`. Reviewer 2's sheet is blank. Do not open the saved HTML in a normal browser; inspect escaped source and extracted visible text.

After reviewer 2 has independently completed the sheet, run `python evaluation/pilot_agreement.py` from the repository root. The script reports raw agreement and Cohen's kappa overall and one-versus-rest for each label when both sheets are complete. An undefined kappa is recorded as null. Agreement precedes adjudication and creates no training labels.
