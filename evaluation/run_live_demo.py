"""Run the controlled origin, proxy, paired review, and evidence writer on loopback."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
from http.server import ThreadingHTTPServer
from itertools import count
import json
import os
from pathlib import Path
import socket
import sys
from threading import Thread
import time

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def stop_server(server, thread):
    server.should_exit = True
    thread.join(timeout=10)
    if thread.is_alive():
        raise RuntimeError("Proxy did not shut down")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "outputs" / "live_demo")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    os.environ["FORENSICS_OUTPUT_DIR"] = str(args.output_dir.resolve() / "evidence")
    sys.path.insert(0, str(ROOT))
    from testbed.calibrate_v2 import Handler
    from detection.pipeline.crawl import VIEW_PROFILES
    from app import main as proxy
    from app.pipeline_bridge.repeat_review import VIEW_IDS, review_repeats
    from app.forensics.deep_scan import _write_forensic_report
    from app.forensics.dom_diff import compute_dom_diff

    class DemoHandler(Handler):
        bot_observations = count()

        def do_GET(self):
            if self.path == "/quartz_supply/transient_change":
                first_bot = ("Googlebot" in self.headers.get("User-Agent", "")
                             and next(self.bot_observations) == 0)
                self.path = "/quartz_supply/bot_substantial" if first_bot else "/quartz_supply/clean"
            super().do_GET()

    with ExitStack() as cleanup:
        origin = cleanup.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler))
        worker = Thread(target=origin.serve_forever, daemon=True)
        worker.start()
        cleanup.callback(worker.join, 10)
        cleanup.callback(origin.shutdown)
        proxy.ORIGIN_SERVER_URL = f"http://127.0.0.1:{origin.server_port}"

        listener = cleanup.enter_context(socket.socket())
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(proxy.app, port=port, proxy_headers=False, log_level="warning"))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        cleanup.callback(stop_server, server, thread)
        deadline = time.monotonic() + 10
        while thread.is_alive() and not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("Loopback proxy failed to start")

        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            health = client.get("/_cloakguard/health")
            health.raise_for_status()
            if health.json().get("mode") != "forward_only":
                raise RuntimeError("Unexpected proxy mode")
            results = {}
            scenarios = {
                "clean": "below_threshold", "counter": "below_threshold",
                "transient_change": "inconsistent_cross_profile",
                "bot_substantial": "repeated_profile_difference",
            }
            for scenario, expected_verdict in scenarios.items():
                route = f"/quartz_supply/{scenario}"
                url = str(client.base_url).rstrip("/") + route
                views = {}
                for view_id in VIEW_IDS:
                    profile = "human" if view_id.startswith("H") else "bot"
                    parameters = VIEW_PROFILES[profile]
                    client.cookies.clear()
                    response = client.get(route, headers={"User-Agent": parameters["user_agent"]})
                    views[view_id] = {
                        "status": response.status_code, "html": response.text,
                        "content_type": response.headers.get("content-type", ""),
                        "final_url": str(response.url),
                    }
                decision = review_repeats(url, views)
                if decision["verdict"] != expected_verdict:
                    raise RuntimeError(f"Unexpected review verdict for {scenario}")
                drift, promo, _, fusion = decision.pop("first_pair")
                evidence = None
                report_digest = None
                if decision["alert"]:
                    dom = compute_dom_diff(views["H1"]["html"], views["B1"]["html"])
                    report = _write_forensic_report(
                        url, scenario, fusion, drift, promo, None, dom, None, [], repeat_decision=decision
                    )
                    evidence = (Path("evidence") / Path(report).name).as_posix()
                    report_digest = sha256(Path(report).read_bytes()).hexdigest()
                results[scenario] = {**decision, "score": fusion["final_risk_score"],
                                     "evidence": evidence, "evidence_sha256": report_digest}
    output = {"transport": "real HTTP over loopback", "proxy_mode": "forward_only", "cases": results}
    (args.output_dir / "demo_result.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
