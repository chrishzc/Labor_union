"""
File: service_day_log_workflow.py
Description: 協調月嫂已驗證身分、服務日所有權、日誌完成、receipt 與 Scheduling outbox。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Callable, Protocol

from domains.scheduling.service_day_log import ServiceDayLogIntent, require_service_day_log_completion
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


@dataclass(frozen=True, slots=True)
class PreviewServiceDayLog:
    staff_id: int
    line_user_id: str
    assignment_id: int
    intent: ServiceDayLogIntent
    controlled_file_attachments: tuple["ControlledServiceDayLogAttachment", ...] = field(
        default_factory=tuple, kw_only=True
    )


@dataclass(frozen=True, slots=True)
class ControlledServiceDayLogAttachment:
    """Validated reference facts for the 1015 Scheduling bridge.

    The object and staging identities are produced by the controlled-file
    staging flow.  Scheduling only carries these opaque facts into its own
    outer transaction; it never performs a storage-provider operation.
    """

    controlled_file_object_id: str
    staging_id: str
    sha256_digest: str
    attachment_kind: str = "meal_photo"
    sequence: int = 1
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"cf_[0-9a-f]{32}", self.controlled_file_object_id) is None:
            raise ValueError("controlled file object identity is invalid")
        if re.fullmatch(r"cfs_[0-9a-f]{32}", self.staging_id) is None:
            raise ValueError("controlled file staging identity is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256_digest) is None:
            raise ValueError("controlled file digest is invalid")
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", self.attachment_kind) is None:
            raise ValueError("controlled file attachment kind is invalid")
        if self.attachment_kind != "meal_photo":
            raise ValueError("controlled file attachment kind is not supported")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("controlled file attachment sequence is invalid")
        if self.created_at is not None and (
            self.created_at.tzinfo is None or self.created_at.utcoffset() is None
        ):
            raise ValueError("controlled file attachment created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ApplyServiceDayLog(PreviewServiceDayLog):
    idempotency_key: str
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ServiceDayLogResult:
    log_id: int
    case_no: str
    assignment_id: int
    service_date: str
    baby_log_text: str
    requires_cooking: bool
    outcome: str


@dataclass(frozen=True, slots=True)
class ServiceDayLogPreview:
    case_no: str
    assignment_id: int
    service_date: str
    baby_log_text: str
    requires_cooking: bool | None
    preview_fingerprint: PreviewFingerprint
    blockers: tuple[str, ...]

    @property
    def can_apply(self) -> bool:
        return not self.blockers


class ServiceDayLogRepository(Protocol):
    def load_assignment(
        self, staff_id: int, assignment_id: int, service_date, *, for_update: bool
    ): ...
    def submit(self, command: ApplyServiceDayLog, assignment) -> ServiceDayLogResult: ...
    def load_replay(self, command: ApplyServiceDayLog) -> ServiceDayLogResult | None: ...
    def load_for_staff(
        self, log_id: int, staff_id: int, line_user_id: str
    ) -> ServiceDayLogResult | None: ...


class ServiceDayLogWorkflowError(ValueError):
    pass


class ServiceDayLogWorkflow:
    def __init__(self, repository: ServiceDayLogRepository) -> None:
        self._repository = repository

    def preview(self, command: PreviewServiceDayLog) -> ServiceDayLogPreview:
        assignment = self._repository.load_assignment(
            command.staff_id,
            command.assignment_id,
            command.intent.service_date,
            for_update=False,
        )
        normalized_text = command.intent.baby_log_text.strip()
        blockers = _blockers(
            assignment["requires_cooking"],
            has_media=bool(
                command.intent.meal_photo_media_ids
                or command.controlled_file_attachments
            ),
        )
        fingerprint = _preview_fingerprint(command, assignment, normalized_text)
        return ServiceDayLogPreview(
            str(assignment["case_no"]),
            command.assignment_id,
            command.intent.service_date.isoformat(),
            normalized_text,
            assignment["requires_cooking"],
            fingerprint,
            blockers,
        )

    def apply(self, command: ApplyServiceDayLog) -> ServiceDayLogResult:
        replay = self._repository.load_replay(command)
        if replay is not None:
            return replay
        assignment = self._repository.load_assignment(
            command.staff_id,
            command.assignment_id,
            command.intent.service_date,
            for_update=True,
        )
        preview = ServiceDayLogPreview(
            str(assignment["case_no"]),
            command.assignment_id,
            command.intent.service_date.isoformat(),
            command.intent.baby_log_text.strip(),
            assignment["requires_cooking"],
            _preview_fingerprint(command, assignment, command.intent.baby_log_text.strip()),
            _blockers(
                assignment["requires_cooking"],
                has_media=bool(
                    command.intent.meal_photo_media_ids
                    or command.controlled_file_attachments
                ),
            ),
        )
        if preview.preview_fingerprint != command.preview_fingerprint:
            raise ServiceDayLogWorkflowError("service_day_log_preview_stale")
        if not preview.can_apply:
            raise ServiceDayLogWorkflowError(preview.blockers[0])
        if command.controlled_file_attachments:
            _require_with_controlled_media(
                requires_cooking=assignment["requires_cooking"]
            )
        else:
            require_service_day_log_completion(
                command.intent, requires_cooking=assignment["requires_cooking"]
            )
        return self._repository.submit(command, assignment)

    def query(self, log_id: int, staff_id: int, line_user_id: str) -> ServiceDayLogResult:
        result = self._repository.load_for_staff(log_id, staff_id, line_user_id)
        if result is None:
            raise ServiceDayLogWorkflowError("service_day_log_not_found")
        return result


class ServiceDayLogApplication:
    def __init__(self, repository: ServiceDayLogRepository, unit_of_work_factory: Callable[[], object]) -> None:
        self._workflow = ServiceDayLogWorkflow(repository)
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, command: PreviewServiceDayLog) -> ServiceDayLogPreview:
        return self._workflow.preview(command)

    def apply(self, command: ApplyServiceDayLog) -> ServiceDayLogResult:
        with self._unit_of_work_factory() as unit_of_work:
            result = self._workflow.apply(command)
            unit_of_work.commit()
            return result

    def query(self, log_id: int, staff_id: int, line_user_id: str) -> ServiceDayLogResult:
        return self._workflow.query(log_id, staff_id, line_user_id)


def _blockers(requires_cooking: bool | None, *, has_media: bool = False) -> tuple[str, ...]:
    if requires_cooking is True and not has_media:
        return ("service_day_log_meal_photo_required",)
    if requires_cooking is None:
        return ("service_day_log_cooking_requirement_unresolved",)
    return ()


def _preview_fingerprint(command, assignment, normalized_text: str) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "family": "scheduling-service-day-log-text",
            "staff_id": command.staff_id,
            "line_user_id": command.line_user_id,
            "assignment_id": command.assignment_id,
            "case_no": str(assignment["case_no"]),
            "service_date": command.intent.service_date.isoformat(),
            "baby_log_text": normalized_text,
            "requires_cooking": assignment["requires_cooking"],
            "meal_photo_media_ids": command.intent.meal_photo_media_ids,
            "controlled_file_attachments": tuple(
                {
                    "controlled_file_object_id": item.controlled_file_object_id,
                    "staging_id": item.staging_id,
                    "sha256_digest": item.sha256_digest,
                    "attachment_kind": item.attachment_kind,
                    "sequence": item.sequence,
                }
                for item in command.controlled_file_attachments
            ),
        }
    )


def _require_with_controlled_media(*, requires_cooking: bool | None) -> None:
    if requires_cooking is None:
        raise ValueError("cooking requirement is unresolved")
    # The presence of a controlled-file attachment was checked by the caller;
    # this helper intentionally keeps the domain's legacy provider-media rule
    # unchanged while accepting the 1015 typed replacement.


__all__ = [
    "ApplyServiceDayLog",
    "ControlledServiceDayLogAttachment",
    "PreviewServiceDayLog",
    "ServiceDayLogPreview",
    "ServiceDayLogResult",
    "ServiceDayLogWorkflow",
    "ServiceDayLogWorkflowError",
]
