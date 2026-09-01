"""
File: service_day_log_workflow.py
Description: 協調月嫂已驗證身分、服務日所有權、日誌完成、receipt 與 Scheduling outbox。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import re
from typing import Callable, Protocol

from domains.scheduling.service_day_log import ServiceDayLogIntent, require_service_day_log_completion
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.controlled_files.workflow import ControlledFileWorkflowError


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

    controlled_file_object_id: str | None
    staging_id: str
    sha256_digest: str
    attachment_kind: str = "meal_photo"
    sequence: int = 1
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.controlled_file_object_id is not None and re.fullmatch(
            r"cf_[0-9a-f]{32}", self.controlled_file_object_id
        ) is None:
            raise ValueError("controlled file object identity is invalid")
        if re.fullmatch(r"cfs_[0-9a-f]{32}", self.staging_id) is None:
            raise ValueError("controlled file staging identity is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256_digest) is None:
            raise ValueError("controlled file digest is invalid")
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", self.attachment_kind) is None:
            raise ValueError("controlled file attachment kind is invalid")
        if self.attachment_kind not in {"meal_photo", "baby_log_photo"}:
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
    controlled_file_attachments: tuple[ControlledServiceDayLogAttachment, ...] = field(
        default_factory=tuple
    )


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
    def __init__(self, repository: ServiceDayLogRepository, controlled_file_workflow=None) -> None:
        self._repository = repository
        self._controlled_file_workflow = controlled_file_workflow

    def preview(self, command: PreviewServiceDayLog) -> ServiceDayLogPreview:
        assignment = self._repository.load_assignment(
            command.staff_id,
            command.assignment_id,
            command.intent.service_date,
            for_update=False,
        )
        normalized_text = command.intent.baby_log_text.strip()
        _validate_attachment_sequence(command.controlled_file_attachments)
        _validate_controlled_media(
            command,
            assignment,
            controlled_file_workflow=self._controlled_file_workflow,
        )
        blockers = _blockers(
            assignment["requires_cooking"],
            has_meal_photo=_has_meal_photo(command),
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
        _validate_attachment_sequence(command.controlled_file_attachments)
        preview = ServiceDayLogPreview(
            str(assignment["case_no"]),
            command.assignment_id,
            command.intent.service_date.isoformat(),
            command.intent.baby_log_text.strip(),
            assignment["requires_cooking"],
            _preview_fingerprint(command, assignment, command.intent.baby_log_text.strip()),
            _blockers(
                assignment["requires_cooking"],
                has_meal_photo=_has_meal_photo(command),
            ),
        )
        if preview.preview_fingerprint != command.preview_fingerprint:
            raise ServiceDayLogWorkflowError("service_day_log_preview_stale")
        if not preview.can_apply:
            raise ServiceDayLogWorkflowError(preview.blockers[0])
        resolved_command = command
        if command.controlled_file_attachments:
            _require_with_controlled_media(
                requires_cooking=assignment["requires_cooking"],
                attachments=command.controlled_file_attachments,
            )
            resolved_command = self._resolve_controlled_media(command, assignment)
        else:
            require_service_day_log_completion(
                command.intent, requires_cooking=assignment["requires_cooking"]
            )
        return self._repository.submit(resolved_command, assignment)

    def _resolve_controlled_media(self, command: ApplyServiceDayLog, assignment):
        if self._controlled_file_workflow is None:
            if any(item.controlled_file_object_id is None for item in command.controlled_file_attachments):
                raise ServiceDayLogWorkflowError(
                    "service_day_log_controlled_file_workflow_unavailable"
                )
            return command
        attachments = []
        for attachment in command.controlled_file_attachments:
            if attachment.controlled_file_object_id is not None:
                attachments.append(attachment)
                continue
            intent = _controlled_file_intent(command, assignment, attachment)
            try:
                media_preview = self._controlled_file_workflow.preview(intent)
            except ControlledFileWorkflowError as error:
                raise ServiceDayLogWorkflowError(error.code) from error
            if media_preview.blockers:
                raise ServiceDayLogWorkflowError(media_preview.blockers[0])
            from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
            from subsystems.controlled_files.workflow import ApplyControlledFile

            try:
                receipt = self._controlled_file_workflow.apply_borrowed(
                    ApplyControlledFile(
                        intent=intent,
                        expected_staging_version=media_preview.expected_staging_version,
                        preview_fingerprint=media_preview.preview_fingerprint,
                        idempotency_key=IdempotencyKey(
                            f"{command.idempotency_key}:media:{attachment.sequence}"
                        ),
                        actor=ActorContext(f"staff:{command.staff_id}"),
                        correlation_id=CorrelationId(
                            f"scheduling-service-day-log:{command.idempotency_key}"
                        ),
                    )
                )
            except ControlledFileWorkflowError as error:
                raise ServiceDayLogWorkflowError(error.code) from error
            attachments.append(
                replace(
                    attachment,
                    controlled_file_object_id=receipt.readback.file_id,
                    created_at=receipt.readback.applied_at,
                )
            )
        return replace(command, controlled_file_attachments=tuple(attachments))

    def query(self, log_id: int, staff_id: int, line_user_id: str) -> ServiceDayLogResult:
        result = self._repository.load_for_staff(log_id, staff_id, line_user_id)
        if result is None:
            raise ServiceDayLogWorkflowError("service_day_log_not_found")
        return result


class ServiceDayLogApplication:
    def __init__(
        self,
        repository: ServiceDayLogRepository,
        unit_of_work_factory: Callable[[], object],
        controlled_file_workflow=None,
    ) -> None:
        self._workflow = ServiceDayLogWorkflow(repository, controlled_file_workflow)
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


def _blockers(
    requires_cooking: bool | None,
    *,
    has_media: bool = False,
    has_meal_photo: bool | None = None,
) -> tuple[str, ...]:
    # ``has_media`` is retained for callers compiled against the earlier
    # controlled-meal-only helper; new callers distinguish baby photos from
    # meal photos because non-cooking days may still carry baby photos.
    if has_meal_photo is None:
        has_meal_photo = has_media
    if requires_cooking is False and has_meal_photo:
        return ("service_day_log_meal_photo_forbidden",)
    if requires_cooking is True and not has_meal_photo:
        return ("service_day_log_meal_photo_required",)
    if requires_cooking is None:
        return ("service_day_log_cooking_requirement_unresolved",)
    return ()


def _validate_attachment_sequence(attachments) -> None:
    """The released 1015 attachment table has no sequence column.

    Keep the caller fail-closed until an additive schema/release explicitly
    stores ordering; the current lane therefore permits exactly one attachment
    at sequence 1.
    """
    if not attachments:
        return
    if len(attachments) != 1 or attachments[0].sequence != 1:
        raise ServiceDayLogWorkflowError(
            "service_day_log_attachment_sequence_unsupported"
        )


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


def _require_with_controlled_media(
    *, requires_cooking: bool | None, attachments=()
) -> None:
    if requires_cooking is None:
        raise ValueError("cooking requirement is unresolved")
    if requires_cooking is False and any(
        item.attachment_kind == "meal_photo" for item in attachments
    ):
        raise ServiceDayLogWorkflowError("service_day_log_meal_photo_forbidden")
    # The presence of a controlled-file attachment was checked by the caller;
    # this helper intentionally keeps the domain's legacy provider-media rule
    # unchanged while accepting the 1015 typed replacement.


def _controlled_file_intent(command, assignment, attachment):
    from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
    from subsystems.controlled_files.workflow import (
        ControlledFileIntent,
        ControlledFileOwner,
        ControlledFilePurpose,
    )

    object_key = canonical_scheduling_object_key(
        assignment_id=command.assignment_id,
        service_date=command.intent.service_date,
        attachment_kind=attachment.attachment_kind,
        sequence=attachment.sequence,
        sha256_digest=attachment.sha256_digest,
    )
    return ControlledFileIntent(
        staging_id=attachment.staging_id,
        owner=ControlledFileOwner.SCHEDULING,
        purpose=(
            ControlledFilePurpose.MEAL_PHOTO
            if attachment.attachment_kind == "meal_photo"
            else ControlledFilePurpose.BABY_LOG_PHOTO
        ),
        subject_reference=str(assignment["case_no"]),
        object_key=object_key,
        logical_folder=f"scheduling/service-day/{command.assignment_id}/{command.intent.service_date.isoformat()}",
    )


def _validate_controlled_media(command, assignment, *, controlled_file_workflow):
    if not command.controlled_file_attachments:
        return
    if assignment["requires_cooking"] is False and any(
        item.attachment_kind == "meal_photo"
        for item in command.controlled_file_attachments
    ):
        raise ServiceDayLogWorkflowError("service_day_log_meal_photo_forbidden")
    if controlled_file_workflow is None:
        if any(item.controlled_file_object_id is None for item in command.controlled_file_attachments):
            raise ServiceDayLogWorkflowError(
                "service_day_log_controlled_file_workflow_unavailable"
            )
        return
    for attachment in command.controlled_file_attachments:
        if attachment.controlled_file_object_id is not None:
            continue
        intent = _controlled_file_intent(command, assignment, attachment)
        try:
            preview = controlled_file_workflow.preview(intent)
        except ControlledFileWorkflowError as error:
            raise ServiceDayLogWorkflowError(error.code) from error
        if preview.blockers:
            raise ServiceDayLogWorkflowError(preview.blockers[0])


def _has_meal_photo(command: PreviewServiceDayLog | ApplyServiceDayLog) -> bool:
    return bool(
        command.intent.meal_photo_media_ids
        or any(
            item.attachment_kind == "meal_photo"
            for item in command.controlled_file_attachments
        )
    )


__all__ = [
    "ApplyServiceDayLog",
    "ControlledServiceDayLogAttachment",
    "PreviewServiceDayLog",
    "ServiceDayLogPreview",
    "ServiceDayLogResult",
    "ServiceDayLogWorkflow",
    "ServiceDayLogWorkflowError",
]
