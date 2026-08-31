"""Read-only MySQL composition for Government Subsidy current facts."""

from __future__ import annotations

from collections.abc import Mapping

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.government_subsidy.current_anomaly_facts import (
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
    GovernmentSubsidyAllocationCurrentFact,
    GovernmentSubsidyCurrentIssueCode,
    GovernmentSubsidyReceiptCurrentFact,
    GovernmentSubsidyReversalCurrentFact,
)


class MySqlGovernmentSubsidyCurrentIssueAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        _validate_scope(scope)
        code = GovernmentSubsidyCurrentIssueCode(scope.subject_type)
        facts = tuple(self._read(code, subject_id) for subject_id in scope.subject_ids)
        token = fingerprint_payload({"code": code.value, "facts": tuple(_fact_payload(fact) for fact in facts)}).value
        return OwnerSnapshot(scope, token, max((fact.owner_version for fact in facts), default=0), facts, all(fact.authoritative_complete for fact in facts))

    def _read(self, code, subject_id):
        if code is GovernmentSubsidyCurrentIssueCode.RECEIPT_UNMATCHED:
            return self._read_receipt(subject_id)
        bank_identity, coordinate = _coordinate(subject_id)
        if code is GovernmentSubsidyCurrentIssueCode.RECEIPT_ALLOCATION_AMBIGUOUS:
            return self._read_allocation(bank_identity, coordinate)
        return self._read_reversal(bank_identity, coordinate)

    def _read_receipt(self, bank_identity: str):
        row = self._one(_RECEIPT_FACT_SQL, (bank_identity,))
        if row is None:
            return GovernmentSubsidyReceiptCurrentFact(bank_identity, None, _missing_token(bank_identity), 0, False, False, False, False)
        applicable = row["classification_type"] == "government_subsidy"
        terminal = _terminal_receipt(row)
        flags = (not applicable or terminal or int(row["eligible_batch_count"]) == 1, not applicable or terminal, not applicable or terminal)
        return GovernmentSubsidyReceiptCurrentFact(bank_identity, int(row["finance_import_row_id"]), _token(row), int(row["owner_version"]), True, *flags)

    def _read_allocation(self, bank_identity: str, batch_id: int):
        row = self._one(_ALLOCATION_FACT_SQL, (batch_id, bank_identity))
        if row is None:
            return GovernmentSubsidyAllocationCurrentFact(bank_identity, batch_id, None, _missing_token(bank_identity + ":" + str(batch_id)), 0, False, False, False, False)
        applicable = row["classification_type"] == "government_subsidy"
        terminal = _terminal_receipt(row) and int(row["claim_batch_id"] or 0) == batch_id
        unambiguous = not applicable or terminal
        within = not applicable or terminal and int(row["invalid_item_count"]) == 0
        total = not applicable or terminal
        return GovernmentSubsidyAllocationCurrentFact(bank_identity, batch_id, int(row["finance_import_row_id"]), _token(row), int(row["owner_version"]), True, unambiguous, within, total)

    def _read_reversal(self, bank_identity: str, source_receipt_id: int):
        row = self._one(_REVERSAL_FACT_SQL, (source_receipt_id, source_receipt_id, bank_identity))
        if row is None:
            return GovernmentSubsidyReversalCurrentFact(bank_identity, source_receipt_id, None, _missing_token(bank_identity + ":" + str(source_receipt_id)), 0, False, False, False, False, False)
        applicable = row["classification_type"] == "government_subsidy"
        target_unique = not applicable or int(row["target_count"]) == 1
        target_valid = not applicable or (row["source_transaction_type"] == "receipt" and row["source_transaction_status"] == "succeeded")
        terminal = (
            not applicable
            or (
                row["reversal_transaction_status"] == "succeeded"
                and int(row["reversal_of_transaction_id"] or 0) == source_receipt_id
                and int(row["reversal_allocation_total_ntd"]) == int(row["bank_amount_ntd"])
                and int(row["invalid_reversal_count"]) == 0
            )
        )
        return GovernmentSubsidyReversalCurrentFact(bank_identity, source_receipt_id, int(row["finance_import_row_id"]), _token(row), int(row["owner_version"]), True, target_unique, target_valid, terminal, terminal)

    def _one(self, sql, parameters):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            row = cursor.fetchone()
        if row is not None and not isinstance(row, Mapping):
            raise TypeError("government subsidy current-fact row is invalid")
        return row


