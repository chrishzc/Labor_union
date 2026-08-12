"""MySQL adapter for the Government Subsidy owning ledger."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
import json
from typing import Any

from pymysql.err import IntegrityError

from domains.government_subsidy.claims import (
    ClaimApprovalCandidate,
    ClaimBatchCursorPage,
    ClaimPlanningCandidate,
    ClaimPlanningFacts,
    ClaimPlanningIntent,
    ClaimPlanningSourceItem,
    ClaimSubmissionCandidate,
    GovernmentSubsidyClaimMutationKind,
)
from domains.government_subsidy.ledger import (
    ClaimBatchFacts,
    ClaimBatchIdentity,
    ClaimItemSnapshot,
    GovernmentBankFact,
    GovernmentSubsidyBankDirection,
    GovernmentSubsidyLedgerCandidate,
    GovernmentSubsidyLedgerKind,
    OfficialAssignmentServiceFacts,
    ReceiptIntent,
    ReversalIntent,
    SourceReceiptAllocationFacts,
    SourceReceiptFacts,
    reduce_batch_status,
)
from domains.government_subsidy.overpayment import GovernmentRecipientSnapshot, GovernmentSubsidyOverpayment, GovernmentSubsidyOverpaymentStatus
from domains.government_subsidy.payer_master import PAYER_IDENTITY, PAYER_NAME
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.ledger_workflow import (
    GovernmentSubsidyApplyRequest,
    GovernmentSubsidyClaimState,
    GovernmentSubsidyCommandReceipt,
    GovernmentSubsidyProjectionCommand,
    GovernmentSubsidyReceiptContext,
    GovernmentSubsidyReceiptPersistenceCommand,
    GovernmentSubsidyReversalContext,
    StoredGovernmentSubsidyReceipt,
)
from subsystems.government_subsidy.claim_workflow import (
    ClaimApprovalApplyRequest,
    ClaimPlanningApplyRequest,
    ClaimSubmissionApplyRequest,
    GovernmentSubsidyClaimApplyRequest,
    GovernmentSubsidyClaimReceipt,
    GovernmentSubsidyClaimReceiptCommand,
    StoredGovernmentSubsidyClaimReceipt,
)
from subsystems.government_subsidy.overpayment_workflow import OffsetApplyRequest, ReceiptWithOverageApplyRequest, ReturnApplyRequest, ReturnReconciliationApplyRequest

_GENERAL_CITIZEN = "一般市民"
_SUBSIDIZED_CITIZEN = "補助市民"
_GENERAL_CITIZEN_UNIT_PRICE_NTD = 300
_SUBSIDIZED_CITIZEN_UNIT_PRICE_NTD = 350


def _advance_overpayment(cursor, request, candidate, event_type, evidence_reference):
    cursor.execute("UPDATE government_subsidy_overpayments SET remaining_amount_ntd=%s,status=%s,projection_version=%s WHERE overpayment_identity=%s AND projection_version=%s", (candidate.remaining_after_ntd.amount, candidate.resulting_status.value, request.expected_version.value + 1, request.identity, request.expected_version.value))
    _require_single_updated_row(cursor)
    cursor.execute("INSERT INTO government_subsidy_overpayment_events (overpayment_identity,event_type,before_remaining_ntd,after_remaining_ntd,resulting_status,expected_version,resulting_version,preview_fingerprint,idempotency_key,actor,reason,evidence_reference) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (request.identity, event_type, candidate.remaining_before_ntd.amount, candidate.remaining_after_ntd.amount, candidate.resulting_status.value, request.expected_version.value, request.expected_version.value + 1, candidate.fingerprint.value, request.idempotency_key.value, request.actor.actor_id, request.reason, evidence_reference))


def _overpayment_receipt(candidate, payable_identity=None):
    return {"overpayment_identity": candidate.overpayment_identity, "remaining_after_ntd": candidate.remaining_after_ntd.amount, "status": candidate.resulting_status.value, "preview_fingerprint": candidate.fingerprint.value, "payable_identity": payable_identity}


def _overpayment_outbox_lineage(cursor, overpayment_identity):
    cursor.execute(
        "SELECT transaction.claim_batch_id,transaction.id transaction_id,"
        "(SELECT event.id FROM government_subsidy_projection_events event "
        "WHERE event.batch_id=transaction.claim_batch_id ORDER BY event.id DESC LIMIT 1) projection_event_id "
        "FROM government_subsidy_overpayments overpayment "
        "JOIN government_subsidy_transactions transaction "
        "ON transaction.id=overpayment.source_transaction_id "
        "WHERE overpayment.overpayment_identity=%s FOR UPDATE",
        (overpayment_identity,),
    )
    row = cursor.fetchone()
    if row is None or row["projection_event_id"] is None:
        raise RuntimeError("government_subsidy_overpayment_lineage_missing")
    return int(row["claim_batch_id"]), int(row["transaction_id"]), int(row["projection_event_id"])


def _apply_offset_target_accounts(cursor, overpayment_event_id, request, candidate):
    amount_by_item = {item.claim_item_id: item.amount_ntd.amount for item in request.intents}
    targets_by_batch = defaultdict(list)
    for target in candidate.offset_targets:
        targets_by_batch[target.claim_batch_id].append(target)
    for batch_id, targets in targets_by_batch.items():
        first = targets[0]
        if any(target.batch_version != first.batch_version for target in targets):
            raise RuntimeError("government_subsidy_overpayment_target_version_conflict")
        amount = sum(amount_by_item[target.claim_item_id] for target in targets)
        after_net = first.batch_net_allocated_amount_ntd.amount + amount
        after_outstanding = first.batch_approved_amount_ntd.amount - after_net
        if after_outstanding < 0:
            raise RuntimeError("government_subsidy_overpayment_amount_exceeded")
        after_status = "paid" if after_outstanding == 0 else "partially_paid"
        cursor.execute(
            "UPDATE government_subsidy_batch_accounts SET net_allocated_ntd=%s,"
            "outstanding_ntd=%s,status=%s,aggregate_version=%s "
            "WHERE batch_id=%s AND aggregate_version=%s",
            (after_net, after_outstanding, after_status, first.batch_version + 1,
             batch_id, first.batch_version),
        )
        _require_single_updated_row(cursor)
        cursor.execute(
            "INSERT INTO government_subsidy_overpayment_target_projection_events "
            "(overpayment_event_id,batch_id,before_net_allocated_ntd,"
            "after_net_allocated_ntd,outstanding_ntd,expected_batch_version,"
            "resulting_batch_version,preview_fingerprint,actor,reason) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (overpayment_event_id, batch_id, first.batch_net_allocated_amount_ntd.amount,
             after_net, after_outstanding, first.batch_version,
             first.batch_version + 1, candidate.fingerprint.value,
             request.actor.actor_id, request.reason),
        )


class MySqlGovernmentSubsidyRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_receipt_context(
        self,
        intent: ReceiptIntent,
        *,
        lock: bool,
    ) -> GovernmentSubsidyReceiptContext:
        with self._connection.cursor() as cursor:
            bank = _load_bank_fact(cursor, intent.finance_import_row_id, lock)
            batches = _load_batches(cursor, intent.batch_id, lock)
        return GovernmentSubsidyReceiptContext(bank, batches)

    def load_reversal_context(
        self,
        intent: ReversalIntent,
        *,
        lock: bool,
    ) -> GovernmentSubsidyReversalContext:
        with self._connection.cursor() as cursor:
            bank = _load_bank_fact(cursor, intent.finance_import_row_id, lock)
            source = _load_source_receipt(
                cursor,
                intent.source_receipt_id,
                lock,
            )
            batch = _load_batch(cursor, source.batch_id, lock)
        return GovernmentSubsidyReversalContext(bank, batch, source)

    def load_overage_receipt_context(self, row_id, batch_id, *, lock):
        with self._connection.cursor() as cursor:
            return _load_bank_fact(cursor, row_id, lock), _load_batch(cursor, batch_id, lock)

    def load_overpayment(self, identity, *, lock):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT overpayment_identity,payer_identity,remaining_amount_ntd,status,projection_version FROM government_subsidy_overpayments WHERE overpayment_identity=%s" + (" FOR UPDATE" if lock else ""), (identity,))
            row=cursor.fetchone()
        if row is None: raise ValueError("government_subsidy_overpayment_not_found")
        return GovernmentSubsidyOverpayment(str(row['overpayment_identity']),str(row['payer_identity']),MoneyNTD(int(row['remaining_amount_ntd'])),GovernmentSubsidyOverpaymentStatus(str(row['status'])),int(row['projection_version']))

    def find_overpayment_apply_receipt(self, idempotency_key, command_fingerprint):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM government_subsidy_overpayment_apply_receipts "
                "WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if str(row["command_fingerprint"]) != command_fingerprint.value:
            raise ValueError("government_subsidy_overpayment_idempotency_mismatch")
        result = json.loads(row["result_snapshot"])
        if not isinstance(result, dict):
            raise RuntimeError("government_subsidy_overpayment_idempotency_evidence_incomplete")
        return result

    def save_overpayment_apply_receipt(self, request, candidate, receipt, command_kind, command_fingerprint):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO government_subsidy_overpayment_apply_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,command_kind,overpayment_identity,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (request.idempotency_key.value, command_fingerprint.value,
                 candidate.fingerprint.value, command_kind, request.identity,
                 _canonical_json(receipt)),
            )

    def load_offset_targets(self, intents, *, lock):
        ids=tuple(item.claim_item_id for item in intents)
        if not ids: return ()
        from domains.government_subsidy.overpayment import GovernmentSubsidyOffsetTarget
        marks=','.join('%s' for _ in ids)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT i.id claim_item_id,i.batch_id,account.aggregate_version,"
                "account.approved_total_ntd,account.net_allocated_ntd,"
                "(i.approved_amount-COALESCE(receipts.net_amount,0)-COALESCE(offsets.offset_amount,0)) outstanding,"
                "batch.submitted_at IS NOT NULL submitted,batch.approved_at IS NOT NULL approved "
                "FROM subsidy_claim_batch_items i "
                "JOIN government_subsidy_batch_accounts account ON account.batch_id=i.batch_id "
                "JOIN subsidy_claim_batches batch ON batch.id=i.batch_id "
                "LEFT JOIN (SELECT claim_item_id,claim_batch_id,SUM(CASE WHEN allocation_type='receipt' THEN allocated_amount WHEN allocation_type='reversal' THEN -allocated_amount ELSE 0 END) net_amount FROM government_subsidy_allocations GROUP BY claim_item_id,claim_batch_id) receipts ON receipts.claim_item_id=i.id AND receipts.claim_batch_id=i.batch_id "
                "LEFT JOIN (SELECT claim_item_id,claim_batch_id,SUM(allocated_amount_ntd) offset_amount FROM government_subsidy_overpayment_offsets GROUP BY claim_item_id,claim_batch_id) offsets ON offsets.claim_item_id=i.id AND offsets.claim_batch_id=i.batch_id "
                f"WHERE i.id IN ({marks})" + (" FOR UPDATE" if lock else ""),
                ids,
            )
            rows=cursor.fetchall()
        return tuple(
            GovernmentSubsidyOffsetTarget(
                int(row["claim_item_id"]), int(row["batch_id"]),
                int(row["aggregate_version"]), MoneyNTD(int(row["approved_total_ntd"])),
                MoneyNTD(int(row["net_allocated_ntd"])), PAYER_IDENTITY,
                MoneyNTD(int(row["outstanding"])), bool(row["submitted"]),
                bool(row["approved"]),
            )
            for row in rows
        )

    def load_return_recipient(self, due_date, evidence_reference, *, lock):
        lock_clause = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT bank_code,account_number,effective_from FROM government_payer_receiving_accounts "
                "WHERE payer_identity=%s AND effective_until IS NULL "
                "ORDER BY effective_from DESC LIMIT 1" + lock_clause,
                (PAYER_IDENTITY,),
            )
            account = cursor.fetchone()
        if account is None:
            raise ValueError("government_subsidy_recipient_account_missing")
        account_number = str(account["account_number"])
        display = "*" * max(0, len(account_number) - 4) + account_number[-4:]
        fingerprint = fingerprint_payload({
            "payer_identity": PAYER_IDENTITY,
            "bank_code": str(account["bank_code"]),
            "account_number": account_number,
            "effective_date": account["effective_from"].isoformat(),
        })
        return GovernmentRecipientSnapshot(
            PAYER_IDENTITY, PAYER_NAME, str(account["bank_code"]), display,
            fingerprint.value, account["effective_from"].isoformat(), due_date,
            evidence_reference,
        )

    def load_return_reconciliation_context(self, identity, finance_import_row_id, *, lock):
        lock_clause = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT overpayment_identity,payer_identity,remaining_amount_ntd,status,projection_version "
                "FROM government_subsidy_overpayments WHERE overpayment_identity=%s" + lock_clause,
                (identity,),
            )
            overpayment = cursor.fetchone()
            cursor.execute(
                "SELECT payable_identity,remaining_amount_ntd,projection_version "
                "FROM government_overpayment_return_payables WHERE overpayment_identity=%s "
                "AND status IN ('payable','partially_paid')" + lock_clause,
                (identity,),
            )
            payable = cursor.fetchone()
            bank = _load_bank_fact(cursor, finance_import_row_id, lock)
            _require_return_recipient_matches_bank(cursor, bank)
        if overpayment is None:
            raise ValueError("government_subsidy_overpayment_not_found")
        if payable is None:
            raise ValueError("government_overpayment_return_not_open")
        return (
            GovernmentSubsidyOverpayment(
                str(overpayment["overpayment_identity"]), str(overpayment["payer_identity"]),
                MoneyNTD(int(overpayment["remaining_amount_ntd"])),
                GovernmentSubsidyOverpaymentStatus(str(overpayment["status"])),
                int(overpayment["projection_version"]),
            ),
            (str(payable["payable_identity"]), MoneyNTD(int(payable["remaining_amount_ntd"])), int(payable["projection_version"])),
            bank,
        )

    def persist_receipt_with_overage(self, request, candidate, bank, batch):
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT INTO government_subsidy_transactions (claim_batch_id,finance_import_row_id,transaction_type,transaction_status,amount,occurred_at,external_reference,expected_batch_version,resulting_batch_version,preview_fingerprint,idempotency_key,actor,reason,correlation_id) VALUES (%s,%s,'receipt','succeeded',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(batch.batch_id,request.finance_import_row_id,bank.amount_ntd.amount,bank.occurred_on,bank.bank_fact_identity,batch.aggregate_version,batch.aggregate_version+1,candidate.fingerprint.value,request.idempotency_key.value,request.actor.actor_id,request.reason,request.correlation_id.value))
            transaction_id=int(cursor.lastrowid)
            cursor.executemany("INSERT INTO government_subsidy_allocations (transaction_id,claim_batch_id,claim_item_id,allocation_type,allocated_amount) VALUES (%s,%s,%s,'receipt',%s)",tuple((transaction_id,batch.batch_id,item.claim_item_id,item.amount_ntd.amount) for item in candidate.allocations))
            cursor.execute(_ACCOUNT_UPDATE_SQL,(batch.requested_total_ntd.amount,batch.approved_total_ntd.amount,candidate.resulting_net_allocated_ntd.amount,candidate.resulting_outstanding_ntd.amount,candidate.resulting_batch_status,batch.aggregate_version+1,batch.batch_id,batch.aggregate_version))
            _require_single_updated_row(cursor)
            identity=f"government-overpayment:{bank.bank_fact_identity}"
            cursor.execute("INSERT INTO government_subsidy_overpayments (overpayment_identity,source_finance_import_row_id,source_transaction_id,payer_identity,original_amount_ntd,remaining_amount_ntd,status,projection_version,actor,reason,evidence_reference) VALUES (%s,%s,%s,%s,%s,%s,'pending_review',1,%s,%s,%s)",(identity,request.finance_import_row_id,transaction_id,PAYER_IDENTITY,candidate.overpayment_amount_ntd.amount,candidate.overpayment_amount_ntd.amount,request.actor.actor_id,request.reason,request.evidence_reference))
            cursor.execute("INSERT INTO government_subsidy_overpayment_events (overpayment_identity,event_type,before_remaining_ntd,after_remaining_ntd,resulting_status,expected_version,resulting_version,preview_fingerprint,idempotency_key,actor,reason,evidence_reference) VALUES (%s,'established',1,%s,'pending_review',0,1,%s,%s,%s,%s,%s)",(identity,candidate.overpayment_amount_ntd.amount,candidate.fingerprint.value,request.idempotency_key.value,request.actor.actor_id,request.reason,request.evidence_reference))
            cursor.execute("INSERT INTO government_subsidy_projection_events (batch_id,transaction_id,before_status,after_status,before_net_allocated_ntd,after_net_allocated_ntd,outstanding_ntd,expected_batch_version,resulting_batch_version,preview_fingerprint,actor,reason,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(batch.batch_id,transaction_id,reduce_batch_status(batch).value,candidate.resulting_batch_status,batch.net_allocated_total_ntd.amount,candidate.resulting_net_allocated_ntd.amount,candidate.resulting_outstanding_ntd.amount,batch.aggregate_version,batch.aggregate_version+1,candidate.fingerprint.value,request.actor.actor_id,request.reason,request.idempotency_key.value))
            projection_event_id=int(cursor.lastrowid)
            cursor.execute(_OUTBOX_INSERT_SQL,(batch.batch_id,transaction_id,projection_event_id,f"government_subsidy_overpayment:{request.idempotency_key.value}",'government_subsidy_overpayment_established',_canonical_json({'overpayment_identity':identity,'amount_ntd':candidate.overpayment_amount_ntd.amount,'payer_identity':PAYER_IDENTITY})))
        return {'overpayment_identity':identity,'transaction_id':transaction_id,'status':'pending_review','amount_ntd':candidate.overpayment_amount_ntd.amount,'preview_fingerprint':candidate.fingerprint.value}

    def persist_offset(self, request: OffsetApplyRequest, candidate):
        with self._connection.cursor() as cursor:
            _advance_overpayment(cursor, request, candidate, "offset_applied", request.evidence_reference)
            lineage = _overpayment_outbox_lineage(cursor, request.identity)
            cursor.execute("SELECT id FROM government_subsidy_overpayment_events WHERE idempotency_key=%s", (request.idempotency_key.value,))
            event_id = int(cursor.fetchone()["id"])
            cursor.executemany(
                "INSERT INTO government_subsidy_overpayment_offsets (overpayment_event_id,overpayment_identity,claim_batch_id,claim_item_id,allocated_amount_ntd) SELECT %s,%s,batch_id,%s,%s FROM subsidy_claim_batch_items WHERE id=%s",
                tuple((event_id, request.identity, item.claim_item_id, item.amount_ntd.amount, item.claim_item_id) for item in request.intents),
            )
            _apply_offset_target_accounts(cursor, event_id, request, candidate)
            cursor.execute(_OUTBOX_INSERT_SQL, (*lineage, f"government_overpayment_offset:{request.idempotency_key.value}", "government_subsidy_overpayment_offset", _canonical_json({"overpayment_identity": request.identity, "remaining_ntd": candidate.remaining_after_ntd.amount})))
        return _overpayment_receipt(candidate)

    def persist_return(self, request: ReturnApplyRequest, candidate, recipient):
        with self._connection.cursor() as cursor:
            _advance_overpayment(cursor, request, candidate, "return_payable_created", recipient.evidence_reference)
            lineage = _overpayment_outbox_lineage(cursor, request.identity)
            payable_identity = f"government-overpayment-return:{request.identity}"
            cursor.execute(
                "INSERT INTO government_overpayment_return_payables (payable_identity,overpayment_identity,amount_due_ntd,remaining_amount_ntd,status,agency_identity,agency_name,bank_code,account_display,account_fingerprint,effective_date,due_date,evidence_reference,projection_version) VALUES (%s,%s,%s,%s,'payable',%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (payable_identity, request.identity, candidate.disposition_amount_ntd.amount, candidate.disposition_amount_ntd.amount, recipient.agency_identity, recipient.agency_name, recipient.bank_code, recipient.account_display, recipient.account_fingerprint, recipient.effective_date, recipient.due_date, recipient.evidence_reference),
            )
            cursor.execute(_OUTBOX_INSERT_SQL, (*lineage, f"government_overpayment_return:{request.idempotency_key.value}", "government_overpayment_return_payable", _canonical_json({"overpayment_identity": request.identity, "payable_identity": payable_identity})))
        return _overpayment_receipt(candidate, payable_identity)

    def persist_return_reconciliation(self, request: ReturnReconciliationApplyRequest, candidate):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE government_overpayment_return_payables SET remaining_amount_ntd=%s,"
                "status=%s,projection_version=projection_version+1 "
                "WHERE payable_identity=%s AND remaining_amount_ntd=%s",
                (candidate.remaining_after_ntd.amount,
                 "paid" if candidate.remaining_after_ntd.amount == 0 else "partially_paid",
                 candidate.payable_identity,
                 candidate.amount_ntd.amount + candidate.remaining_after_ntd.amount),
            )
            _require_single_updated_row(cursor)
            cursor.execute(
                "UPDATE government_subsidy_overpayments SET remaining_amount_ntd=%s,status=%s,"
                "projection_version=%s WHERE overpayment_identity=%s AND projection_version=%s",
                (candidate.remaining_after_ntd.amount, candidate.resulting_status.value,
                 request.expected_version.value + 1, request.identity,
                 request.expected_version.value),
            )
            _require_single_updated_row(cursor)
            cursor.execute(
                "INSERT INTO government_subsidy_overpayment_events "
                "(overpayment_identity,event_type,before_remaining_ntd,after_remaining_ntd,resulting_status,"
                "expected_version,resulting_version,preview_fingerprint,idempotency_key,actor,reason,evidence_reference) "
                "VALUES (%s,'return_reconciled',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (request.identity, candidate.amount_ntd.amount + candidate.remaining_after_ntd.amount,
                 candidate.remaining_after_ntd.amount, candidate.resulting_status.value,
                 request.expected_version.value, request.expected_version.value + 1,
                 candidate.fingerprint.value, request.idempotency_key.value,
                 request.actor.actor_id, request.reason, request.evidence_reference),
            )
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO government_overpayment_return_payouts "
                "(overpayment_event_id,payable_identity,finance_import_row_id,amount_ntd,"
                "preview_fingerprint,idempotency_key,actor,reason,evidence_reference) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (event_id, candidate.payable_identity, request.finance_import_row_id,
                 candidate.amount_ntd.amount, candidate.fingerprint.value,
                 request.idempotency_key.value, request.actor.actor_id, request.reason,
                 request.evidence_reference),
            )
            lineage = _overpayment_outbox_lineage(cursor, request.identity)
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (*lineage, f"government_overpayment_return_reconciliation:{request.idempotency_key.value}",
                 "government_overpayment_return_payout", _canonical_json({
                    "overpayment_identity": request.identity,
                    "payable_identity": candidate.payable_identity,
                    "remaining_ntd": candidate.remaining_after_ntd.amount,
                 })),
            )
        return _overpayment_receipt(candidate)

    def load_batch(
        self,
        batch_id: int,
        *,
        lock: bool = False,
    ) -> ClaimBatchFacts:
        with self._connection.cursor() as cursor:
            return _load_batch(cursor, batch_id, lock)

    def load_claim_planning_facts(
        self,
        intent: ClaimPlanningIntent,
        *,
        lock: bool,
    ) -> ClaimPlanningFacts:
        with self._connection.cursor() as cursor:
            existing_batch_id = _load_existing_batch_id(
                cursor,
                intent,
                lock,
            )
            sources = _load_claim_planning_sources(cursor, intent, lock)
        return ClaimPlanningFacts(intent, sources, existing_batch_id)

    def list_batches(
        self,
        cursor: int | None,
        limit: int,
    ) -> ClaimBatchCursorPage:
        with self._connection.cursor() as database_cursor:
            batch_ids = _load_batch_page_ids(
                database_cursor,
                cursor,
                limit,
            )
            visible_ids, next_cursor = _split_batch_page(batch_ids, limit)
            batches = tuple(
                _load_batch(database_cursor, batch_id, False)
                for batch_id in visible_ids
            )
        return ClaimBatchCursorPage(batches, next_cursor)

    def claim_command(
        self,
        request: GovernmentSubsidyApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> GovernmentSubsidyClaimState:
        with self._connection.cursor() as cursor:
            if _insert_claim(cursor, request, command_fingerprint):
                return GovernmentSubsidyClaimState.CREATED
            claim = _locked_claim(cursor, request.idempotency_key)
        return _claim_state(request, command_fingerprint, claim)

    def find_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredGovernmentSubsidyReceipt | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + lock_clause, (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        return _stored_receipt(row)

    def append_ledger_transaction(
        self,
        request: GovernmentSubsidyApplyRequest,
        candidate: GovernmentSubsidyLedgerCandidate,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _TRANSACTION_INSERT_SQL,
                _transaction_values(request, candidate),
            )
            return int(cursor.lastrowid)

    def append_allocations(
        self,
        transaction_id: int,
        candidate: GovernmentSubsidyLedgerCandidate,
    ) -> tuple[int, ...]:
        with self._connection.cursor() as cursor:
            return tuple(
                _insert_allocation(cursor, transaction_id, candidate, item)
                for item in candidate.allocations
            )

    def update_batch_projection(
        self,
        command: GovernmentSubsidyProjectionCommand,
    ) -> None:
        candidate = command.candidate
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ACCOUNT_UPDATE_SQL,
                _projection_values(candidate),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("government_subsidy_version_conflict")

    def append_projection_event(
        self,
        request: GovernmentSubsidyApplyRequest,
        candidate: GovernmentSubsidyLedgerCandidate,
        transaction_id: int,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PROJECTION_EVENT_INSERT_SQL,
                _projection_event_values(
                    request,
                    candidate,
                    transaction_id,
                ),
            )
            return int(cursor.lastrowid)

    def append_outbox(
        self,
        request: GovernmentSubsidyApplyRequest,
        candidate: GovernmentSubsidyLedgerCandidate,
        transaction_id: int,
        projection_event_id: int,
    ) -> None:
        with self._connection.cursor() as cursor:
            case_by_claim_item = _claim_item_case_numbers(cursor, candidate)
            for values in _outbox_values(
                request,
                candidate,
                transaction_id,
                projection_event_id,
                case_by_claim_item,
            ):
                cursor.execute(_OUTBOX_INSERT_SQL, values)

    def save_receipt(
        self,
        command: GovernmentSubsidyReceiptPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, _receipt_values(command))

    def find_claim_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredGovernmentSubsidyClaimReceipt | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_RECEIPT_SELECT_SQL + lock_clause,
                (key.value,),
            )
            row = cursor.fetchone()
        return None if row is None else _stored_claim_receipt(row)

    def create_claim_batch(
        self,
        request: ClaimPlanningApplyRequest,
        candidate: ClaimPlanningCandidate,
    ) -> int:
        with self._connection.cursor() as cursor:
            batch_id = _insert_claim_batch(cursor, candidate)
            _insert_claim_items(cursor, batch_id, candidate)
            _insert_claim_account(cursor, batch_id, candidate)
        return batch_id

    def append_claim_submission(
        self,
        request: ClaimSubmissionApplyRequest,
        candidate: ClaimSubmissionCandidate,
    ) -> None:
        with self._connection.cursor() as cursor:
            _insert_submission_event(cursor, request, candidate)
            _update_submitted_batch(cursor, candidate)
            _update_claim_account_for_submission(cursor, candidate)

    def append_claim_approval(
        self,
        request: ClaimApprovalApplyRequest,
        candidate: ClaimApprovalCandidate,
    ) -> None:
        with self._connection.cursor() as cursor:
            approval_event_id = _insert_approval_event(
                cursor,
                request,
                candidate,
            )
            _insert_approval_items(cursor, approval_event_id, candidate)
            _update_approved_items(cursor, candidate)
            _update_approved_batch(cursor, candidate)
            _update_claim_account_for_approval(cursor, candidate)

    def append_claim_outbox(
        self,
        request: GovernmentSubsidyClaimApplyRequest,
        candidate,
        batch_id: int,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_OUTBOX_INSERT_SQL,
                _claim_outbox_values(request, candidate, batch_id),
            )

    def save_claim_receipt(
        self,
        command: GovernmentSubsidyClaimReceiptCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_RECEIPT_INSERT_SQL,
                _claim_receipt_values(command),
            )


def _load_existing_batch_id(cursor, intent, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    identity = intent.identity
    cursor.execute(
        _EXISTING_CLAIM_BATCH_SELECT_SQL + lock_clause,
        (
            identity.application_year,
            identity.quarter,
            identity.revision,
        ),
    )
    row = cursor.fetchone()
    return None if row is None else int(row["id"])


def _load_claim_planning_sources(cursor, intent, lock):
    start_date, end_date = _quarter_date_range(intent)
    if lock:
        _lock_claim_planning_rows(cursor, start_date, end_date)
    cursor.execute(
        _CLAIM_PLANNING_SOURCE_SELECT_SQL,
        (start_date, end_date, _GENERAL_CITIZEN, _SUBSIDIZED_CITIZEN),
    )
    rows = cursor.fetchall()
    if not rows:
        raise ValueError("government_subsidy_claim_facts_invalid")
    return tuple(_planning_source(row) for row in rows)


def _lock_claim_planning_rows(cursor, start_date, end_date):
    cursor.execute(
        _CLAIM_PLANNING_LOCK_SQL,
        (
            start_date,
            end_date,
            _GENERAL_CITIZEN,
            _SUBSIDIZED_CITIZEN,
        ),
    )
    cursor.fetchall()


def _quarter_date_range(intent):
    identity = intent.identity
    start_month = (identity.quarter - 1) * 3 + 1
    start_date = date(identity.application_year, start_month, 1)
    if identity.quarter < 4:
        return start_date, date(identity.application_year, start_month + 3, 1)
    return start_date, date(identity.application_year + 1, 1, 1)


def _planning_source(row):
    identity_status = str(row["identity_status"])
    unit_price = _subsidy_unit_price(identity_status)
    return ClaimPlanningSourceItem(
        OfficialAssignmentServiceFacts(
            int(row["assignment_id"]),
            str(row["case_no"]),
            int(row["staff_id"]),
            int(row["official_service_day_count"]),
            int(row["service_hours_per_day"]),
            bool(row["assignment_effective"]),
        ),
        MoneyNTD(unit_price),
    )


def _subsidy_unit_price(identity_status):
    if identity_status == _GENERAL_CITIZEN:
        return _GENERAL_CITIZEN_UNIT_PRICE_NTD
    if identity_status == _SUBSIDIZED_CITIZEN:
        return _SUBSIDIZED_CITIZEN_UNIT_PRICE_NTD
    raise ValueError("government_subsidy_claim_facts_invalid")


def _load_batch_page_ids(cursor, after_batch_id, limit):
    cursor.execute(
        _BATCH_PAGE_SELECT_SQL,
        (after_batch_id or 0, limit + 1),
    )
    return tuple(int(row["batch_id"]) for row in cursor.fetchall())


def _split_batch_page(batch_ids, limit):
    visible = batch_ids[:limit]
    next_cursor = visible[-1] if len(batch_ids) > limit else None
    return visible, next_cursor


def _insert_claim_batch(cursor, candidate):
    identity = candidate.identity
    cursor.execute(
        _CLAIM_BATCH_INSERT_SQL,
        (
            identity.application_year,
            identity.quarter,
            identity.revision,
            candidate.requested_total_ntd.amount,
        ),
    )
    return int(cursor.lastrowid)


def _insert_claim_items(cursor, batch_id, candidate):
    rows = tuple(
        (
            batch_id,
            item.case_no,
            item.assignment_id,
            item.staff_id,
            item.claimed_hours,
            item.unit_price_ntd.amount,
            item.requested_amount_ntd.amount,
        )
        for item in candidate.items
    )
    cursor.executemany(_CLAIM_ITEM_INSERT_SQL, rows)


def _insert_claim_account(cursor, batch_id, candidate):
    cursor.execute(
        _CLAIM_ACCOUNT_INSERT_SQL,
        (
            batch_id,
            candidate.resulting_batch_version,
            candidate.requested_total_ntd.amount,
        ),
    )


def _insert_submission_event(cursor, request, candidate):
    cursor.execute(
        _SUBMISSION_EVENT_INSERT_SQL,
        (
            candidate.batch.batch_id,
            candidate.expected_batch_version,
            candidate.resulting_batch_version,
            candidate.fingerprint.value,
            request.idempotency_key.value,
            request.actor.actor_id,
            request.reason,
            request.correlation_id.value,
        ),
    )


def _update_submitted_batch(cursor, candidate):
    cursor.execute(
        _CLAIM_BATCH_SUBMIT_UPDATE_SQL,
        (candidate.batch.batch_id,),
    )
    _require_single_updated_row(cursor)


def _update_claim_account_for_submission(cursor, candidate):
    cursor.execute(
        _CLAIM_ACCOUNT_SUBMIT_UPDATE_SQL,
        (
            candidate.resulting_batch_version,
            candidate.batch.batch_id,
            candidate.expected_batch_version,
        ),
    )
    _require_single_updated_row(cursor)


def _insert_approval_event(cursor, request, candidate):
    cursor.execute(
        _APPROVAL_EVENT_INSERT_SQL,
        (
            candidate.batch.batch_id,
            candidate.approved_total_ntd.amount,
            candidate.expected_batch_version,
            candidate.resulting_batch_version,
            candidate.fingerprint.value,
            request.idempotency_key.value,
            request.actor.actor_id,
            request.reason,
            request.correlation_id.value,
        ),
    )
    return int(cursor.lastrowid)


def _insert_approval_items(cursor, event_id, candidate):
    cursor.executemany(
        _APPROVAL_ITEM_INSERT_SQL,
        tuple(
            (
                event_id,
                candidate.batch.batch_id,
                intent.target_identity,
                intent.amount_ntd.amount,
            )
            for intent in candidate.intent.item_approvals
        ),
    )


def _update_approved_items(cursor, candidate):
    cursor.executemany(
        _CLAIM_ITEM_APPROVAL_UPDATE_SQL,
        tuple(
            (
                intent.amount_ntd.amount,
                intent.target_identity,
                candidate.batch.batch_id,
            )
            for intent in candidate.intent.item_approvals
        ),
    )


def _update_approved_batch(cursor, candidate):
    cursor.execute(
        _CLAIM_BATCH_APPROVAL_UPDATE_SQL,
        (
            candidate.approved_total_ntd.amount,
            candidate.batch.batch_id,
        ),
    )
    _require_single_updated_row(cursor)


def _update_claim_account_for_approval(cursor, candidate):
    cursor.execute(
        _CLAIM_ACCOUNT_APPROVAL_UPDATE_SQL,
        (
            candidate.approved_total_ntd.amount,
            candidate.approved_total_ntd.amount,
            candidate.resulting_batch_version,
            candidate.batch.batch_id,
            candidate.expected_batch_version,
        ),
    )
    _require_single_updated_row(cursor)


def _require_single_updated_row(cursor):
    if cursor.rowcount != 1:
        raise RuntimeError("government_subsidy_version_conflict")


def _claim_outbox_values(request, candidate, batch_id):
    payload = {
        "batch_id": batch_id,
        "batch_version": candidate.resulting_batch_version,
        "kind": candidate.kind.value,
        "preview_fingerprint": candidate.fingerprint.value,
    }
    return (
        batch_id,
        f"government_subsidy_claim_{candidate.kind.value}:"
        f"{request.idempotency_key.value}",
        candidate.kind.value,
        _canonical_json(payload),
    )


def _claim_receipt_values(command):
    request = command.request
    stored = command.stored_receipt
    receipt = stored.receipt
    return (
        request.idempotency_key.value,
        stored.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.kind.value,
        receipt.batch_id,
        receipt.batch_version,
        receipt.status,
        receipt.item_count,
        receipt.total_ntd,
        request.correlation_id.value,
        _canonical_json(_claim_receipt_payload(receipt)),
    )


def _stored_claim_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = _claim_receipt_from_payload(payload)
    _validate_claim_receipt_columns(row, receipt)
    return StoredGovernmentSubsidyClaimReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _claim_receipt_from_payload(payload):
    if set(payload) != _CLAIM_RECEIPT_PAYLOAD_KEYS:
        raise ValueError("government_subsidy_receipt_integrity_violation")
    return GovernmentSubsidyClaimReceipt(
        GovernmentSubsidyClaimMutationKind(_required_text(payload, "kind")),
        _required_positive_integer(payload, "batch_id"),
        _required_positive_integer(payload, "batch_version"),
        _required_text(payload, "status"),
        _required_positive_integer(payload, "item_count"),
        _required_nonnegative_integer(payload, "total_ntd"),
        PreviewFingerprint(_required_text(payload, "preview_fingerprint")),
    )


def _claim_receipt_payload(receipt):
    return {
        "batch_id": receipt.batch_id,
        "batch_version": receipt.batch_version,
        "item_count": receipt.item_count,
        "kind": receipt.kind.value,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "status": receipt.status,
        "total_ntd": receipt.total_ntd,
    }


def _validate_claim_receipt_columns(row, receipt):
    expected = (
        receipt.preview_fingerprint.value,
        receipt.kind.value,
        receipt.batch_id,
        receipt.batch_version,
        receipt.status,
        receipt.item_count,
        receipt.total_ntd,
    )
    actual = (
        str(row["preview_fingerprint"]),
        str(row["command_kind"]),
        int(row["batch_id"]),
        int(row["batch_version"]),
        str(row["status"]),
        int(row["item_count"]),
        int(row["total_ntd"]),
    )
    if actual != expected:
        raise ValueError("government_subsidy_receipt_integrity_violation")


def _load_bank_fact(cursor, row_id, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_BANK_FACT_SELECT_SQL + lock_clause, (row_id,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("government_subsidy_bank_fact_invalid")
    amount, direction = _bank_amount_and_direction(row)
    if row.get("transaction_date") is None:
        raise ValueError("government_subsidy_bank_fact_invalid")
    return GovernmentBankFact(
        int(row["id"]),
        str(row["dedup_fingerprint"]),
        direction,
        str(row["classification_type"]),
        MoneyNTD(amount),
        row["transaction_date"],
        _optional_positive_integer(row.get("existing_transaction_id")),
        str(row.get("resolved_counterparty_account") or ""),
    )


def _require_return_recipient_matches_bank(cursor, bank):
    if not bank.counterparty_account:
        raise ValueError("government_overpayment_return_recipient_mismatch")
    # The refund bill snapshots its recipient; the preserved receiving-account
    # history is the canonical way to verify that the later bank row targets it.
    # The bank date deliberately is not part of this predicate.
    # This helper is called while the canonical bank row is locked.
    cursor.execute(
        "SELECT COUNT(*) AS count FROM government_payer_receiving_accounts "
        "WHERE payer_identity=%s AND account_number=%s",
        (PAYER_IDENTITY, bank.counterparty_account),
    )
    if int(cursor.fetchone()["count"]) != 1:
        raise ValueError("government_overpayment_return_recipient_mismatch")


def _bank_amount_and_direction(row):
    direction = str(row["direction"])
    credit = _optional_integer_ntd(row.get("credit"))
    debit = _optional_integer_ntd(row.get("debit"))
    if direction == GovernmentSubsidyBankDirection.INCOMING.value:
        _require_other_side_zero(debit)
        amount = _required_positive_amount(credit)
        return amount, GovernmentSubsidyBankDirection.INCOMING
    if direction == GovernmentSubsidyBankDirection.OUTGOING.value:
        _require_other_side_zero(credit)
        return _required_positive_amount(debit), GovernmentSubsidyBankDirection.OUTGOING
    raise ValueError("government_subsidy_bank_fact_invalid")


def _load_batches(cursor, batch_id, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    if batch_id is None:
        cursor.execute(_BATCH_LIST_SELECT_SQL + lock_clause)
    else:
        cursor.execute(
            _BATCH_SELECT_SQL + lock_clause,
            (batch_id,),
        )
    rows = cursor.fetchall()
    if batch_id is not None and not rows:
        raise ValueError("government_subsidy_batch_not_found")
    return tuple(_batch_from_row(cursor, row, lock) for row in rows)


def _load_batch(cursor, batch_id, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_BATCH_SELECT_SQL + lock_clause, (batch_id,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("government_subsidy_batch_not_found")
    return _batch_from_row(cursor, row, lock)


def _batch_from_row(cursor, row, lock):
    batch_id = int(row["batch_id"])
    items = _load_claim_items(cursor, batch_id, lock)
    batch = ClaimBatchFacts(
        batch_id,
        ClaimBatchIdentity(
            int(row["application_year"]),
            int(row["quarter"]),
            int(row["revision"]),
        ),
        int(row["aggregate_version"]),
        row.get("submitted_at") is not None,
        row.get("approved_at") is not None,
        items,
    )
    _validate_account_projection(row, batch)
    return batch


def _load_claim_items(cursor, batch_id, lock):
    if lock:
        _lock_claim_item_sources(cursor, batch_id)
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_CLAIM_ITEMS_SELECT_SQL + lock_clause, (batch_id,))
    rows = cursor.fetchall()
    if not rows:
        raise ValueError("government_subsidy_claim_facts_invalid")
    return tuple(_claim_item(row, batch_id) for row in rows)


def _lock_claim_item_sources(cursor, batch_id):
    cursor.execute(_CLAIM_ITEM_SOURCE_LOCK_SQL, (batch_id,))
    cursor.fetchall()


def _claim_item(row, batch_id):
    claimed_hours = _integer_ntd(row["claimed_hours"])
    official_hours = int(row["official_service_hours"])
    effective = bool(row["assignment_effective"])
    if not effective or claimed_hours != official_hours:
        raise ValueError("government_subsidy_assignment_facts_stale")
    return ClaimItemSnapshot(
        int(row["item_id"]),
        batch_id,
        int(row["assignment_id"]),
        str(row["case_no"]),
        int(row["staff_id"]),
        claimed_hours,
        MoneyNTD(_integer_ntd(row["unit_price"])),
        MoneyNTD(_integer_ntd(row["requested_amount"])),
        MoneyNTD(_integer_ntd(row["approved_amount"])),
        MoneyNTD(_integer_ntd(row["net_allocated_amount"])),
    )


def _validate_account_projection(row, batch):
    expected = (
        batch.requested_total_ntd.amount,
        batch.approved_total_ntd.amount,
        batch.net_allocated_total_ntd.amount,
        batch.outstanding_total_ntd.amount,
        reduce_batch_status(batch).value,
    )
    actual = (
        int(row["requested_total_ntd"]),
        int(row["approved_total_ntd"]),
        int(row["net_allocated_ntd"]),
        int(row["outstanding_ntd"]),
        str(row["account_status"]),
    )
    if actual != expected:
        raise ValueError("government_subsidy_claim_facts_invalid")


# Kept cohesive so a reversal source and its allocation roots use one lock scope.
def _load_source_receipt(cursor, transaction_id, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        _SOURCE_TRANSACTION_SELECT_SQL + lock_clause,
        (transaction_id,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("government_subsidy_reversal_target_invalid")
    batch_id = int(row["claim_batch_id"])
    allocations = _load_source_allocations(
        cursor,
        transaction_id,
        batch_id,
        lock,
    )
    return SourceReceiptFacts(
        int(row["id"]),
        batch_id,
        GovernmentSubsidyLedgerKind(str(row["transaction_type"])),
        MoneyNTD(_integer_ntd(row["amount"])),
        allocations,
    )


def _load_source_allocations(cursor, transaction_id, batch_id, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        _SOURCE_ALLOCATIONS_SELECT_SQL + lock_clause,
        (transaction_id, batch_id),
    )
    rows = cursor.fetchall()
    return tuple(
        SourceReceiptAllocationFacts(
            int(row["allocation_id"]),
            batch_id,
            int(row["claim_item_id"]),
            MoneyNTD(_integer_ntd(row["receipt_amount"])),
            MoneyNTD(_integer_ntd(row["reversed_amount"])),
        )
        for row in rows
    )


def _insert_claim(cursor, request, command_fingerprint):
    family = f"government_subsidy_{_request_kind(request).value}"
    try:
        cursor.execute(
            _CLAIM_INSERT_SQL,
            (
                request.idempotency_key.value,
                family,
                _aggregate_identity(request),
                command_fingerprint.value,
                request.correlation_id.value,
            ),
        )
    except IntegrityError as error:
        if _mysql_error_code(error) != 1062:
            raise
        return False
    return True


def _locked_claim(cursor, key):
    cursor.execute(_CLAIM_SELECT_SQL, (key.value,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return row


def _claim_state(request, command_fingerprint, claim):
    expected = (
        f"government_subsidy_{_request_kind(request).value}",
        _aggregate_identity(request),
        command_fingerprint.value,
    )
    actual = (
        str(claim["command_family"]),
        str(claim["aggregate_identity"]),
        str(claim["command_fingerprint"]),
    )
    if actual == expected:
        return GovernmentSubsidyClaimState.MATCHED
    return GovernmentSubsidyClaimState.MISMATCH


def _request_kind(request):
    if isinstance(request, ClaimPlanningApplyRequest):
        return GovernmentSubsidyClaimMutationKind.PLAN
    if isinstance(request, ClaimSubmissionApplyRequest):
        return GovernmentSubsidyClaimMutationKind.SUBMIT
    if isinstance(request, ClaimApprovalApplyRequest):
        return GovernmentSubsidyClaimMutationKind.APPROVAL
    if isinstance(request.intent, ReceiptIntent):
        return GovernmentSubsidyLedgerKind.RECEIPT
    return GovernmentSubsidyLedgerKind.REVERSAL


def _aggregate_identity(request):
    if isinstance(request, ClaimPlanningApplyRequest):
        return f"claim-batch:{request.intent.identity.value}"
    if isinstance(
        request,
        (ClaimSubmissionApplyRequest, ClaimApprovalApplyRequest),
    ):
        return f"claim-batch-id:{request.intent.batch_id}"
    return f"bank-row:{request.intent.finance_import_row_id}"


def _transaction_values(request, candidate):
    kind = candidate.kind
    return (
        candidate.batch_id,
        candidate.bank_fact.finance_import_row_id,
        kind.value,
        "succeeded",
        candidate.amount_ntd.amount,
        candidate.bank_fact.occurred_on,
        f"fp:{candidate.bank_fact.bank_fact_identity}",
        candidate.source_receipt_id,
        candidate.expected_batch_version,
        candidate.resulting_batch_version,
        candidate.fingerprint.value,
        request.idempotency_key.value,
        request.actor.actor_id,
        request.reason,
        request.correlation_id.value,
    )


def _insert_allocation(cursor, transaction_id, candidate, allocation):
    cursor.execute(
        _ALLOCATION_INSERT_SQL,
        (
            transaction_id,
            candidate.batch_id,
            allocation.claim_item_id,
            candidate.kind.value,
            allocation.amount_ntd.amount,
            allocation.reversal_of_allocation_id,
        ),
    )
    return int(cursor.lastrowid)


def _projection_values(candidate):
    return (
        candidate.requested_total_ntd.amount,
        candidate.approved_total_ntd.amount,
        candidate.after_net_allocated_ntd.amount,
        candidate.outstanding_ntd.amount,
        candidate.after_status.value,
        candidate.resulting_batch_version,
        candidate.batch_id,
        candidate.expected_batch_version,
    )


def _projection_event_values(request, candidate, transaction_id):
    return (
        candidate.batch_id,
        transaction_id,
        candidate.before_status.value,
        candidate.after_status.value,
        candidate.before_net_allocated_ntd.amount,
        candidate.after_net_allocated_ntd.amount,
        candidate.outstanding_ntd.amount,
        candidate.expected_batch_version,
        candidate.resulting_batch_version,
        candidate.fingerprint.value,
        request.actor.actor_id,
        request.reason,
        request.idempotency_key.value,
    )


# Kept cohesive so persisted outbox identity and payload cannot drift apart.
def _outbox_values(
    request,
    candidate,
    transaction_id,
    projection_event_id,
    case_by_claim_item=None,
):
    case_by_claim_item = case_by_claim_item or {}
    payload = {
        "after_status": candidate.after_status.value,
        "amount_ntd": candidate.amount_ntd.amount,
        "bank_fact_identity": candidate.bank_fact.bank_fact_identity,
        "batch_id": candidate.batch_id,
        "kind": candidate.kind.value,
        "outstanding_ntd": candidate.outstanding_ntd.amount,
        "transaction_id": transaction_id,
        "allocations": [
            {
                "claim_item_id": allocation.claim_item_id,
                "case_no": case_by_claim_item.get(allocation.claim_item_id),
                "amount_ntd": allocation.amount_ntd.amount,
            }
            for allocation in candidate.allocations
        ],
    }
    receipt_applied = (
        candidate.batch_id,
        transaction_id,
        projection_event_id,
        f"government_subsidy_receipt_applied:{request.idempotency_key.value}",
        "government_subsidy_receipt_applied",
        _canonical_json(payload),
    )
    if candidate.kind is not GovernmentSubsidyLedgerKind.RECEIPT:
        return ((
            candidate.batch_id,
            transaction_id,
            projection_event_id,
            f"government_subsidy_reversal_applied:{request.idempotency_key.value}",
            "government_subsidy_reversal_applied",
            _canonical_json(payload),
        ),)
    allocated = (
        candidate.batch_id,
        transaction_id,
        projection_event_id,
        f"government_subsidy_receipt_allocated:{request.idempotency_key.value}",
        "government_subsidy_receipt_allocated",
        _canonical_json(payload),
    )
    return (receipt_applied, allocated)


def _claim_item_case_numbers(cursor, candidate):
    item_ids = tuple(allocation.claim_item_id for allocation in candidate.allocations)
    if not item_ids:
        return {}
    placeholders = ",".join("%s" for _ in item_ids)
    cursor.execute(
        f"SELECT id,case_no FROM subsidy_claim_batch_items WHERE id IN ({placeholders}) FOR UPDATE",
        item_ids,
    )
    result = {int(row["id"]): str(row["case_no"]) for row in cursor.fetchall()}
    if len(result) != len(set(item_ids)):
        raise RuntimeError("government_subsidy_claim_item_not_found")
    return result




def _receipt_values(command):
    request = command.request
    stored = command.stored_receipt
    receipt = stored.receipt
    return (
        request.idempotency_key.value,
        stored.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.kind.value,
        receipt.transaction_id,
        receipt.batch_id,
        receipt.batch_version,
        receipt.bank_fact_identity,
        receipt.amount_ntd,
        receipt.allocation_count,
        receipt.status,
        receipt.outstanding_ntd,
        request.correlation_id.value,
        _canonical_json(_receipt_payload(receipt)),
    )


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = _receipt_from_payload(payload)
    _validate_receipt_columns(row, receipt)
    return StoredGovernmentSubsidyReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_from_payload(payload):
    if set(payload) != _RECEIPT_PAYLOAD_KEYS:
        raise ValueError("government_subsidy_receipt_integrity_violation")
    return GovernmentSubsidyCommandReceipt(
        GovernmentSubsidyLedgerKind(_required_text(payload, "kind")),
        _required_positive_integer(payload, "transaction_id"),
        _required_positive_integer(payload, "batch_id"),
        _required_positive_integer(payload, "batch_version"),
        _required_text(payload, "bank_fact_identity"),
        _required_positive_integer(payload, "amount_ntd"),
        _required_positive_integer(payload, "allocation_count"),
        _required_text(payload, "status"),
        _required_nonnegative_integer(payload, "outstanding_ntd"),
        PreviewFingerprint(_required_text(payload, "preview_fingerprint")),
    )


def _receipt_payload(receipt):
    return {
        "allocation_count": receipt.allocation_count,
        "amount_ntd": receipt.amount_ntd,
        "bank_fact_identity": receipt.bank_fact_identity,
        "batch_id": receipt.batch_id,
        "batch_version": receipt.batch_version,
        "kind": receipt.kind.value,
        "outstanding_ntd": receipt.outstanding_ntd,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "status": receipt.status,
        "transaction_id": receipt.transaction_id,
    }


# Kept cohesive because this tuple is the stored receipt integrity contract.
def _validate_receipt_columns(row, receipt):
    expected = (
        receipt.preview_fingerprint.value,
        receipt.kind.value,
        receipt.transaction_id,
        receipt.batch_id,
        receipt.batch_version,
        receipt.bank_fact_identity,
        receipt.amount_ntd,
        receipt.allocation_count,
        receipt.status,
        receipt.outstanding_ntd,
    )
    actual = (
        str(row["preview_fingerprint"]),
        str(row["command_kind"]),
        int(row["transaction_id"]),
        int(row["batch_id"]),
        int(row["batch_version"]),
        str(row["bank_fact_identity"]),
        int(row["amount_ntd"]),
        int(row["allocation_count"]),
        str(row["status"]),
        int(row["outstanding_ntd"]),
    )
    if actual != expected:
        raise ValueError("government_subsidy_receipt_integrity_violation")


def _integer_ntd(value):
    decimal_value = Decimal(str(value))
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError("government_subsidy_claim_facts_invalid")
    return int(decimal_value)


def _optional_integer_ntd(value):
    if value is None:
        return None
    return _integer_ntd(value)


def _required_positive_amount(value):
    if value is None or value <= 0:
        raise ValueError("government_subsidy_bank_fact_invalid")
    return value


def _require_other_side_zero(value):
    if value not in {None, 0}:
        raise ValueError("government_subsidy_bank_fact_invalid")


def _optional_positive_integer(value):
    if value is None:
        return None
    result = int(value)
    return result if result > 0 else None


def _required_text(payload, key):
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("government_subsidy_receipt_integrity_violation")
    return value


def _required_positive_integer(payload, key):
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("government_subsidy_receipt_integrity_violation")
    return value


def _required_nonnegative_integer(payload, key):
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("government_subsidy_receipt_integrity_violation")
    return value


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("government subsidy receipt must be an object")
    return parsed


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _mysql_error_code(error):
    if error.args and isinstance(error.args[0], int):
        return error.args[0]
    return None


_EXISTING_CLAIM_BATCH_SELECT_SQL = (
    "SELECT id FROM subsidy_claim_batches "
    "WHERE application_year=%s AND quarter=%s AND revision=%s"
)
_CLAIM_PLANNING_SOURCE_SELECT_SQL = (
    "SELECT a.id AS assignment_id,a.case_no,a.staff_id,"
    "COUNT(DISTINCT s.work_date) AS official_service_day_count,"
    "o.service_hours_per_day,c.identity_status,"
    "CASE WHEN a.status NOT IN ('cancelled','replaced') "
    "AND g.effective_marker=1 THEN 1 ELSE 0 END AS assignment_effective "
    "FROM case_staff_assignments a "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN staff_schedule s ON s.assignment_id=a.id "
    "AND s.generation_id=a.generation_id "
    "JOIN orders o ON o.case_no=a.case_no "
    "JOIN clients c ON c.id=o.client_id "
    "WHERE s.effective_marker=1 AND s.is_work_day=1 "
    "AND s.work_date >= %s AND s.work_date < %s "
    "AND c.identity_status IN (%s,%s) "
    "GROUP BY a.id,a.case_no,a.staff_id,o.service_hours_per_day,"
    "c.identity_status,a.status,g.effective_marker ORDER BY a.id"
)
_CLAIM_PLANNING_LOCK_SQL = (
    "SELECT a.id,s.id FROM case_staff_assignments a "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN staff_schedule s ON s.assignment_id=a.id "
    "AND s.generation_id=a.generation_id "
    "JOIN orders o ON o.case_no=a.case_no "
    "JOIN clients c ON c.id=o.client_id "
    "WHERE s.effective_marker=1 AND s.is_work_day=1 "
    "AND s.work_date >= %s AND s.work_date < %s "
    "AND c.identity_status IN (%s,%s) "
    "ORDER BY a.id,s.work_date FOR UPDATE"
)
_BATCH_PAGE_SELECT_SQL = (
    "SELECT batch_id FROM government_subsidy_batch_accounts "
    "WHERE batch_id > %s ORDER BY batch_id LIMIT %s"
)
_CLAIM_BATCH_INSERT_SQL = (
    "INSERT INTO subsidy_claim_batches "
    "(application_year,quarter,revision,status,requested_amount,"
    "approved_amount,paid_amount) VALUES (%s,%s,%s,'draft',%s,0,0)"
)
_CLAIM_ITEM_INSERT_SQL = (
    "INSERT INTO subsidy_claim_batch_items "
    "(batch_id,case_no,assignment_id,staff_id,claimed_hours,unit_price,"
    "requested_amount,approved_amount,paid_amount) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,0,0)"
)
_CLAIM_ACCOUNT_INSERT_SQL = (
    "INSERT INTO government_subsidy_batch_accounts "
    "(batch_id,aggregate_version,requested_total_ntd,approved_total_ntd,"
    "net_allocated_ntd,outstanding_ntd,status) "
    "VALUES (%s,%s,%s,0,0,0,'draft')"
)
_SUBMISSION_EVENT_INSERT_SQL = (
    "INSERT INTO government_subsidy_claim_submission_events "
    "(batch_id,expected_batch_version,resulting_batch_version,"
    "preview_fingerprint,idempotency_key,actor,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CLAIM_BATCH_SUBMIT_UPDATE_SQL = (
    "UPDATE subsidy_claim_batches SET status='submitted',"
    "submitted_at=CURRENT_TIMESTAMP WHERE id=%s AND status='draft'"
)
_CLAIM_ACCOUNT_SUBMIT_UPDATE_SQL = (
    "UPDATE government_subsidy_batch_accounts SET status='submitted',"
    "aggregate_version=%s WHERE batch_id=%s AND aggregate_version=%s "
    "AND status='draft'"
)
_APPROVAL_EVENT_INSERT_SQL = (
    "INSERT INTO government_subsidy_claim_approval_events "
    "(batch_id,approved_total_ntd,expected_batch_version,"
    "resulting_batch_version,preview_fingerprint,idempotency_key,actor,"
    "reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_APPROVAL_ITEM_INSERT_SQL = (
    "INSERT INTO government_subsidy_claim_approval_items "
    "(approval_event_id,batch_id,claim_item_id,approved_amount_ntd) "
    "VALUES (%s,%s,%s,%s)"
)
_CLAIM_ITEM_APPROVAL_UPDATE_SQL = (
    "UPDATE subsidy_claim_batch_items SET approved_amount=%s "
    "WHERE id=%s AND batch_id=%s"
)
_CLAIM_BATCH_APPROVAL_UPDATE_SQL = (
    "UPDATE subsidy_claim_batches SET status='approved',"
    "approved_amount=%s,approved_at=CURRENT_TIMESTAMP "
    "WHERE id=%s AND status='submitted'"
)
_CLAIM_ACCOUNT_APPROVAL_UPDATE_SQL = (
    "UPDATE government_subsidy_batch_accounts SET "
    "approved_total_ntd=%s,outstanding_ntd=%s,status='approved',"
    "aggregate_version=%s WHERE batch_id=%s AND aggregate_version=%s "
    "AND status='submitted'"
)
_CLAIM_OUTBOX_INSERT_SQL = (
    "INSERT INTO government_subsidy_claim_outbox "
    "(batch_id,intent_key,intent_type,payload_snapshot) "
    "VALUES (%s,%s,%s,%s)"
)
_CLAIM_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,command_kind,batch_id,"
    "batch_version,status,item_count,total_ntd,result_snapshot "
    "FROM government_subsidy_claim_apply_receipts "
    "WHERE idempotency_key=%s"
)
_CLAIM_RECEIPT_INSERT_SQL = (
    "INSERT INTO government_subsidy_claim_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,command_kind,"
    "batch_id,batch_version,status,item_count,total_ntd,correlation_id,"
    "result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CLAIM_RECEIPT_PAYLOAD_KEYS = frozenset(
    {
        "batch_id",
        "batch_version",
        "item_count",
        "kind",
        "preview_fingerprint",
        "status",
        "total_ntd",
    }
)
_BANK_FACT_SELECT_SQL = (
    "SELECT r.id,r.dedup_fingerprint,r.transaction_date,r.debit,r.credit,"
    "r.direction,r.classification_type,r.resolved_counterparty_account,"
    "(SELECT t.id FROM government_subsidy_transactions t "
    "WHERE t.finance_import_row_id=r.id LIMIT 1) AS existing_transaction_id "
    "FROM finance_import_rows r WHERE r.id=%s"
)
_BATCH_COLUMNS = (
    "a.batch_id,a.aggregate_version,a.requested_total_ntd,"
    "a.approved_total_ntd,a.net_allocated_ntd,a.outstanding_ntd,"
    "a.status AS account_status,b.application_year,b.quarter,b.revision,"
    "b.submitted_at,b.approved_at "
)
_BATCH_LIST_SELECT_SQL = (
    f"SELECT {_BATCH_COLUMNS}FROM government_subsidy_batch_accounts a "
    "JOIN subsidy_claim_batches b ON b.id=a.batch_id "
    "ORDER BY a.batch_id"
)
_BATCH_SELECT_SQL = (
    f"SELECT {_BATCH_COLUMNS}FROM government_subsidy_batch_accounts a "
    "JOIN subsidy_claim_batches b ON b.id=a.batch_id "
    "WHERE a.batch_id=%s"
)
_CLAIM_ITEMS_SELECT_SQL = (
    "SELECT i.id AS item_id,i.assignment_id,i.case_no,i.staff_id,"
    "i.claimed_hours,i.unit_price,i.requested_amount,i.approved_amount,"
    "CASE WHEN a.status NOT IN ('cancelled','replaced') "
    "AND g.effective_marker=1 THEN 1 ELSE 0 END AS assignment_effective,"
    "(SELECT COUNT(DISTINCT ss.work_date) FROM staff_schedule ss "
    "WHERE ss.assignment_id=i.assignment_id AND ss.effective_marker=1 "
    "AND ss.is_work_day=1 AND ss.work_date >= "
    "MAKEDATE(b.application_year,1) + "
    "INTERVAL ((b.quarter-1)*3) MONTH AND ss.work_date < "
    "MAKEDATE(b.application_year,1) + "
    "INTERVAL (b.quarter*3) MONTH)*o.service_hours_per_day "
    "AS official_service_hours,"
    "COALESCE(ga.net_allocated_amount,0)+COALESCE(oa.offset_amount,0) "
    "AS net_allocated_amount "
    "FROM subsidy_claim_batch_items i "
    "JOIN subsidy_claim_batches b ON b.id=i.batch_id "
    "JOIN case_staff_assignments a ON a.id=i.assignment_id "
    "AND a.case_no=i.case_no AND a.staff_id=i.staff_id "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN orders o ON o.case_no=i.case_no "
    "LEFT JOIN (SELECT claim_item_id,claim_batch_id,"
    "SUM(CASE WHEN allocation_type='receipt' THEN allocated_amount "
    "WHEN allocation_type='reversal' THEN -allocated_amount ELSE 0 END) "
    "AS net_allocated_amount FROM government_subsidy_allocations "
    "GROUP BY claim_item_id,claim_batch_id) ga "
    "ON ga.claim_item_id=i.id AND ga.claim_batch_id=i.batch_id "
    "LEFT JOIN (SELECT claim_item_id,claim_batch_id,"
    "SUM(allocated_amount_ntd) AS offset_amount "
    "FROM government_subsidy_overpayment_offsets "
    "GROUP BY claim_item_id,claim_batch_id) oa "
    "ON oa.claim_item_id=i.id AND oa.claim_batch_id=i.batch_id "
    "WHERE i.batch_id=%s ORDER BY i.id"
)
_CLAIM_ITEM_SOURCE_LOCK_SQL = (
    "SELECT a.id,ss.id FROM subsidy_claim_batch_items i "
    "JOIN subsidy_claim_batches b ON b.id=i.batch_id "
    "JOIN case_staff_assignments a ON a.id=i.assignment_id "
    "JOIN staff_schedule ss ON ss.assignment_id=i.assignment_id "
    "WHERE i.batch_id=%s AND ss.effective_marker=1 AND ss.is_work_day=1 "
    "AND ss.work_date >= MAKEDATE(b.application_year,1) + "
    "INTERVAL ((b.quarter-1)*3) MONTH "
    "AND ss.work_date < MAKEDATE(b.application_year,1) + "
    "INTERVAL (b.quarter*3) MONTH ORDER BY a.id,ss.work_date FOR UPDATE"
)
_SOURCE_TRANSACTION_SELECT_SQL = (
    "SELECT id,claim_batch_id,transaction_type,amount "
    "FROM government_subsidy_transactions WHERE id=%s"
)
_SOURCE_ALLOCATIONS_SELECT_SQL = (
    "SELECT a.id AS allocation_id,a.claim_item_id,"
    "a.allocated_amount AS receipt_amount,"
    "COALESCE(SUM(r.allocated_amount),0) AS reversed_amount "
    "FROM government_subsidy_allocations a "
    "LEFT JOIN government_subsidy_allocations r "
    "ON r.reversal_of_allocation_id=a.id "
    "AND r.allocation_type='reversal' "
    "WHERE a.transaction_id=%s AND a.claim_batch_id=%s "
    "AND a.allocation_type='receipt' "
    "GROUP BY a.id,a.claim_item_id,a.allocated_amount ORDER BY a.id"
)
_CLAIM_INSERT_SQL = (
    "INSERT INTO application_command_claims "
    "(idempotency_key,command_family,aggregate_identity,"
    "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)
_CLAIM_SELECT_SQL = (
    "SELECT command_family,aggregate_identity,command_fingerprint "
    "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE"
)
_TRANSACTION_INSERT_SQL = (
    "INSERT INTO government_subsidy_transactions "
    "(claim_batch_id,finance_import_row_id,transaction_type,"
    "transaction_status,amount,occurred_at,external_reference,"
    "reversal_of_transaction_id,expected_batch_version,"
    "resulting_batch_version,preview_fingerprint,idempotency_key,actor,"
    "reason,correlation_id) VALUES "
    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_ALLOCATION_INSERT_SQL = (
    "INSERT INTO government_subsidy_allocations "
    "(transaction_id,claim_batch_id,claim_item_id,allocation_type,"
    "allocated_amount,reversal_of_allocation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)
_ACCOUNT_UPDATE_SQL = (
    "UPDATE government_subsidy_batch_accounts SET "
    "requested_total_ntd=%s,approved_total_ntd=%s,net_allocated_ntd=%s,"
    "outstanding_ntd=%s,status=%s,aggregate_version=%s "
    "WHERE batch_id=%s AND aggregate_version=%s"
)
_PROJECTION_EVENT_INSERT_SQL = (
    "INSERT INTO government_subsidy_projection_events "
    "(batch_id,transaction_id,before_status,after_status,"
    "before_net_allocated_ntd,after_net_allocated_ntd,outstanding_ntd,"
    "expected_batch_version,resulting_batch_version,preview_fingerprint,"
    "actor,reason,idempotency_key) VALUES "
    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO government_subsidy_outbox "
    "(batch_id,transaction_id,projection_event_id,intent_key,intent_type,"
    "payload_snapshot) VALUES (%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,command_kind,"
    "transaction_id,batch_id,batch_version,bank_fact_identity,amount_ntd,"
    "allocation_count,status,outstanding_ntd,result_snapshot "
    "FROM government_subsidy_apply_receipts WHERE idempotency_key=%s"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO government_subsidy_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,command_kind,"
    "transaction_id,batch_id,batch_version,bank_fact_identity,amount_ntd,"
    "allocation_count,status,outstanding_ntd,correlation_id,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_PAYLOAD_KEYS = frozenset(
    {
        "allocation_count",
        "amount_ntd",
        "bank_fact_identity",
        "batch_id",
        "batch_version",
        "kind",
        "outstanding_ntd",
        "preview_fingerprint",
        "status",
        "transaction_id",
    }
)


__all__ = ["MySqlGovernmentSubsidyRepository"]
