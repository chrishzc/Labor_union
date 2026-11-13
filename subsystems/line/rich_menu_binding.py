"""Durable per-user Rich Menu binding scheduled by identity transactions."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from random import randint
from typing import Callable

from domains.line.identities import LineRichMenuPublicationId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.ports import OutboxIntent
from subsystems.line.outbox_contracts import (
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
    RICH_MENU_BINDING_INTENT,
    RICH_MENU_BINDING_MAX_ATTEMPTS,
    RICH_MENU_BINDING_VERIFIED,
)
from subsystems.line.ports import LineAuditIntent, LineRichMenuProviderPort, LineUnitOfWorkPort
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
)

_MENU_BY_SUBJECT = {
    LineBindingSubjectType.CUSTOMER: "customer_menu",
    LineBindingSubjectType.STAFF: "staff_menu",
    LineBindingSubjectType.ADMIN: "union_staff_menu",
}
_SUBJECT_BY_AUDIENCE = {
    "visitor": None,
    "customer": LineBindingSubjectType.CUSTOMER,
    "staff": LineBindingSubjectType.STAFF,
    "union_staff": LineBindingSubjectType.ADMIN,
}
_RETRYABLE_OUTCOMES = {
    LineRichMenuProviderOutcomeType.RATE_LIMITED,
    LineRichMenuProviderOutcomeType.UNAVAILABLE,
    LineRichMenuProviderOutcomeType.TIMEOUT,
}


def schedule_rich_menu_binding(unit_of_work, binding: LineIdentityBindingSnapshot) -> None:
    if binding.status is not LineIdentityBindingStatus.BOUND or binding.subject_type is None:
        raise ValueError("Rich Menu binding requires a bound LINE identity")
    unit_of_work.outbox.append(_binding_intent(binding))


def schedule_resolved_identity_menu(unit_of_work, line_user_id, *, selection_version=None) -> bool:
    """Queue one menu only when the LINE-owned active role is unambiguous."""

    binding = _resolved_identity_binding(unit_of_work, line_user_id)
    if binding is None:
        return False
    unit_of_work.outbox.append(
        _binding_intent(binding, role_scoped=True, selection_version=selection_version)
    )
    return True


def schedule_revocation_successor_menu(unit_of_work, line_user_id, request_id) -> bool:
    """Queue one post-revocation menu without colliding with an older role bind."""

    binding = _resolved_identity_binding(unit_of_work, line_user_id)
    if binding is None:
        return False
    unit_of_work.outbox.append(
        _binding_intent(
            binding,
            role_scoped=True,
            revocation_request_id=request_id,
        )
    )
    return True


def schedule_staff_default_restore_menu(
    unit_of_work,
    binding: LineIdentityBindingSnapshot,
    source_event_identity: str,
    menu_revision: int | None = None,
) -> str:
    """Queue the existing staff menu provider intent for a terminal-closure restore."""

    if (
        binding.status is not LineIdentityBindingStatus.BOUND
        or binding.subject_type is not LineBindingSubjectType.STAFF
    ):
        raise ValueError("staff default restore requires an active staff binding")
    if not source_event_identity:
        raise ValueError("terminal closure source event identity is required")
    payload = {
        "line_user_id": binding.line_user_id.value,
        "menu_definition_id": _MENU_BY_SUBJECT[LineBindingSubjectType.STAFF],
        "restore_reason": "case_terminal_closure",
        "source_event_identity": source_event_identity,
    }
    if menu_revision is not None:
        payload["menu_revision"] = menu_revision
    intent_identity = f"staff-default-restore:{source_event_identity}"
    unit_of_work.outbox.append(
        OutboxIntent(
            "line_identity",
            binding.line_user_id.value,
            RICH_MENU_BINDING_INTENT,
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            intent_identity,
        )
    )
    return intent_identity


def _resolved_identity_binding(unit_of_work, line_user_id, *, lock=False):
    read_options = {"lock": True} if lock else {}
    scoped = tuple(
        binding
        for binding in unit_of_work.identities.list_by_user(line_user_id, **read_options)
        if binding.status is LineIdentityBindingStatus.BOUND
    )
    if not scoped:
        return None
    if len(scoped) == 1:
        return scoped[0]
    if any(binding.subject_type is LineBindingSubjectType.ADMIN for binding in scoped):
        raise RuntimeError("line_identity_admin_role_exclusive")
    selected_role, _ = unit_of_work.identities.selected_role(line_user_id, **read_options)
    if selected_role is None:
        return None
    selected = tuple(
        binding for binding in scoped if binding.subject_type is selected_role
    )
    if len(selected) != 1:
        raise RuntimeError("line_identity_selected_role_stale")
    return selected[0]


def schedule_published_menu_rebindings(
    unit_of_work,
    definition_json: str,
    publication_id: LineRichMenuPublicationId,
    provider_menu_id: str,
) -> int:
    definition = json.loads(definition_json)
    subject_type = _SUBJECT_BY_AUDIENCE.get(str(definition["audience_role"]))
    if subject_type is None:
        return 0
    menu_definition_id = str(definition["id"])
    bindings = unit_of_work.identities.list_bound_by_subject_type(subject_type)
    scheduled = 0
    for binding in bindings:
        unit_of_work.outbox.lock_menu_user(binding.line_user_id)
        current = _resolved_identity_binding(unit_of_work, binding.line_user_id, lock=True)
        if current is None or current.subject_type is not subject_type:
            continue
        unit_of_work.outbox.append(
            _publication_binding_intent(
                current,
                menu_definition_id,
                publication_id,
                provider_menu_id,
            )
        )
        scheduled += 1
    return scheduled


def _binding_intent(binding, *, role_scoped=False, revocation_request_id=None, selection_version=None):
    menu_definition_id = _MENU_BY_SUBJECT[binding.subject_type]
    role_segment = f":{binding.subject_type.value}" if role_scoped else ""
    revocation_segment = (
        f":revocation:{revocation_request_id}"
        if revocation_request_id is not None
        else ""
    )
    selection_segment = f":selection:{selection_version.value}" if selection_version is not None else ""
    return OutboxIntent(
        "line_identity",
        binding.line_user_id.value,
        RICH_MENU_BINDING_INTENT,
        _binding_payload(binding, menu_definition_id),
        f"rich-menu-bind:{binding.line_user_id.value}{role_segment}:"
        f"{binding.version.value}{revocation_segment}{selection_segment}",
    )


def _publication_binding_intent(
    binding,
    menu_definition_id,
    publication_id,
    provider_menu_id,
):
    return OutboxIntent(
        "line_identity",
        binding.line_user_id.value,
        RICH_MENU_BINDING_INTENT,
        _binding_payload(binding, menu_definition_id, provider_menu_id),
        f"rich-menu-rebind:{publication_id.value}:{binding.line_user_id.value}",
    )


def _binding_payload(binding, menu_definition_id, provider_menu_id=None):
    payload = {
        "line_user_id": binding.line_user_id.value,
        "menu_definition_id": menu_definition_id,
    }
    if provider_menu_id is not None:
        payload["provider_menu_id"] = provider_menu_id
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class LineRichMenuBindingWorker:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        provider: LineRichMenuProviderPort,
        worker_identity: str,
        now: Callable[[], datetime],
        batch_size: int = 1,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._provider = provider
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        processed = 0
        for _ in range(self._batch_size):
            items = self._claim()
            if not items:
                break
            self._process(items[0])
            processed += 1
        return processed

    def _claim(self):
        query = ClaimLineOutboxQuery(
            self._worker_identity,
            self._now(),
            1,
            RICH_MENU_BINDING_INTENT,
        )
        with self._unit_of_work_factory() as unit_of_work:
            items = unit_of_work.outbox.claim(query)
            unit_of_work.commit()
        return items

    def _process(self, item) -> None:
        # Claim has committed its attempt count. Hold the per-user and exact lease
        # locks through the provider operation so competing workers cannot overtake it.
        with self._unit_of_work_factory() as unit_of_work:
            line_user_id = LineUserId(item.aggregate_identity)
            unit_of_work.outbox.lock_menu_user(line_user_id)
            if not unit_of_work.outbox.lock_menu_lease(item, self._now()):
                return
            try:
                outcome = self._bind(unit_of_work, item, line_user_id)
            except (KeyError, TypeError, ValueError):
                outcome = _failure("rich_menu_binding_payload_invalid", "圖文選單工作資料無效")
            self._complete(unit_of_work, item, outcome)
            unit_of_work.commit()

    def _bind(self, unit_of_work, item, line_user_id):
        if unit_of_work.outbox.latest_menu_intent_id(line_user_id) != item.outbox_id:
            return _failure("rich_menu_binding_superseded", "已有較新的圖文選單切換工作")
        if self._now() >= item.deadline:
            return _failure("rich_menu_binding_deadline_exhausted", "圖文選單同步已逾時")
        if unit_of_work.outbox.menu_reset_pending(line_user_id):
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.UNAVAILABLE,
                error_code="rich_menu_binding_waiting_for_reset",
                error_message="等待身分解除回復圖文選單",
            )
        payload = json.loads(item.payload_json)
        menu_definition_id = payload["menu_definition_id"]
        if payload["line_user_id"] != line_user_id.value or menu_definition_id not in (
            *_MENU_BY_SUBJECT.values(), "default_menu"
        ):
            raise ValueError("Rich Menu binding target is invalid")
        if not _is_current_target(unit_of_work, item, line_user_id, payload):
            return _failure("rich_menu_binding_superseded", "身分或選單意圖已變更")
        provider_menu_id = unit_of_work.rich_menu_publications.published_provider_menu_id(
            menu_definition_id
        ) or payload.get("provider_menu_id")
        if not provider_menu_id:
            return _failure("rich_menu_binding_not_published", "圖文選單尚未發布")
        if item.attempt_count > 1 or item.maximum_attempts < RICH_MENU_BINDING_MAX_ATTEMPTS:
            current = self._provider.get_user_rich_menu(line_user_id)
            if current.provider_menu_id == provider_menu_id:
                return current
            if current.provider_menu_id is None and current.error_code != "line_http_404":
                return current
        if self._now() >= item.deadline:
            return _failure("rich_menu_binding_deadline_exhausted", "圖文選單同步已逾時")
        linked = self._provider.link_to_user(provider_menu_id, line_user_id)
        if linked.outcome_type not in {
            LineRichMenuProviderOutcomeType.SUCCESS,
            LineRichMenuProviderOutcomeType.TIMEOUT,
            LineRichMenuProviderOutcomeType.UNAVAILABLE,
        }:
            return linked
        if self._now() >= item.deadline:
            return _failure("rich_menu_binding_deadline_exhausted", "圖文選單同步已逾時")
        current = self._provider.get_user_rich_menu(line_user_id)
        if current.provider_menu_id == provider_menu_id:
            return current
        if current.provider_menu_id is None and current.error_code != "line_http_404":
            if current.outcome_type not in _RETRYABLE_OUTCOMES:
                return current
            return replace(
                current,
                retry_after_seconds=max(current.retry_after_seconds or 0, linked.retry_after_seconds or 0),
            )
        if linked.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            return linked
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.UNAVAILABLE,
            error_code="rich_menu_binding_readback_mismatch",
            error_message="LINE 讀回的選單與預期不符",
        )

    def _complete(self, unit_of_work, item, outcome):
        completed_at = self._now()
        if completed_at >= item.deadline:
            outcome = _failure("rich_menu_binding_deadline_exhausted", "圖文選單同步已逾時")
        if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
            unit_of_work.audit.append(LineAuditIntent(
                RICH_MENU_BINDING_VERIFIED, "system:line-worker", "line_domain_outbox", str(item.outbox_id)
            ))
            unit_of_work.outbox.complete(CompleteLineOutboxCommand(item, completed_at))
            return
        retryable = outcome.outcome_type in _RETRYABLE_OUTCOMES
        code = outcome.error_code
        message = outcome.error_message
        delay = 0
        if retryable:
            backoff = 15 * 2 ** (item.attempt_count - 1)
            delay = max(backoff + randint(0, backoff // 2), outcome.retry_after_seconds or 0)
            if item.attempt_count >= item.maximum_attempts:
                code, message = "rich_menu_binding_attempts_exhausted", f"已達重試上限（{code}）"
                retryable = False
            elif delay >= (item.deadline - completed_at).total_seconds():
                code, message = "rich_menu_binding_deadline_exhausted", f"重試已超過時限（{code}）"
                retryable = False
        unit_of_work.outbox.complete(CompleteLineOutboxCommand(
            item, completed_at, code, message, retry_after_seconds=delay, retryable=retryable,
        ))


def _is_current_target(unit_of_work, item, line_user_id, payload):
    menu_definition_id = payload["menu_definition_id"]
    if menu_definition_id == "default_menu":
        return True
    if item.idempotency_identity.startswith("line-menu-command:"):
        roles = {
            binding.subject_type for binding in unit_of_work.identities.list_by_user(line_user_id)
            if binding.status is LineIdentityBindingStatus.BOUND
        }
        return LineBindingSubjectType.ADMIN in roles or any(
            _MENU_BY_SUBJECT[role] == menu_definition_id for role in roles
        )
    if payload.get("restore_reason") == "case_terminal_closure":
        binding = unit_of_work.identities.get(line_user_id, LineBindingSubjectType.STAFF)
        if unit_of_work.identity_management.active_client_cases(line_user_id):
            return False
    else:
        binding = _resolved_identity_binding(unit_of_work, line_user_id)
    return (
        binding is not None
        and binding.status is LineIdentityBindingStatus.BOUND
        and _MENU_BY_SUBJECT[binding.subject_type] == menu_definition_id
        and _binding_version_matches(item.idempotency_identity, binding)
    )


def _binding_version_matches(identity, binding):
    prefix = f"rich-menu-bind:{binding.line_user_id.value}:"
    if not identity.startswith(prefix):
        return True
    parts = identity.removeprefix(prefix).split(":")
    if parts[0] in {role.value for role in _MENU_BY_SUBJECT}:
        return len(parts) > 1 and parts[0] == binding.subject_type.value and parts[1] == str(binding.version.value)
    version = parts[0]
    return version == str(binding.version.value)


def _failure(code, message):
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType.REJECTED, error_code=code, error_message=message
    )


__all__ = [
    "LineRichMenuBindingWorker",
    "RICH_MENU_BINDING_INTENT",
    "schedule_published_menu_rebindings",
    "schedule_rich_menu_binding",
    "schedule_resolved_identity_menu",
    "schedule_revocation_successor_menu",
    "schedule_staff_default_restore_menu",
]
