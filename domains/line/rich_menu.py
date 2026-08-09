"""Pure LINE Rich Menu publication lifecycle rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import (
    LineConfigurationRevision,
    LineRichMenuPublicationId,
)
from shared_kernel.validation import require_canonical_text

_MENU_DEFINITION_ID_MAXIMUM_LENGTH = 191


class LineRichMenuPublicationStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PUBLISH_RETRYABLE_FAILED = "publish_retryable_failed"
    FAILED = "failed"
    ROLLBACK_QUEUED = "rollback_queued"
    DELETE_QUEUED = "delete_queued"
    ROLLBACK_RETRYABLE_FAILED = "rollback_retryable_failed"
    DELETE_RETRYABLE_FAILED = "delete_retryable_failed"
    ROLLED_BACK = "rolled_back"
    DELETED = "deleted"


_ALLOWED_PUBLICATION_TRANSITIONS = {
    LineRichMenuPublicationStatus.DRAFT: {LineRichMenuPublicationStatus.QUEUED},
    LineRichMenuPublicationStatus.QUEUED: {
        LineRichMenuPublicationStatus.PUBLISHING,
    },
    LineRichMenuPublicationStatus.PUBLISHING: {
        LineRichMenuPublicationStatus.PUBLISHED,
        LineRichMenuPublicationStatus.PUBLISH_RETRYABLE_FAILED,
        LineRichMenuPublicationStatus.FAILED,
    },
    LineRichMenuPublicationStatus.PUBLISH_RETRYABLE_FAILED: {
        LineRichMenuPublicationStatus.QUEUED,
        LineRichMenuPublicationStatus.FAILED,
    },
    LineRichMenuPublicationStatus.PUBLISHED: {
        LineRichMenuPublicationStatus.ROLLBACK_QUEUED,
        LineRichMenuPublicationStatus.DELETE_QUEUED,
    },
    LineRichMenuPublicationStatus.ROLLBACK_QUEUED: {
        LineRichMenuPublicationStatus.ROLLED_BACK,
        LineRichMenuPublicationStatus.ROLLBACK_RETRYABLE_FAILED,
        LineRichMenuPublicationStatus.FAILED,
    },
    LineRichMenuPublicationStatus.ROLLBACK_RETRYABLE_FAILED: {
        LineRichMenuPublicationStatus.ROLLBACK_QUEUED,
        LineRichMenuPublicationStatus.FAILED,
    },
    LineRichMenuPublicationStatus.DELETE_QUEUED: {
        LineRichMenuPublicationStatus.DELETED,
        LineRichMenuPublicationStatus.DELETE_RETRYABLE_FAILED,
        LineRichMenuPublicationStatus.FAILED,
    },
    LineRichMenuPublicationStatus.DELETE_RETRYABLE_FAILED: {
        LineRichMenuPublicationStatus.DELETE_QUEUED,
        LineRichMenuPublicationStatus.FAILED,
    },
}


class LineRichMenuPublicationConflict(ValueError):
    """Raised when a Rich Menu publication transition is invalid."""


@dataclass(frozen=True, slots=True)
class LineRichMenuPublicationSnapshot:
    publication_id: LineRichMenuPublicationId
    menu_definition_id: str
    configuration_revision: LineConfigurationRevision
    status: LineRichMenuPublicationStatus

    def __post_init__(self) -> None:
        require_canonical_text(
            self.menu_definition_id,
            "LINE Rich Menu definition ID",
            _MENU_DEFINITION_ID_MAXIMUM_LENGTH,
        )
        if not isinstance(self.status, LineRichMenuPublicationStatus):
            raise TypeError("LINE Rich Menu publication status is invalid")


def transition_rich_menu_publication(
    current: LineRichMenuPublicationStatus,
    target: LineRichMenuPublicationStatus,
) -> LineRichMenuPublicationStatus:
    if not isinstance(current, LineRichMenuPublicationStatus):
        raise TypeError("current LINE Rich Menu publication status is invalid")
    if target not in _ALLOWED_PUBLICATION_TRANSITIONS.get(current, set()):
        raise LineRichMenuPublicationConflict(
            f"cannot transition Rich Menu from {current.value} to {target.value}"
        )
    return target


__all__ = [
    "LineRichMenuPublicationConflict",
    "LineRichMenuPublicationSnapshot",
    "LineRichMenuPublicationStatus",
    "transition_rich_menu_publication",
]
