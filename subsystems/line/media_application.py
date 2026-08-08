"""Schedule and execute durable archival of media received from LINE messages."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Callable

from domains.line.identities import LineSourceIdentity, LineSourceType, LineUserId
from domains.line.media import (
    LineMediaCategory,
    LineMediaMetadata,
    LineMediaPolicy,
    validate_media_against_policy,
)
from shared_kernel.identities import IdempotencyKey
from shared_kernel.ports import OutboxIntent
from subsystems.line.media_contracts import LineMediaDownload
from subsystems.line.outbox_contracts import (
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
)
from subsystems.line.ports import (
    LineMediaObjectStorePort,
    LineMediaProviderPort,
    LineUnitOfWorkPort,
)

MEDIA_ARCHIVE_INTENT = "line.media.archive"
_ARCHIVABLE_MESSAGE_TYPES = {"audio", "file", "image", "video"}


def schedule_line_media_archive(inbox, unit_of_work) -> bool:
    payload = json.loads(inbox.event.payload_json)
    message = payload.get("message")
    if not isinstance(message, dict) or message.get("type") not in _ARCHIVABLE_MESSAGE_TYPES:
        return False
    provider_media_id = message.get("id")
    if not isinstance(provider_media_id, str) or not provider_media_id.strip():
        raise ValueError("LINE media message ID is required")
    source = inbox.event.source
    intent_payload = {
        "category": LineMediaCategory.USER_UPLOAD.value,
        "provider_media_id": provider_media_id,
        "received_at": inbox.event.occurred_at.isoformat(),
        "source_identity": source.source_id,
        "source_type": source.source_type.value,
        "source_user_id": source.user_id.value if source.user_id else None,
    }
    unit_of_work.outbox.append(
        OutboxIntent(
            "line_media",
            provider_media_id,
            MEDIA_ARCHIVE_INTENT,
            json.dumps(
                intent_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            f"line-media-archive:{provider_media_id}",
        )
    )
    return True


class LineMediaArchiveWorker:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        provider: LineMediaProviderPort,
        object_store: LineMediaObjectStorePort,
        worker_identity: str,
        now: Callable[[], datetime],
        *,
        policy: LineMediaPolicy,
        batch_size: int = 10,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._provider = provider
        self._object_store = object_store
        self._worker_identity = worker_identity
        self._now = now
        self._policy = policy
        self._batch_size = batch_size

    def run_once(self) -> int:
        items = self._claim()
        for item in items:
            try:
                metadata, content = self._download(item)
                reference = self._object_store.put(metadata, content.content)
                self._record_success(item, metadata, reference)
            except Exception as error:
                self._record_failure(item, error)
        return len(items)

    def _claim(self):
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.outbox.claim(
                ClaimLineOutboxQuery(
                    self._worker_identity,
                    self._now(),
                    self._batch_size,
                )
            )
            unit_of_work.commit()
        return tuple(item for item in result if item.intent_type == MEDIA_ARCHIVE_INTENT)

    def _download(self, item):
        payload = json.loads(item.payload_json)
        provider_media_id = str(payload["provider_media_id"])
        content = self._provider.download(provider_media_id)
        metadata = LineMediaMetadata(
            provider_media_id,
            _source(payload),
            content.content_type,
            len(content.content),
            hashlib.sha256(content.content).hexdigest(),
            datetime.fromisoformat(str(payload["received_at"])),
            LineMediaCategory(str(payload["category"])),
        )
        validate_media_against_policy(metadata, self._policy)
        return metadata, content

    def _record_success(self, item, metadata, reference):
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.media_metadata.register(
                metadata,
                reference,
                IdempotencyKey(f"line-media:{metadata.provider_media_id}"),
            )
            unit_of_work.outbox.complete(
                CompleteLineOutboxCommand(item, self._now())
            )
            unit_of_work.commit()

    def _record_failure(self, item, error):
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.outbox.complete(
                CompleteLineOutboxCommand(
                    item,
                    self._now(),
                    type(error).__name__[:191],
                    str(error)[:1000] or "LINE media archive failed",
                )
            )
            unit_of_work.commit()


def _source(payload) -> LineSourceIdentity:
    source_type = LineSourceType(str(payload["source_type"]))
    raw_user_id = payload.get("source_user_id")
    user_id = LineUserId(str(raw_user_id)) if raw_user_id else None
    return LineSourceIdentity(source_type, str(payload["source_identity"]), user_id)


__all__ = [
    "LineMediaArchiveWorker",
    "MEDIA_ARCHIVE_INTENT",
    "schedule_line_media_archive",
]
