"""Strong LINE platform and workflow identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_PLATFORM_IDENTITY_MAXIMUM_LENGTH = 191
_REFERENCE_MAXIMUM_LENGTH = 191


class LineSourceType(StrEnum):
    USER = "user"
    GROUP = "group"
    ROOM = "room"


@dataclass(frozen=True, slots=True)
class LineUserId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "LINE user ID",
            _PLATFORM_IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class LineGroupId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "LINE group ID",
            _PLATFORM_IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class LineRoomId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "LINE room ID",
            _PLATFORM_IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class LineDestinationId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "LINE destination ID",
            _PLATFORM_IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class LineWebhookEventId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "LINE webhook event ID",
            _REFERENCE_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class LineProviderMessageId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "LINE provider message ID",
            _REFERENCE_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class LineDeliveryTaskId:
    value: int

    def __post_init__(self) -> None:
        require_positive_integer(self.value, "LINE delivery task ID")


@dataclass(frozen=True, slots=True)
class LineReviewRequestId:
    value: int

    def __post_init__(self) -> None:
        require_positive_integer(self.value, "LINE review request ID")


@dataclass(frozen=True, slots=True)
class LineRichMenuPublicationId:
    value: int

    def __post_init__(self) -> None:
        require_positive_integer(self.value, "LINE Rich Menu publication ID")


@dataclass(frozen=True, slots=True)
class LineConfigurationRevision:
    value: int

    def __post_init__(self) -> None:
        require_nonnegative_integer(self.value, "LINE configuration revision")


@dataclass(frozen=True, slots=True)
class LineSourceIdentity:
    source_type: LineSourceType
    source_id: str
    user_id: LineUserId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, LineSourceType):
            raise TypeError("LINE source type is invalid")
        require_canonical_text(
            self.source_id,
            "LINE source ID",
            _PLATFORM_IDENTITY_MAXIMUM_LENGTH,
        )
        if self.user_id is not None and not isinstance(self.user_id, LineUserId):
            raise TypeError("LINE source user ID is invalid")
        self._validate_user_source()

    def _validate_user_source(self) -> None:
        if self.source_type is LineSourceType.USER:
            if self.user_id is None or self.source_id != self.user_id.value:
                raise ValueError("LINE user source must contain the same user ID")


__all__ = [
    "LineConfigurationRevision",
    "LineDeliveryTaskId",
    "LineDestinationId",
    "LineGroupId",
    "LineProviderMessageId",
    "LineReviewRequestId",
    "LineRichMenuPublicationId",
    "LineRoomId",
    "LineSourceIdentity",
    "LineSourceType",
    "LineUserId",
    "LineWebhookEventId",
]
