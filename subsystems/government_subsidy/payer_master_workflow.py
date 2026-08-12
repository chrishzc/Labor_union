"""Preview/Apply orchestration for versioned government refund accounts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.government_subsidy.payer_master import (
    GovernmentPayerMaster,
    GovernmentPayerMasterError,
    GovernmentRefundAccount,
    GovernmentRefundAccountPreview,
    build_refund_account_preview,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId


@dataclass(frozen=True, slots=True)
class GovernmentRefundAccountApplyRequest:
    account: GovernmentRefundAccount
    preview_fingerprint: PreviewFingerprint
    actor: ActorContext
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class GovernmentRefundAccountReceipt:
    payer_identity: str
    effective_from: str
    account_display: str
    preview_fingerprint: PreviewFingerprint
    replayed: bool


class GovernmentPayerMasterRepository(Protocol):
    def load_master(self, *, lock: bool) -> GovernmentPayerMaster: ...
    def append_account_version(self, account: GovernmentRefundAccount, actor_id: str) -> bool: ...
    def account_display(self, account_number: str) -> str: ...


class UnitOfWork(Protocol):
    def __enter__(self): ...
    def __exit__(self, exception_type, exception, traceback) -> bool: ...
    def commit(self) -> None: ...


class GovernmentPayerMasterWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class GovernmentPayerMasterWorkflow:
    def __init__(self, repository: GovernmentPayerMasterRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self) -> GovernmentPayerMaster:
        return self._repository.load_master(lock=False)

    def account_display(self, account_number: str) -> str:
        return self._repository.account_display(account_number)

    def preview(self, account: GovernmentRefundAccount) -> GovernmentRefundAccountPreview:
        return build_refund_account_preview(self.query(), account)

    def apply(self, request: GovernmentRefundAccountApplyRequest) -> GovernmentRefundAccountReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            preview = build_refund_account_preview(self._repository.load_master(lock=True), request.account)
            if preview.fingerprint != request.preview_fingerprint:
                raise _error(request, "government_payer_account_preview_stale", "退款帳戶主檔在預覽後已變更。")
            replayed = not self._repository.append_account_version(request.account, request.actor.actor_id)
            unit_of_work.commit()
        return GovernmentRefundAccountReceipt(
            preview.payer_identity, request.account.effective_from.isoformat(),
            self._repository.account_display(request.account.account_number), preview.fingerprint, replayed,
        )


def _error(request, code: str, message: str) -> GovernmentPayerMasterWorkflowError:
    return GovernmentPayerMasterWorkflowError(TypedError(ErrorCategory.CONFLICT, code, message, request.correlation_id))
