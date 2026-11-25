"""Forward HTTP traffic to one configured, owner-controlled origin."""

from contextlib import asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
import logging

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.config import ORIGIN_SERVER_URL

logger = logging.getLogger(__name__)

HOP_BY_HOP = {
    b"connection", b"keep-alive", b"proxy-authenticate", b"proxy-authorization",
    b"proxy-connection", b"te", b"trailer", b"transfer-encoding", b"upgrade",
}


def end_to_end_headers(headers, extra_exclusions=()):
    excluded = HOP_BY_HOP.union(extra_exclusions)
    for name, value in headers:
        if name.lower() == b"connection":
            excluded.update(token.strip().lower() for token in value.split(b","))
    return [(name, value) for name, value in headers if name.lower() not in excluded]


@asynccontextmanager
async def lifespan(app):
    origin = httpx.URL(ORIGIN_SERVER_URL)
    if (
        origin.scheme not in ("http", "https") or not origin.host
        or origin.userinfo or origin.query or origin.fragment
    ):
        raise ValueError("ORIGIN_SERVER_URL requires an HTTP(S) origin without credentials, query or fragment")
    app.state.origin = origin
    cookie_policy = DefaultCookiePolicy(allowed_domains=())
    async with httpx.AsyncClient(
        timeout=20.0, trust_env=False, cookies=CookieJar(policy=cookie_policy)
    ) as client:
        app.state.upstream = client
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/_cloakguard/health")
async def health():
    return {"status": "ok", "mode": "forward_only"}


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(request: Request):
    origin = request.app.state.origin
    path = request.scope["raw_path"]
    query = request.scope["query_string"]
    target_path = origin.raw_path.rstrip(b"/") + path
    if query:
        target_path += b"?" + query
    target = origin.copy_with(raw_path=target_path)

    inbound = request.headers.raw
    headers = end_to_end_headers(inbound, {b"host", b"forwarded", b"x-real-ip"})
    headers = [(name, value) for name, value in headers if not name.lower().startswith(b"x-forwarded-")]
    has_body = "content-length" in request.headers or "transfer-encoding" in request.headers
    outgoing = httpx.Request(
        request.method, target, headers=headers, content=request.stream() if has_body else None
    )
    try:
        upstream = await request.app.state.upstream.send(outgoing, stream=True)
    except httpx.RequestError:
        logger.warning("Configured origin request failed")
        return Response("Bad Gateway", status_code=502)

    response = StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        background=BackgroundTask(upstream.aclose),
    )
    response.raw_headers = end_to_end_headers(upstream.headers.raw)
    return response
