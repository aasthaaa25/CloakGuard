# CloakGuard implementation

CloakGuard compares two client profiles and produces an uncalibrated review score. The controlled review threshold is 0.270 on the fixed-weight path. The existing 0.50 alert remains separate from review and owner-confirmed enforcement. The review rule covers bot-directed promotional injection. Human-only injection is outside its scope.

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
