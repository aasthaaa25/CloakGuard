"""Capture ClientHello on the public TCP listener before private TLS termination."""

import asyncio
import logging

from app.fingerprint.ja3 import compute_ja3

logger = logging.getLogger(__name__)
# Private connection tuple -> (real client IP, JA3). Shared within one process.
_connections = {}
MAX_HELLO = 65535


def connection_metadata(peer):
    return _connections.get(peer)


async def read_client_hello(reader):
    """Read complete handshake records, preserving their original wire bytes."""
    records = bytearray()
    handshake = bytearray()
    while len(records) < MAX_HELLO:
        header = await reader.readexactly(5)
        size = int.from_bytes(header[3:5], "big")
        if header[0] != 22 or not 0 < size <= 16384:
            raise ValueError("Invalid TLS handshake record")
        body = await reader.readexactly(size)
        records.extend(header + body)
        handshake.extend(body)
        if len(handshake) >= 4:
            length = int.from_bytes(handshake[1:4], "big") + 4
            if handshake[0] != 1 or length > MAX_HELLO:
                raise ValueError("Expected a bounded ClientHello")
            if len(handshake) >= length:
                hello = handshake[:length]
                if len(hello) > MAX_HELLO:
                    return bytes(records), None
                packet = bytes(header[:3]) + len(hello).to_bytes(2, "big") + hello
                return bytes(records), compute_ja3(packet)["ja3_hash"]
    raise ValueError("ClientHello exceeds capture limit")


async def _pipe(reader, writer):
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()


async def start_capture(host, port, private_port):
    """Relay TLS bytes to Uvicorn and convey metadata via process-local state."""
    active = set()

    async def handle(reader, writer):
        if len(active) >= 256:
            writer.close()
            return
        task = asyncio.current_task()
        active.add(task)
        upstream = None
        key = None
        pumps = []
        try:
            wire, fingerprint = await asyncio.wait_for(read_client_hello(reader), 3)
            remote, upstream = await asyncio.open_connection("127.0.0.1", private_port)
            key = upstream.get_extra_info("sockname")
            ip = writer.get_extra_info("peername")[0]
            _connections[key] = (ip, fingerprint)
            upstream.write(wire)
            await upstream.drain()
            pumps = [asyncio.create_task(_pipe(reader, upstream)),
                     asyncio.create_task(_pipe(remote, writer))]
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        except (ValueError, OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            logger.debug("TLS capture connection closed", exc_info=True)
        finally:
            for pump in pumps:
                pump.cancel()
            if key is not None:
                _connections.pop(key, None)
            if upstream is not None:
                upstream.close()
            writer.close()
            active.discard(task)
            await asyncio.gather(*pumps, return_exceptions=True)

    return await asyncio.start_server(handle, host, port)
