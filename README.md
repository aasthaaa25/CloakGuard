# CloakGuard

CloakGuard is a defensive research prototype: paired User-Agent fetches, heuristic drift and jargon scores, and owner-side middleware. The corrected write-up is [`paper/CloakGuard_corrected.md`](paper/CloakGuard_corrected.md). The earlier PDF in `paper/` is a historical draft. Read [`docs/CLAIM_AUDIT.md`](docs/CLAIM_AUDIT.md) before citing any accuracy number.

The 160,000-URL file is not in this repository. The 5,122-row parquet is not a fully observed multimodal cloaking benchmark. The crawl sample has 300 URLs and no independent cloaking labels.

**Author:** Aastha Tyagi

## Layout

| Directory | What it contains |
| --- | --- |
| [`paper/`](paper/) | Corrected Markdown write-up and historical PDF |
| [`results/`](results/) | Implementation, tests, trained artifacts, crawl sample, and the generated report |

## Paper

`paper/CloakGuard_Paper.pdf` describes a two-phase detector and an active defense layer:

- Archived URL-model numbers live in `results/detection/artifacts/metrics.json`. They were not rerun here. HistGradientBoosting is the best archived model by accuracy and ROC-AUC.
- The paired-view audit is `evaluation/outputs/claim_audit.json`.
- The defense service collects evidence in monitoring mode. In owner-authorized mode, confirmed reviews can add points to an observed JA3 and approved URLs can serve inert decoys. See [Active defense setup](results/README.md#active-defense-setup).

## Results

`results/` contains the current implementation and historical training artifacts. Start with [`results/README.md`](results/README.md) for setup and how to rerun the pipeline.

Main pieces inside `results/`:

- `app/` — FastAPI defense service (fingerprint, rate limit, decoy, forensics)
- `detection/` — feature extraction, training, and report generation
- `data/` — feature table and dual-view crawl sample
- `report/` — generated HTML report
- `tests/` — detection and integration tests
- `deploy/` — Dockerfile and compose file

`PASSIVE_DNS_API_KEY` is optional and read from the environment. It is not stored in this repository.
