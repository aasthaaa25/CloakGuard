"""Run the controlled origin, proxy, paired review, and evidence writer on loopback."""

import argparse
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
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
    from app.pipeline_bridge.adapter import score_capture
    from app.forensics.deep_scan import _write_forensic_report
    from app.forensics.dom_diff import compute_dom_diff

    with ExitStack() as cleanup:
        origin = cleanup.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Handler))
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
            for scenario, expected_alert in (("clean", False), ("bot_substantial", True)):
                route = f"/quartz_supply/{scenario}"
                record = {"url": str(client.base_url).rstrip("/") + route}
                for profile, parameters in VIEW_PROFILES.items():
                    response = client.get(route, headers={"User-Agent": parameters["user_agent"]})
                    response.raise_for_status()
                    record[profile] = {"status": response.status_code, "html": response.text}
                drift, promo, _, fusion = score_capture(record)
                if fusion["alert"] != expected_alert:
                    raise RuntimeError(f"Unexpected review verdict for {scenario}")
                evidence = None
                if fusion["alert"]:
                    dom = compute_dom_diff(record["human"]["html"], record["bot"]["html"])
                    report = _write_forensic_report(
                        record["url"], scenario, fusion, drift, promo, None, dom, None, []
                    )
                    evidence = (Path("evidence") / Path(report).name).as_posix()
                results[scenario] = {"alert": fusion["alert"], "score": fusion["final_risk_score"],
                                     "threshold": fusion["alert_threshold"], "evidence": evidence}
    output = {"transport": "real HTTP over loopback", "proxy_mode": "forward_only", "cases": results}
    (args.output_dir / "demo_result.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
