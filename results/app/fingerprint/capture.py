"""
Lightweight ClientHello capture using a raw socket listener.
Runs as a background task alongside the FastAPI proxy.
Pairs captured fingerprints with requests via (src_ip, src_port).
"""

import asyncio
from app.fingerprint.ja3 import compute_ja3

# In-memory short-lived cache: (src_ip, src_port) -> ja3_hash
# Entries expire quickly since they only need to survive the handshake-to-request gap
_fingerprint_cache: dict = {}
_CACHE_TTL_SECONDS = 5


def is_tls_client_hello(data: bytes) -> bool:
    """Quick check: TLS record type 0x16 (handshake), then ClientHello (0x01)"""
    return len(data) > 5 and data[0] == 0x16 and data[5] == 0x01


async def capture_loop(listen_port: int = 8443):
    """
    Background task: listens on the raw TCP port the proxy binds to,
    peeks at the first bytes of each new connection (the ClientHello),
    computes its JA3 hash, and caches it keyed by (src_ip, src_port)
    so the HTTP-layer handler can look it up moments later.
    """
    server = await asyncio.start_server(_handle_conn, "0.0.0.0", listen_port)
    async with server:
        await server.serve_forever()


async def _handle_conn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    src_ip, src_port = addr[0], addr[1]
    try:
        data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
        if is_tls_client_hello(data):
            result = compute_ja3(data)
            _fingerprint_cache[(src_ip, src_port)] = {
                "ja3_hash": result["ja3_hash"],
                "timestamp": asyncio.get_event_loop().time(),
            }
    except (asyncio.TimeoutError, Exception):
        pass
    finally:
        writer.close()


def lookup_fingerprint(src_ip: str, src_port: int):
    """Called by the HTTP middleware to retrieve the JA3 hash for an inbound request."""
    entry = _fingerprint_cache.get((src_ip, src_port))
    if entry is None:
        return None
    try:
        now = asyncio.get_event_loop().time()
    except RuntimeError:
        return None
    if now - entry["timestamp"] > _CACHE_TTL_SECONDS:
        return None
    return entry["ja3_hash"]
