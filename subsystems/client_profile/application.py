"""Client-owned profile change Query/Preview/Apply application."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from domains.clients.profile import (
    ClientProfileValidationError,
    can_reclassify_client,
    requested_before_values,
    validate_changes,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from .contracts import (
    ClientProfileAdminReceipt,
    ClientProfileNotFoundError,
    ClientProfilePreview,
    ClientProfileRequestConflictError,
    ClientProfileStaleError,
    ClientProfileView,
)


class ClientProfileRepository(Protocol):
    def prepare_identity_change(self, case_no: str, client_id: int, *, lock: bool): ...
    def apply_identity_pricing(self, prepared, *, actor_id: str, reason: str, key: str) -> None: ...
    def load_email_fill_target(self, case_no: str, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def load_profile(self, client_id: int, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def load_profile_by_case_no(self, case_no: str, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def claim_admin_command(self, *, case_no: str, idempotency_key: str, command_fingerprint: str, correlation_id: str) -> None: ...
    def find_admin_receipt(self, key: str, *, for_update: bool = False) -> Mapping[str, Any] | None: ...
    def apply_admin_change(self, *, client_id: int, expected_version: int, before: Mapping[str, str], requested: Mapping[str, str], actor_id: str, reason: str, idempotency_key: str, correlation_id: str) -> int: ...
    def save_admin_receipt(self, *, idempotency_key: str, command_fingerprint: str, preview_fingerprint: str, actor_id: str, reason: str, result: Mapping[str, Any]) -> None: ...


class ClientProfileUnitOfWork(Protocol):
    client_profiles: ClientProfileRepository

    def __enter__(self): ...
    def __exit__(self, exception_type, exception, traceback): ...
    def commit(self) -> None: ...


class ClientProfileApplication:
    def __init__(self, unit_of_work_factory: Callable[[], ClientProfileUnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @staticmethod
    def preview_hcm_email_fill(repository: ClientProfileRepository, case_no: str, email: object,
                               *, for_update: bool = False) -> ClientProfilePreview | None:
        row = repository.load_email_fill_target(_case_no(case_no), for_update=for_update)
        if row is None:
            raise ClientProfileNotFoundError("client_profile_not_found")
        if str(row.get("email") or "").strip() or email is None or not str(email).strip():
            return None
        changes = validate_changes({"email": email})
        profile = ClientProfileView(int(row["client_id"]), int(row["client_profile_version"]),
                                    {"email": str(row.get("email") or "")})
        return _preview(profile, changes, ExpectedVersion(profile.version))

    @staticmethod
    def fill_hcm_email_in_current_uow(repository: ClientProfileRepository, case_no: str, email: object,
                                      *, source_identity: str, actor: ActorContext,
                                      correlation_id: CorrelationId) -> bool:
        """Borrow the workbook transaction; only a fresh, locked empty email can change."""
        preview = ClientProfileApplication.preview_hcm_email_fill(repository, case_no, email, for_update=True)
        if preview is None:
            return False
        key = "hcm-email-fill:" + fingerprint_payload({"source_identity": source_identity}).value
        if repository.find_admin_receipt(key, for_update=True) is not None:
            return False
        reason = "HCM 工作簿補入既有案件的空白 email"
        command = _command_fingerprint("client_profile_admin_change/v1", case_no,
            {"changes": preview.requested, "actor": actor.actor_id}, ExpectedVersion(preview.current_version),
            reason, preview.preview_fingerprint)
        try:
            repository.claim_admin_command(case_no=case_no, idempotency_key=key,
                command_fingerprint=command.value, correlation_id=correlation_id.value)
            version = repository.apply_admin_change(client_id=preview.client_id,
                expected_version=preview.current_version, before=preview.before, requested=preview.requested,
                actor_id=actor.actor_id, reason=reason, idempotency_key=key, correlation_id=correlation_id.value)
        except RuntimeError as error:
            if str(error) == "client_profile_version_stale":
                raise ClientProfileStaleError("client_profile_version_stale") from error
            if str(error) == "idempotency_mismatch":
                raise ClientProfileRequestConflictError("profile_idempotency_conflict") from error
            raise
        repository.save_admin_receipt(idempotency_key=key, command_fingerprint=command.value,
            preview_fingerprint=preview.preview_fingerprint.value, actor_id=actor.actor_id, reason=reason,
            result={"case_no": case_no, "client_id": preview.client_id,
                    "resulting_version": version, "changed_fields": ["email"]})
        return True

    def query_admin(self, case_no: str) -> ClientProfileView:
        case_identity = _case_no(case_no)
        with self._unit_of_work_factory() as unit_of_work:
            profile = _require_profile(
                unit_of_work.client_profiles.load_profile_by_case_no(case_identity)
            )
        return profile

    def preview_admin(
        self,
        case_no: str,
        changes: Mapping[str, object],
        expected_version: ExpectedVersion,
    ) -> ClientProfilePreview:
        case_identity = _case_no(case_no)
        normalized = validate_changes(changes)
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.client_profiles
            row = repository.load_profile_by_case_no(case_identity)
            profile = _require_profile(row)
            if "identity_status" in normalized:
                _require_identity_change(row)
                repository.prepare_identity_change(case_identity, profile.client_id, lock=False)
        return _preview(profile, normalized, expected_version)

    def apply_admin(
        self,
        case_no: str,
        changes: Mapping[str, object],
        expected_version: ExpectedVersion,
        actor: ActorContext,
        reason: str,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> ClientProfileAdminReceipt:
        case_identity = _case_no(case_no)
        normalized = validate_changes(changes)
        clean_reason = reason.strip()
        command_fingerprint = _command_fingerprint(
            "client_profile_admin_change/v1",
            case_identity,
            {"changes": normalized, "actor": actor.actor_id},
            expected_version,
            clean_reason,
            preview_fingerprint,
        )
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.client_profiles
            repository.claim_admin_command(
                case_no=case_identity,
                idempotency_key=idempotency_key.value,
                command_fingerprint=command_fingerprint.value,
                correlation_id=correlation_id.value,
            )
            replay = repository.find_admin_receipt(
                idempotency_key.value, for_update=True
            )
            if replay is not None:
                _require_replay(replay, command_fingerprint)
                current = _require_profile(
                    repository.load_profile_by_case_no(case_identity)
                )
                result = replay.get("result", replay)
                unit_of_work.commit()
                return ClientProfileAdminReceipt(
                    case_identity,
                    int(result["resulting_version"]),
                    tuple(str(item) for item in result["changed_fields"]),
                    PreviewFingerprint(str(replay["preview_fingerprint"])),
                    idempotency_key.value,
                    True,
                    current,
                )
            row = repository.load_profile_by_case_no(case_identity, for_update=True)
            profile = _require_profile(row)
            preview = _preview(profile, normalized, expected_version)
            _require_preview(preview.preview_fingerprint, preview_fingerprint)
            if "identity_status" in normalized:
                _require_identity_change(row)
                prepared_pricing = repository.prepare_identity_change(case_identity, profile.client_id, lock=True)
            resulting_version = repository.apply_admin_change(
                client_id=profile.client_id,
                expected_version=expected_version.value,
                before=preview.before,
                requested=preview.requested,
                actor_id=actor.actor_id,
                reason=clean_reason,
                idempotency_key=idempotency_key.value,
                correlation_id=correlation_id.value,
            )
            if "identity_status" in normalized:
                repository.apply_identity_pricing(
                    prepared_pricing, actor_id=actor.actor_id,
                    reason=clean_reason or "補助資格更正為一般市民", key=idempotency_key.value,
                )
            result = {
                "case_no": case_identity,
                "client_id": profile.client_id,
                "resulting_version": resulting_version,
                "changed_fields": sorted(normalized),
            }
            repository.save_admin_receipt(
                idempotency_key=idempotency_key.value,
                command_fingerprint=command_fingerprint.value,
                preview_fingerprint=preview_fingerprint.value,
                actor_id=actor.actor_id,
                reason=clean_reason,
                result=result,
            )
            unit_of_work.commit()
            fresh = _require_profile(repository.load_profile(profile.client_id))
        return ClientProfileAdminReceipt(
            case_identity,
            resulting_version,
            tuple(sorted(normalized)),
            preview_fingerprint,
            idempotency_key.value,
            False,
            fresh,
        )


def _require_identity_change(row: Mapping[str, Any]) -> None:
    if not can_reclassify_client(row.get("identity_status"), row.get("order_status"),
                                  row.get("actual_start_date"), row.get("actual_end_date")):
        raise ClientProfileRequestConflictError("profile_identity_change_unavailable")


def _require_profile(row: Mapping[str, Any] | None) -> ClientProfileView:
    if not row:
        raise ClientProfileNotFoundError("client_profile_not_found")
    values = {field: str(row.get(field) or "") for field in (
        "name", "gender", "phone", "email", "city", "address", "residence_type", "delivery_type", "baby_info", "notes", "due_month", "reject_reason", "service_type", "admin_notes", "identity_status",
    )}
    return ClientProfileView(int(row["client_id"] if "client_id" in row else row["id"]), int(row.get("client_profile_version", row.get("version", 0))), values)


def _preview(profile: ClientProfileView, changes: Mapping[str, str], expected_version: ExpectedVersion) -> ClientProfilePreview:
    if profile.version != expected_version.value:
        raise ClientProfileStaleError("client_profile_version_stale")
    before = requested_before_values(profile.values, changes)
    fingerprint = fingerprint_payload({"client_id": profile.client_id, "version": profile.version, "before": before, "requested": dict(changes)})
    return ClientProfilePreview(profile.client_id, profile.version, before, dict(changes), fingerprint)


def _require_preview(actual: PreviewFingerprint, supplied: PreviewFingerprint) -> None:
    if actual != supplied:
        raise ClientProfileRequestConflictError("profile_preview_fingerprint_mismatch")


def _command_fingerprint(family, identity, payload, expected_version, reason, preview):
    return fingerprint_payload({"family": family, "identity": identity, "payload": dict(payload), "expected_version": expected_version.value, "reason": reason.strip(), "preview_fingerprint": preview.value})


def _require_replay(receipt: Mapping[str, Any], command_fingerprint: PreviewFingerprint) -> None:
    if str(receipt.get("command_fingerprint", "")) != command_fingerprint.value:
        raise ClientProfileRequestConflictError("idempotency_key_reused_with_different_payload")


def _case_no(value: str) -> str:
    case_no = str(value or "").strip()
    if not case_no or len(case_no) > 50:
        raise ClientProfileValidationError("case_no_invalid")
    return case_no
