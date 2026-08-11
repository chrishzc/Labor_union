"""Administrative LINE identity queries and durable revocation saga."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from domains.line.identities import LineUserId
from domains.line.identity_binding import LineIdentityBindingStatus
from domains.line.identity_binding import LineIdentityClaim
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ExpectedVersion, IdempotencyKey
from shared_kernel.ports import OutboxIntent
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.identity_management_contracts import (
    LineIdentityBindingListQuery,
    LineIdentityRevocationPreview,
    LineIdentityReplacementPreview,
    LineIdentityRevocationStatus,
    RequestLineIdentityRevocationCommand,
    ReplaceLineIdentitySubjectCommand,
)
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


IDENTITY_MENU_RESET_INTENT = "line.identity.revocation.menu_reset"


class LineIdentityManagementApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        now: Callable[[], datetime],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def list(self, query: LineIdentityBindingListQuery):
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.identity_management.list(query)
            unit_of_work.commit()
        return result

    def detail(self, line_user_id: LineUserId):
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.identity_management.detail(line_user_id)
            unit_of_work.commit()
        return result

    def preview_revocation(
        self,
        line_user_id: LineUserId,
    ) -> LineIdentityRevocationPreview:
        with self._unit_of_work_factory() as unit_of_work:
            binding = unit_of_work.identity_management.detail(line_user_id)
            publication = unit_of_work.identity_management.default_menu_publication()
            unit_of_work.commit()
        blockers = _revocation_blockers(binding.status, publication)
        return LineIdentityRevocationPreview(
            binding,
            int(publication["id"]) if publication else None,
            str(publication["line_rich_menu_id"]) if publication else None,
            blockers,
        )

    def preview_replacement(
        self,
        line_user_id: LineUserId,
        target_subject_reference: str,
    ) -> LineIdentityReplacementPreview:
        with self._unit_of_work_factory() as unit_of_work:
            binding = unit_of_work.identity_management.detail(line_user_id)
            candidate = unit_of_work.identity_management.subject_candidate(
                binding.subject_type,
                target_subject_reference,
            )
            unit_of_work.commit()
        blockers = _replacement_blockers(binding, candidate, target_subject_reference)
        return LineIdentityReplacementPreview(
            binding,
            target_subject_reference,
            str((candidate or {}).get("subject_name") or "-"),
            blockers,
        )

    # Kept cohesive so binding root and both owner projections change in one transaction.
    def replace_subject(self, command: ReplaceLineIdentitySubjectCommand):
        require_line_capability(command.actor, LineCapability.IDENTITY_BINDING_MANAGE)
        _require_reason(command.reason)
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.identity_management.detail(command.line_user_id)
            if current.subject_reference == command.target_subject_reference:
                unit_of_work.commit()
                return current
            candidate = unit_of_work.identity_management.subject_candidate(
                current.subject_type,
                command.target_subject_reference,
            )
            blockers = _replacement_blockers(
                current,
                candidate,
                command.target_subject_reference,
            )
            if blockers:
                raise RuntimeError(blockers[0])
            claim = LineIdentityClaim(
                command.line_user_id,
                current.subject_type,
                command.target_subject_reference,
            )
            resulting = unit_of_work.identities.replace_subject(
                claim,
                command.expected_version,
                command.actor.actor_id,
                command.idempotency_key,
                command.correlation_id.value,
            )
            _clear_binding_owner(unit_of_work, current)
            _bind_replacement_owner(unit_of_work, resulting)
            unit_of_work.audit.append(
                LineAuditIntent(
                    "line.identity.binding.replaced",
                    command.actor.actor_id,
                    "line_identity_binding",
                    command.line_user_id.value,
                )
            )
            result = unit_of_work.identity_management.detail(command.line_user_id)
            unit_of_work.commit()
        return result

    # Kept cohesive so binding disable, saga root, audit, and outbox share one commit.
    def request_revocation(self, command: RequestLineIdentityRevocationCommand):
        require_line_capability(command.actor, LineCapability.IDENTITY_BINDING_MANAGE)
        _require_reason(command.reason)
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.identity_management.get_request_by_key(
                command.idempotency_key.value
            )
            if replay is not None:
                _require_same_request(replay, command)
                unit_of_work.commit()
                return replay
            publication = unit_of_work.identity_management.default_menu_publication()
            if publication is None:
                raise RuntimeError("line_identity_default_menu_not_published")
            pending = unit_of_work.identities.request_revocation(
                command.line_user_id,
                command.expected_version,
                command.actor.actor_id,
                _derived_key(command.idempotency_key, "pending"),
                command.correlation_id.value,
            )
            request = unit_of_work.identity_management.create_request(
                command,
                pending,
                publication,
            )
            unit_of_work.outbox.append(_menu_reset_intent(request))
            unit_of_work.audit.append(_audit("requested", command.actor.actor_id, request))
            unit_of_work.commit()
        return request

    def retry(self, request_id: int, actor, reason: str):
        require_line_capability(actor, LineCapability.IDENTITY_BINDING_MANAGE)
        _require_reason(reason)
        with self._unit_of_work_factory() as unit_of_work:
            request = unit_of_work.identity_management.get_request(request_id, lock=True)
            if request.status is not LineIdentityRevocationStatus.MENU_RESET_FAILED:
                raise RuntimeError("line_identity_revocation_not_retryable")
            unit_of_work.outbox.append(_menu_reset_intent(request, request.attempt_count + 1))
            unit_of_work.audit.append(_audit("retry", actor.actor_id, request))
            unit_of_work.commit()
        return request

    # Kept cohesive so binding, owner projection, saga root, and audit commit atomically.
    def finalize(self, request_id: int, *, manual_actor=None, reason: str | None = None):
        manual = manual_actor is not None
        if manual:
            require_line_capability(
                manual_actor,
                LineCapability.IDENTITY_BINDING_OVERRIDE,
            )
            _require_reason(reason or "")
        actor_id = manual_actor.actor_id if manual else "system:line-worker"
        with self._unit_of_work_factory() as unit_of_work:
            request = unit_of_work.identity_management.get_request(request_id, lock=True)
            if request.status in _COMPLETED_STATUSES:
                unit_of_work.commit()
                return request
            if manual and request.status is not LineIdentityRevocationStatus.MENU_RESET_FAILED:
                raise RuntimeError("line_identity_manual_completion_forbidden")
            completed = unit_of_work.identities.complete_revocation(
                request.line_user_id,
                request.pending_binding_version,
                actor_id,
                _completion_key(request, manual),
                f"line-identity-revocation:{request.request_id}",
            )
            _clear_owner_projection(unit_of_work, request)
            unit_of_work.identity_management.complete(
                request,
                completed.version,
                actor_id,
                manual=manual,
                reason=reason,
            )
            unit_of_work.audit.append(_audit("completed", actor_id, request))
            result = unit_of_work.identity_management.get_request(request_id)
            unit_of_work.commit()
        return result


def _revocation_blockers(status, publication) -> tuple[str, ...]:
    blockers = []
    if status is not LineIdentityBindingStatus.BOUND:
        blockers.append("line_identity_binding_not_bound")
    if publication is None:
        blockers.append("line_identity_default_menu_not_published")
    return tuple(blockers)


def _replacement_blockers(binding, candidate, target_reference) -> tuple[str, ...]:
    blockers = []
    if binding.status is not LineIdentityBindingStatus.BOUND:
        blockers.append("line_identity_binding_not_bound")
    if binding.subject_reference == target_reference:
        blockers.append("line_identity_subject_unchanged")
    if candidate is None:
        blockers.append("line_identity_replacement_subject_not_found")
    elif str(candidate.get("line_user_id") or "").strip():
        blockers.append("line_identity_replacement_subject_already_bound")
    return tuple(blockers)


def _menu_reset_intent(request, retry_number: int = 0) -> OutboxIntent:
    payload = json.dumps(
        {
            "line_user_id": request.line_user_id.value,
            "provider_menu_id": request.provider_menu_id,
            "request_id": request.request_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    suffix = f":retry:{retry_number}" if retry_number else ""
    return OutboxIntent(
        "line_identity_revocation",
        str(request.request_id),
        IDENTITY_MENU_RESET_INTENT,
        payload,
        f"identity-menu-reset:{request.request_id}{suffix}",
    )


def _derived_key(key: IdempotencyKey, suffix: str) -> IdempotencyKey:
    digest = fingerprint_payload({"key": key.value, "suffix": suffix})
    return IdempotencyKey(f"identity-management:{digest.value}")


def _completion_key(request, manual: bool) -> IdempotencyKey:
    suffix = "manual" if manual else "provider"
    return IdempotencyKey(f"identity-revocation:{request.request_id}:{suffix}")


def _require_same_request(request, command) -> None:
    if request.line_user_id != command.line_user_id:
        raise RuntimeError("line_identity_revocation_idempotency_conflict")
    expected = (
        command.expected_version,
        command.actor.actor_id,
        command.reason,
        command.idempotency_key.value,
        command.correlation_id.value,
    )
    actual = (
        request.requested_binding_version,
        request.requested_by_actor_id,
        request.reason,
        request.idempotency_key,
        request.correlation_id,
    )
    if actual != expected:
        raise RuntimeError("line_identity_revocation_idempotency_conflict")


def _require_reason(reason: str) -> None:
    if not reason.strip():
        raise ValueError("line_identity_revocation_reason_required")


def _audit(action: str, actor_id: str, request) -> LineAuditIntent:
    return LineAuditIntent(
        f"line.identity.revocation.{action}",
        actor_id,
        "line_identity_revocation_request",
        str(request.request_id),
    )


def _clear_owner_projection(unit_of_work, request) -> None:
    if request.subject_type.value == "customer":
        unit_of_work.customers.clear_customer(
            request.subject_reference,
            request.line_user_id,
        )
        return
    if request.subject_type.value == "staff":
        unit_of_work.staff.clear_staff(
            request.subject_reference,
            request.line_user_id,
        )
        return
    unit_of_work.admins.clear_admin(
        request.subject_reference,
        request.line_user_id,
    )


def _clear_binding_owner(unit_of_work, binding) -> None:
    line_user_id = LineUserId(binding.line_user_id)
    if binding.subject_type.value == "customer":
        unit_of_work.customers.clear_customer(binding.subject_reference, line_user_id)
        return
    if binding.subject_type.value == "staff":
        unit_of_work.staff.clear_staff(binding.subject_reference, line_user_id)
        return
    unit_of_work.admins.clear_admin(binding.subject_reference, line_user_id)


def _bind_replacement_owner(unit_of_work, binding) -> None:
    if binding.subject_type.value == "customer":
        unit_of_work.customers.bind_customer(
            binding.subject_reference,
            binding.line_user_id,
            None,
        )
        return
    if binding.subject_type.value == "staff":
        unit_of_work.staff.bind_staff(
            binding.subject_reference,
            binding.line_user_id,
            None,
        )
        return
    unit_of_work.admins.bind_admin(
        binding.subject_reference,
        binding.line_user_id,
        None,
    )


_COMPLETED_STATUSES = {
    LineIdentityRevocationStatus.COMPLETED,
    LineIdentityRevocationStatus.MANUAL_COMPLETED,
}


__all__ = ["IDENTITY_MENU_RESET_INTENT", "LineIdentityManagementApplication"]
