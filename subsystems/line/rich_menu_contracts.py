"""Typed application contracts for LINE Rich Menu publication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import (
    LineConfigurationRevision,
    LineRichMenuPublicationId,
)
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_positive_integer
from domains.line.canonical_payload import validate_canonical_line_payload_json

_MENU_DEFINITION_ID_MAXIMUM_LENGTH = 191
_PROVIDER_MENU_ID_MAXIMUM_LENGTH = 191


class LineRichMenuCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


class LineRichMenuProviderOutcomeType(StrEnum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class PreviewLineRichMenuCommand:
    menu_definition_id: str
    configuration_revision: LineConfigurationRevision
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_menu_definition_id(self.menu_definition_id)


@dataclass(frozen=True, slots=True)
class QueueLineRichMenuPublicationCommand:
    menu_definition_id: str
    configuration_revision: LineConfigurationRevision
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_menu_definition_id(self.menu_definition_id)


@dataclass(frozen=True, slots=True)
class QueueLineRichMenuRollbackCommand:
    publication_id: LineRichMenuPublicationId
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class QueueLineRichMenuDeleteCommand:
    publication_id: LineRichMenuPublicationId
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class QueueLineRichMenuPublicationResult:
    outcome: LineRichMenuCommandOutcome
    publication: LineRichMenuPublicationSnapshot


@dataclass(frozen=True, slots=True)
class LineRichMenuProviderOutcome:
    outcome_type: LineRichMenuProviderOutcomeType
    provider_menu_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome_type, LineRichMenuProviderOutcomeType):
            raise TypeError("LINE Rich Menu provider outcome type is invalid")
        if self.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
            require_canonical_text(
                self.provider_menu_id,
                "LINE provider Rich Menu ID",
                _PROVIDER_MENU_ID_MAXIMUM_LENGTH,
            )
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("successful Rich Menu operation cannot contain an error")
            return
        if self.provider_menu_id is not None:
            raise ValueError("failed Rich Menu operation cannot contain provider menu ID")
        require_canonical_text(self.error_code, "LINE Rich Menu error code", 191)
        require_canonical_text(self.error_message, "LINE Rich Menu error message", 500)


@dataclass(frozen=True, slots=True)
class LineRichMenuProviderRequest:
    publication_id: LineRichMenuPublicationId
    definition_json: str
    image_object_reference: str

    def __post_init__(self) -> None:
        validate_canonical_line_payload_json(self.definition_json)
        require_canonical_text(
            self.image_object_reference,
            "LINE Rich Menu image object reference",
            500,
        )


@dataclass(frozen=True, slots=True)
class LineRichMenuPublicationQuery:
    statuses: tuple[LineRichMenuPublicationStatus, ...] = ()
    page_size: int = 25

    def __post_init__(self) -> None:
        if not isinstance(self.statuses, tuple):
            raise TypeError("LINE Rich Menu statuses must be a tuple")
        if any(not isinstance(item, LineRichMenuPublicationStatus) for item in self.statuses):
            raise TypeError("LINE Rich Menu statuses contain an invalid value")
        values = tuple(item.value for item in self.statuses)
        if values != tuple(sorted(set(values))):
            raise ValueError("LINE Rich Menu statuses must be sorted and unique")
        require_positive_integer(self.page_size, "LINE Rich Menu page size")
        if self.page_size > 100:
            raise ValueError("LINE Rich Menu page size must be between 1 and 100")


def _validate_menu_definition_id(value: str) -> None:
    require_canonical_text(
        value,
        "LINE Rich Menu definition ID",
        _MENU_DEFINITION_ID_MAXIMUM_LENGTH,
    )


__all__ = [
    "LineRichMenuCommandOutcome",
    "LineRichMenuProviderOutcome",
    "LineRichMenuProviderOutcomeType",
    "LineRichMenuProviderRequest",
    "LineRichMenuPublicationQuery",
    "PreviewLineRichMenuCommand",
    "QueueLineRichMenuDeleteCommand",
    "QueueLineRichMenuPublicationCommand",
    "QueueLineRichMenuPublicationResult",
    "QueueLineRichMenuRollbackCommand",
]
