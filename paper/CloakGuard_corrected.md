# CloakGuard: an evidence-bounded account of paired-view heuristics and owner-side controls

**Status.** This document replaces the numerical claims in `CloakGuard_Paper.pdf` wherever those claims are not supported by files in this repository. The PDF is retained as a historical draft. Figures in that PDF were not regenerated, because the prediction files and the 160,000-URL table are not here.

## Abstract

CloakGuard is a defensive prototype with two separable parts. The first part fetches a URL twice, once with a Chrome User-Agent and once with a Googlebot User-Agent, and computes drift, promotional-keyword, and jargon-composition features. The second part is middleware that a site owner can run in front of an origin they control. It can record a JA3 hash, apply a scored rate limit or block, and serve an inert decoy. An external-monitor mode records evidence and does not take those actions.

This repository does not establish real-world cloaking-detection performance. The 160,000-URL file used for the archived URL classifier is absent, and its `drift_score` column is not a confirmed cloaking label. The paired-view table used for the archived multimodal numbers has 5,122 rows: 5,000 URL-only rows with multimodal features filled by zero, and 122 crawled rows whose labels match a fusion threshold exactly and are all negative. The crawl directory now holds 300 distinct URLs. Of those, 204 have two nonempty HTTP 200 bodies, 96 are incomplete, none has a screenshot, and none has an independent cloaking annotation. On the 204 complete pairs, the mean drift score is 0.012 and the mean corrected jargon score is approximately 0. Those are descriptive facts about UA-only `httpx` fetches, not a detection rate.

The detector feature set has 61 fields: 41 URL fields, 9 drift fields, 6 promotional fields, and 5 jargon fields. Two further columns in the archived 63-feature list, `final_risk_score` and `model_probability`, are fusion outputs and are excluded from training. Visual SSIM is implemented and was not computed on this crawl. The operational score is an uncalibrated heuristic with an operational alert threshold of 0.45 and a fixed-weight review threshold of 0.270. It is not the archived multimodal ensemble, and it is not a probability. A 400-example synthetic confusion matrix is not in the repository, so it is not reported.

## Contributions

The supported contribution is methodological and engineering:

- Separate URL-risk classification, paired-view description, synthetic fixtures, and owner-side controls, and refuse to treat a result on one as a result on another.
- Publish the crawl manifest outcomes, including failures, instead of a fully observed multimodal benchmark.
- Define the jargon score precisely, fix the mass calculation so it uses raw hit counts, and return the simpler alternatives beside the combined score.
- State the operational scoring path, the operational threshold, and the fact that the score is uncalibrated.
- Separate external monitoring from owner-authorized response, and attach JA3 points to the observed client rather than to a remote operator.

Prior split-view detectors and promotional-defacement detectors already exist. This paper does not claim to be the first dual-view system. It does not claim a performance improvement from jargon features, because the unlabeled crawl does not support that comparison.

## Related work

Invernizzi et al. (IEEE S&P 2016) study cloaking that depends on browser, network, and contextual signals, and they detect split views across browsing profiles. Cloaker Catcher compares a client view with a crawler view. Yang et al. (USENIX Security 2021) detect promotional defacements at scale with jargon normalization and tag-aware features; their deployment evidence is their own, and it is not reused here. CloakGuard borrows the paired-fetch idea and the promotional-keyword idea. It does not reproduce either study’s dataset or metrics.

Changing the User-Agent string to Googlebot does not reproduce the network position of Google’s crawlers. Google’s published check is reverse DNS, a hostname suffix, and a forward lookup back to the same address. The middleware implements that check and fails closed when DNS fails. The paired fetcher does not perform it, because the fetcher is the client, not a verifier of its own source address.

## Methods

### Capture

