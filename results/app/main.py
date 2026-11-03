"""Reverse proxy for monitoring and owner-authorized defense."""

import asyncio
import logging
from contextlib import asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

from app.config import CRAWLER_DNS_TIMEOUT_SECONDS, DEFENSE_MODE, LOG_ONLY, ORIGIN_SERVER_URL
from app.decoy.decoy_store import STATIC_DECOY, get_decoy_if_armed
from app.fingerprint.blocklist import get_fingerprint_status
from app.fingerprint.capture import connection_metadata
from app.fingerprint.crawler_verify import identify_claimed_bot, verify_crawler
from app.fingerprint.rate_limiter import check_rate_limit
from app.pipeline_bridge.adapter import schedule_review

logger = logging.getLogger(__name__)
_HOP_HEADERS = {
    b"connection", b"keep-alive", b"proxy-authenticate", b"proxy-authorization",
    b"proxy-connection", b"te", b"trailer", b"transfer-encoding", b"upgrade",
}
_DECOY_HEADERS = {
    "Cache-Control": "private, no-store",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
}


class RejectOriginCookies(DefaultCookiePolicy):
    def set_ok(self, cookie, request):
        return False


@asynccontextmanager
async def lifespan(app):
    cookies = CookieJar(policy=RejectOriginCookies())
    async with httpx.AsyncClient(timeout=20.0, trust_env=False, cookies=cookies) as client:
        app.state.origin_client = client
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "HEAD"])
async def proxy(request: Request, full_path: str):
    # Retain the wire path and query without allowing Host to choose the origin.
    path = request.scope["raw_path"].decode("ascii")
    query = request.scope["query_string"].decode("ascii")
    url = ORIGIN_SERVER_URL.rstrip("/") + path
    if query:
        url += "?" + query

    metadata = connection_metadata(tuple(request.client)) if request.client else None
    fingerprint = metadata[1] if metadata else None
    enforce = DEFENSE_MODE == "owner_authorized" and not LOG_ONLY and fingerprint

    user_agent = request.headers.get("user-agent", "")
    if enforce and identify_claimed_bot(user_agent):
        try:
            verdict = await asyncio.wait_for(
                asyncio.to_thread(verify_crawler, metadata[0], user_agent),
                timeout=CRAWLER_DNS_TIMEOUT_SECONDS,
            )
            enforce = not (verdict["verified"] or verdict["reason"] == "dns_unavailable")
        except (asyncio.TimeoutError, OSError):
            enforce = False

    if enforce:
        status = await asyncio.to_thread(get_fingerprint_status, fingerprint, confirmed_only=True)
        if status["action"] == "BLOCK":
            return Response("Forbidden", status_code=403, headers={"Cache-Control": "no-store"})
        if status["action"] == "RATE_LIMIT":
            if not await check_rate_limit(fingerprint):
                return Response("Too Many Requests", status_code=429,
                                headers={"Cache-Control": "no-store"})
            if request.method in {"GET", "HEAD"} and await asyncio.to_thread(get_decoy_if_armed, url, approved_only=True):
                # Always use static output, including when reading a legacy decoy row.
                response = HTMLResponse(STATIC_DECOY,
                                        headers=_DECOY_HEADERS)
                if request.method == "HEAD":
                    response.body = b""
                return response

    response = await _forward_to_origin(request, url)
    if (request.method == "GET" and response.status_code == 200
            and response.headers.get("content-type", "").lower().startswith("text/html")):
        schedule_review(url, fingerprint)
    return response


def _end_to_end(headers):
    excluded = _HOP_HEADERS | {
        value.strip().lower()
        for key, values in headers if key.lower() == b"connection"
        for value in values.split(b",")
    }
    return [(key, value) for key, value in headers if key.lower() not in excluded]


async def _forward_to_origin(request, url):
    headers = [
        (key, value) for key, value in _end_to_end(request.headers.raw)
        if key.lower() not in {b"host", b"forwarded", b"x-real-ip", b"x-ja3"}
        and not key.lower().startswith((b"x-forwarded-", b"x-cloakguard-"))
    ]
    try:
        upstream = await request.app.state.origin_client.request(
            request.method, url, headers=headers, content=await request.body(),
        )
    except httpx.HTTPError:
        logger.warning("Origin request failed", exc_info=True)
        return Response("Bad Gateway", status_code=502)

    response = Response(upstream.content, status_code=upstream.status_code)
    response.raw_headers = [
        (key.lower(), value) for key, value in _end_to_end(upstream.headers.raw)
        if request.method == "HEAD" or key.lower() not in {b"content-encoding", b"content-length"}
    ] + ([] if request.method == "HEAD" else response.raw_headers)
    return response
