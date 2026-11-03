"""Run the single-process TLS defense ingress with a loopback-only backend."""

import argparse
import asyncio
import socket

import uvicorn

from app.fingerprint.capture import start_capture


class DefenseServer(uvicorn.Server):
    def __init__(self, config, host, port):
        super().__init__(config)
        self.host = host
        self.port = port

    async def startup(self, sockets=None):
        with socket.socket() as backend:
            backend.bind(("127.0.0.1", 0))
            private_port = backend.getsockname()[1]
            await super().startup(sockets=[backend.dup()])
        if self.started:
            self.ingress = await start_capture(self.host, self.port, private_port)

    async def shutdown(self, sockets=None):
        self.ingress.close()
        await self.ingress.wait_closed()
        await super().shutdown(sockets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    config = uvicorn.Config(
        "app.main:app", http="h11", ws="none", proxy_headers=False,
        ssl_certfile=args.cert, ssl_keyfile=args.key,
    )
    asyncio.run(DefenseServer(config, args.host, args.port).serve())


if __name__ == "__main__":
    main()
