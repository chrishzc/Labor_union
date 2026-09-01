"""Durable per-user Rich Menu binding scheduled by identity transactions."""

from __future__ import annotations

import json
from datetime import datetime
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
)
from subsystems.line.ports import LineRichMenuProviderPort, LineUnitOfWorkPort
from subsystems.line.rich_menu_contracts import LineRichMenuProviderOutcomeType

RICH_MENU_BINDING_INTENT = "line.rich_menu.bind"
_MENU_BY_SUBJECT = {
    LineBindingSubjectType.CUSTOMER: "default_menu",
    LineBindingSubjectType.STAFF: "staff_menu",
    LineBindingSubjectType.ADMIN: "union_staff_menu",
}
_SUBJECT_BY_AUDIENCE = {
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


def schedule_resolved_identity_menu(unit_of_work, line_user_id) -> bool:
    """Queue one menu only when the LINE-owned active role is unambiguous."""

    binding = _resolved_identity_binding(unit_of_work, line_user_id)
    if binding is None:
        return False
    unit_of_work.outbox.append(_binding_intent(binding, role_scoped=True))
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


def _resolved_identity_binding(unit_of_work, line_user_id):
    scoped = tuple(
        binding
        for binding in unit_of_work.identities.list_by_user(line_user_id)
        if binding.status is LineIdentityBindingStatus.BOUND
    )
    if not scoped:
        return None
    if len(scoped) == 1:
        return scoped[0]
    if any(binding.subject_type is LineBindingSubjectType.ADMIN for binding in scoped):
        raise RuntimeError("line_identity_admin_role_exclusive")
    selected_role, _ = unit_of_work.identities.selected_role(line_user_id)
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
    bindings = unit_of_work.identities.list_bound_by_subject_type(subject_type)
    for binding in bindings:
        unit_of_work.outbox.append(
            _publication_binding_intent(
                binding,
                str(definition["id"]),
                publication_id,
                provider_menu_id,
            )
        )
    return len(bindings)


def _binding_intent(binding, *, role_scoped=False, revocation_request_id=None):
    menu_definition_id = _MENU_BY_SUBJECT[binding.subject_type]
    role_segment = f":{binding.subject_type.value}" if role_scoped else ""
    revocation_segment = (
        f":revocation:{revocation_request_id}"
        if revocation_request_id is not None
        else ""
    )
    return OutboxIntent(
        "line_identity",
        binding.line_user_id.value,
        RICH_MENU_BINDING_INTENT,
        _binding_payload(binding, menu_definition_id),
        f"rich-menu-bind:{binding.line_user_id.value}{role_segment}:"
        f"{binding.version.value}{revocation_segment}",
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
        batch_size: int = 10,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._provider = provider
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        items = self._claim()
        for item in items:
            self._process(item)
        return len(items)

    def _claim(self):
        query = ClaimLineOutboxQuery(
            self._worker_identity,
            self._now(),
            self._batch_size,
            RICH_MENU_BINDING_INTENT,
        )
        with self._unit_of_work_factory() as unit_of_work:
            items = unit_of_work.outbox.claim(query)
            unit_of_work.commit()
        return items

    def _process(self, item) -> None:
        try:
            outcome = self._bind(item.payload_json)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._complete(
                item,
                "rich_menu_binding_payload_invalid",
                str(error),
                retryable=False,
            )
            return
        except Exception as error:
            self._complete(item, "rich_menu_binding_unavailable", str(error), retryable=True)
            return
        self._record_outcome(item, outcome)

    def _record_outcome(self, item, outcome) -> None:
        if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
            self._complete(item)
            return
        self._complete(
            item,
            outcome.error_code,
            outcome.error_message,
            retryable=outcome.outcome_type in _RETRYABLE_OUTCOMES,
        )

    def _bind(self, payload_json):
        payload = json.loads(payload_json)
        line_user_id = LineUserId(str(payload["line_user_id"]))
        menu_definition_id = str(payload["menu_definition_id"])
        if menu_definition_id not in _MENU_BY_SUBJECT.values():
            raise ValueError("Rich Menu binding target is invalid")
        provider_menu_id = str(payload.get("provider_menu_id") or "")
        if not provider_menu_id:
            provider_menu_id = self._provider_menu_id(menu_definition_id)
        return self._provider.link_to_user(provider_menu_id, line_user_id)

    def _provider_menu_id(self, menu_definition_id: str) -> str:
        with self._unit_of_work_factory() as unit_of_work:
            provider_menu_id = unit_of_work.rich_menu_publications.published_provider_menu_id(
                menu_definition_id
            )
            unit_of_work.commit()
        if provider_menu_id is None:
            raise LookupError(f"Rich Menu {menu_definition_id} 尚未發布")
        return provider_menu_id

    def _complete(self, item, error_code=None, error_message=None, *, retryable=True):
        command = CompleteLineOutboxCommand(
            item,
            self._now(),
            str(error_code)[:191] if error_code else None,
            str(error_message or error_code)[:1000] if error_code else None,
            retryable=retryable,
        )
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.outbox.complete(command)
            unit_of_work.commit()


__all__ = [
    "LineRichMenuBindingWorker",
    "RICH_MENU_BINDING_INTENT",
    "schedule_published_menu_rebindings",
    "schedule_rich_menu_binding",
    "schedule_resolved_identity_menu",
    "schedule_revocation_successor_menu",
    "schedule_staff_default_restore_menu",
]
