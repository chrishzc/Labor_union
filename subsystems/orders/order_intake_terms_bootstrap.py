"""Orders-owned bootstrap and completion boundary for pending intake data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import fingerprint_payload


_FAMILY = "orders_intake_terms_bootstrap/v1"
_COMPLETION_FAMILY = "orders_intake_completion/v1"


@dataclass(frozen=True, slots=True)
class OrderIntakeTermsBootstrapFacts:
    case_no: str
    status: OrderLifecycleStatus
    lifecycle_version: int
    start_date: date | None
    service_days: int | None
    actual_start_date: date | None
    service_data_locked: bool
    client_finance_present: bool
    payroll_present: bool
    scheduling_present: bool
    scheduling_pristine: bool
    client_name: str | None = None


@dataclass(frozen=True, slots=True)
class OrderIntakeTermsBootstrapPreview:
    case_no: str
    lifecycle_version: int
    before_start_date: date | None
    before_service_days: int | None
    after_start_date: date
    after_service_days: int
    changed_fields: tuple[str, ...]
    blockers: tuple[str, ...]
    apply_allowed: bool
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class OrderIntakeTermsBootstrapReceipt:
    receipt_key: str
    case_no: str
    lifecycle_version: int
    start_date: date
    service_days: int
    changed_fields: tuple[str, ...]
    preview_fingerprint: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class OrderIntakeCompletionPreview:
    case_no: str
    lifecycle_version: int
    current_status: OrderLifecycleStatus
    target_status: OrderLifecycleStatus
    missing_fields: tuple[str, ...]
    blockers: tuple[str, ...]
    apply_allowed: bool
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class OrderIntakeCompletionReceipt:
    receipt_key: str
    case_no: str
    lifecycle_version: int
    status: OrderLifecycleStatus
    preview_fingerprint: str
    replayed: bool


class OrderIntakeTermsBootstrapError(Exception):
    def __init__(self, code: str, *, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.blockers = blockers


class OrderIntakeTermsBootstrapRepository(Protocol):
    def load_case(
        self, case_no: str, *, for_update: bool
    ) -> OrderIntakeTermsBootstrapFacts | None: ...

    def update_missing_terms(
        self,
        case_no: str,
        expected_lifecycle_version: int,
        start_date: date,
        service_days: int,
        *,
        fill_start_date: bool,
        fill_service_days: bool,
    ) -> int: ...

    def complete_intake(
        self,
        case_no: str,
        expected_lifecycle_version: int,
    ) -> int: ...

    def load_receipt(self, family: str, key: str): ...

    def save_receipt(
        self,
        family: str,
        key: str,
        request_fingerprint: str,
        preview_fingerprint: str,
        actor: str,
        reason: str,
        result: dict[str, object],
    ) -> None: ...


class OrderIntakeTermsBootstrapApplication:
    def __init__(
        self,
        repository: OrderIntakeTermsBootstrapRepository,
        unit_of_work_factory: Callable[[], object],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(
        self,
        case_no: str,
        proposed_start_date: date,
        proposed_service_days: int,
    ) -> OrderIntakeTermsBootstrapPreview:
        return preview_case(
            self._repository,
            case_no,
            proposed_start_date,
            proposed_service_days,
            for_update=False,
        )

    def apply(
        self,
        case_no: str,
        proposed_start_date: date,
        proposed_service_days: int,
        expected_lifecycle_version: int,
        preview_fingerprint: str,
        idempotency_key: str,
        actor: str,
        reason: str,
    ) -> OrderIntakeTermsBootstrapReceipt:
        _validate_command_fields(
            expected_lifecycle_version,
            preview_fingerprint,
            idempotency_key,
            actor,
            reason,
            prefix="order_intake_terms_bootstrap",
        )
        with self._unit_of_work_factory() as unit_of_work:
            receipt = apply_case(
                self._repository,
                case_no,
                proposed_start_date,
                proposed_service_days,
                expected_lifecycle_version,
                preview_fingerprint,
                idempotency_key,
                actor,
                reason,
            )
            unit_of_work.commit()
        return receipt

    def preview_completion(self, case_no: str) -> OrderIntakeCompletionPreview:
        return preview_completion_case(self._repository, case_no, for_update=False)

    def apply_completion(
        self,
        case_no: str,
        expected_lifecycle_version: int,
        preview_fingerprint: str,
        idempotency_key: str,
        actor: str,
        reason: str,
    ) -> OrderIntakeCompletionReceipt:
        _validate_command_fields(
            expected_lifecycle_version,
            preview_fingerprint,
            idempotency_key,
            actor,
            reason,
            prefix="order_intake_completion",
        )
        with self._unit_of_work_factory() as unit_of_work:
            receipt = apply_completion_case(
                self._repository,
                case_no,
                expected_lifecycle_version,
                preview_fingerprint,
                idempotency_key,
                actor,
                reason,
            )
            unit_of_work.commit()
        return receipt


def preview_case(
    repository: OrderIntakeTermsBootstrapRepository,
    case_no: str,
    proposed_start_date: date,
    proposed_service_days: int,
    *,
    for_update: bool,
) -> OrderIntakeTermsBootstrapPreview:
    normalized_case_no = str(case_no).strip()
    if not normalized_case_no:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_case_no_required"
        )
    _validate_proposed_terms(proposed_start_date, proposed_service_days)
    facts = repository.load_case(normalized_case_no, for_update=for_update)
    if facts is None:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_case_not_found"
        )

    start_missing = facts.start_date is None
    service_days_missing = _service_days_missing(facts)
    blockers = _blockers(
        facts,
        proposed_start_date,
        proposed_service_days,
        start_missing=start_missing,
        service_days_missing=service_days_missing,
    )
    after_start_date = proposed_start_date if start_missing else facts.start_date
    after_service_days = proposed_service_days if service_days_missing else facts.service_days
    if after_start_date is None or after_service_days is None or after_service_days <= 0:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_current_terms_invalid"
        )
    changed_fields = tuple(
        field
        for field, changed in (
            ("start_date", start_missing),
            ("service_days", service_days_missing),
        )
        if changed
    )
    payload = {
        "case_no": facts.case_no,
        "status": facts.status.value,
        "lifecycle_version": facts.lifecycle_version,
        "before_start_date": _iso(facts.start_date),
        "before_service_days": facts.service_days,
        "after_start_date": after_start_date.isoformat(),
        "after_service_days": after_service_days,
        "actual_start_date": _iso(facts.actual_start_date),
        "service_data_locked": facts.service_data_locked,
        "client_finance_present": facts.client_finance_present,
        "payroll_present": facts.payroll_present,
        "scheduling_present": facts.scheduling_present,
        "scheduling_pristine": facts.scheduling_pristine,
        "changed_fields": changed_fields,
        "blockers": blockers,
    }
    return OrderIntakeTermsBootstrapPreview(
        case_no=facts.case_no,
        lifecycle_version=facts.lifecycle_version,
        before_start_date=facts.start_date,
        before_service_days=facts.service_days,
        after_start_date=after_start_date,
        after_service_days=after_service_days,
        changed_fields=changed_fields,
        blockers=blockers,
        apply_allowed=not blockers,
        preview_fingerprint=fingerprint_payload(payload).value,
    )


def apply_case(
    repository: OrderIntakeTermsBootstrapRepository,
    case_no: str,
    proposed_start_date: date,
    proposed_service_days: int,
    expected_lifecycle_version: int,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
) -> OrderIntakeTermsBootstrapReceipt:
    _validate_proposed_terms(proposed_start_date, proposed_service_days)
    request_fingerprint = fingerprint_payload(
        {
            "case_no": str(case_no).strip(),
            "proposed_start_date": proposed_start_date.isoformat(),
            "proposed_service_days": proposed_service_days,
            "expected_lifecycle_version": expected_lifecycle_version,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor.strip(),
            "reason": reason.strip(),
        }
    ).value
    stored = repository.load_receipt(_FAMILY, idempotency_key)
    if stored is not None:
        if stored["request_fingerprint"] != request_fingerprint:
            raise OrderIntakeTermsBootstrapError(
                "order_intake_terms_bootstrap_idempotency_key_conflict"
            )
        return _receipt_from_snapshot(stored["result_snapshot"], replayed=True)

    current = preview_case(
        repository,
        case_no,
        proposed_start_date,
        proposed_service_days,
        for_update=True,
    )
    if current.lifecycle_version != expected_lifecycle_version:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_stale_preview"
        )
    if current.preview_fingerprint != preview_fingerprint:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_stale_preview"
        )
    if not current.apply_allowed:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_blocked",
            blockers=current.blockers,
        )

    new_version = repository.update_missing_terms(
        current.case_no,
        current.lifecycle_version,
        current.after_start_date,
        current.after_service_days,
        fill_start_date="start_date" in current.changed_fields,
        fill_service_days="service_days" in current.changed_fields,
    )
    readback = repository.load_case(current.case_no, for_update=True)
    if (
        readback is None
        or readback.lifecycle_version != new_version
        or readback.start_date != current.after_start_date
        or readback.service_days != current.after_service_days
        or readback.status is not OrderLifecycleStatus.PENDING_COMPLETION
    ):
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_readback_failed"
        )

    receipt = OrderIntakeTermsBootstrapReceipt(
        receipt_key=idempotency_key,
        case_no=current.case_no,
        lifecycle_version=new_version,
        start_date=current.after_start_date,
        service_days=current.after_service_days,
        changed_fields=current.changed_fields,
        preview_fingerprint=current.preview_fingerprint,
        replayed=False,
    )
    repository.save_receipt(
        _FAMILY,
        idempotency_key,
        request_fingerprint,
        preview_fingerprint,
        actor.strip(),
        reason.strip(),
        _receipt_payload(receipt),
    )
    return receipt


def preview_completion_case(
    repository: OrderIntakeTermsBootstrapRepository,
    case_no: str,
    *,
    for_update: bool,
) -> OrderIntakeCompletionPreview:
    normalized_case_no = str(case_no).strip()
    if not normalized_case_no:
        raise OrderIntakeTermsBootstrapError("order_intake_completion_case_no_required")
    facts = repository.load_case(normalized_case_no, for_update=for_update)
    if facts is None:
        raise OrderIntakeTermsBootstrapError("order_intake_completion_case_not_found")
    missing_fields = _completion_missing_fields(facts)
    blockers = _completion_blockers(facts)
    payload = {
        "case_no": facts.case_no,
        "lifecycle_version": facts.lifecycle_version,
        "current_status": facts.status.value,
        "target_status": OrderLifecycleStatus.DISCUSSION.value,
        "client_name": facts.client_name,
        "start_date": _iso(facts.start_date),
        "service_days": facts.service_days,
        "actual_start_date": _iso(facts.actual_start_date),
        "service_data_locked": facts.service_data_locked,
        "client_finance_present": facts.client_finance_present,
        "payroll_present": facts.payroll_present,
        "scheduling_present": facts.scheduling_present,
        "scheduling_pristine": facts.scheduling_pristine,
        "missing_fields": missing_fields,
        "blockers": blockers,
    }
    return OrderIntakeCompletionPreview(
        case_no=facts.case_no,
        lifecycle_version=facts.lifecycle_version,
        current_status=facts.status,
        target_status=OrderLifecycleStatus.DISCUSSION,
        missing_fields=missing_fields,
        blockers=blockers,
        apply_allowed=not missing_fields and not blockers,
        preview_fingerprint=fingerprint_payload(payload).value,
    )


def apply_completion_case(
    repository: OrderIntakeTermsBootstrapRepository,
    case_no: str,
    expected_lifecycle_version: int,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
) -> OrderIntakeCompletionReceipt:
    request_fingerprint = fingerprint_payload(
        {
            "case_no": str(case_no).strip(),
            "expected_lifecycle_version": expected_lifecycle_version,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor.strip(),
            "reason": reason.strip(),
        }
    ).value
    stored = repository.load_receipt(_COMPLETION_FAMILY, idempotency_key)
    if stored is not None:
        if stored["request_fingerprint"] != request_fingerprint:
            raise OrderIntakeTermsBootstrapError(
                "order_intake_completion_idempotency_key_conflict"
            )
        return _completion_receipt_from_snapshot(
            stored["result_snapshot"], replayed=True
        )

    current = preview_completion_case(repository, case_no, for_update=True)
    if current.lifecycle_version != expected_lifecycle_version:
        raise OrderIntakeTermsBootstrapError("order_intake_completion_stale_preview")
    if current.preview_fingerprint != preview_fingerprint:
        raise OrderIntakeTermsBootstrapError("order_intake_completion_stale_preview")
    if not current.apply_allowed:
        combined = tuple(
            f"order_intake_completion_{field}_missing"
            for field in current.missing_fields
        ) + current.blockers
        raise OrderIntakeTermsBootstrapError(
            "order_intake_completion_blocked", blockers=combined
        )

    new_version = repository.complete_intake(
        current.case_no,
        current.lifecycle_version,
    )
    readback = repository.load_case(current.case_no, for_update=True)
    if (
        readback is None
        or readback.lifecycle_version != new_version
        or readback.status is not OrderLifecycleStatus.DISCUSSION
        or _completion_missing_fields(readback)
    ):
        raise OrderIntakeTermsBootstrapError("order_intake_completion_readback_failed")

    receipt = OrderIntakeCompletionReceipt(
        receipt_key=idempotency_key,
        case_no=current.case_no,
        lifecycle_version=new_version,
        status=OrderLifecycleStatus.DISCUSSION,
        preview_fingerprint=current.preview_fingerprint,
        replayed=False,
    )
    repository.save_receipt(
        _COMPLETION_FAMILY,
        idempotency_key,
        request_fingerprint,
        preview_fingerprint,
        actor.strip(),
        reason.strip(),
        _completion_receipt_payload(receipt),
    )
    return receipt


def _blockers(
    facts: OrderIntakeTermsBootstrapFacts,
    proposed_start_date: date,
    proposed_service_days: int,
    *,
    start_missing: bool,
    service_days_missing: bool,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if facts.status is not OrderLifecycleStatus.PENDING_COMPLETION:
        blockers.append("order_intake_terms_bootstrap_status_not_eligible")
    if facts.actual_start_date is not None:
        blockers.append("order_intake_terms_bootstrap_actual_start_exists")
    if facts.service_data_locked:
        blockers.append("order_intake_terms_bootstrap_service_data_locked")
    if facts.client_finance_present:
        blockers.append("order_intake_terms_bootstrap_client_finance_exists")
    if facts.payroll_present:
        blockers.append("order_intake_terms_bootstrap_payroll_exists")
    if facts.scheduling_present and not facts.scheduling_pristine:
        blockers.append("order_intake_terms_bootstrap_scheduling_not_pristine")
    if facts.service_days is not None and facts.service_days < 0:
        blockers.append("order_intake_terms_bootstrap_current_service_days_invalid")
    if not start_missing and facts.start_date != proposed_start_date:
        blockers.append("order_intake_terms_bootstrap_start_date_already_set")
    if not service_days_missing and facts.service_days != proposed_service_days:
        blockers.append("order_intake_terms_bootstrap_service_days_already_set")
    if not start_missing and not service_days_missing:
        blockers.append("order_intake_terms_bootstrap_nothing_missing")
    return tuple(sorted(set(blockers)))


def _completion_missing_fields(
    facts: OrderIntakeTermsBootstrapFacts,
) -> tuple[str, ...]:
    missing: list[str] = []
    if facts.client_name is None or not facts.client_name.strip():
        missing.append("client_name")
    if facts.start_date is None:
        missing.append("start_date")
    if _service_days_missing(facts):
        missing.append("service_days")
    return tuple(missing)


def _completion_blockers(
    facts: OrderIntakeTermsBootstrapFacts,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if facts.status is not OrderLifecycleStatus.PENDING_COMPLETION:
        blockers.append("order_intake_completion_status_not_eligible")
    if facts.actual_start_date is not None:
        blockers.append("order_intake_completion_actual_start_exists")
    if facts.service_data_locked:
        blockers.append("order_intake_completion_service_data_locked")
    if facts.client_finance_present:
        blockers.append("order_intake_completion_client_finance_exists")
    if facts.payroll_present:
        blockers.append("order_intake_completion_payroll_exists")
    if facts.scheduling_present and not facts.scheduling_pristine:
        blockers.append("order_intake_completion_scheduling_not_pristine")
    if facts.service_days is not None and facts.service_days < 0:
        blockers.append("order_intake_completion_current_service_days_invalid")
    return tuple(sorted(set(blockers)))


def _service_days_missing(facts: OrderIntakeTermsBootstrapFacts) -> bool:
    if facts.service_days is None:
        return True
    return facts.service_days == 0 and facts.start_date is None


def _validate_proposed_terms(start_date: date, service_days: int) -> None:
    if type(start_date) is not date:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_start_date_invalid"
        )
    if isinstance(service_days, bool) or not isinstance(service_days, int) or service_days <= 0:
        raise OrderIntakeTermsBootstrapError(
            "order_intake_terms_bootstrap_service_days_invalid"
        )


def _validate_command_fields(
    expected_lifecycle_version: int,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
    *,
    prefix: str,
) -> None:
    if (
        isinstance(expected_lifecycle_version, bool)
        or not isinstance(expected_lifecycle_version, int)
        or expected_lifecycle_version < 0
    ):
        raise OrderIntakeTermsBootstrapError(f"{prefix}_expected_version_invalid")
    fingerprint = str(preview_fingerprint)
    if len(fingerprint) != 64 or any(character not in "0123456789abcdef" for character in fingerprint):
        raise OrderIntakeTermsBootstrapError(f"{prefix}_preview_fingerprint_invalid")
    if not idempotency_key.strip():
        raise OrderIntakeTermsBootstrapError(f"{prefix}_idempotency_key_required")
    if not actor.strip():
        raise OrderIntakeTermsBootstrapError(f"{prefix}_actor_required")
    if not reason.strip():
        raise OrderIntakeTermsBootstrapError(f"{prefix}_reason_required")


def _receipt_payload(receipt: OrderIntakeTermsBootstrapReceipt) -> dict[str, object]:
    return {
        "receipt_key": receipt.receipt_key,
        "case_no": receipt.case_no,
        "lifecycle_version": receipt.lifecycle_version,
        "start_date": receipt.start_date.isoformat(),
        "service_days": receipt.service_days,
        "changed_fields": list(receipt.changed_fields),
        "preview_fingerprint": receipt.preview_fingerprint,
    }


def _receipt_from_snapshot(snapshot, *, replayed: bool) -> OrderIntakeTermsBootstrapReceipt:
    payload = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return OrderIntakeTermsBootstrapReceipt(
        receipt_key=str(payload["receipt_key"]),
        case_no=str(payload["case_no"]),
        lifecycle_version=int(payload["lifecycle_version"]),
        start_date=date.fromisoformat(str(payload["start_date"])),
        service_days=int(payload["service_days"]),
        changed_fields=tuple(str(value) for value in payload["changed_fields"]),
        preview_fingerprint=str(payload["preview_fingerprint"]),
        replayed=replayed,
    )


def _completion_receipt_payload(
    receipt: OrderIntakeCompletionReceipt,
) -> dict[str, object]:
    return {
        "receipt_key": receipt.receipt_key,
        "case_no": receipt.case_no,
        "lifecycle_version": receipt.lifecycle_version,
        "status": receipt.status.value,
        "preview_fingerprint": receipt.preview_fingerprint,
    }


def _completion_receipt_from_snapshot(
    snapshot,
    *,
    replayed: bool,
) -> OrderIntakeCompletionReceipt:
    payload = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return OrderIntakeCompletionReceipt(
        receipt_key=str(payload["receipt_key"]),
        case_no=str(payload["case_no"]),
        lifecycle_version=int(payload["lifecycle_version"]),
        status=OrderLifecycleStatus(str(payload["status"])),
        preview_fingerprint=str(payload["preview_fingerprint"]),
        replayed=replayed,
    )


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "OrderIntakeCompletionPreview",
    "OrderIntakeCompletionReceipt",
    "OrderIntakeTermsBootstrapApplication",
    "OrderIntakeTermsBootstrapError",
    "OrderIntakeTermsBootstrapFacts",
    "OrderIntakeTermsBootstrapPreview",
    "OrderIntakeTermsBootstrapReceipt",
    "OrderIntakeTermsBootstrapRepository",
    "apply_case",
    "apply_completion_case",
    "preview_case",
    "preview_completion_case",
]
