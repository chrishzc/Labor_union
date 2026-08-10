"""Typed application contracts for LINE media download and archival."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.media import LineMediaMetadata
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text

_OBJECT_REFERENCE_MAXIMUM_LENGTH = 500


class LineMediaArchiveOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class LineMediaDownload:
    content: bytes
    content_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("LINE media download must contain bytes")
        require_canonical_text(self.content_type, "LINE media content type", 100)


@dataclass(frozen=True, slots=True)
class ArchiveLineMediaCommand:
    metadata: LineMediaMetadata
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ArchiveLineMediaResult:
    outcome: LineMediaArchiveOutcome
    metadata: LineMediaMetadata
    object_reference: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.object_reference,
            "LINE media object reference",
            _OBJECT_REFERENCE_MAXIMUM_LENGTH,
        )


__all__ = [
    "ArchiveLineMediaCommand",
    "ArchiveLineMediaResult",
    "LineMediaArchiveOutcome",
    "LineMediaDownload",
]
