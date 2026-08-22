"""Local-only TCP bridge from a published loopback port to the Docker MySQL service."""

from __future__ import annotations

import argparse
import select
import socket
import socketserver


class _ForwardHandler(socketserver.BaseRequestHandler):
    upstream_host = "mysql_db"
    upstream_port = 3306

    def handle(self) -> None:
        with socket.create_connection((self.upstream_host, self.upstream_port), timeout=10) as upstream:
            sockets = (self.request, upstream)
            while True:
                readable, _, _ = select.select(sockets, (), (), 30)
                if not readable:
                    continue
                for source in readable:
                    payload = source.recv(65536)
                    if not payload:
                        return
                    target = upstream if source is self.request else self.request
                    target.sendall(payload)


class _ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, default=13306)
    parser.add_argument("--upstream-host", default="mysql_db")
    parser.add_argument("--upstream-port", type=int, default=3306)
    arguments = parser.parse_args()
    _ForwardHandler.upstream_host = arguments.upstream_host
    _ForwardHandler.upstream_port = arguments.upstream_port
    with _ThreadingServer(("0.0.0.0", arguments.listen_port), _ForwardHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