`detection/pipeline/crawl.py` can use Playwright for a rendered DOM and a screenshot. The stored sample did not. Each meta file records `httpx` or `httpx_fail`, a status code, and HTML lengths. The sample does not record redirect chains, response headers, a second human capture, or a second bot capture. Failed fetches remain in the directory. Error pages are not treated as clean successes: the audit marks a pair incomplete when a body is empty or a status is not 200.

Profiles actually tested in the stored sample are a Chrome 120 User-Agent and a Googlebot User-Agent, both issued by `httpx` from this machine. Claims are limited to those two profiles.

### Features

URL features are the 41 fields exported by `detection/features.py`. Two of them duplicate others: `path_depth` repeats `num_path_slashes`, and `num_query_params` repeats `query_param_count`.

Drift uses HTML size, tag-distribution Jensen–Shannon divergence, link Jaccard distance, text difference, title difference, and a capped bot-only link count. `visual_ssim` and `visual_pixel_delta` are computed only when both screenshot paths exist. Otherwise SSIM stays at its default of 1, pixel delta stays at 0, and the aggregate drops the visual term. No stored capture took that branch.

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

The alert threshold defaults to 0.45 as an operational setting requested on 13 November 2026. Its field false-positive rate is unmeasured. A 0.05 cutoff appears in the old training script only as a plotting filter. It is not an operating point. The trained soft-voting ensemble in `train_multimodal.py` is a separate archived path and is not called by the middleware.

### Labels

Publication labels follow `docs/ANNOTATION_RUBRIC.md`. A fusion threshold may be stored as `weak_fusion_label`. It is not `label`. The archived parquet still contains the old circular labels; it was not overwritten, so the audit can show them.

### Defense

The defense follows §8 of the historical draft. A public TCP listener captures JA3 from the inbound ClientHello and relays the original TLS bytes to a loopback-only TLS terminator. The application receives the fingerprint and peer address through process-local connection state. Request headers cannot supply either value.

An alert opens a review and collects forensic evidence, including for requests without a fingerprint. A site owner can confirm an incident after independently linking it to the fingerprint recorded for the review. Each confirmed review adds 25 points once, with decay of one point per hour. Owner-authorized mode rate-limits at 25 and hard-blocks at 75. Verified crawlers and claimed crawlers with temporarily unavailable DNS pass through. Monitor and log-only modes forward while collecting review evidence.

An owner can approve a static, non-cacheable decoy for an exact origin URL for 72 hours. Requests with a rate-limited fingerprint can receive it for GET or HEAD after passing the token bucket. Hard blocks take precedence. Shared TLS libraries and fingerprint rotation limit JA3’s value as an identity signal. Origin cleanup remains a separate remediation step.

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

`metrics.json` records Logistic Regression accuracy 0.95315 and ROC-AUC 0.98578, Random Forest accuracy 0.971325 and ROC-AUC 0.99578, HistGradientBoosting accuracy 0.972675 and ROC-AUC 0.996074, and the soft-voting ensemble accuracy 0.971225 and ROC-AUC 0.995309. HistGradientBoosting is the best archived model by accuracy and ROC-AUC. The ensemble ROC-AUC is not the HistGradientBoosting ROC-AUC. These numbers were not regenerated. `model.joblib` was pickled with scikit-learn 1.7.2 and does not unpickle under scikit-learn 1.9.0 in this environment, so the archived URL model was not executed again.

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

Capture completeness is 204/300 (68%). In the 30-pair pilot, the first reviewer recorded 25 pairs without suspicious differences, three benign profile differences, two unusable pairs, and zero supported malicious cloaking pairs. The second review and adjudication are pending. Precision, recall, and ROC-AUC for a shared domain-held-out URL-only versus fused comparison remain unreported. Such a comparison requires both independently adjudicated classes and a threshold chosen outside the held-out domains.

### Fixture check

`evaluation/demo_case.py` runs the pipeline on two local HTML strings. The identical pair scores below the injected-keyword pair. The output records the scoring path, the threshold, and `score_is_probability: false`. See `evaluation/outputs/demo_trace.json`.

