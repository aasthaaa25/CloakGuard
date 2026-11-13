"""Run the controlled attack and defense presentation on loopback only."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent


def make_certificate(directory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CloakGuard local demo")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]), critical=False).sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "cert.pem", directory / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                          serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return cert_path, key_path


async def run_demo(output, temporary, model_path=None):
    import httpx
    import uvicorn

    fixture = ROOT / "testbed/live_captures/north_market"
    human = (fixture / "selective_promotional_injection_H1.html").read_bytes()
    bot = (fixture / "selective_promotional_injection_B1.html").read_bytes()

    class Origin(BaseHTTPRequestHandler):
        def do_GET(self):
            body = bot if "googlebot" in self.headers.get("User-Agent", "").lower() else human
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    origin_url = f"http://127.0.0.1:{origin.server_port}"
    os.environ.update({
        "ORIGIN_SERVER_URL": origin_url, "DEFENSE_MODE": "owner_authorized",
        "LOG_ONLY": "false", "REVIEW_THRESHOLD": "0.270", "ALERT_THRESHOLD": "0.45",
        "BLOCKLIST_DB_PATH": str(temporary / "blocklist.db"),
        "DECOY_DB_PATH": str(temporary / "decoys.db"),
        "FORENSICS_OUTPUT_DIR": str(output / "forensics"),
        "PASSIVE_DNS_API_KEY": "", "PASSIVE_DNS_API_URL": "",
        "URL_MODEL_PATH": "disabled",
    })
    sys.path.insert(0, str(ROOT / "results"))
    from app.main import app
    from app.fingerprint.capture import connection_metadata
    from app.fingerprint.blocklist import get_fingerprint_status, register_cloak_match
    from app.decoy.decoy_store import STATIC_DECOY, arm_decoy
    from app.pipeline_bridge import adapter
    from app.tls_ingress import DefenseServer

    observed = []

    async def traced_app(scope, receive, send):
        if scope["type"] == "http":
            observed.append(connection_metadata(scope["client"]))
        await app(scope, receive, send)

    certificate, key = make_certificate(temporary)
    config = uvicorn.Config(traced_app, http="h11", ws="none", proxy_headers=False,
                            ssl_certfile=str(certificate), ssl_keyfile=str(key), log_level="error")
    server = DefenseServer(config, "127.0.0.1", 0)
    server_task = asyncio.create_task(server.serve())
    try:
        async def ready():
            while not hasattr(server, "ingress"):
                if server_task.done():
                    await server_task
                    raise RuntimeError("TLS server stopped during startup")
                await asyncio.sleep(0.01)

        await asyncio.wait_for(ready(), 10)
        port = server.ingress.sockets[0].getsockname()[1]
        public_url = f"https://127.0.0.1:{port}/demo"
        context = ssl.create_default_context(cafile=str(certificate))
        async with httpx.AsyncClient(verify=context, trust_env=False, timeout=10) as client:
            first = await client.get(public_url, headers={"User-Agent": "CloakGuard-Demo/1.0 (controlled local client)"})
            first.raise_for_status()
            fingerprint = observed[-1][1]
            if not fingerprint:
                raise RuntimeError("JA3 capture unavailable. Install Scapy from requirements.")
            print(f"1. Real TLS handshake captured JA3 {fingerprint}", flush=True)
            # The proxy's normal entry point scheduled this crawl and report.
            tasks = list(adapter._active.values())
            if not tasks:
                raise RuntimeError("Proxy did not schedule a dual-view review")
            await asyncio.wait_for(asyncio.gather(*tasks), 45)
            review_files = list((output / "forensics").glob("review_*.json"))
            if len(review_files) != 1:
                raise RuntimeError("Expected one review for the controlled bot-only injection")
            review_file = review_files[0]
            review = json.loads(review_file.read_text())
            verdict = review["fusion"]
            if review["observed_ja3"] != fingerprint:
                raise RuntimeError("Review fingerprint differs from the observed TLS client")
            url_risk_prediction = None
            if model_path:
                import joblib
                import pandas as pd
                from detection.features import build_url_features

                bundle = joblib.load(model_path)
                features = build_url_features(review["url"])
                names = bundle["feature_names"]
                row = pd.DataFrame([{name: features[name] for name in names}])
                probability = float(bundle["pipeline"].predict_proba(row)[0, 1])
                url_risk_prediction = {"model_path": str(model_path), "probability": probability}
                print(f"   URL-risk model probability for the local URL: {probability:.3f}", flush=True)
            print(f"2. Live paired-view inference: {verdict['scoring_path']}, "
                  f"score={verdict['final_risk_score']:.3f}, alert={verdict['alert']}", flush=True)
            if not verdict["review_alert"] or not verdict["alert"]:
                raise RuntimeError("Selected scorer did not alert on this controlled fixture")
            before = get_fingerprint_status(fingerprint, confirmed_only=True)["score"]
            print("3. Controlled fixture confirmation: this script owns the origin and test client.", flush=True)
            review_id = review_file.stem.removeprefix("review_")
            register_cloak_match(fingerprint, review["url"], evidence_id="controlled-demo-incident",
                                 review_id=review_id)
            arm_decoy(review["url"], STATIC_DECOY, approved=True)
            after = get_fingerprint_status(fingerprint, confirmed_only=True)["score"]
            decoy = await client.get(public_url)
            inert = (decoy.text == STATIC_DECOY and "no-store" in decoy.headers.get("cache-control", "")
                     and "default-src 'none'" in decoy.headers.get("content-security-policy", ""))
            print(f"4. Confirmed score={after}; decoy HTTP {decoy.status_code}; inert={inert}", flush=True)
            # More independently named, explicitly controlled fixture events reach the block threshold.
            for number in (2, 3):
                register_cloak_match(fingerprint, review["url"], evidence_id=f"controlled-demo-incident-{number}")
            blocked = await client.get(public_url)
            async with httpx.AsyncClient(trust_env=False) as direct:
                original = await direct.get(origin_url + "/demo", headers={"User-Agent": "Googlebot/2.1 (controlled local test)"})
            report_path = output / "forensics" / f"forensic_report_{review_id}.html"
            result = {
                "scope": "Controlled loopback fixture. Confirmation and repeated incidents are scripted.",
                "tls_ja3": fingerprint, "fusion": verdict, "url_risk_prediction": url_risk_prediction,
                "score_before_confirmation": before, "score_after_confirmation": after,
                "decoy_status": decoy.status_code, "decoy_inert": inert,
                "blocked_status": blocked.status_code,
                "origin_still_injected": original.content == bot,
                "forensic_report_exists": report_path.exists(),
                "forensic_report": str(report_path),
            }
            (output / "demo_result.json").write_text(json.dumps(result, indent=2) + "\n")
            if not (inert and blocked.status_code == 403 and result["origin_still_injected"]
                    and result["forensic_report_exists"] and before == 0 and after == 25):
                raise RuntimeError("Defense demo verification failed. Inspect demo_result.json")
            print(f"5. Repeat controlled incidents: HTTP {blocked.status_code}. Origin still contains the fixture.", flush=True)
            print(f"Evidence saved in {output}", flush=True)
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, 10)
        finally:
            await asyncio.to_thread(origin.shutdown)
            origin.server_close()
            thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "demo_outputs" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ"))
    parser.add_argument("--url-model", type=Path, help="Show a separate URL-risk prediction from a trusted local model bundle")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.url_model and not args.url_model.is_file():
        parser.error("The requested model bundle does not exist")
    if (args.output / "demo_result.json").exists() or (args.output / "forensics").exists():
        parser.error("Choose a fresh --output directory to preserve previous evidence")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix="cloakguard-demo-") as temporary:
            if args.url_model is None:
                from generate_dataset import generate_dataset

                dataset = args.output / "url_model_training.csv"
                generate_dataset(dataset, rows=400)
                model_directory = args.output / "url_model"
                print("Preparing four URL-risk models on 400 synthetic demonstration URLs...", flush=True)
                training = subprocess.run([
                    sys.executable, str(ROOT / "results/detection/train_model.py"),
                    "--csv", str(dataset), "--artifacts", str(model_directory), "--quick",
                ], capture_output=True, encoding="utf-8", timeout=120,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                (args.output / "training.log").write_text(training.stdout + training.stderr, encoding="utf-8")
                if training.returncode:
                    raise RuntimeError("Demo model training failed. Inspect training.log")
                args.url_model = model_directory / "model.joblib"
            asyncio.run(run_demo(args.output, Path(temporary), args.url_model.resolve() if args.url_model else None))
    except (ImportError, RuntimeError, OSError, asyncio.TimeoutError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Demo failed: {error}\nInstall results/requirements.txt and choose a fresh --output directory.\n")


if __name__ == "__main__":
    main()
