"""
File: case_manual_supplement.py
Description: 案件抽屜手動補登並自動銷帳應用服務，自動將選定操作銀行、方向、期款轉化為標準規格對帳單明細並完成領域銷帳。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import ContextManager, Mapping, Protocol, TypedDict
from domains.client_finance.reconciliation import PaymentStage
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    MySqlClientReceiptReconciliationRepository,
)
from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
from infrastructure.mysql.staff_payout_repository import MySqlStaffPayoutRepository
from domains.staff_payables.reconciliation import StaffPayoutDifferenceMode, StaffPayoutEventType
from subsystems.staff_payables.payout_reconciliation import (
    ManualStaffPayoutSource, StaffPayoutApplyRequest, StaffPayoutReconciliationWorkflow, StaffPayoutSelection,
)
from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationWorkflow, ReconciliationSelection,
)
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest, ClientRefundReversalSelection,
    ClientRefundReversalWorkflow, ManualClientRefundSource,
)
from subsystems.finance_import.statement_archive import StatementCommandConflict


def _bank_references(bank, reason, cancellation_code, memo, *, allow_overage_disposition=False,
                     manual_command=None):
    # Sinopac's canonical parser reads the original reference column; storing
    # only the row-level cancellation_code would make the owner reject it.
    references = {"source": "manual_supplement", "bank": bank, "reason": reason,
                  "銷帳編號": cancellation_code, "備註": memo}
    if allow_overage_disposition:
        references["allow_overage_disposition"] = True
    if manual_command is not None:
        references["manual_command"] = dict(manual_command)
        references["manual_command_digest"] = fingerprint_payload(manual_command).value
    return references


def _supplement_command(case_no, bank, direction, target_item, amount_ntd,
                        transaction_date, reason, actor, *, allow_overage_disposition=False):
    command = {
        "case_no": case_no, "bank": bank, "direction": direction,
        "target_item": target_item, "amount_ntd": amount_ntd,
        "transaction_date": transaction_date, "reason": reason, "actor": actor,
    }
    # Omission means false, preserving receipts saved before this option existed.
    if allow_overage_disposition:
        command["allow_overage_disposition"] = True
    return command


def _replay_reason(command, stored_digest):
    if stored_digest == fingerprint_payload(command).value:
        return None
    # A former no-intent command can never authorize a new overage disposition.
    if command.get("allow_overage_disposition", False):
        raise StatementCommandConflict("idempotency_conflict")
    legacy_note = command["reason"] or "人工補登"
    legacy_digest = hashlib.sha256(
        (f"{command['case_no']}:{command['bank']}:{command['direction']}:"
         f"{command['target_item']}:{command['amount_ntd']}:{command['transaction_date']}:"
         f"{legacy_note}:{command['actor']}").encode()
    ).hexdigest()
    if stored_digest == legacy_digest:
        return legacy_note
    raise StatementCommandConflict("idempotency_conflict")


class ManualSupplementBlocked(ValueError):
    """A known owner blocker; the caller must roll back the whole command."""

    def __init__(self, code: str):
        self.error = TypedError(
            ErrorCategory.DOMAIN_BLOCKED, code,
            ("政府補助入款請從銀行對帳選取原政府流水，進入政府整期核對。"
             if code == "government_subsidy_period_selection_required"
             else "Manual supplement requires review before posting."),
            CorrelationId("finance-manual-supplement"), domain_blockers=(code,),
        )
        super().__init__(code)


@dataclass(frozen=True)
class ManualSupplementResult:
    case_no: str
    row_id: int
    entry_id: int
    direction: str
    target_item: str
    amount_ntd: int
    reconciled: bool


class ManualSupplementTarget(TypedDict, total=False):
    obligation_type: str
    remaining_ntd: int
    staff_id: int


class ManualSupplementStoredCommand(TypedDict):
    command_digest: str
    result_identity: str


@dataclass(frozen=True)
class ManualSupplementSourceRow:
    """The existing fourteen source columns, in their original INSERT order."""
    dedup_fingerprint: str
    format_id: str
    transaction_date: str
    direction: str
    credit: int | None
    debit: int | None
    summary: str
    memo: str
    cancellation_code: str
    bank_references: str
    warnings: str
    classification_type: str
    reconciliation_status: str
    raw_payload: str

    @property
    def values(self) -> tuple[object, ...]:
        return (self.dedup_fingerprint, self.format_id, self.transaction_date, self.direction,
                self.credit, self.debit, self.summary, self.memo, self.cancellation_code,
                self.bank_references, self.warnings, self.classification_type,
                self.reconciliation_status, self.raw_payload)


@dataclass(frozen=True)
class ManualSupplementReplayFacts:
    row_id: int
    source: Mapping[str, object]


class ManualSupplementSourceSession(Protocol):
    def require_case(self, case_no: str) -> None: ...
    def find_command(self, key: str) -> ManualSupplementStoredCommand | None: ...
    def lock_target(self, case_no: str, direction: str, target_item: str) -> ManualSupplementTarget: ...
    def resolve_virtual_account(self, case_no: str) -> Mapping[str, object]: ...
    def append_source(self, row: ManualSupplementSourceRow) -> int: ...
    def posted_entry_id(self, direction: str, case_no: str, row_id: int, target_item: str, obligation_type: str | None) -> int: ...
    def save_command(self, key: str, digest: str, row_id: int, actor: str) -> None: ...
    def load_replay_source(self, identity: str) -> ManualSupplementReplayFacts: ...
    def load_replay_entries(self, row_id: int, command: Mapping[str, object]) -> tuple[Mapping[str, object], ...]: ...


class ManualSupplementSourceStore(Protocol):
    def session(self) -> ContextManager[ManualSupplementSourceSession]: ...


def _replay_result(store: ManualSupplementSourceSession, result_identity, command, *, legacy_reason=None):
    facts = store.load_replay_source(result_identity)
    row_id, source = facts.row_id, facts.source
    case_no, direction = command["case_no"], command["direction"]
    references = source["bank_references"]
    if isinstance(references, str):
        references = json.loads(references)
    expected_reason = command["reason"] if legacy_reason is None else legacy_reason
    source_amount = source["credit"] if direction in {"client_receipt", "government_subsidy"} else source["debit"]
    if (
        source["format_id"] != command["bank"]
        or str(source["transaction_date"]) != command["transaction_date"]
        or not isinstance(references, dict)
        or references.get("source") != "manual_supplement"
        or references.get("reason") != expected_reason
        or references.get("allow_overage_disposition", False) is not command.get("allow_overage_disposition", False)
        or source_amount is None
        or int(source_amount) != command["amount_ntd"]
    ):
        raise StatementCommandConflict("idempotency_conflict")
    rows = store.load_replay_entries(row_id, command)
    if len(rows) != 1:
        raise StatementCommandConflict("manual_supplement_receipt_invalid")
    original = rows[0]
    if direction == "client_refund" and original["entry_type"] != (
        "subsidy_return" if original["obligation_type"] == "subsidy_return" else "refund"
    ):
        raise StatementCommandConflict("manual_supplement_receipt_invalid")
    if (
        int(original["amount_ntd"]) != command["amount_ntd"]
        or original["actor"] != command["actor"]
        or (direction != "government_subsidy" and original["target_item"] != command["target_item"])
    ):
        raise StatementCommandConflict("idempotency_conflict")
    return ManualSupplementResult(
        case_no, row_id, int(original["entry_id"]), direction,
        command["target_item"] if direction == "government_subsidy" else str(original["target_item"]),
        int(original["amount_ntd"]), True,
    )


class CaseManualSupplementService:
    """案件手動補登核心服務。在單一事務內建立標準對帳單明細並調用各領域核銷。"""

    def __init__(self, connection, *, source_store: ManualSupplementSourceStore | None = None):
        self.connection = connection
        if source_store is None:
            # The concrete adapter imports this module's typed port records.
            from infrastructure.mysql.case_manual_supplement_source_store import MySqlManualSupplementSourceStore
            source_store = MySqlManualSupplementSourceStore(connection)
        self.source_store = source_store

    def execute(
        self,
        case_no: str,
        bank: str,
        direction: str,
        target_item: str,
        amount_ntd: int,
        transaction_date: str,
        reason: str | None,
        idempotency_key: str,
        actor: str,
        allow_overage_disposition: bool = False,
    ) -> ManualSupplementResult:
        if bank not in {"sinopac", "taishin"}:
            raise ValueError(f"不支援的操作銀行: {bank}")
        if direction not in {"client_receipt", "staff_salary", "client_refund", "government_subsidy"}:
            raise ValueError(f"不支援的交易方向: {direction}")
        if not isinstance(allow_overage_disposition, bool) or (allow_overage_disposition and direction not in {"client_receipt", "client_refund"}):
            raise ValueError("invalid_client_receipt_intent")
        if amount_ntd <= 0:
            raise ValueError("補登金額必須大於 0")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", transaction_date):
            raise ValueError("交易日期格式必須為 YYYY-MM-DD")
        if not idempotency_key.strip():
            raise ValueError("缺少冪等鍵 (Idempotency-Key)")
        if not target_item.strip():
            raise ValueError("缺少沖銷對象／期款代碼")

        note_text = (reason or "").strip()
        command = _supplement_command(
            case_no, bank, direction, target_item, amount_ntd, transaction_date, note_text, actor,
            allow_overage_disposition=allow_overage_disposition,
        )

        with self.source_store.session() as source:
            source.require_case(case_no)
            cmd_digest = fingerprint_payload(command).value
            existing = source.find_command(idempotency_key)
            if existing:
                # Old receipts used a delimiter-based digest and a generated
                # default reason. Accept them only after checking original facts.
                return _replay_result(
                    source, existing["result_identity"], command,
                    legacy_reason=_replay_reason(command, existing["command_digest"]),
                )

            if direction == "government_subsidy":
                raise ManualSupplementBlocked("government_subsidy_period_selection_required")

            # Replay precedes mutable balance/status checks: a settled target can replay.
            target = source.lock_target(case_no, direction, target_item)
            if direction == "client_refund" and target["obligation_type"] == "subsidy_return" and allow_overage_disposition:
                raise ManualSupplementBlocked("invalid_client_refund_intent")
            resolution = source.resolve_virtual_account(case_no)
            if resolution["result"] != "resolved":
                raise ManualSupplementBlocked(str(resolution["reason"]))
            virtual_account = str(resolution["virtual_account"])
            case_suffix = virtual_account[-6:]
            if (direction in {"staff_salary", "client_refund"} and amount_ntd > int(target["remaining_ntd"])
                and not (direction == "client_refund" and allow_overage_disposition)):
                code = "staff_payout_difference_mode_invalid" if direction == "staff_salary" else "allocation_exceeds_obligation"
                raise ManualSupplementBlocked(code)

            # 3. 建立標準對帳單明細 (finance_import_rows)
            row_fp = hashlib.sha256(
                f"manual-supplement:{case_no}:{bank}:{direction}:{amount_ntd}:{transaction_date}:{idempotency_key}".encode()
            ).hexdigest()

            is_incoming = direction == "client_receipt"
            cancellation_code = virtual_account if direction == "client_receipt" else ""
            memo = (
                f"HC{case_suffix}服務人員"
                if direction == "staff_salary"
                else f"HC{case_suffix}退款"
                if direction == "client_refund"
                else note_text
            )
            classification = (
                "client_receipt"
                if direction == "client_receipt"
                else "staff_payout"
                if direction == "staff_salary"
                else "client_refund"
            )
            if direction == "client_refund" and target["obligation_type"] == "subsidy_return":
                classification = "client_subsidy_return"
            date_slash = transaction_date.replace("-", "/")
            raw_payload = {
                "帳號": None,
                "交易日": date_slash,
                "計息日": date_slash,
                "入帳日": date_slash,
                "摘要": "人工補登",
                "幣別": "TWD",
                "支出": "" if is_incoming else amount_ntd,
                "存入": amount_ntd if is_incoming else "",
                "餘額": "",
                "票據號碼": "",
                "銷帳編號": cancellation_code,
                "交易參考編號": f"MANUAL-{idempotency_key[:16]}",
                "備註": memo,
                "更正註記": "",
                "存摺備註": "",
            }

            row_id = source.append_source(ManualSupplementSourceRow(
                row_fp,
                bank,
                transaction_date,
                "incoming" if is_incoming else "outgoing",
                amount_ntd if is_incoming else None,
                None if is_incoming else amount_ntd,
                "人工補登",
                memo,
                cancellation_code,
                json.dumps(
                    _bank_references(bank, note_text, cancellation_code, memo,
                                     allow_overage_disposition=allow_overage_disposition,
                                     manual_command=command if direction in {"client_refund", "staff_salary"} else None),
                    ensure_ascii=False,
                ),
                "[]",
                classification,
                "pending" if direction in {"client_receipt", "client_refund", "staff_salary"} else "reconciled",
                json.dumps(raw_payload, ensure_ascii=False),
            ))

            # 4. 領域核銷連動
            entry_id = 0
            if direction == "client_receipt":
                self._post_client_receipt(
                    case_no, row_id, target_item, target["obligation_type"],
                    idempotency_key, actor, note_text,
                    allow_overage_disposition=allow_overage_disposition,
                )

            elif direction == "staff_salary":
                self._post_staff_payout(
                    case_no, row_id, target_item, int(target["staff_id"]), amount_ntd,
                    int(target["remaining_ntd"]), transaction_date, idempotency_key, actor, note_text, cmd_digest,
                )

            elif direction == "client_refund":
                self._post_client_refund(
                    case_no, row_id, target_item, amount_ntd, transaction_date,
                    idempotency_key, actor, note_text, cmd_digest,
                    allow_overage_disposition=allow_overage_disposition,
                    refund_purpose=(ClientRefundPurpose.SUBSIDY_RETURN if target["obligation_type"] == "subsidy_return"
                                    else ClientRefundPurpose.CUSTOMER_REFUND),
                )

            entry_id = source.posted_entry_id(direction, case_no, row_id, target_item, target.get("obligation_type"))
            source.save_command(idempotency_key, cmd_digest, row_id, actor)

        return ManualSupplementResult(
            case_no=case_no,
            row_id=row_id,
            entry_id=entry_id,
            direction=direction,
            target_item=target_item,
            amount_ntd=amount_ntd,
            reconciled=True,
        )


    def _post_client_receipt(self, case_no, row_id, target_item, obligation_type, key, actor, reason,
                             *, allow_overage_disposition=False):
        repository = MySqlClientReceiptReconciliationRepository(self.connection)
        workflow = ClientReconciliationWorkflow(repository, BorrowedTransactionUnitOfWork)
        selection = ReconciliationSelection(
            case_no, PaymentStage(obligation_type), (str(row_id),), (target_item,),
            allow_overage_disposition=allow_overage_disposition,
            allow_partial_receipt=not allow_overage_disposition,
        )
        preview = workflow.preview(selection)
        request = ClientReconciliationApplyRequest(
            selection, ExpectedVersion(preview.account_version), preview.fingerprint,
            IdempotencyKey("manual-client-receipt:" + hashlib.sha256(key.encode()).hexdigest()),
            ActorContext(actor), reason, CorrelationId("finance-manual-supplement"),
        )
        repository.bind_apply_request(request)
        try:
            return workflow.apply(request)
        except ValueError as error:
            if str(error) == "client_refund_recipient_snapshot_missing":
                raise ManualSupplementBlocked(str(error)) from error
            raise
        finally:
            repository.clear_apply_request()

    def _post_staff_payout(self, case_no, row_id, target_item, staff_id, amount_ntd, remaining_ntd,
                           transaction_date, key, actor, reason, command_digest):
        context = ManualStaffPayoutSource(int(row_id), case_no, target_item, staff_id, amount_ntd,
            transaction_date, ActorContext(actor), command_digest, reason)
        repository = MySqlStaffPayoutRepository(self.connection, manual_source=context)
        workflow = StaffPayoutReconciliationWorkflow(repository, BorrowedTransactionUnitOfWork)
        selection = StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(row_id),), (target_item,),
            difference_mode=StaffPayoutDifferenceMode.UNDERPAYMENT if amount_ntd < remaining_ntd else None)
        correlation = CorrelationId("finance-manual-supplement")
        preview = workflow.preview(selection, correlation)
        request = StaffPayoutApplyRequest(selection, ExpectedVersion(preview.staff_payables_version),
            ExpectedVersion(preview.bank_facts_version), preview.fingerprint,
            IdempotencyKey("manual-staff-payout:" + hashlib.sha256(key.encode()).hexdigest()),
            ActorContext(actor), reason, correlation)
        repository.bind_apply_request(request)
        try:
            return workflow.apply(request)
        finally:
            repository.clear_apply_request()

    def _post_client_refund(self, case_no, row_id, target_item, amount_ntd, transaction_date,
                            key, actor, reason, command_digest, *, allow_overage_disposition=False,
                            refund_purpose=ClientRefundPurpose.CUSTOMER_REFUND):
        context = ManualClientRefundSource(
            int(row_id), case_no, target_item, amount_ntd, transaction_date,
            ActorContext(actor), command_digest, allow_overage_disposition, reason=reason, refund_purpose=refund_purpose,
        )
        repository = MySqlClientRefundReversalRepository(self.connection, manual_source=context)
        workflow = ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork)
        selection = ClientRefundReversalSelection(
            case_no,
            ClientFinanceCorrectionType.REFUND_OVERAGE if allow_overage_disposition else ClientFinanceCorrectionType.REFUND,
            refund_purpose,
            bank_fact_identities=(str(row_id),), obligation_identities=(target_item,),
            allow_partial_refund_recovery=not allow_overage_disposition,
        )
        preview = workflow.preview(selection, CorrelationId("finance-manual-supplement"))
        request = ClientRefundReversalApplyRequest(
            selection, ExpectedVersion(preview.account_version), preview.fingerprint,
            IdempotencyKey("manual-client-refund:" + hashlib.sha256(key.encode()).hexdigest()),
            ActorContext(actor), reason, CorrelationId("finance-manual-supplement"),
        )
        repository.bind_apply_request(request)
        try:
            return workflow.apply(request)
        finally:
            repository.clear_apply_request()
