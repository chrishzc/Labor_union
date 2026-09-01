"""Query/Preview/Apply workflow for the Client Finance payment destination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Callable, ContextManager

from domains.client_finance.payment_destination import (
    ClientPaymentDestination,
    canonical_account_display,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


class PaymentDestinationConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PaymentDestinationPreview:
    current: ClientPaymentDestination | None
    candidate_account_display: str
    expected_revision: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PaymentDestinationApplyRequest:
    account_display: str
    expected_revision: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    actor: ActorContext
    reason: str


@dataclass(frozen=True, slots=True)
class PaymentDestinationReceipt:
    account_display: str
    resulting_revision: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredPaymentDestinationReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: PaymentDestinationReceipt


class PaymentDestinationRepository(Protocol):
    def load_current(self, *, lock: bool = False) -> ClientPaymentDestination | None: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredPaymentDestinationReceipt | None: ...
    def persist(self, request: PaymentDestinationApplyRequest, receipt: PaymentDestinationReceipt, command_fingerprint: PreviewFingerprint) -> None: ...


class UnitOfWork(Protocol):
    def __enter__(self): ...
    def __exit__(self, exc_type, exc, traceback): ...
    def commit(self) -> None: ...


class PaymentDestinationConfigurationApplication:
    def __init__(self, repository: PaymentDestinationRepository, unit_of_work_factory: Callable[[], ContextManager[UnitOfWork]]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self) -> ClientPaymentDestination | None:
        return self._repository.load_current()

    def preview(self, account_display: str, expected_revision: int) -> PaymentDestinationPreview:
        current = self._repository.load_current()
        current_revision = 0 if current is None else current.revision
        if expected_revision != current_revision:
            raise PaymentDestinationConfigurationError("client_payment_destination_stale", "收款帳戶設定已變更，請重新整理。")
        candidate = canonical_account_display(account_display)
        return PaymentDestinationPreview(current, candidate, expected_revision, _preview_fingerprint(candidate, expected_revision))

    def apply(self, request: PaymentDestinationApplyRequest) -> PaymentDestinationReceipt:
        candidate = canonical_account_display(request.account_display)
        reason = canonical_account_display(request.reason)
        command = fingerprint_payload({
            "account_display": candidate,
            "expected_revision": request.expected_revision,
            "preview_fingerprint": request.preview_fingerprint.value,
            "reason": reason,
        })
        with self._unit_of_work_factory() as unit:
            stored = self._repository.find_receipt(request.idempotency_key)
            if stored is not None:
                if stored.command_fingerprint != command:
                    raise PaymentDestinationConfigurationError("client_payment_destination_idempotency_conflict", "相同操作識別碼已用於不同內容。")
                return stored.receipt
            current = self._repository.load_current(lock=True)
            revision = 0 if current is None else current.revision
            if revision != request.expected_revision:
                raise PaymentDestinationConfigurationError("client_payment_destination_stale", "收款帳戶設定已變更，請重新整理。")
            expected_preview = _preview_fingerprint(candidate, revision)
            if expected_preview != request.preview_fingerprint:
                raise PaymentDestinationConfigurationError("client_payment_destination_preview_stale", "預覽內容已失效，請重新預覽。")
            receipt = PaymentDestinationReceipt(candidate, revision + 1, expected_preview)
            self._repository.persist(request, receipt, command)
            unit.commit()
            return receipt


def _preview_fingerprint(account_display: str, expected_revision: int) -> PreviewFingerprint:
    return fingerprint_payload({"account_display": account_display, "expected_revision": expected_revision})

