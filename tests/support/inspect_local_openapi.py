"""
File: inspect_local_openapi.py
Description: 安全讀取 localhost OpenAPI，驗證 health 僅為 GET 並回報指定方法的 operation 數量。
"""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_SCHEMA_BYTES = 20 * 1024 * 1024


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise HTTPError(request.full_url, code, "OpenAPI redirect is forbidden", headers, file_pointer)


def _load_schema(schema_url: str, timeout_seconds: int) -> dict[str, Any]:
    parsed = urlsplit(schema_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("schema URL must use HTTP(S) and an exact localhost host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("schema URL must not contain credentials, query, or fragment")

    request = Request(schema_url, method="GET", headers={"Accept": "application/json"})
    with build_opener(_RejectRedirects()).open(request, timeout=timeout_seconds) as response:
        payload = response.read(MAX_SCHEMA_BYTES + 1)
    if len(payload) > MAX_SCHEMA_BYTES:
        raise ValueError("OpenAPI schema exceeds the 20 MiB safety limit")
    document = json.loads(payload)
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise ValueError("OpenAPI schema must contain a paths object")
    return document


def _require_only_get_path(document: dict[str, Any], path: str) -> None:
    path_item = document["paths"].get(path)
    if not isinstance(path_item, dict):
        raise ValueError(f"OpenAPI schema does not declare {path}")
    declared_methods = {key.lower() for key in path_item if key.lower() in HTTP_METHODS}
    if declared_methods != {"get"}:
        raise ValueError(f"{path} must declare GET only; received {sorted(declared_methods)}")


def _count_method(document: dict[str, Any], method: str) -> int:
    normalized_method = method.lower()
    return sum(
        1
        for path_item in document["paths"].values()
        if isinstance(path_item, dict) and normalized_method in {key.lower() for key in path_item}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--require-only-get-path")
    parser.add_argument("--count-method", choices=sorted(HTTP_METHODS))
    arguments = parser.parse_args()

    document = _load_schema(arguments.schema_url, arguments.timeout_seconds)
    if arguments.require_only_get_path:
        _require_only_get_path(document, arguments.require_only_get_path)
    if arguments.count_method:
        print(f"{arguments.count_method.upper()}_OPERATIONS={_count_method(document, arguments.count_method)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
