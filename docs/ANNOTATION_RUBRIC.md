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
