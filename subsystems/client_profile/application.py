"""Client-owned profile change Query/Preview/Apply application."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from domains.clients.profile import (
    ClientProfileValidationError,
    requested_before_values,
    validate_changes,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from .contracts import (
    ClientProfileApprovalReceipt,
    ClientProfileApplicantReceipt,
    ClientProfileBindingError,
    ClientBindingPort,
    ClientProfileNotFoundError,
    ClientProfilePreview,
    ClientProfileRequestConflictError,
    ClientProfileRequestView,
    ClientProfileStaleError,
    ClientProfileView,
)


class ClientProfileRepository(Protocol):
    def load_profile(self, client_id: int, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def load_request(self, request_id: int, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def list_requests(self, *, status: str | None, page: int, page_size: int) -> tuple[tuple[Mapping[str, Any], ...], int]: ...
    def find_receipt(self, key: str, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def create_request(self, *, line_user_id: str, client_id: int, expected_version: int, before: Mapping[str, str], requested: Mapping[str, str], reason: str, idempotency_key: str, correlation_id: str, preview_fingerprint: str, command_fingerprint: str) -> Mapping[str, Any]: ...
    def approve_request(self, *, request_id: int, expected_request_version: int, client_id: int, expected_profile_version: int, before: Mapping[str, str], requested: Mapping[str, str], actor_id: str, reason: str, idempotency_key: str, correlation_id: str, preview_fingerprint: str, command_fingerprint: str) -> Mapping[str, Any]: ...
    def reject_request(self, *, request_id: int, expected_request_version: int, reason: str, actor_id: str, idempotency_key: str, correlation_id: str, preview_fingerprint: str, command_fingerprint: str) -> Mapping[str, Any]: ...
    def save_receipt(self, *, idempotency_key: str, command_fingerprint: str, preview_fingerprint: str, result: Mapping[str, Any]) -> None: ...


class ClientProfileUnitOfWork(Protocol):
    client_profiles: ClientProfileRepository
    binding: ClientBindingPort

    def __enter__(self): ...
    def __exit__(self, exception_type, exception, traceback): ...
    def commit(self) -> None: ...


class ClientProfileApplication:
    def __init__(self, unit_of_work_factory: Callable[[], ClientProfileUnitOfWork], *, city_allowlist=()) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._city_allowlist = frozenset(city_allowlist)

    def query_applicant(self, applicant_identity: str, client_id: int) -> ClientProfileView:
        with self._unit_of_work_factory() as unit_of_work:
            _read_binding(unit_of_work, applicant_identity, client_id)
            profile = _require_profile(unit_of_work.client_profiles.load_profile(client_id))
        return _profile_view(profile)

    def preview_applicant(
        self,
        applicant_identity: str,
        client_id: int,
        changes: Mapping[str, object],
        expected_version: ExpectedVersion,
    ) -> ClientProfilePreview:
        normalized = validate_changes(changes, city_allowlist=self._city_allowlist)
        with self._unit_of_work_factory() as unit_of_work:
            _read_binding(unit_of_work, applicant_identity, client_id)
            profile = _require_profile(unit_of_work.client_profiles.load_profile(client_id))
        return _preview(profile, normalized, expected_version)

    def apply_applicant(
        self,
        applicant_identity: str,
        client_id: int,
        changes: Mapping[str, object],
        expected_version: ExpectedVersion,
        reason: str,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> ClientProfileApplicantReceipt:
        normalized = validate_changes(changes, city_allowlist=self._city_allowlist)
        command_fingerprint = _command_fingerprint(
            "client_profile_change/v1", applicant_identity, normalized, expected_version,
            reason, preview_fingerprint,
        )
        with self._unit_of_work_factory() as unit_of_work:
            _read_binding(unit_of_work, applicant_identity, client_id, lock=True)
            replay = unit_of_work.client_profiles.find_receipt(idempotency_key.value, for_update=True)
            if replay is not None:
                _require_replay(replay, command_fingerprint)
                profile = _require_profile(unit_of_work.client_profiles.load_profile(client_id))
                result = replay.get("result", replay)
                request_id = result.get("request_id")
                request = _require_request(
                    unit_of_work.client_profiles.load_request(int(request_id))
                    if request_id is not None else None
                )
                unit_of_work.commit()
                return ClientProfileApplicantReceipt(
                    request,
                    PreviewFingerprint(str(replay["preview_fingerprint"])),
                    str(replay.get("idempotency_key", idempotency_key.value)),
                    True,
                    _profile_view(profile),
                )
            profile = _require_profile(unit_of_work.client_profiles.load_profile(client_id, for_update=True))
            preview = _preview(profile, normalized, expected_version)
            _require_preview(preview.preview_fingerprint, preview_fingerprint)
            result = unit_of_work.client_profiles.create_request(
                line_user_id=applicant_identity,
                client_id=client_id,
                expected_version=expected_version.value,
                before=preview.before,
                requested=preview.requested,
                reason=reason.strip(),
                idempotency_key=idempotency_key.value,
                correlation_id=correlation_id.value,
                preview_fingerprint=preview_fingerprint.value,
                command_fingerprint=command_fingerprint.value,
            )
            request = _require_request(result)
            unit_of_work.client_profiles.save_receipt(
                idempotency_key=idempotency_key.value,
                command_fingerprint=command_fingerprint.value,
                preview_fingerprint=preview_fingerprint.value,
                result={"request_id": request.request_id},
            )
            unit_of_work.commit()
        return ClientProfileApplicantReceipt(request, preview_fingerprint, idempotency_key.value, False, _profile_view(profile))

    def list_requests(self, *, status: str | None, page: int, page_size: int) -> tuple[tuple[ClientProfileRequestView, ...], int]:
        with self._unit_of_work_factory() as unit_of_work:
            rows, total = unit_of_work.client_profiles.list_requests(status=status, page=page, page_size=page_size)
        return tuple(_require_request(row) for row in rows), total

    def query_request(self, request_id: int) -> ClientProfileRequestView:
        with self._unit_of_work_factory() as unit_of_work:
            row = unit_of_work.client_profiles.load_request(request_id)
        return _require_request(row)

    def preview_approval(self, request_id: int, expected_request_version: ExpectedVersion) -> ClientProfilePreview:
        with self._unit_of_work_factory() as unit_of_work:
            request = _require_request(unit_of_work.client_profiles.load_request(request_id))
            if request.status != "pending":
                raise ClientProfileRequestConflictError("profile_request_not_pending")
            if request.request_version != expected_request_version.value:
                raise ClientProfileStaleError("profile_request_version_stale")
            _read_binding(unit_of_work, request.line_user_id, request.client_id)
            profile = _require_profile(unit_of_work.client_profiles.load_profile(request.client_id))
        return _approval_preview(request, profile)

    def apply_approval(
        self,
        request_id: int,
        actor: ActorContext,
        reason: str,
        expected_request_version: ExpectedVersion,
        expected_profile_version: ExpectedVersion,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> ClientProfileApprovalReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            request = _require_request(unit_of_work.client_profiles.load_request(request_id, for_update=True))
            profile = _require_profile(unit_of_work.client_profiles.load_profile(request.client_id, for_update=True))
            _read_binding(unit_of_work, request.line_user_id, request.client_id, lock=True)
            replay = unit_of_work.client_profiles.find_receipt(idempotency_key.value, for_update=True)
            if replay is not None:
                _require_replay(replay, _approval_command_fingerprint(request_id, actor, reason, expected_request_version, expected_profile_version, preview_fingerprint))
                unit_of_work.commit()
                return ClientProfileApprovalReceipt(request, preview_fingerprint, idempotency_key.value, True, _profile_view(profile))
            if request.status != "pending":
                raise ClientProfileRequestConflictError("profile_request_not_pending")
            if request.request_version != expected_request_version.value:
                raise ClientProfileStaleError("profile_request_version_stale")
            if profile.version != expected_profile_version.value:
                raise ClientProfileStaleError("client_profile_version_stale")
            preview = _approval_preview(request, profile)
            _require_preview(preview.preview_fingerprint, preview_fingerprint)
            command_fingerprint = _approval_command_fingerprint(request_id, actor, reason, expected_request_version, expected_profile_version, preview_fingerprint)
            result = unit_of_work.client_profiles.approve_request(
                request_id=request_id,
                expected_request_version=expected_request_version.value,
                client_id=request.client_id,
                expected_profile_version=expected_profile_version.value,
                before=preview.before,
                requested=preview.requested,
                actor_id=actor.actor_id,
                reason=reason.strip(),
                idempotency_key=idempotency_key.value,
                correlation_id=correlation_id.value,
                preview_fingerprint=preview_fingerprint.value,
                command_fingerprint=command_fingerprint.value,
            )
            approved = _require_request(result)
            unit_of_work.client_profiles.save_receipt(
                idempotency_key=idempotency_key.value,
                command_fingerprint=command_fingerprint.value,
                preview_fingerprint=preview_fingerprint.value,
                result={"request_id": approved.request_id, "client_id": approved.client_id},
            )
            fresh = _require_profile(unit_of_work.client_profiles.load_profile(request.client_id))
            unit_of_work.commit()
        return ClientProfileApprovalReceipt(approved, preview_fingerprint, idempotency_key.value, False, _profile_view(fresh))

    def reject_request(
        self, request_id: int, actor: ActorContext, reason: str,
        expected_request_version: ExpectedVersion, preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey, correlation_id: CorrelationId,
    ) -> ClientProfileRequestView:
        command_fingerprint = _rejection_command_fingerprint(request_id, actor, reason, expected_request_version, preview_fingerprint)
        with self._unit_of_work_factory() as unit_of_work:
            request = _require_request(unit_of_work.client_profiles.load_request(request_id, for_update=True))
            profile = _require_profile(unit_of_work.client_profiles.load_profile(request.client_id, for_update=True))
            _read_binding(unit_of_work, request.line_user_id, request.client_id, lock=True)
            replay = unit_of_work.client_profiles.find_receipt(idempotency_key.value, for_update=True)
            if replay is not None:
                _require_replay(replay, command_fingerprint)
                result = replay.get("result", replay)
                replay_request = _require_request(
                    unit_of_work.client_profiles.load_request(int(result["request_id"]))
                )
                unit_of_work.commit()
                return replay_request
            if request.request_version != expected_request_version.value:
                raise ClientProfileStaleError("profile_request_version_stale")
            if request.status != "pending":
                raise ClientProfileRequestConflictError("profile_request_not_pending")
            preview = _rejection_preview(request, profile, reason)
            _require_preview(preview.preview_fingerprint, preview_fingerprint)
            result = unit_of_work.client_profiles.reject_request(
                request_id=request_id, expected_request_version=expected_request_version.value,
                reason=reason.strip(), actor_id=actor.actor_id, idempotency_key=idempotency_key.value,
                correlation_id=correlation_id.value, preview_fingerprint=preview_fingerprint.value,
                command_fingerprint=command_fingerprint.value,
            )
            rejected = _require_request(result)
            unit_of_work.client_profiles.save_receipt(
                idempotency_key=idempotency_key.value, command_fingerprint=command_fingerprint.value,
                preview_fingerprint=preview_fingerprint.value, result={"request_id": rejected.request_id},
            )
            unit_of_work.commit()
        return rejected

    def preview_rejection(
        self, request_id: int, expected_request_version: ExpectedVersion, reason: str,
    ) -> ClientProfilePreview:
        with self._unit_of_work_factory() as unit_of_work:
            request = _require_request(unit_of_work.client_profiles.load_request(request_id))
            if request.request_version != expected_request_version.value:
                raise ClientProfileStaleError("profile_request_version_stale")
            if request.status != "pending":
                raise ClientProfileRequestConflictError("profile_request_not_pending")
            _read_binding(unit_of_work, request.line_user_id, request.client_id)
            profile = _require_profile(unit_of_work.client_profiles.load_profile(request.client_id))
        return _rejection_preview(request, profile, reason)


def _require_profile(row: Mapping[str, Any] | None) -> ClientProfileView:
    if not row:
        raise ClientProfileNotFoundError("client_profile_not_found")
    values = {field: str(row.get(field) or "") for field in (
        "name", "gender", "phone", "city", "address", "residence_type", "delivery_type", "baby_info", "notes",
    )}
    return ClientProfileView(int(row["client_id"] if "client_id" in row else row["id"]), int(row.get("client_profile_version", row.get("version", 0))), values)


def _require_request(row: Mapping[str, Any] | None) -> ClientProfileRequestView:
    if not row:
        raise ClientProfileNotFoundError("client_profile_request_not_found")
    return ClientProfileRequestView(
        request_id=int(row.get("request_id", row.get("id"))), client_id=int(row["client_id"]),
        line_user_id=str(row.get("line_user_id", "")), status=str(row["status"]),
        request_version=int(row.get("request_version", row.get("version", 0))),
        profile_version=int(row.get("profile_version", row.get("client_profile_version", 0))),
        before=dict(row.get("before", row.get("old_values", {}))),
        requested=dict(row.get("requested", row.get("requested_changes", {}))), reason=str(row.get("reason", "")),
        created_at=row.get("created_at"), reviewed_at=row.get("reviewed_at"),
    )


def _profile_view(profile: ClientProfileView) -> ClientProfileView:
    return profile


def _read_binding(
    unit_of_work: ClientProfileUnitOfWork,
    applicant_identity: str,
    client_id: int,
    *,
    lock: bool = False,
) -> None:
    evidence = unit_of_work.binding.read_current(
        applicant_identity, client_id=client_id, lock=lock,
    )
    if not evidence.complete or evidence.client_id != client_id:
        raise ClientProfileBindingError("client_binding_evidence_incomplete")
    if {"customer", "staff"}.issubset(evidence.roles) and not evidence.legal_customer_staff_dual_role:
        raise ClientProfileBindingError("client_binding_dual_role_not_legal")


def _preview(profile: ClientProfileView, changes: Mapping[str, str], expected_version: ExpectedVersion) -> ClientProfilePreview:
    if profile.version != expected_version.value:
        raise ClientProfileStaleError("client_profile_version_stale")
    before = requested_before_values(profile.values, changes)
    fingerprint = fingerprint_payload({"client_id": profile.client_id, "version": profile.version, "before": before, "requested": dict(changes)})
    return ClientProfilePreview(profile.client_id, profile.version, before, dict(changes), fingerprint)


def _approval_preview(request: ClientProfileRequestView, profile: ClientProfileView) -> ClientProfilePreview:
    before = requested_before_values(profile.values, request.requested)
    if before != dict(request.before):
        raise ClientProfileStaleError("client_profile_requested_field_stale")
    fingerprint = fingerprint_payload({"request_id": request.request_id, "request_version": request.request_version, "client_id": profile.client_id, "version": profile.version, "before": before, "requested": dict(request.requested)})
    return ClientProfilePreview(profile.client_id, profile.version, before, dict(request.requested), fingerprint)


def _rejection_preview(
    request: ClientProfileRequestView,
    profile: ClientProfileView,
    reason: str,
) -> ClientProfilePreview:
    before = requested_before_values(profile.values, request.requested)
    if before != dict(request.before):
        raise ClientProfileStaleError("client_profile_requested_field_stale")
    fingerprint = fingerprint_payload({
        "operation": "client_profile_rejection/v1",
        "request_id": request.request_id,
        "request_version": request.request_version,
        "client_id": profile.client_id,
        "version": profile.version,
        "before": before,
        "requested": dict(request.requested),
        "reason": reason.strip(),
    })
    return ClientProfilePreview(profile.client_id, profile.version, before, dict(request.requested), fingerprint)


def _require_preview(actual: PreviewFingerprint, supplied: PreviewFingerprint) -> None:
    if actual != supplied:
        raise ClientProfileRequestConflictError("profile_preview_fingerprint_mismatch")


def _command_fingerprint(family, identity, payload, expected_version, reason, preview):
    return fingerprint_payload({"family": family, "identity": identity, "payload": dict(payload), "expected_version": expected_version.value, "reason": reason.strip(), "preview_fingerprint": preview.value})


def _approval_command_fingerprint(request_id, actor, reason, request_version, profile_version, preview):
    return fingerprint_payload({"family": "client_profile_approval/v1", "request_id": request_id, "actor": actor.actor_id, "reason": reason.strip(), "request_version": request_version.value, "profile_version": profile_version.value, "preview_fingerprint": preview.value})


def _rejection_command_fingerprint(request_id, actor, reason, request_version, preview):
    return fingerprint_payload({"family": "client_profile_rejection/v1", "request_id": request_id, "actor": actor.actor_id, "reason": reason.strip(), "request_version": request_version.value, "preview_fingerprint": preview.value})


def _require_replay(receipt: Mapping[str, Any], command_fingerprint: PreviewFingerprint) -> None:
    if str(receipt.get("command_fingerprint", "")) != command_fingerprint.value:
        raise ClientProfileRequestConflictError("idempotency_key_reused_with_different_payload")
