"""NAS LINE JSON transport to the existing, identity-verified management owners."""
from __future__ import annotations

import os
from pathlib import Path
import ssl
from urllib.parse import quote, urlsplit

import httpx

from infrastructure.runtime.worker_credentials import LINE_OPERATIONS_SERVICE


PREFIX = "/internal/v1/line-operations"


class LineOperationsUnavailable(RuntimeError):
    """Safe transport failure without request contents, addresses or credentials."""


class LineOperationsClient:
    def __init__(self, base_url: str, token_file: str, ca_file: str):
        parsed = urlsplit(base_url)
        parsed.port
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or any(char.isspace() for char in base_url) or not token_file or not ca_file):
            raise LineOperationsUnavailable()
        self._base_url = base_url.rstrip("/")
        self._token_file = Path(token_file)
        self._ca_file = ca_file
        self._timeout = int(os.getenv("FILE_TRANSFER_TIMEOUT_SECONDS", "60"))
        if self._timeout < 0:
            raise LineOperationsUnavailable()

    @classmethod
    def from_environment(cls):
        return cls(*(os.getenv(key, "").strip() for key in (
            "LINE_OPERATIONS_API_BASE_URL", "LINE_OPERATIONS_SERVICE_TOKEN_FILE", "LINE_OPERATIONS_API_CA_FILE")))

    async def request(self, method: str, path: str, *, content: bytes, headers, params):
        # The NAS route composition selects the exact existing operation. Reject
        # path normalization that could escape this private service prefix.
        if (method not in {"GET", "POST"} or not path.startswith("/api/v1/line/")
                or any(part in {".", ".."} for part in path.split("/"))):
            raise LineOperationsUnavailable()
        try:
            token = self._token_file.read_text(encoding="utf-8").strip()
            if len(token) < 32 or any(char.isspace() for char in token):
                raise ValueError("invalid credential")
            context = ssl.create_default_context(cafile=self._ca_file)
            forwarded = {key: value for key, value in headers.items()
                         if key.lower() in {"content-type", "idempotency-key", "x-correlation-id"}}
            forwarded.update({"Authorization": f"Bearer {token}",
                              "X-Internal-Service-Name": LINE_OPERATIONS_SERVICE})
            async with httpx.AsyncClient(verify=context, trust_env=False, follow_redirects=False,
                                         timeout=self._timeout or None) as client:
                return await client.request(method, self._base_url + PREFIX + quote(path, safe="/"),
                                            content=content, headers=forwarded, params=params)
        except (OSError, ValueError, httpx.HTTPError, httpx.InvalidURL):
            raise LineOperationsUnavailable() from None
