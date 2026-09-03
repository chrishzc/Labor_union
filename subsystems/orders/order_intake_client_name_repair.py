"""Typed repair for a missing client name on a pending-completion order."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.order_intake_terms_bootstrap import OrderIntakeTermsBootstrapFacts


_FAMILY = "orders_intake_client_name_repair/v1"


@dataclass(frozen=True, slots=True)
class OrderIntakeClientNamePreview:
    case_no: str
    lifecycle_version: int
    before_client_name: str | None
    after_client_name: str
    blockers: tuple[str, ...]
    apply_allowed: bool
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class OrderIntakeClientNameReceipt:
    receipt_key: str
    case_no: str
    lifecycle_version: int
    client_name: str
    preview_fingerprint: str
    replayed: bool


class OrderIntakeClientNameRepairError(Exception):
    def __init__(self, code: str, *, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.blockers = blockers


class OrderIntakeClientNameRepairRepository(Protocol):
    def load_case(
        self,
        case_no: str,
        *,
        for_update: bool,
    ) -> OrderIntakeTermsBootstrapFacts | None: ...

    def update_missing_client_name(self, case_no: str, client_name: str) -> None: ...

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


class OrderIntakeClientNameRepairApplication:
    def __init__(
        self,
        repository: OrderIntakeClientNameRepairRepository,
        unit_of_work_factory: Callable[[], object],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, case_no: str, client_name: str) -> OrderIntakeClientNamePreview:
        return preview_case(self._repository, case_no, client_name, for_update=False)

    def apply(
        self,
        case_no: str,
        client_name: str,
        expected_lifecycle_version: int,
        preview_fingerprint: str,
        idempotency_key: str,
        actor: str,
        reason: str,
    ) -> OrderIntakeClientNameReceipt:
        _validate_command_fields(
            expected_lifecycle_version,
            preview_fingerprint,
            idempotency_key,
            actor,
            reason,
        )
        with self._unit_of_work_factory() as unit_of_work:
            receipt = apply_case(
                self._repository,
                case_no,
                client_name,
                expected_lifecycle_version,
                preview_fingerprint,
                idempotency_key,
                actor,
                reason,
            )
            unit_of_work.commit()
        return receipt


def preview_case(
    repository: OrderIntakeClientNameRepairRepository,
    case_no: str,
    client_name: str,
    *,
    for_update: bool,
) -> OrderIntakeClientNamePreview:
    canonical_case_no = str(case_no).strip()
    if not canonical_case_no:
        raise OrderIntakeClientNameRepairError("order_intake_client_name_case_no_required")
    canonical_name = _validate_client_name(client_name)
    facts = repository.load_case(canonical_case_no, for_update=for_update)
    if facts is None:
        raise OrderIntakeClientNameRepairError("order_intake_client_name_case_not_found")

    blockers: list[str] = []
    if facts.status is not OrderLifecycleStatus.PENDING_COMPLETION:
        blockers.append("order_intake_client_name_status_not_eligible")
    if facts.client_name is not None and facts.client_name.strip():
        blockers.append("order_intake_client_name_already_set")
    normalized_blockers = tuple(sorted(set(blockers)))
    payload = {
        "case_no": facts.case_no,
        "lifecycle_version": facts.lifecycle_version,
        "status": facts.status.value,
        "before_client_name": facts.client_name,
        "after_client_name": canonical_name,
        "blockers": normalized_blockers,
    }
    return OrderIntakeClientNamePreview(
        case_no=facts.case_no,
        lifecycle_version=facts.lifecycle_version,
        before_client_name=facts.client_name,
        after_client_name=canonical_name,
        blockers=normalized_blockers,
        apply_allowed=not normalized_blockers,
        preview_fingerprint=fingerprint_payload(payload).value,
    )


def apply_case(
    repository: OrderIntakeClientNameRepairRepository,
    case_no: str,
    client_name: str,
    expected_lifecycle_version: int,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
) -> OrderIntakeClientNameReceipt:
    canonical_name = _validate_client_name(client_name)
    request_fingerprint = fingerprint_payload(
        {
            "case_no": str(case_no).strip(),
            "client_name": canonical_name,
            "expected_lifecycle_version": expected_lifecycle_version,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor.strip(),
            "reason": reason.strip(),
        }
    ).value
    stored = repository.load_receipt(_FAMILY, idempotency_key)
    if stored is not None:
        if stored["request_fingerprint"] != request_fingerprint:
            raise OrderIntakeClientNameRepairError(
                "order_intake_client_name_idempotency_key_conflict"
            )
        return _receipt_from_snapshot(stored["result_snapshot"], replayed=True)

    current = preview_case(
        repository,
        case_no,
        canonical_name,
        for_update=True,
    )
    if current.lifecycle_version != expected_lifecycle_version:
        raise OrderIntakeClientNameRepairError("order_intake_client_name_stale_preview")
    if current.preview_fingerprint != preview_fingerprint:
        raise OrderIntakeClientNameRepairError("order_intake_client_name_stale_preview")
    if not current.apply_allowed:
        raise OrderIntakeClientNameRepairError(
            "order_intake_client_name_blocked",
            blockers=current.blockers,
        )

    repository.update_missing_client_name(current.case_no, canonical_name)
    readback = repository.load_case(current.case_no, for_update=True)
    if (
        readback is None
        or readback.lifecycle_version != current.lifecycle_version
        or readback.status is not OrderLifecycleStatus.PENDING_COMPLETION
        or readback.client_name != canonical_name
    ):
        raise OrderIntakeClientNameRepairError("order_intake_client_name_readback_failed")

    receipt = OrderIntakeClientNameReceipt(
        receipt_key=idempotency_key,
        case_no=current.case_no,
        lifecycle_version=current.lifecycle_version,
        client_name=canonical_name,
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


def _validate_client_name(client_name: str) -> str:
    if not isinstance(client_name, str):
        raise OrderIntakeClientNameRepairError("order_intake_client_name_invalid")
    canonical = client_name.strip()
    if not canonical or canonical != client_name or len(canonical) > 100:
        raise OrderIntakeClientNameRepairError("order_intake_client_name_invalid")
    return canonical


def _validate_command_fields(
    expected_lifecycle_version: int,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
) -> None:
    if (
        isinstance(expected_lifecycle_version, bool)
        or not isinstance(expected_lifecycle_version, int)
        or expected_lifecycle_version < 0
    ):
        raise OrderIntakeClientNameRepairError(
            "order_intake_client_name_expected_version_invalid"
        )
    fingerprint = str(preview_fingerprint)
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise OrderIntakeClientNameRepairError(
            "order_intake_client_name_preview_fingerprint_invalid"
        )
    if not idempotency_key.strip():
        raise OrderIntakeClientNameRepairError(
            "order_intake_client_name_idempotency_key_required"
        )
    if not actor.strip():
        raise OrderIntakeClientNameRepairError("order_intake_client_name_actor_required")
    if not reason.strip():
        raise OrderIntakeClientNameRepairError("order_intake_client_name_reason_required")


def _receipt_payload(receipt: OrderIntakeClientNameReceipt) -> dict[str, object]:
    return {
        "receipt_key": receipt.receipt_key,
        "case_no": receipt.case_no,
        "lifecycle_version": receipt.lifecycle_version,
        "client_name": receipt.client_name,
        "preview_fingerprint": receipt.preview_fingerprint,
    }


def _receipt_from_snapshot(snapshot, *, replayed: bool) -> OrderIntakeClientNameReceipt:
    payload = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return OrderIntakeClientNameReceipt(
        receipt_key=str(payload["receipt_key"]),
        case_no=str(payload["case_no"]),
        lifecycle_version=int(payload["lifecycle_version"]),
        client_name=str(payload["client_name"]),
        preview_fingerprint=str(payload["preview_fingerprint"]),
        replayed=replayed,
    )


__all__ = [
    "OrderIntakeClientNamePreview",
    "OrderIntakeClientNameReceipt",
    "OrderIntakeClientNameRepairApplication",
    "OrderIntakeClientNameRepairError",
    "OrderIntakeClientNameRepairRepository",
    "apply_case",
    "preview_case",
]