def _terminal_receipt(row) -> bool:
    if row["transaction_status"] != "succeeded" or int(row["transaction_amount_ntd"] or 0) != int(row["bank_amount_ntd"]) or int(row["allocation_count"]) <= 0:
        return False
    allocated = int(row["allocation_total_ntd"])
    bank_amount = int(row["bank_amount_ntd"])
    if allocated == bank_amount:
        return True
    overpayment = int(row.get("overpayment_original_ntd") or 0)
    return (
        allocated + overpayment == bank_amount
        and int(row.get("overpayment_remaining_ntd") or -1) == 0
        and row.get("overpayment_status") in {"offset_applied", "returned"}
    )


def _validate_scope(scope: RecheckScope) -> None:
    if scope.owner_domain != GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN or scope.owner_root_type != GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE:
        raise ValueError("government subsidy anomaly owner scope is invalid")
    GovernmentSubsidyCurrentIssueCode(scope.subject_type)


def _coordinate(value: str) -> tuple[str, int]:
    identity, separator, coordinate = value.rpartition(":")
    if not separator or not identity or not coordinate.isdecimal() or int(coordinate) <= 0:
        raise ValueError("government subsidy current-fact subject is invalid")
    return identity, int(coordinate)


def _token(row) -> str:
    return fingerprint_payload({str(key): value for key, value in row.items()}).value


def _missing_token(identity: str) -> str:
    return fingerprint_payload({"identity": identity, "missing": True}).value


def _fact_payload(fact):
    return {"type": type(fact).__name__, "token": fact.owner_snapshot_token, "version": fact.owner_version, "complete": fact.authoritative_complete, "active": fact.predicate_active}


_RECEIPT_FACT_SQL = """
SELECT bank.id AS finance_import_row_id,bank.dedup_fingerprint AS bank_fact_identity,bank.credit AS bank_amount_ntd,
 classification.id AS owner_version,classification.classification_type,
 (SELECT COUNT(*) FROM government_subsidy_batch_accounts account JOIN subsidy_claim_batches batch ON batch.id=account.batch_id
   WHERE batch.submitted_at IS NOT NULL AND batch.approved_at IS NOT NULL
     AND account.status IN ('approved','partially_paid') AND account.outstanding_ntd>=bank.credit) AS eligible_batch_count,
 receipt.claim_batch_id,receipt.transaction_status,receipt.amount AS transaction_amount_ntd,
 overpayment.original_amount_ntd AS overpayment_original_ntd,overpayment.remaining_amount_ntd AS overpayment_remaining_ntd,overpayment.status AS overpayment_status,
 COALESCE(SUM(allocation.allocated_amount),0) AS allocation_total_ntd,COUNT(allocation.id) AS allocation_count
FROM finance_import_rows bank
JOIN finance_import_classification_events classification ON classification.id=(SELECT MAX(latest.id) FROM finance_import_classification_events latest WHERE latest.finance_import_row_id=bank.id)
LEFT JOIN government_subsidy_transactions receipt ON receipt.finance_import_row_id=bank.id AND receipt.transaction_type='receipt'
LEFT JOIN government_subsidy_allocations allocation ON allocation.transaction_id=receipt.id AND allocation.allocation_type='receipt'
LEFT JOIN government_subsidy_overpayments overpayment ON overpayment.source_transaction_id=receipt.id
WHERE bank.dedup_fingerprint=%s AND bank.direction='incoming'
GROUP BY bank.id,bank.dedup_fingerprint,bank.credit,classification.id,classification.classification_type,receipt.id,receipt.claim_batch_id,receipt.transaction_status,receipt.amount,overpayment.original_amount_ntd,overpayment.remaining_amount_ntd,overpayment.status
"""

