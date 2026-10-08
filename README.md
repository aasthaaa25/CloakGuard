# CloakGuard

CloakGuard is a research system for detecting promotional cloaking and web defacement, plus a three-layer active defense prototype. The write-up and the experiment bundle are in this repository.

**Author:** Aastha Tyagi

## Layout

| Directory | What it contains |
| --- | --- |
| [`paper/`](paper/) | `CloakGuard_Paper.pdf` — the paper |
| [`results/`](results/) | Implementation, tests, trained artifacts, crawl sample, and the generated report |

## Paper

`paper/CloakGuard_Paper.pdf` describes a two-phase detector and an active defense layer:

- Phase 1 engineers 41 URL-lexical features on a 160,000-URL dataset (95.32% accuracy with logistic regression; 97.12% with a soft-voting ensemble).
- Phase 2 adds a dual-view crawl (human Chrome user-agent and Googlebot) and 22 more signals, then fuses them into a multimodal ensemble (96.17% accuracy, 99.24% ROC-AUC on the reported evaluation).
- The defense layer covers TLS/JA3 fingerprinting, decoy neutralization, and forensic packaging. The bundle reports a 53-test suite.

## Results

`results/` is the active defense system that produced those numbers. Start with [`results/README.md`](results/README.md) for setup and how to rerun the pipeline.

Main pieces inside `results/`:

- `app/` — FastAPI defense service (fingerprint, rate limit, decoy, forensics)
- `detection/` — feature extraction, training, and report generation
- `data/` — feature table and dual-view crawl sample
- `report/` — generated HTML report
- `tests/` — detection and integration tests
- `deploy/` — Dockerfile and compose file

`PASSIVE_DNS_API_KEY` is optional and read from the environment. It is not stored in this repository.
