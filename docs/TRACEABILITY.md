# Traceability checklist

Each row names the artifact that supports the statement in `paper/CloakGuard_corrected.md`. A statement that is not in this table is not a result of this repository.

| Statement | Artifact |
| --- | --- |
| Repository freeze | `archive/FREEZE_MANIFEST.json` |
| 5,122-row table composition | `evaluation/outputs/claim_audit.json` key `parquet` |
| 300-capture crawl audit | `evaluation/outputs/claim_audit.json` key `crawl` and `evaluation/outputs/paired_view_observations.jsonl` |
| 61-feature schema and the two excluded fusion columns | `evaluation/outputs/feature_schema.json` |
| Archived Phase 1 model numbers | `results/detection/artifacts/metrics.json` |
| Archived Phase 2 debugging numbers | `results/detection/artifacts/multimodal_metrics.json` |
| Jargon definitions and weights | `results/detection/pipeline/jargon.py` |
| Operational scoring path and threshold 0.50 | `results/detection/pipeline/fusion.py`, `results/app/config.py` |
| Reverse/forward crawler verification and outage handling | `results/app/fingerprint/crawler_verify.py`, `results/app/main.py` |
| Client fingerprint scoring, decay, and actions | `results/app/fingerprint/blocklist.py`, `results/app/config.py` |
| External-monitor versus owner-authorized mode | `results/app/main.py`, `DEFENSE_MODE` |
| Approved static decoy and expiry | `results/app/decoy/decoy_store.py`, `results/app/main.py` |
| Controlled TLS-to-origin enforcement check | `results/tests/test_defense_ingress.py` |
| Fixture walk-through | `evaluation/outputs/demo_trace.json`, produced by `evaluation/demo_case.py` |
| Annotation categories | `docs/ANNOTATION_RUBRIC.md` |
| Historical paper PDF | `paper/CloakGuard_Paper.pdf` |

## Three limits this checklist does not remove

1. The test suite can still miss bugs. Passing tests are not a proof that every branch is correct.
2. Nothing here shows that the jargon score improves detection. The successful httpx pairs have almost no jargon asymmetry. A future labeled study might find that the signal helps, helps in one category, or adds nothing. The crawl labels must not be edited to produce one of those outcomes.
3. This dataset cannot support a large-scale cloaking-detection claim. The 160,000-URL file is absent, and the paired captures have no independent labels. The honest scope is the audit, the pipeline behavior on fixtures, and the owner-side control tests.

## Operational follow-up

| Statement | Evidence |
| --- | --- |
| Fixed-weight review at 0.270 and separate legacy alert | `archive/FREEZE_MANIFEST.json`, `testbed/results/frozen_detector_v2.json`, `results/tests/test_review_threshold.py` |
| Same replacement in both views can be flagged by an owner-approved digest check | `results/detection/pipeline/integrity.py`, `results/tests/test_review_threshold.py` |
| Pilot second-review coverage and agreement status | `evaluation/pilot_agreement.py` → `evaluation/outputs/pilot_agreement.json` |