_ALLOCATION_FACT_SQL = """
SELECT bank.id AS finance_import_row_id,bank.dedup_fingerprint AS bank_fact_identity,bank.credit AS bank_amount_ntd,
 classification.id AS owner_version,classification.classification_type,
 receipt.claim_batch_id,receipt.transaction_status,receipt.amount AS transaction_amount_ntd,
 overpayment.original_amount_ntd AS overpayment_original_ntd,overpayment.remaining_amount_ntd AS overpayment_remaining_ntd,overpayment.status AS overpayment_status,
 COALESCE(SUM(allocation.allocated_amount),0) AS allocation_total_ntd,COUNT(allocation.id) AS allocation_count,
 COALESCE(SUM(CASE WHEN allocation.allocated_amount>item.approved_amount THEN 1 ELSE 0 END),0) AS invalid_item_count
FROM finance_import_rows bank
JOIN finance_import_classification_events classification ON classification.id=(SELECT MAX(latest.id) FROM finance_import_classification_events latest WHERE latest.finance_import_row_id=bank.id)
LEFT JOIN government_subsidy_transactions receipt ON receipt.finance_import_row_id=bank.id AND receipt.transaction_type='receipt' AND receipt.claim_batch_id=%s
LEFT JOIN government_subsidy_allocations allocation ON allocation.transaction_id=receipt.id AND allocation.allocation_type='receipt'
LEFT JOIN government_subsidy_overpayments overpayment ON overpayment.source_transaction_id=receipt.id
LEFT JOIN subsidy_claim_batch_items item ON item.id=allocation.claim_item_id AND item.batch_id=receipt.claim_batch_id
WHERE bank.dedup_fingerprint=%s AND bank.direction='incoming'
GROUP BY bank.id,bank.dedup_fingerprint,bank.credit,classification.id,classification.classification_type,receipt.id,receipt.claim_batch_id,receipt.transaction_status,receipt.amount,overpayment.original_amount_ntd,overpayment.remaining_amount_ntd,overpayment.status
"""

_REVERSAL_FACT_SQL = """
SELECT bank.id AS finance_import_row_id,bank.dedup_fingerprint AS bank_fact_identity,bank.debit AS bank_amount_ntd,
 classification.id AS owner_version,classification.classification_type,
 source.transaction_type AS source_transaction_type,source.transaction_status AS source_transaction_status,
 (SELECT COUNT(*) FROM government_subsidy_transactions target WHERE target.id=%s AND target.transaction_type='receipt') AS target_count,
 reversal.transaction_status AS reversal_transaction_status,reversal.reversal_of_transaction_id,
 COALESCE(SUM(reversed.allocated_amount),0) AS reversal_allocation_total_ntd,
 COALESCE(SUM(CASE WHEN reversed.reversal_of_allocation_id IS NULL OR reversed.allocated_amount>original.allocated_amount THEN 1 ELSE 0 END),0) AS invalid_reversal_count
FROM finance_import_rows bank
JOIN finance_import_classification_events classification ON classification.id=(SELECT MAX(latest.id) FROM finance_import_classification_events latest WHERE latest.finance_import_row_id=bank.id)
LEFT JOIN government_subsidy_transactions source ON source.id=%s
LEFT JOIN government_subsidy_transactions reversal ON reversal.finance_import_row_id=bank.id AND reversal.transaction_type='reversal'
LEFT JOIN government_subsidy_allocations reversed ON reversed.transaction_id=reversal.id AND reversed.allocation_type='reversal'
LEFT JOIN government_subsidy_allocations original ON original.id=reversed.reversal_of_allocation_id AND original.transaction_id=source.id
WHERE bank.dedup_fingerprint=%s AND bank.direction='outgoing'
GROUP BY bank.id,bank.dedup_fingerprint,bank.debit,classification.id,classification.classification_type,source.id,source.transaction_type,source.transaction_status,reversal.id,reversal.transaction_status,reversal.reversal_of_transaction_id
"""


__all__ = ["MySqlGovernmentSubsidyCurrentIssueAdapter"]
