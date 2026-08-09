"""LINE media download and configured filesystem/NAS object-store adapters."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from domains.line.media import LineMediaMetadata
from subsystems.line.media_contracts import LineMediaDownload

_CONTENT_ENDPOINT = "https://api-data.line.me/v2/bot/message/{media_id}/content"


class LineMediaApiAdapter:
    def __init__(
        self,
        channel_access_token: str,
        *,
        session: Any | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        normalized = channel_access_token.strip()
        if not normalized:
            raise ValueError("LINE channel access token is required")
        self._access_token = normalized
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds

    def download(self, provider_media_id: str) -> LineMediaDownload:
        response = self._session.get(
            _CONTENT_ENDPOINT.format(media_id=provider_media_id),
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0]
        return LineMediaDownload(bytes(response.content), content_type.lower())


class FileSystemLineMediaObjectStore:
    def __init__(self, storage_root: str | Path) -> None:
        self._storage_root = Path(storage_root).resolve()
        self._storage_root.mkdir(parents=True, exist_ok=True)

    def put(self, metadata: LineMediaMetadata, content: bytes) -> str:
        if hashlib.sha256(content).hexdigest() != metadata.content_sha256:
            raise ValueError("LINE media content hash does not match metadata")
        if len(content) != metadata.size_bytes:
            raise ValueError("LINE media content size does not match metadata")
        relative_path = _relative_media_path(metadata)
        target = (self._storage_root / relative_path).resolve()
        if self._storage_root not in target.parents:
            raise ValueError("LINE media storage path escaped configured root")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != metadata.content_sha256:
                raise RuntimeError("LINE media object reference collision")
            return relative_path.as_posix()
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return relative_path.as_posix()


def _relative_media_path(metadata: LineMediaMetadata) -> Path:
    digest = metadata.content_sha256
    extension = _CONTENT_TYPE_EXTENSIONS.get(metadata.content_type, ".bin")
    return Path(metadata.category.value) / digest[:2] / f"{digest}{extension}"


_CONTENT_TYPE_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


__all__ = ["FileSystemLineMediaObjectStore", "LineMediaApiAdapter"]
