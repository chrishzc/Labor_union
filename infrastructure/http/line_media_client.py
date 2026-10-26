"""Bounded NAS photo/day-log transport; no filesystem storage or local fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit

import httpx


SERVICE = "line-media-proxy"
PREFIX = "/internal/v1/line-media"


class LineMediaError(RuntimeError):
    def __init__(self, code="line_media_unavailable", status_code=503, safe_message=None):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.safe_message = safe_message


@dataclass(frozen=True)
class LineMediaPhoto:
    content: bytes
    content_type: str


class LineMediaClient:
    def __init__(self, base_url: str, token_file: str, ca_file: str):
        parsed = urlsplit(base_url)
        parsed.port  # Reject a malformed configured port before transport.
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
                or any(c.isspace() for c in base_url) or not token_file or not ca_file):
            raise LineMediaError("line_media_configuration_unavailable")
        self._base_url = base_url.rstrip("/")
        self._token_file, self._ca_file = Path(token_file), ca_file
        # Bootstrap only from environment; public LINE never reads management's settings file.
        self._timeout_seconds = int(os.getenv("FILE_TRANSFER_TIMEOUT_SECONDS", "60"))
        if self._timeout_seconds < 0:
            raise LineMediaError("line_media_configuration_unavailable")

    @classmethod
    def from_environment(cls):
        # Deliberately do not load .env, a Worker credential, or a development key.
        return cls(*(os.getenv(key, "").strip() for key in (
            "LINE_MEDIA_API_BASE_URL", "LINE_MEDIA_SERVICE_TOKEN_FILE", "LINE_MEDIA_API_CA_FILE")))

    async def upload(self, fields, content: bytes, filename: str, content_type: str, key: str):
        return await self._send("/service-day-media", data=fields,
                                files={"photo": (filename, content, content_type)}, key=key)

    async def settings(self, body):
        result = await self._send("/service-day-media/settings", json=body)
        value = result["data"].get("timeout_seconds")
        if type(value) is not int or value < 0:
            raise LineMediaError("line_media_response_invalid")
        self._timeout_seconds = value
        return result

    async def preview(self, body):
        return await self._send("/service-day-logs/preview", json=body)

    async def apply(self, body, key: str):
        return await self._send("/service-day-logs/apply", json=body, key=key)

    async def options(self, body):
        return await self._send("/service-day-logs/options", json=body)

    async def query(self, log_id: int, body):
        if type(log_id) is not int or log_id < 1:
            raise LineMediaError("service_day_log_not_found", 404)
        return await self._send(f"/service-day-logs/{log_id}/query", json=body)

    async def download(self, log_id: int, file_id: str, body):
        if type(log_id) is not int or log_id < 1 or not re.fullmatch(r"cf_[0-9a-f]{32}", file_id):
            raise LineMediaError("service_day_log_photo_not_found", 404)
        response = await self._request(f"/service-day-logs/{log_id}/photos/{file_id}/download", json=body)
        if response.status_code != 200:
            self._decode(response)
            raise LineMediaError()
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type not in {"image/jpeg", "image/png"}:
            raise LineMediaError()
        return LineMediaPhoto(response.content, content_type)

    async def _send(self, path, *, key=None, **payload):
        return self._decode(await self._request(path, key=key, **payload))

    async def _request(self, path, *, key=None, **payload):
        try:
            token = self._token_file.read_text(encoding="utf-8").strip()
            if len(token) < 32 or any(c.isspace() for c in token):
                raise ValueError("invalid credential")
            context = ssl.create_default_context(cafile=self._ca_file)
        except (OSError, ValueError):
            raise LineMediaError("line_media_configuration_unavailable") from None
        headers = {"Authorization": f"Bearer {token}", "X-Internal-Service-Name": SERVICE}
        if key:
            headers["Idempotency-Key"] = key
        try:
            async with httpx.AsyncClient(verify=context, trust_env=False, follow_redirects=False,
                                         timeout=self._timeout_seconds or None) as client:
                response = await client.post(self._base_url + PREFIX + path, headers=headers, **payload)
        except (httpx.HTTPError, httpx.InvalidURL, ValueError):
            # Never include a token, original request, provider body or URL in the error.
            raise LineMediaError() from None
        return response

    @staticmethod
    def _decode(response):
        try:
            body = response.json()
        except ValueError:
            raise LineMediaError() from None
        if response.status_code >= 400:
            detail = body.get("detail", {}) if isinstance(body, dict) else {}
            error = detail.get("error", detail) if isinstance(detail, dict) else {}
            code = error.get("code", "") if isinstance(error, dict) else ""
            if (response.status_code in {401, 403, 404, 409, 422}
                    and isinstance(code, str)
                    and re.fullmatch(r"(?:service_day_|controlled_file_|liff_|line_flow_)[a-z_]{1,100}", code)):
                # Forward only the trusted service's specific capacity explanation, never arbitrary errors.
                message = error.get("message") if code == "service_day_meal_photo_too_large" else None
                raise LineMediaError(code, response.status_code,
                                     message if isinstance(message, str) and len(message) <= 300 else None)
            raise LineMediaError()
        if (response.status_code != 200 or not isinstance(body, dict)
                or body.get("success") is not True or not isinstance(body.get("data"), dict)):
            raise LineMediaError()
        return body
