"""
Main reverse-proxy middleware entrypoint.
Run with: uvicorn app.main:app --host 0.0.0.0 --port 8443

Layer 1 (L1): JA3/HTTP2 fingerprint + scored blocklist + rate limiting
Layer 2 (L2): Decoy-neutralization engine
Layer 3 (L3): Auto forensic deep-scan (triggered async on alert)

§1.10 Calibration: set LOG_ONLY=true in env to forward-only mode for
Googlebot allowlist calibration (never blocks/decoys, just logs).
"""

import asyncio
import logging
import sys
from pathlib import Path

# FastAPI import guard
try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import HTMLResponse
    import httpx
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    print("[app/main.py] fastapi/httpx not installed. "
          "Install with: pip install fastapi uvicorn[standard] httpx")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ORIGIN_SERVER_URL, LOG_ONLY
from app.fingerprint.capture import capture_loop, lookup_fingerprint
from app.fingerprint.crawler_verify import verify_crawler, identify_claimed_bot
from app.fingerprint.blocklist import get_fingerprint_status, register_cloak_match
from app.fingerprint.rate_limiter import check_rate_limit
from app.decoy.decoy_store import get_decoy_if_armed
from app.pipeline_bridge.adapter import run_detection_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("defacement_defense")

app = FastAPI(title="Defacement Defense Middleware — Active Defense System")
_http_client = httpx.AsyncClient(timeout=20.0)


@app.on_event("startup")
async def startup():
    # Background task: TLS ClientHello capture for JA3 fingerprinting
    asyncio.create_task(capture_loop())
    if LOG_ONLY:
        logger.warning("═" * 60)
        logger.warning("LOG_ONLY=true — calibration mode active.")
        logger.warning("All requests forwarded; JA3s of verified crawlers are logged.")
        logger.warning("Populate GOOGLEBOT_ALLOWLIST_JA3 in config.py before going live.")
        logger.warning("═" * 60)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "HEAD"])
async def proxy(full_path: str, request: Request):
    client_ip   = request.client.host
    client_port = request.client.port
    user_agent  = request.headers.get("user-agent", "")
    url         = str(request.url)

    # ── Step 1: Crawler verification (ALWAYS runs first, see §1.6) ──
    claimed_bot = identify_claimed_bot(user_agent)
    if claimed_bot:
        verify_result = verify_crawler(client_ip, user_agent)
        if verify_result["verified"]:
            # §1.10 calibration: log the JA3 of real verified crawlers
            ja3_for_log = lookup_fingerprint(client_ip, client_port)
            if ja3_for_log:
                logger.info(f"VERIFIED_CRAWLER ja3={ja3_for_log} bot={claimed_bot} ip={client_ip}")
            # Verified real Googlebot/Bingbot — skip ALL fingerprint logic
            return await _forward_to_origin(request, full_path)
        else:
            # Claims to be Googlebot but FAILED verification — high-confidence malicious
            impersonation_detected = True
            logger.warning(f"IMPERSONATION_DETECTED reason={verify_result['reason']} ip={client_ip}")
    else:
        impersonation_detected = False

    # LOG_ONLY mode: skip all enforcement and just forward
    if LOG_ONLY:
        return await _forward_to_origin(request, full_path)

    # ── Step 2: Fingerprint lookup ─────────────────────────────────
    ja3_hash = lookup_fingerprint(client_ip, client_port)

    if ja3_hash:
        status = get_fingerprint_status(ja3_hash)

        if impersonation_detected:
            # Auto-escalate: impersonating Googlebot is high-confidence malicious
            register_cloak_match(ja3_hash, url)
            status = get_fingerprint_status(ja3_hash)  # re-fetch updated score

        if status["action"] == "BLOCK":
            logger.warning(f"BLOCK ja3={ja3_hash} score={status['score']} url={url[:80]}")
            return Response(content="Forbidden", status_code=403)

        if status["action"] == "RATE_LIMIT":
            allowed = await check_rate_limit(ja3_hash)
            if not allowed:
                logger.info(f"RATE_LIMITED ja3={ja3_hash} url={url[:80]}")
                return Response(content="Too Many Requests", status_code=429)

            # ── Step 3: Decoy check — is this URL's cloaking already confirmed? ──
            decoy_html = get_decoy_if_armed(url)
            if decoy_html:
                logger.info(f"DECOY_SERVED ja3={ja3_hash} url={url[:80]}")
                return HTMLResponse(content=decoy_html, status_code=200)

    # ── Step 4: Normal forward to origin ───────────────────────────
    response = await _forward_to_origin(request, full_path)

    # ── Step 5: Async feed into existing detection pipeline ───────
    # Fire-and-forget — never blocks the response to the real client
    asyncio.create_task(
        run_detection_async(url=url, ja3_hash=ja3_hash,
                            response_body=getattr(response, "body", b""))
    )

    return response


async def _forward_to_origin(request: Request, full_path: str) -> Response:
    target_url = f"{ORIGIN_SERVER_URL}/{full_path}"
    body = await request.body()
    try:
        upstream = await _http_client.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            params=dict(request.query_params),
            content=body,
        )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=dict(upstream.headers),
        )
    except Exception as e:
        logger.error(f"UPSTREAM_ERROR: {e}")
        return Response(content=f"Bad Gateway: {e}", status_code=502)
