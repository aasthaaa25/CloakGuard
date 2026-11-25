# CloakGuard: an evidence-bounded account of paired-view heuristics and owner-side controls

**Status.** This document replaces the numerical claims in `CloakGuard_Paper.pdf` wherever those claims are not supported by files in this repository. The PDF is retained as a historical draft. Figures in that PDF were not regenerated, because the prediction files and the 160,000-URL table are not here.

## Abstract

CloakGuard compares responses to Chrome and Googlebot HTTP profiles using content drift, promotional vocabulary, and jargon composition. A separate forward-only service proxies traffic to a configured origin. An isolated owner-policy harness evaluates fingerprint scoring, rate-limit decisions, static decoy rollback, and forensic reporting.

This repository does not establish real-world cloaking-detection performance. The 160,000-URL file used for the archived URL classifier is absent, and its `drift_score` column is not a confirmed cloaking label. The paired-view table used for the archived multimodal numbers has 5,122 rows: 5,000 URL-only rows with multimodal features filled by zero, and 122 crawled rows whose labels match a fusion threshold exactly and are all negative. The archived audit lists 300 distinct URLs, including 204 pairs with two nonempty HTTP 200 bodies. The local rerun found 203 complete and 97 incomplete pairs because both HTML files for one archived URL were unavailable. The sample contains no screenshots or independent cloaking annotations. On the 204 complete pairs, the mean drift score is 0.012 and the mean corrected jargon score is approximately 0. Those are descriptive facts about UA-only `httpx` fetches, not a detection rate.

The detector feature set has 61 fields: 41 URL fields, 9 drift fields, 6 promotional fields, and 5 jargon fields. Two further columns in the archived 63-feature list, `final_risk_score` and `model_probability`, are fusion outputs and are excluded from training. Visual SSIM is implemented and was not computed on this crawl. The operational score is an uncalibrated heuristic with threshold 0.50. It is not the archived multimodal ensemble, and it is not a probability. A 400-example synthetic confusion matrix is not in the repository, so it is not reported.

## Contributions

The supported contribution is methodological and engineering:

- Separate URL-risk classification, paired-view description, synthetic fixtures, and owner-side controls, and refuse to treat a result on one as a result on another.
- Publish the crawl manifest outcomes, including failures, instead of a fully observed multimodal benchmark.
- Define the jargon score precisely, fix the mass calculation so it uses raw hit counts, and return the simpler alternatives beside the combined score.
- State the operational scoring path, the 0.50 threshold, and the fact that the score is uncalibrated.
- Separate traffic forwarding, evidence generation, and the owner-policy harness. The harness supplies the subject explicitly.

Prior split-view detectors and promotional-defacement detectors already exist. This paper does not claim to be the first dual-view system. It does not claim a performance improvement from jargon features, because the unlabeled crawl does not support that comparison.

## Related work

