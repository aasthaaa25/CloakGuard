# CloakGuard implementation

CloakGuard compares two client profiles and produces an uncalibrated review score. The controlled review threshold is 0.270 on the fixed-weight path. The alert defaults to 0.45 and is configurable with `ALERT_THRESHOLD`. Owner-confirmed attribution determines fingerprint enforcement. The review rule covers bot-directed promotional injection. Human-only injection is outside its scope.

## Portable URL training

From the repository root, install `results/requirements.txt`, then run:

```bash
python generate_dataset.py
python results/detection/train_model.py --quick
```

The generator writes `final_full (1).csv` at the repository root with 160,000 seeded, locally constructed `.test` URLs and a SHA-256 manifest. Its labels describe generated URL-risk scenarios. It makes no network requests. These fixtures support a training and presentation check. Real-world detection performance remains unmeasured. The original historical dataset remains unavailable.

The training entry point uses 41 lexical features and fits Logistic Regression, Random Forest, HistGradientBoosting, and a soft-voting ensemble. `--quick` uses smaller estimators and skips presentation graphs. Omit it for the full training and graph workflow. Artifacts go into `results/detection/artifacts/url_risk_runs/`, including metrics, model bundle, and a model card with versions, features, seed, provenance, split, and data hash. Existing archived results stay in their original files.

For your own labeled data, pass `--csv PATH --artifacts RUN_DIRECTORY`. A CSV must contain `url` and explicit binary `label` columns. Detector scores are unsuitable as training labels. The current trainer uses a stratified row split. A domain-held-out external benchmark remains pending. The generator accepts even row counts of at least 80 so the full SMOTE demonstration has enough neighbors.

## One-click presentation

After installing the requirements, double-click `start_demo.bat` on Windows, or run from the repository root:

```bash
python demo_live.py
```

The demo trains four URL-risk models on 400 clearly marked synthetic URLs, starts its own loopback origin and TLS proxy on free ports, fetches the two profiles, and prints a live URL-risk prediction plus the fixed-weight cloaking score. It explicitly confirms its controlled incident, adds JA3 points, serves a static decoy, and demonstrates the block threshold through additional scripted incidents. The original page remains injected until the owner remediates it.

Each run writes a fresh directory under `demo_outputs/` with the generated model, model card, training log, JSON result, and forensic report. Optional browser or passive DNS evidence is marked unavailable when absent. A cross-platform local certificate is generated with Cryptography. The demo owns its test origin and client and scripts the confirmation step. This demonstration does not measure detection against field traffic.

To present an already trained trusted model bundle, run `python demo_live.py --url-model results/detection/artifacts/url_risk_runs/model.joblib`. The lexical prediction is displayed alongside the controlled fixed-weight verdict. The Windows launcher uses the repository `.venv` when present and preserves the exit code. Windows execution still requires validation on a Windows host.

## Independent review

The second reviewer sheet in `data/annotation/pilot_30_reviewer_2_blank.csv` remains awaiting human labels. Run `python evaluation/pilot_agreement.py` from the repository root after independent review. Agreement cannot be inferred from an empty sheet.

## Reproduce local checks

From this directory, install the requirements and pytest, then run:

```bash
python -m pytest -q
python ../evaluation/demo_case.py
python ../evaluation/audit_repository.py
```

The audit requires a parquet engine such as pyarrow. The archived training inputs are incomplete. See [the claim audit](../docs/CLAIM_AUDIT.md) for the missing URL corpus, circular historical labels, incomplete pairs, and absent screenshots. See [controlled validation](../docs/CONTROLLED_VALIDATION.md) for the fixture results and [the corrected write-up](../paper/CloakGuard_corrected.md) for the supported research scope.

The single-view integrity command compares a saved static page with an owner-approved digest. Use an immutable page or artifact because any legitimate byte change also raises a mismatch.

```bash
python -m detection.pipeline.integrity CURRENT_HTML OWNER_APPROVED_SHA256
```

## Active defense setup

Run from `results/` after installing the requirements. Use a trusted certificate and a reachable origin that bypasses this ingress. Bind the TLS ingress directly to client traffic so JA3 reflects the client handshake.

```bash
DEFENSE_MODE=external_monitor ORIGIN_SERVER_URL=http://127.0.0.1:8000 \
  python -m app.tls_ingress --host 127.0.0.1 --port 8443 --cert cert.pem --key key.pem
```

This single-process launcher relays TLS to an ephemeral loopback listener. Keep the backend and review directory private. `uvicorn app.main:app` can run as a plain HTTP monitor and will have no trusted fingerprint. Run browser-based collection in an isolated environment with restricted egress and use a trusted origin. For Docker Compose, set `TLS_CERT_DIR` to the directory containing `cert.pem` and `key.pem`. The systemd unit reads them from `/etc/cloakguard/tls/`. Both deployment templates start in monitor mode. Playwright and OpenCV are optional. Passive DNS requires an HTTPS provider base URL in `PASSIVE_DNS_API_URL` and a bearer token in `PASSIVE_DNS_API_KEY`. The provider must accept a domain appended as a path segment and return the fields used by the report.

Reviews are written to `logs/forensics/` by default. Check the report and independently confirm the client attribution before recording a review. Run the CLI from the same directory and with the same database and report paths as the service. Set `DEFENSE_MODE=owner_authorized` on the service when ready to enforce.

```bash
DEFENSE_MODE=owner_authorized python -m app.review confirm REVIEW_ID --ja3 OBSERVED_JA3 --evidence-id INCIDENT_ID
DEFENSE_MODE=owner_authorized python -m app.review arm REVIEW_ID
DEFENSE_MODE=owner_authorized python -m app.review disarm 'http://127.0.0.1:8000/example'
```

Arming approves the exact configured origin URL, including its path and query. Use the same incident ID when referring to the same independent evidence. A repeat of either the review or the incident leaves the score unchanged. Legacy scores and decoys remain readable by offline callers and are isolated from live enforcement. The local fixture is available with `python -m pytest -q tests/test_defense_ingress.py` and uses OpenSSL to create its TLS certificate.
