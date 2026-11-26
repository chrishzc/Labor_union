"""Minimal loopback-only TCP relay from host 127.0.0.1:8080 into internal registration-ingress."""
from __future__ import annotations

import asyncio
import os
import signal

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("RELAY_LISTEN_PORT", "8080"))
UPSTREAM_HOST = os.environ.get("RELAY_UPSTREAM_HOST", "registration-intake")
UPSTREAM_PORT = int(os.environ.get("RELAY_UPSTREAM_PORT", "8080"))


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
    except (ConnectionError, OSError, asyncio.CancelledError):
        pass


async def _handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    upstream_writer: asyncio.StreamWriter | None = None
    try:
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(UPSTREAM_HOST, UPSTREAM_PORT),
            timeout=10,
        )
        t1 = asyncio.create_task(_pipe(client_reader, upstream_writer))
        t2 = asyncio.create_task(_pipe(upstream_reader, client_writer))
        await asyncio.gather(t1, t2)
    except (ConnectionError, OSError, TimeoutError):
        pass
    finally:
        for writer in (upstream_writer, client_writer):
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, OSError):
                    pass


async def _main() -> None:
    server = await asyncio.start_server(_handle, LISTEN_HOST, LISTEN_PORT)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    async with server:
        await stop.wait()


if __name__ == "__main__":
    asyncio.run(_main())
