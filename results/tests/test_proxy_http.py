import asyncio
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from app import main


def test_closing_stream_releases_upstream():
    class Upstream:
        closed = False

        async def aiter_raw(self):
            yield b"partial response"

        async def aclose(self):
            self.closed = True

    async def check():
        upstream = Upstream()
        stream = main.stream_origin(upstream)
        assert await anext(stream) == b"partial response"
        await stream.aclose()
        assert upstream.closed

    asyncio.run(check())


@pytest.fixture
def origin(monkeypatch):
    observed = {}
    payload = gzip.compress(b"origin response")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            observed["path"] = self.path
            observed["headers"] = self.headers
            observed["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Set-Cookie", "a=1")
            self.send_header("Set-Cookie", "b=2")
            self.send_header("Connection", "close, X-Origin-Hop")
            self.send_header("X-Origin-Hop", "strip")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            observed["cookie"] = self.headers.get("Cookie")
            self.send_response(204)
            self.end_headers()

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        monkeypatch.setattr(main, "ORIGIN_SERVER_URL", f"http://127.0.0.1:{server.server_port}/base")
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield observed, payload
        finally:
            server.shutdown()
            worker.join()


def test_forwarding_over_real_upstream_socket(origin):
    observed, payload = origin
    with TestClient(main.app) as client:
        response = client.post(
            "/a%2Fb?k=one&k=two", content=b"hello",
            headers={"X-Forwarded-For": "192.0.2.1", "Connection": "X-Request-Hop", "X-Request-Hop": "strip"},
        )
        assert response.status_code == 200
        assert response.content == b"origin response"
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["content-length"] == str(len(payload))
        assert response.headers.get_list("set-cookie") == ["a=1", "b=2"]
        assert "x-origin-hop" not in response.headers
        assert observed["path"] == "/base/a%2Fb?k=one&k=two"
        assert observed["body"] == b"hello"
        assert observed["headers"].get("X-Forwarded-For") is None
        assert observed["headers"].get("X-Request-Hop") is None
        client.cookies.clear()
        assert client.get("/").status_code == 204
        assert observed["cookie"] is None


def test_health_and_upstream_status(origin):
    with TestClient(main.app) as client:
        assert client.get("/_cloakguard/health").json() == {"status": "ok", "mode": "forward_only"}
        response = client.put("/unsupported-by-fixture")
        assert response.status_code == 501


def test_origin_timeout_returns_generic_502(origin, monkeypatch):
    import httpx

    async def timeout(*args, **kwargs):
        raise httpx.ConnectTimeout("internal origin information")

    with TestClient(main.app) as client:
        monkeypatch.setattr(main.app.state.upstream, "send", timeout)
        response = client.get("/origin-unavailable")
        assert response.status_code == 502
        assert response.text == "Bad Gateway"


def test_proxy_to_paired_review_on_local_fixture(monkeypatch):
    from app.pipeline_bridge.adapter import score_capture
    from detection.pipeline.crawl import VIEW_PROFILES
    from testbed.calibrate_v2 import Handler

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        monkeypatch.setattr(main, "ORIGIN_SERVER_URL", f"http://127.0.0.1:{server.server_port}")
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with TestClient(main.app) as client:
                route = "/quartz_supply/bot_substantial"
                record = {"url": f"http://example.test{route}"}
                for profile in ("human", "bot"):
                    response = client.get(route, headers={"User-Agent": VIEW_PROFILES[profile]["user_agent"]})
                    record[profile] = {"status": response.status_code, "html": response.text}
                _, _, _, fusion = score_capture(record)
                assert fusion["alert"] is True
                assert fusion["score_is_probability"] is False
        finally:
            server.shutdown()
            worker.join()
