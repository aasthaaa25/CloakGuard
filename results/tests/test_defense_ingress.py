"""Integration coverage from TLS ClientHello to the protected HTTP origin."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
import shutil
import ssl
import subprocess
import sys
from types import SimpleNamespace

from dns import resolver

import pytest
import uvicorn

from app import main, review
from app.decoy import decoy_store
from app.fingerprint import blocklist
from app.fingerprint.capture import connection_metadata
from app.fingerprint.crawler_verify import verify_crawler
from app.forensics import deep_scan
from app.tls_ingress import DefenseServer


@pytest.fixture
def databases(monkeypatch, tmp_path):
    monkeypatch.setattr(blocklist, "BLOCKLIST_DB_PATH", tmp_path / "scores.db")
    monkeypatch.setattr(decoy_store, "DECOY_DB_PATH", tmp_path / "decoys.db")


def test_confirmed_score_atomic_and_decaying(databases, monkeypatch):
    monkeypatch.setattr(blocklist.time, "time", lambda: 3600)
    with ThreadPoolExecutor(8) as pool:
        applied = list(pool.map(
            lambda _: blocklist.register_cloak_match("test", "url", evidence_id="review"),
            range(16),
        ))
    assert applied.count(True) == 1
    assert blocklist.get_fingerprint_status("test", confirmed_only=True)["score"] == 25
    monkeypatch.setattr(blocklist.time, "time", lambda: 7200)
    assert blocklist.get_fingerprint_status("test", confirmed_only=True)["score"] == 24


def test_cli_requires_observed_ja3_and_deduplicates_incident(databases, monkeypatch, tmp_path):
    monkeypatch.setattr(review, "FORENSICS_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(review, "DEFENSE_MODE", "owner_authorized")
    monkeypatch.setattr(review, "LOG_ONLY", False)
    ja3 = "a" * 32
    first, second = "b" * 32, "c" * 32
    for review_id in (first, second):
        (tmp_path / f"review_{review_id}.json").write_text(json.dumps({
            "url": "https://example.test/", "observed_ja3": ja3,
        }))

    def confirm(review_id, fingerprint, evidence_id):
        monkeypatch.setattr(sys, "argv", [
            "review", "confirm", review_id, "--ja3", fingerprint, "--evidence-id", evidence_id,
        ])
        review.main()

    with pytest.raises(SystemExit):
        confirm(first, "d" * 32, "incident")
    assert blocklist.get_fingerprint_status(ja3, confirmed_only=True)["score"] == 0
    confirm(first, ja3, "incident")
    confirm(first, ja3, "another-id")
    confirm(second, ja3, "incident")
    assert blocklist.get_fingerprint_status(ja3, confirmed_only=True)["score"] == 25


def test_approved_decoy_expires(databases, monkeypatch):
    monkeypatch.setattr(decoy_store.time, "time", lambda: 0)
    decoy_store.arm_decoy("url", "<script>unsafe()</script>", approved=True)
    assert decoy_store.get_decoy_if_armed("url", approved_only=True) == decoy_store.STATIC_DECOY
    monkeypatch.setattr(decoy_store.time, "time", lambda: 72 * 3600)
    assert decoy_store.get_decoy_if_armed("url", approved_only=True) is None


def test_partial_forensics(monkeypatch, tmp_path):
    monkeypatch.setattr(deep_scan, "FORENSICS_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(deep_scan, "capture_js_trace", lambda *_: {"error": "missing browser"})
    report = asyncio.run(deep_scan.trigger_deep_scan(
        "https://example.test/<script>", {"url_id": "test"}, {}, {}, {}, {"alert": True},
    ))
    body = (tmp_path / "forensic_report_test.html").read_text()
    assert report
    for label in ("Screenshot diff", "DOM diff", "JavaScript trace diff", "Passive DNS"):
        assert f"{label}: unavailable" in body
    assert "<script>" not in body


def test_crawler_dns_requires_reverse_and_forward_match(monkeypatch):
    monkeypatch.setattr(resolver, "resolve_address", lambda *args, **kwargs: [
        SimpleNamespace(target="CRAWL.Googlebot.com."),
    ])
    def forward(name, record_type, **kwargs):
        assert (name, record_type) == ("crawl.googlebot.com.", "AAAA")
        return [SimpleNamespace(address="2001:db8::1")]

    monkeypatch.setattr(resolver, "resolve", forward)
    assert verify_crawler("2001:db8::1", "Googlebot")["verified"]
    assert not verify_crawler("2001:db8::2", "Googlebot")["verified"]

    def outage(*args, **kwargs):
        raise resolver.LifetimeTimeout

    monkeypatch.setattr(resolver, "resolve", outage)
    assert verify_crawler("2001:db8::1", "Googlebot")["reason"] == "dns_unavailable"


@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl is required for the TLS fixture")
def test_tls_handshake_enforces_only_confirmed_observed_ja3(databases, monkeypatch, tmp_path):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-subj", "/CN=localhost", "-days", "1", "-out", str(cert), "-keyout", str(key),
    ], check=True, capture_output=True)
    observed = []
    origin_requests = []
    reviews = []

    async def traced_app(scope, receive, send):
        if scope["type"] == "http":
            observed.append(connection_metadata(scope["client"]))
        await main.app(scope, receive, send)

    async def origin(reader, writer):
        origin_requests.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                     b"Content-Length: 6\r\nSet-Cookie: origin_secret=value\r\nConnection: close\r\n\r\norigin")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def exercise():
        upstream = await asyncio.start_server(origin, "127.0.0.1", 0)
        origin_url = f"http://127.0.0.1:{upstream.sockets[0].getsockname()[1]}"
        monkeypatch.setattr(main, "ORIGIN_SERVER_URL", origin_url)
        monkeypatch.setattr(main, "DEFENSE_MODE", "owner_authorized")
        monkeypatch.setattr(main, "LOG_ONLY", False)
        monkeypatch.setattr(main, "schedule_review", lambda *args: reviews.append(args))

        config = uvicorn.Config(
            traced_app, proxy_headers=False, http="h11",
            ssl_certfile=str(cert), ssl_keyfile=str(key), log_level="error", ws="none",
        )
        server = DefenseServer(config, "127.0.0.1", 0)
        task = asyncio.create_task(server.serve())
        context = ssl.create_default_context(cafile=str(cert))

        async def request(method="GET", user_agent="Test"):
            port = server.ingress.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", port, ssl=context, server_hostname="localhost",
            )
            writer.write(
                f"{method} /test?a=1&a=2 HTTP/1.1\r\nHost: localhost\r\n"
                f"User-Agent: {user_agent}\r\nX-JA3: fake\r\nX-CloakGuard-JA3: fake\r\n"
                "X-Forwarded-For: 192.0.2.1\r\nConnection: close\r\n\r\n".encode()
            )
            await writer.drain()
            result = await asyncio.wait_for(reader.read(), 5)
            writer.close()
            await writer.wait_closed()
            return result

        try:
            while not hasattr(server, "ingress"):
                if task.done():
                    await task
                    raise AssertionError("TLS ingress did not start")
                await asyncio.sleep(0.01)
            assert (await request()).endswith(b"origin")
            peer, fingerprint = observed[-1]
            assert peer == "127.0.0.1"
            assert re.fullmatch(r"[0-9a-f]{32}", fingerprint)
            assert reviews == [(origin_url + "/test?a=1&a=2", fingerprint)]
            forwarded = origin_requests[-1].lower()
            assert b"get /test?a=1&a=2 http/" in forwarded
            assert b"fake" not in forwarded and b"192.0.2.1" not in forwarded
            url = reviews[0][0]
            decoy_store.arm_decoy(url, "", approved=True)
            for _ in range(3):
                blocklist.register_cloak_match(fingerprint, url)
            assert (await request()).endswith(b"origin")
            assert b"cookie:" not in origin_requests[-1].lower()
            blocklist.register_cloak_match(fingerprint, url, evidence_id="one")
            decoy = await request()
            assert b"200 OK" in decoy and b"Welcome" in decoy
            assert b"cache-control: private, no-store" in decoy.lower()
            assert b"default-src 'none'; sandbox" in decoy
            assert (await request("HEAD")).endswith(b"\r\n\r\n")
            for _ in range(8):
                assert b"Welcome" in await request()
            assert b"429 Too Many Requests" in await request()
            for event in ("two", "three"):
                blocklist.register_cloak_match(fingerprint, url, evidence_id=event)
            assert b"403 Forbidden" in await request()
            for verdict in (
                {"verified": True, "reason": "dns_verification_passed"},
                {"verified": False, "reason": "dns_unavailable"},
            ):
                monkeypatch.setattr(main, "verify_crawler", lambda *_: verdict)
                assert (await request(user_agent="Googlebot")).endswith(b"origin")
            monkeypatch.setattr(main, "LOG_ONLY", True)
            assert (await request()).endswith(b"origin")
            monkeypatch.setattr(main, "LOG_ONLY", False)
            monkeypatch.setattr(main, "DEFENSE_MODE", "external_monitor")
            assert (await request()).endswith(b"origin")
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)
            upstream.close()
            await upstream.wait_closed()

    asyncio.run(exercise())