## Defense evaluation

A controlled local test opened a real TLS connection to the ingress and sent HTTP through to a local origin. It captured a JA3 and the original peer address, discarded spoofed forwarding metadata, and exercised origin forwarding, confirmed-score enforcement, decoy GET/HEAD responses, and hard-block precedence. The test used controlled DNS outcomes to check crawler exemption and forwarding during a DNS outage. Separate tests cover duplicate confirmations under concurrent writes, decay, decoy expiry, and a partial forensic report. These checks measure implementation behavior in fixtures. Field effectiveness, collateral blocking, latency, and throughput remain unmeasured.

## Discussion

The main risk in the historical draft was circular evaluation: labels, features, and the reported detector shared the fusion score, while missing modalities were stored as zeros. Correcting the prose without a labeled paired corpus would not create a detection result. The present scope is the largest scope the files support.

The TLS check used a direct loopback client and a single ingress process. Deployments behind another TLS terminator, shared JA3 hashes in the field, fingerprint rotation, and production traffic loads remain untested. The claimed-crawler check shares a two-second DNS budget by default and forwards on resolver failure.

## Controlled local validation

The files previously written under `testbed/captures/` are prewritten HTML. They do not exercise the crawler. A later run served two local template families and fetched each scenario with the project's httpx client in the order H1, B1, H2, B2. Expectations were frozen in `testbed/expectations.csv` before those scores were inspected. Every fetch succeeded. Every score used the fixed-weight heuristic, because the archived URL model was not loaded. Visual features were not used.

At threshold 0.50, identical clean pages, shared lawful promotional wording, a rotating counter, a hidden link, an identical defacement, a bot challenge, and a known bot-only keyword injection all stayed below the alert line. The bot-only injection scored 0.480. The breakdown is 0.078 of drift, 0.122 of promotion, and 0.280 of jargon under the no-URL fallback. That historical experiment retained its preselected 0.50 threshold. A later review threshold of 0.270 was chosen on two new calibration templates and checked on two reserved templates. It is a review alert for bot-directed keyword injection, not a block and not a defacement detector. Details are in `docs/CONTROLLED_VALIDATION.md`. No ROC-AUC is reported for the pilot, because that set has no supported positive class.

## Operational follow-up

The fixed-weight service path uses the rounded 0.270 threshold for review, alongside the requested 0.45 alert. The URL-assisted path uses the alert threshold for review. Neither score authorizes enforcement. The adapter supplies jargon asymmetry to fusion. A controlled fixture exercises the review path in `results/tests/test_review_threshold.py`. A separate static-artifact integrity check flags a byte mismatch against an owner-approved digest, including a replacement shared by both views. The fixture checks mechanism behavior. Legitimate content changes also trigger a mismatch, and human-only promotional injection remains outside the calibrated cross-view rule.

## Portable training and presentation

`generate_dataset.py` constructs reserved-domain URL-risk fixtures and records their generator seed and SHA-256. The portable training entry point reads explicit labels, saves a model card and models in a separate run directory, and retains historical artifacts. Synthetic training scores establish that the implementation runs on constructed inputs. They provide no estimate of external URL-risk or cloaking performance. `demo_live.py` serves the existing North Market controlled fixture through a local origin and TLS ingress. It shows live lexical prediction, fixed-weight cross-view inference, scripted confirmation, fingerprint scoring, and decoy response. The demo result and model card describe those choices.

## Conclusion

CloakGuard now has a traceable account of what was crawled, which labels are weak, which scores are heuristics, and which defense actions are available to a site owner. The local application shows what the current heuristic separates and what it does not alert on. It does not have a reproduced URL-classification experiment, a labeled paired-view benchmark, or a field measurement of active defense. In a randomly selected 30-pair pilot, the first reviewer identified no supported malicious cloaking. Independent review and adjudication are pending. That pilot does not establish that the other complete pairs are negative.
