"""Response compression with an explicit XLSX archive exclusion."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.middleware.gzip import (
    GZipMiddleware,
    GZipResponder,
)
from starlette.types import Message, Receive, Scope, Send

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


class _ArchiveAwareGZipResponder(GZipResponder):
    async def send_with_compression(self, message: Message) -> None:
        await super().send_with_compression(message)
        if message["type"] != "http.response.start":
            return
        headers = Headers(raw=self.initial_message["headers"])
        content_type = headers.get("content-type", "")
        self.content_type_is_excluded |= content_type.startswith(XLSX_MEDIA_TYPE)


class ResponseCompressionMiddleware(GZipMiddleware):
    """Use Starlette gzip while preserving already-compressed XLSX bytes."""

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        accept_encoding = Headers(scope=scope).get("Accept-Encoding", "")
        if "gzip" not in accept_encoding:
            await self.app(scope, receive, send)
            return
        responder = self._build_responder()
        await responder(scope, receive, send)

    def _build_responder(self) -> GZipResponder:
        return _ArchiveAwareGZipResponder(
            self.app,
            self.minimum_size,
            compresslevel=self.compresslevel,
        )


__all__ = ["ResponseCompressionMiddleware", "XLSX_MEDIA_TYPE"]
