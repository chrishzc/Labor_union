"""Exercise the no-npm bypass transport over real loopback HTTP and WebSocket sockets."""

from contextlib import closing, contextmanager
import base64
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from threading import Thread

import pytest

from scripts.launchers.local_react_gateway import LocalReactGateway


@contextmanager
def running(server):
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def read_exact(reader, size):
    result = bytearray()
    while len(result) < size:
        data = reader.read(size - len(result))
        assert data, "Connection ended before the expected payload"
        result.extend(data)
    return bytes(result)


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.headers.get("Transfer-Encoding") == "chunked":
            body = bytearray()
            while size := int(self.rfile.readline(), 16):
                body.extend(read_exact(self.rfile, size))
                assert self.rfile.read(2) == b"\r\n"
            assert self.rfile.readline() == b"\r\n"
            body = bytes(body)
        else:
            body = read_exact(self.rfile, int(self.headers.get("Content-Length", "0")))
        self.server.calls.append((self.command, self.path, body, self.headers.get("Authorization")))
        self.send_response(409 if self.path.startswith("/api/conflict") else 200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", "first=one; HttpOnly")
        self.send_header("Set-Cookie", "second=two; HttpOnly")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_GET = do_HEAD = do_OPTIONS = do_PATCH = do_PUT = do_DELETE = do_POST


class ViteHandler(BaseHTTPRequestHandler):
    rbufsize = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.calls.append(self.path)
        if self.headers.get("Upgrade") == "websocket":
            key = self.headers["Sec-WebSocket-Key"]
            accept = base64.b64encode(hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
            ).digest()).decode()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.send_header("Sec-WebSocket-Protocol", self.headers["Sec-WebSocket-Protocol"])
            self.end_headers()
            # Send the first frame immediately; a buffered handshake must not lose it.
            self.wfile.write(b"\x81\x05ready")
            frame = read_exact(self.rfile, 6)
            payload = read_exact(self.rfile, frame[1] & 0x7f)
            unmasked = bytes(value ^ frame[2 + i % 4] for i, value in enumerate(payload))
            self.wfile.write(bytes([0x81, len(unmasked)]) + unmasked)
            return
        body = b'<html><div id="root"></div></html>'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_HEAD = do_GET


@pytest.fixture
def gateway():
    with running(ThreadingHTTPServer(("127.0.0.1", 0), APIHandler)) as api:
        api.calls = []
        with running(ThreadingHTTPServer(("127.0.0.1", 0), ViteHandler)) as vite:
            vite.calls = []
            with running(LocalReactGateway(0, api.server_port, vite.server_port)) as proxy:
                yield proxy, api, vite


def request(proxy, method, path, body=None, headers=None, encode_chunked=False):
    with closing(http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)) as client:
        client.request(method, path, body, headers or {}, encode_chunked=encode_chunked)
        response = client.getresponse()
        return response.status, response.getheaders(), response.read()


def test_frontend_stays_on_loopback_and_api_is_not_sent_to_docker(gateway):
    proxy, api, vite = gateway
    assert proxy.server_address[0] == "127.0.0.1"
    status, _, body = request(proxy, "GET", "/admin/orders?view=current")
    assert status == 200 and b'id="root"' in body
    assert vite.calls == ["/admin/orders?view=current"]
    assert not api.calls
    status, _, _ = request(proxy, "GET", "/api/read?filter=current")
    assert status == 200
    assert api.calls[-1][:3] == ("GET", "/api/read?filter=current", b"")
    assert len(vite.calls) == 1


@pytest.mark.parametrize("path", ["/api/upload?dry=true", "/line-status", "/webhook/line"])
def test_uploads_keep_bytes_query_auth_and_response_headers(gateway, path):
    proxy, api, vite = gateway
    body = bytes(range(256)) * 1024
    status, headers, returned = request(proxy, "POST", path, body, {
        "Authorization": "Bearer test-only", "Content-Type": "application/octet-stream",
    })
    assert status == 200 and returned == body
    assert api.calls == [("POST", path, body, "Bearer test-only")]
    assert [value for key, value in headers if key.lower() == "set-cookie"] == [
        "first=one; HttpOnly", "second=two; HttpOnly",
    ]
    assert not vite.calls


def test_chunked_upload_and_typed_conflict_survive_gateway(gateway):
    proxy, api, _ = gateway
    status, _, body = request(proxy, "PATCH", "/api/conflict", iter([b"first", b"second"]), {
        "Transfer-Encoding": "chunked",
    }, encode_chunked=True)
    assert status == 409 and body == b"firstsecond"
    assert api.calls[0][:3] == ("PATCH", "/api/conflict", b"firstsecond")


def test_head_preserves_headers_without_body(gateway):
    proxy, _, _ = gateway
    status, headers, body = request(proxy, "HEAD", "/admin/")
    assert status == 200 and body == b""
    assert int(dict(headers)["Content-Length"]) > 0


def test_webhook_declared_size_is_rejected_before_upstream_upload(gateway):
    proxy, api, vite = gateway
    # No body is sent: the transport must reject from the declared size alone.
    status, _, body = request(proxy, "POST", "/webhook/line", headers={
        "Content-Length": str(1024 * 1024 + 1),
    })
    assert status == 413 and b"LINE webhook body too large" in body
    assert not api.calls and not vite.calls


@pytest.mark.parametrize("headers", [
    {"Content-Length": "invalid"},
    {"Content-Length": "-1"},
    {"Content-Length": "0", "Transfer-Encoding": "chunked"},
])
def test_invalid_request_framing_is_rejected_locally(gateway, headers):
    proxy, api, vite = gateway
    assert request(proxy, "POST", "/api/apply", headers=headers)[0] == 400
    assert not api.calls and not vite.calls


@pytest.mark.parametrize("headers", [
    {"Host": "remote.invalid"},
    {"Origin": "https://remote.invalid"},
    {"Origin": "null"},
])
def test_nonlocal_host_or_origin_cannot_reach_bypass_api(gateway, headers):
    proxy, api, vite = gateway
    assert request(proxy, "POST", "/api/apply", b"denied", headers)[0] == 403
    assert not api.calls and not vite.calls


def test_websocket_hmr_keeps_protocol_query_and_frames(gateway):
    proxy, _, vite = gateway
    with socket.create_connection(("127.0.0.1", proxy.server_port), timeout=5) as client:
        client.sendall((
            "GET /admin/?token=test-only HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{proxy.server_port}\r\n"
            f"Origin: http://localhost:{proxy.server_port}\r\n"
            "Connection: Upgrade\r\nUpgrade: websocket\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: vite-hmr\r\n\r\n"
        ).encode())
        with client.makefile("rb", buffering=0) as reader:
            status = reader.readline()
            headers = []
            while (line := reader.readline()) != b"\r\n":
                assert line
                headers.append(line)
            assert b"101" in status
            assert b"Sec-WebSocket-Protocol: vite-hmr\r\n" in headers
            assert read_exact(reader, 7) == b"\x81\x05ready"
            payload, mask = b"hello", b"1234"
            masked = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
            client.sendall(b"\x81\x85" + mask + masked)
            assert read_exact(reader, 7) == b"\x81\x05hello"
    assert vite.calls == ["/admin/?token=test-only"]


def test_upstream_failure_is_visible_without_retry():
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        closed_port = unused.getsockname()[1]
    with running(LocalReactGateway(0, closed_port, closed_port)) as proxy:
        assert request(proxy, "GET", "/api/read")[0] == 502
