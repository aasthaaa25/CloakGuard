# CloakGuard deployment and demo

## Traffic, detection, and response

```text
Client -> HTTPS ingress -> CloakGuard forward-only proxy -> private site origin

Operator-controlled fixture -> paired HTTP captures -> signal extraction
  -> review score and evidence -> operator decision

Isolated owner-policy harness -> fingerprint / rate-limit decision
  -> inert decoy with rollback -> forensic report
```

The reverse proxy accepts one configured HTTP(S) origin. It preserves duplicate query parameters, encoded paths, repeated end-to-end headers, and compressed responses. It strips hop-by-hop and client-supplied forwarding headers. The upstream route uses the configured authority, and the health route checks the proxy process. Upstream availability is checked by requesting a known origin path.

For a hosted topology, terminate HTTPS at the ingress and keep both the proxy and origin private. Apply request size, connection, and rate limits at the ingress. Use an ingress access log for client attribution. Keep capture workers, evidence storage, and owner-side actions out of the traffic path. Restrict capture egress to authorized origins and approved redirects at the network boundary. Store evidence in an access-controlled location with a defined retention period.

The old ClientHello listener competed with Uvicorn for port 8443. This HTTP service launches no packet capture and receives no TLS fingerprint from an ingress. The saved fingerprint, rate-limit, decoy and forensics components are exercised separately. A page-level finding cannot establish that the current requesting client caused it.

## Native local demo

From the repository root, install the proxy dependencies with `python -m pip install -r results/deploy/requirements.txt`. In two terminals, from the same root, run:

```sh
python results/tests/mock_origin.py
python -m uvicorn app.main:app --app-dir results --host 127.0.0.1 --port 8080 --no-proxy-headers
```

The mock origin listens on port 8000. Request `http://127.0.0.1:8080/_cloakguard/health` and `http://127.0.0.1:8080/`. The proxy follows `ORIGIN_SERVER_URL` when set, with the local mock as the native default.

## Container deployment

For a local container smoke test, start the bundled fixture from the repository root:

```sh
docker compose -f results/deploy/docker-compose.yml --env-file results/deploy/demo.env --profile demo up -d --build
curl --fail http://127.0.0.1:8080/_cloakguard/health
curl --fail http://127.0.0.1:8080/
docker compose -f results/deploy/docker-compose.yml --env-file results/deploy/demo.env --profile demo down
```

The origin stays on the Compose network and the proxy port is published on loopback. Use the native classroom demo for paired detection and report generation.

Set `ORIGIN_SERVER_URL` to an authorized origin reachable from the container, then run from the repository root:

```sh
docker compose -f results/deploy/docker-compose.yml up -d --build
docker compose -f results/deploy/docker-compose.yml ps
```

The host port is loopback-bound. The container runs as a non-root user with a read-only root and no added capabilities. The container health check validates process liveness. For the Linux systemd option, use the dedicated defaceguard account and install the project and its virtual environment at /opt/cloakguard. Install the unit from this directory and set ORIGIN_SERVER_URL in /etc/cloakguard/proxy.env.

## One-command classroom demo

Install the analysis dependencies from `results/requirements.txt`, then run `python evaluation/run_live_demo.py` from the repository root. It starts a controlled origin and Uvicorn on two automatically assigned loopback ports, requests clean and changed cases through the proxy, writes an evidence report, and stops both servers. Results appear in `evaluation/outputs/live_demo/`.

Run `python results/run_all.py` for the live demo, URL proxy-label benchmark, paired experiments and test suite. Pass the JSON from the live demo to `python evaluation/make_class_brief.py --demo evaluation/outputs/live_demo/demo_result.json --output-dir your_output_directory` to recreate the PDF and figures.

## Research demo

Install the analysis dependencies from `results/requirements.txt`. Run the following from the repository root:

```sh
python evaluation/audit_repository.py
python evaluation/demo_case.py
python evaluation/benchmark_controlled_ml.py
python evaluation/stress_controlled_ml.py
python testbed/defense_checks.py
python -m pytest results/tests -q
```

The benchmark reads the committed controlled-capture scores and writes row-level predictions and metrics to `evaluation/outputs/`. To recollect the controlled HTTP pairs on loopback, run `python testbed/calibrate_v2.py`. It refreshes fixture files and capture timestamps. Read the paper’s claim audit before presenting any historical accuracy figures.
