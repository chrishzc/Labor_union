"""Loopback-only gateway for Docker Vite and the host's local-bypass API.

Keep relative API requests on the host; tunnel Vite's WebSocket upgrades so
Docker remains responsible for the frontend without needing host Node.js.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import select
import socket
from urllib.parse import urlsplit


_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
})
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_WEBHOOK_ALIASES = frozenset({"/webhook", "/webhook/", "/webhook/line", "/webhook/line/"})


class LocalReactGateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, listen_port: int, api_port: int, vite_port: int) -> None:
        self.api_port = api_port
        self.vite_port = vite_port
        super().__init__(("127.0.0.1", listen_port), _GatewayHandler)


class _GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Do not prefetch WebSocket frames while reading the HTTP handshake.
    rbufsize = 0

    def log_message(self, format: str, *args: object) -> None:
        # Request paths may contain private data or Vite's WebSocket token.
        pass

    def _body(self):
        encoding = self.headers.get("Transfer-Encoding", "").lower()
        if encoding and encoding != "chunked":
            raise ValueError("Unsupported transfer encoding")
        remaining = int(self.headers.get("Content-Length", "0"))
        if remaining < 0 or (encoding and "Content-Length" in self.headers):
            raise ValueError("Invalid request framing")
        while True:
            if encoding:
                remaining = int(self.rfile.readline(8192).split(b";", 1)[0], 16)
                if remaining < 0:
                    raise ValueError("Invalid chunk size")
                if remaining == 0:
                    while True:
                        trailer = self.rfile.readline(8192)
                        if trailer == b"\r\n":
                            return
                        if not trailer:
                            raise ValueError("Incomplete request trailers")
            while remaining:
                data = self.rfile.read(min(remaining, 65536))
                if not data:
                    raise ValueError("Incomplete request body")
                remaining -= len(data)
                yield data
            if not encoding:
                return
            terminator = bytearray()
            while len(terminator) < 2:
                data = self.rfile.read(2 - len(terminator))
                if not data:
                    raise ValueError("Incomplete chunk terminator")
                terminator.extend(data)
            if terminator != b"\r\n":
                raise ValueError("Invalid chunk terminator")

    def _websocket(self, port: int) -> None:
        with socket.create_connection(("127.0.0.1", port), timeout=30) as upstream:
            request = f"{self.command} {self.path} HTTP/1.1\r\n"
            request += "".join(f"{key}: {value}\r\n" for key, value in self.headers.items())
            upstream.sendall((request + "\r\n").encode("latin-1"))
            with upstream.makefile("rb", buffering=0) as reader:
                status = reader.readline(65537)
                headers = bytearray(status)
                while True:
                    line = reader.readline(65537)
                    if not line or len(headers) + len(line) > 65536:
                        raise OSError("Invalid upstream WebSocket handshake")
                    headers.extend(line)
                    if line == b"\r\n":
                        break
                self._response_started = True
                self.wfile.write(headers)
                self.wfile.flush()
                if status.split()[1:2] != [b"101"]:
                    # Forward an upstream rejection without treating it as an upgrade.
                    while data := reader.read(65536):
                        self.wfile.write(data)
                    return
                upstream.settimeout(None)
                sockets = (self.connection, upstream)
                while True:
                    readable, _, _ = select.select(sockets, (), (), 30)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        target = upstream if source is self.connection else self.connection
                        target.sendall(data)

    def _proxy(self) -> None:
        self.close_connection = True
        try:
            path = urlsplit(self.path)
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
            origin = self.headers.get("Origin")
            origin_host = urlsplit(origin).hostname if origin else None
        except ValueError:
            self.send_error(400)
            return
        if host not in _LOCAL_HOSTS or (origin and origin_host not in _LOCAL_HOSTS):
            self.send_error(403)
            return
        if path.scheme or path.netloc or not self.path.startswith("/"):
            self.send_error(400)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            encoding = self.headers.get("Transfer-Encoding", "").lower()
            if (length < 0 or len(self.headers.get_all("Content-Length", [])) > 1
                or encoding not in {"", "chunked"}
                or (encoding and "Content-Length" in self.headers)):
                raise ValueError("Invalid request framing")
        except ValueError:
            self.send_error(400)
            return
        # Preserve Vite's early transport rejection before a large upload can
        # race the API's 413. The API still owns streamed-body validation.
        if self.command == "POST" and path.path in _WEBHOOK_ALIASES and length > 1024 * 1024:
            body = json.dumps({"detail": "LINE webhook body too large"}).encode()
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            return
        is_api = path.path.startswith(("/api", "/line-", "/webhook"))
        port = self.server.api_port if is_api else self.server.vite_port
        self._response_started = False
        try:
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._websocket(port)
                return
            connection_headers = {
                value.strip().lower()
                for value in self.headers.get("Connection", "").split(",")
            }
            headers = {
                key: value for key, value in self.headers.items()
                if key.lower() not in _HOP_HEADERS | connection_headers
            }
            headers["Connection"] = "close"
            with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=60)) as upstream:
                upstream.request(
                    self.command, self.path, body=self._body(), headers=headers,
                    encode_chunked=self.headers.get("Transfer-Encoding", "").lower() == "chunked",
                )
                response = upstream.getresponse()
                self.send_response_only(response.status, response.reason)
                self._response_started = True
                excluded = _HOP_HEADERS | {
                    value.strip().lower()
                    for value in response.getheader("Connection", "").split(",")
                }
                for key, value in response.getheaders():
                    if key.lower() not in excluded:
                        self.send_header(key, value)
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    while data := response.read1(65536):
                        self.wfile.write(data)
        except (OSError, http.client.HTTPException, ValueError):
            if not self._response_started:
                self.send_error(502, "Local frontend or API unavailable")

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _proxy


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return port


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-port", type=_port, required=True)
    parser.add_argument("--api-port", type=_port, required=True)
    parser.add_argument("--vite-port", type=_port, required=True)
    arguments = parser.parse_args()
    with LocalReactGateway(arguments.listen_port, arguments.api_port, arguments.vite_port) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
