"""
File: runtime_alert_target_contracts.py
Description: 定義 runtime alert target 的 typed command、view、receipt 與錯誤。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_positive_integer


_MAX_REASON = 500
_MAX_TOKEN = 191


class RuntimeAlertTargetError(RuntimeError):
    """可安全映射為 HTTP typed error 的 runtime target 失敗。"""

    def __init__(self, category: str, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class AlertTargetView:
    target_id: int
    target_kind: str
    display_label: str
    state: str
    minimum_status: str
    current_version: str
    updated_at: datetime

    def __post_init__(self) -> None:
        require_positive_integer(self.target_id, "target ID")
        _text(self.target_kind, "target kind", 20)
        _text(self.display_label, "display label", 100)
        _text(self.state, "target state", 20)
        _text(self.minimum_status, "minimum status", 20)
        _text(self.current_version, "current version", _MAX_TOKEN)
        _utc(self.updated_at, "updated_at")
        if self.target_kind not in {"group", "admin_user"}:
            raise ValueError("target kind is invalid")
        if self.state not in {"active", "disabled"}:
            raise ValueError("target state is invalid")
        if self.minimum_status not in {"warning", "critical"}:
            raise ValueError("minimum status is invalid")


@dataclass(frozen=True, slots=True)
class AlertAdminCandidateView:
    candidate_id: int
    display_label: str
    line_linked: bool

    def __post_init__(self) -> None:
        require_positive_integer(self.candidate_id, "candidate ID")
        _text(self.display_label, "display label", 100)
        if not isinstance(self.line_linked, bool):
            raise TypeError("line_linked must be boolean")


@dataclass(frozen=True, slots=True)
class LineAlertTargetMutationReceipt:
    receipt_id: str
    command_family: str
    operation: str
    target_id: int
    previous_state: str
    resulting_state: str
    current_version: str
    replayed: bool
    correlation_id: str
    committed_at: datetime

    def __post_init__(self) -> None:
        for value, name, maximum in (
            (self.receipt_id, "receipt ID", _MAX_TOKEN),
            (self.command_family, "command family", 100),
            (self.operation, "operation", 100),
            (self.previous_state, "previous state", 20),
            (self.resulting_state, "resulting state", 20),
            (self.current_version, "current version", _MAX_TOKEN),
            (self.correlation_id, "correlation ID", _MAX_TOKEN),
        ):
            _text(value, name, maximum)
        require_positive_integer(self.target_id, "target ID")
        _utc(self.committed_at, "committed_at")
        if self.previous_state not in {"active", "disabled"}:
            raise ValueError("previous state is invalid")
        if self.resulting_state not in {"active", "disabled"}:
            raise ValueError("resulting state is invalid")


@dataclass(frozen=True, slots=True)
class LineAlertTargetMutationPreview:
    operation: str
    target_id: int | None
    previous_state: str
    resulting_state: str
    current_version: str
    preview_fingerprint: PreviewFingerprint
    apply_ready: bool

    def __post_init__(self) -> None:
        _text(self.operation, "operation", 100)
        if self.target_id is not None:
            require_positive_integer(self.target_id, "target ID")
        if self.previous_state not in {"absent", "active", "disabled"}:
            raise ValueError("previous state is invalid")
        if self.resulting_state not in {"active", "disabled"}:
            raise ValueError("resulting state is invalid")
        _text(self.current_version, "current version", _MAX_TOKEN)
        if not isinstance(self.apply_ready, bool):
            raise TypeError("apply_ready must be boolean")


@dataclass(frozen=True, slots=True)
class ResetLineAlertGroupCommand:
    expected_version: str
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    actor: ActorContext
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        _text(self.expected_version, "expected version", _MAX_TOKEN)
        _text(self.reason, "reason", _MAX_REASON)


@dataclass(frozen=True, slots=True)
class SetLineAlertTargetEnabledCommand:
    target_id: int
    expected_version: str
    enabled: bool
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    actor: ActorContext
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.target_id, "target ID")
        _text(self.expected_version, "expected version", _MAX_TOKEN)
        _text(self.reason, "reason", _MAX_REASON)
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be boolean")


@dataclass(frozen=True, slots=True)
class AddLineAlertAdminTargetCommand:
    admin_user_id: int
    minimum_status: str
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    actor: ActorContext
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.admin_user_id, "admin user ID")
        _text(self.minimum_status, "minimum status", 20)
        _text(self.reason, "reason", _MAX_REASON)
        if self.minimum_status not in {"warning", "critical"}:
            raise ValueError("minimum status is invalid")


def command_fingerprint(command: object) -> PreviewFingerprint:
    """只把 command identity 放入 fingerprint；不保存 recipient identity。"""
    payload: dict[str, Any] = {
        "command_type": type(command).__name__,
        "reason": command.reason,
        "idempotency_key": command.idempotency_key.value,
        "correlation_id": command.correlation_id.value,
        "actor_id": command.actor.actor_id,
    }
    if isinstance(command, ResetLineAlertGroupCommand):
        payload["expected_version"] = command.expected_version
    elif isinstance(command, SetLineAlertTargetEnabledCommand):
        payload.update(
            target_id=command.target_id,
            expected_version=command.expected_version,
            enabled=command.enabled,
        )
    elif isinstance(command, AddLineAlertAdminTargetCommand):
        payload.update(
            admin_user_id=command.admin_user_id,
            minimum_status=command.minimum_status,
        )
    else:
        raise TypeError("unsupported runtime alert target command")
    return fingerprint_payload(payload)


def _text(value: str, field: str, maximum: int) -> None:
    require_canonical_text(value, field, maximum)


def _utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


__all__ = [
    "AddLineAlertAdminTargetCommand",
    "AlertAdminCandidateView",
    "AlertTargetView",
    "LineAlertTargetMutationReceipt",
    "LineAlertTargetMutationPreview",
    "ResetLineAlertGroupCommand",
    "RuntimeAlertTargetError",
    "SetLineAlertTargetEnabledCommand",
    "command_fingerprint",
]