Wu and Davison compared browser and crawler copies in their study of semantic cloaking. Invernizzi et al. studied split views across browser, network, and contextual signals. Yang et al. studied promotional defacement using jargon normalization and tag-aware features. Borgolte et al. used screenshots to recognize defacement in Meerkat. CloakGuard contributes an auditable comparison of paired promotional signals under a restricted HTTP capture protocol. [Wu and Davison, WWW 2006](https://archives.iw3c2.org/www2006/programme/files/xhtml/6014/fp6041-wu/fp6014-wu-xhtml.html) [Invernizzi et al., IEEE S&P 2016](https://research.google.com/pubs/pub45365.html) [Yang et al., USENIX Security 2021](https://www.usenix.org/conference/usenixsecurity21/presentation/yang-ronghai) [Borgolte et al., USENIX Security 2015](https://www.usenix.org/conference/usenixsecurity15/technical-sessions/presentation/borgolte)

Changing the User-Agent string to Googlebot does not reproduce the network position of Google’s crawlers. Google’s published check is reverse DNS, a hostname suffix, and a forward lookup back to the same address. The crawler verification component implements that check and fails closed when DNS fails. The forward-only service leaves crawler verification to the owner’s ingress policy. The paired fetcher does not perform it, because the fetcher is the client, not a verifier of its own source address.

## Methods

### Capture

`detection/pipeline/crawl.py` can use Playwright for a rendered DOM and a screenshot. The stored sample did not. Each meta file records `httpx` or `httpx_fail`, a status code, and HTML lengths. The sample does not record redirect chains, response headers, a second human capture, or a second bot capture. Failed fetches remain in the directory. Error pages are not treated as clean successes: the audit marks a pair incomplete when a body is empty or a status is not 200.

Profiles actually tested in the stored sample are a Chrome 120 User-Agent and a Googlebot User-Agent, both issued by `httpx` from this machine. Claims are limited to those two profiles.

### Features

URL features are the 41 fields exported by `detection/features.py`. Two of them duplicate others: `path_depth` repeats `num_path_slashes`, and `num_query_params` repeats `query_param_count`.

Drift uses HTML size, tag-distribution Jensen–Shannon divergence, link Jaccard distance, text difference, title difference, and a capped bot-only link count. `visual_ssim` and `visual_pixel_delta` are computed only when both screenshot paths exist. Otherwise SSIM stays at its default of 1, pixel delta stays at 0, and the aggregate drops the visual term. No stored capture took that branch. Text drift is one minus the SequenceMatcher ratio on the first 3,000 characters of parsed body text. Title drift applies the same distance to normalized titles. Both-empty inputs yield zero distance, and exactly one empty input yields one. The parser extracts text without computing CSS visibility.

Promotional features count case-insensitive keyword matches in six overlapping categories: gambling, pharma, adult, replica luxury, finance scam, and generic spam. Quantity and category count are separate from the composition used for divergence.

Jargon uses the same six categories on the title, the first 5,000 characters of visible text, and up to 100 links. Mass is the raw hit count. Density divides mass by the whitespace-token count, and a zero-token window has density 0. The category distribution is the hit vector divided by its sum. A zero-hit view stays a zero vector. Jensen–Shannon divergence uses log base 2. Both views empty yields 0. One view empty yields 1. No smoothing is applied. The combined score is

```
clip(0.60 * clip((bot_density - human_density) / 0.5, 0, 1) + 0.40 * jsd, 0, 1)
```

The 0.5 scale and the 0.60/0.40 weights are fixed constants. They were not fit on a test set. The module also returns human density, bot density, signed and absolute density difference, and divergence alone.

### Scores

`fuse_risk_scores` is the operational scorer.

- If `detection/artifacts/model.joblib` loads and its URL score is positive, the path is `url_model_assisted_heuristic` with weights 0.35, 0.25, 0.25, and 0.15 on the URL score, drift, jargon, and promotional score.
- Otherwise the path is `fixed_weight_heuristic` with weights 0.40, 0.35, and 0.25 on drift, jargon, and promotional score.

The alert threshold on that score is 0.50. A 0.05 cutoff appears in the old training script only as a plotting filter. It is not an operating point. The trained soft-voting ensemble in `train_multimodal.py` is a separate archived path and is not called by the middleware.

### Labels

Publication labels follow `docs/ANNOTATION_RUBRIC.md`. A fusion threshold may be stored as `weak_fusion_label`. It is not `label`. The archived parquet still contains the old circular labels; it was not overwritten, so the audit can show them.

### Defense

Traffic is forwarded to one configured origin. An operator runs paired capture and scores the evidence outside the request path. The owner-policy harness supplies a synthetic client identifier and exercises a 25-point score increment, rate limiting at 25, and blocking at 75. The decoy is a static page with no resources or active content. Reports escape captured evidence and apply a restrictive content policy. The current HTTP proxy does not collect ClientHello fingerprints. Shared fingerprints and TLS termination remain limitations for any future online enforcement.

The site operator controls the origin, capture configuration, and access to evidence. A suspected compromised origin can return different content to the two profiles, while benign personalization can produce the same kind of observable difference. A probing client is a separate actor. The HTTP proxy leaves online identity decisions to the ingress, and the harness uses synthetic subjects. A JA3 hash depends on ClientHello details and can vary with extension ordering or be shared by different clients. The study evaluates no JA4 implementation, crawler impersonation rate, or SEO effect.

## Datasets

| Collection | What it is | What it is not |
| --- | --- | --- |
| Archived URL run | Numbers in `metrics.json` for four models and 41 URL features | A rerun. The CSV is missing. Not a cloaking label set. |
| `multimodal_features.parquet` | 5,000 backbone rows and 122 crawl rows | A 5,122-row fully observed multimodal benchmark |
| `data/crawl_sample` | 300 URL pairs, one domain each, captured by `httpx` | A labeled cloaking corpus, a browser rendering study, or a repeated H1/B1/H2/B2 design |
| Local fixtures in the tests and `evaluation/demo_case.py` | Pipeline checks | A 400-example field study |

The 122 training rows are a subset of the 300 current URLs, not extra observations of 55 sites. Splits, seeds, and hyperparameter search for a final cloaking test do not exist, because there is no independently labeled test to freeze.

## Experiments

### Archived URL run

`metrics.json` records Logistic Regression accuracy 0.95315 and ROC-AUC 0.98578, Random Forest accuracy 0.971325 and ROC-AUC 0.99578, HistGradientBoosting accuracy 0.972675 and ROC-AUC 0.996074, and the soft-voting ensemble accuracy 0.971225 and ROC-AUC 0.995309. HistGradientBoosting is the best archived model by accuracy and ROC-AUC. The ensemble ROC-AUC is not the HistGradientBoosting ROC-AUC. These numbers were not regenerated. `model.joblib` was pickled with scikit-learn 1.7.2 and does not unpickle under scikit-learn 1.9.0 in this environment, so the earlier audit did not execute it. We separately verified single-URL inference with scikit-learn 1.7.2.

### Recovered subset and domain-disjoint evaluation

The supplied results ZIP contains the identical 5,122-row Parquet and semantically identical historical metrics. The notebook and historical PDF describe a balanced 160,000-URL source file. The ZIP contains no CSV and the reviewed artifacts do not identify the data providers or establish how the source labels were assigned. Its 5,000 URL-only rows have 2,500 labels of each class and 5,000 distinct URL strings.

We recomputed the 41 URL features and ran five stratified, registrable-domain-disjoint folds covering 4,794 groups. Logistic regression and histogram gradient boosting achieved mean fold ROC-AUC 0.982 and 0.989, mean fold average precision 0.978 and 0.988, and pooled F1 0.952 and 0.953 at 0.50. The prior baseline achieved mean fold ROC-AUC 0.500. Domain separation controls repeated domains, and may leave shared collection sources or campaign artifacts across folds. These are results on archived proxy labels. No full-corpus reproduction or cloaking ground-truth estimate follows from them.

### Independent 160,000-URL replacement dataset

A separately constructed 80,000-legitimate/80,000-phishing benchmark from UCI PhiUSIIL preserves the historical class balance. The original collection sources could not be identified from the historical draft or the supplied archive. The release filters URL user information and common credential-like query fields before sampling. The replacement uses a 41,152-row domain-disjoint test set. A rule based only on HTTPS, a www. hostname, and absence of a path and query scored 99.69% accuracy, versus 99.59% for histogram gradient boosting. On the subset sharing that URL shape, boosting found 38 of 127 phishing URLs at 0.50. This sensitivity analysis shows how much apparent accuracy a collection shortcut can produce. The task is phishing-URL classification with source labels. [UCI dataset 967](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+website+dataset)

### Archived multimodal run

On the flawed 5,122-row table, the archived ensemble accuracy is 0.9617 and ROC-AUC is 0.9924. Random Forest recall is 0.9968, which is higher than the ensemble recall of 0.9952. The archived ablation URL ROC-AUC is 0.9592 and the fused ROC-AUC is 0.9850. The absolute difference is 0.0258. Drift, promotional features, and jargon each have archived ROC-AUC near 0.51 with zero recall, which is what near-constant zero columns produce. This run is filed as a debugging experiment.

### Current paired-view description

The audit recomputed features on the stored HTML. It did not assign cloaking labels and did not train a model.

| Outcome | Count |
| --- | --- |
| Meta files / unique URLs / unique domains | 300 / 300 / 300 |
| Both bodies nonempty and HTTP 200 | 204 |
| Incomplete or non-success | 96 |
| Screenshots and extracted visual features | 0 |
| Mean drift / promotional / jargon on the 204 | 0.0125 / 0.0514 / 0.0000078 |

The small cross-view scores are a negative result for this capture method. They do not show that the sites are benign, and they do not show that the features would fail on browser-rendered or adversarially cloaked pages. Hard negatives such as consent banners, localization, rotating ads, and challenge pages were not built as a labeled set.

No URL-only versus multimodal comparison on a shared held-out labeled pair is possible until those labels exist.

### Fixture check

`evaluation/demo_case.py` runs the pipeline on two local HTML strings. The identical pair scores below the injected-keyword pair. The output records the scoring path, the threshold, and `score_is_probability: false`. See `evaluation/outputs/demo_trace.json`.

## Defense evaluation

The unit tests check score increments, decay, rate-limit and block thresholds, decoy arming and expiry, DNS rejection of documentation-range addresses that claim to be Googlebot, and generation of a nonempty forensic report. They do not measure collateral blocking of benign clients, proxy or TLS-terminating deployments, cache behavior, latency, or throughput. They do not show that a decoy removes injected content. The report text now says heuristic alert. Integrity of screenshots and execution traces cannot be claimed for the crawl sample, because those artifacts were not stored.

## Discussion

The main risk in the historical draft was circular evaluation: labels, features, and the reported detector shared the fusion score, while missing modalities were stored as zeros. Correcting the prose without a labeled paired corpus would not create a detection result. The present scope is the largest scope the files support.

Deployment assumptions that remain untested include reverse proxies, shared JA3 hashes, crawler-UA spoofing from non-Google networks, fingerprint rotation, and concurrent traffic. The DNS checker is fail-closed for claimed crawlers and has a two-second socket timeout. That policy will reject a real crawler during a DNS failure. It is not advertised as a zero false-block result.

## Controlled local validation

The files previously written under `testbed/captures/` are prewritten HTML. They do not exercise the crawler. A later run served two local template families and fetched each scenario with the project's httpx client in the order H1, B1, H2, B2. Expectations were frozen in `testbed/expectations.csv` before those scores were inspected. Every fetch succeeded. Every score used the fixed-weight heuristic, because the archived URL model was not loaded. Visual features were not used.

At threshold 0.50, identical clean pages, shared lawful promotional wording, a rotating counter, a hidden link, an identical defacement, a bot challenge, and a known bot-only keyword injection all stayed below the alert line. The bot-only injection scored 0.480. The breakdown is 0.078 of drift, 0.122 of promotion, and 0.280 of jargon under the no-URL fallback. That sum is exact, so the threshold was not moved to catch this example. A later review threshold of 0.270 was chosen on two new calibration templates and checked on two reserved templates. It is a review alert for bot-directed keyword injection, not a block and not a defacement detector. Details are in `docs/CONTROLLED_VALIDATION.md`. No ROC-AUC is reported for the pilot, because that set has no supported positive class.

## Controlled ML comparison

We retrospectively compared a drift-only logistic regression and a four-feature logistic regression with the frozen heuristic and an always-negative baseline. The four features were drift, promotional score, jargon score, and signed jargon density difference. Standardization and fitting used only cedar_clinic and maple_archive. Evaluation used linen_press and quartz_supply. Each split contained 32 first-repetition H1/B1 pairs, with 6 positive and 26 negative scenario labels. The test templates were already available in the repository. Scenario mechanisms occur in both splits.

| Method | TP | FP | TN | FN | F1 | Average precision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Always negative | 0 | 0 | 26 | 6 | 0.000 | 0.188 |
| Drift-only logistic regression | 0 | 1 | 25 | 6 | 0.000 | 0.314 |
| Paired-feature logistic regression | 6 | 0 | 26 | 0 | 1.000 | 1.000 |
| Frozen heuristic | 6 | 0 | 26 | 0 | 1.000 | 1.000 |

The learned classifier matched the heuristic at their respective operating points. This experiment does not establish superiority for either model. Repeated scenarios and two reserved template families limit inference. The study target is review of bot-directed promotional modification. Shared defacement and scripted access behavior are separate concerns. A prospective evaluation needs independently adjudicated positives and realistic hard negatives, with domain and campaign grouping and a frozen operating threshold.

The benchmark script, input hashes, metrics, and case-level predictions are available under evaluation. The archived URL model loaded and produced a single inference under scikit-learn 1.7.2. That check does not reproduce the historical training metrics.

### Template and scenario holdout stress test

This retrospective stress test used all four fixture families. Each test group withheld all training examples sharing either its template family or its scenario mechanism. Visible short and substantial promotional insertions were grouped together. Each scenario contributed one H1/B1 pair. TF-IDF vocabularies and scalers were fit inside each training partition. The same-profile control was the larger cosine distance of H1/H2 and B1/B2. Every binary operating point used the preset 0.50 cutoff.

| Method | TP | FP | FN | Average precision |
| --- | ---: | ---: | ---: | ---: |
| Fixed heuristic | 2 | 0 | 10 | 1.000 |
| Drift-only logistic | 0 | 2 | 12 | 0.124 |
| TF-IDF-only logistic | 0 | 0 | 12 | 0.108 |
| TF-IDF with same-profile control | 0 | 0 | 12 | 0.108 |
| Paired features without jargon | 6 | 6 | 6 | 0.717 |
| All four paired features | 12 | 0 | 0 | 1.000 |

The heuristic and the full paired model both ordered all positives above all negatives. Their alert counts differ at the stated cutoff. Removing the two jargon inputs reduced detection on this fixture, whose positive examples still use a common promotional vocabulary. Raw TF-IDF distance achieved 0.439 pooled average precision. Pooled out-of-fold scores from different fitted models can reflect shifts in training class balance. The related fixture cases do not support independent-sample confidence intervals or probability calibration. The resulting precision-recall points, per-template F1, and per-case predictions are provided with the benchmark.

## Conclusion

In a retrospective controlled comparison, paired features helped distinguish scripted review positives, and the learned model matched the frozen heuristic. The forward-only proxy and the isolated owner-policy harness were validated separately. The local application shows what the current heuristic separates and what it does not alert on. It does not have a reproduced URL-classification experiment, a labeled paired-view benchmark, or a field measurement of active defense. In a randomly selected 30-pair pilot, the first reviewer identified no supported malicious cloaking. Independent review and adjudication are pending. That pilot does not establish that the other complete pairs are negative.
