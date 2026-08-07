"""MySQL root-fact scan and atomic projection for GOVSUB-003."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    MySqlAnomalyRepository,
)
from subsystems.anomalies.government_subsidy_integrity_anomaly_source import (
    GovernmentSubsidyIntegrityAnomalyConsumer,
    GovernmentSubsidyIntegrityRootFact,
    GovernmentSubsidyIntegrityScanPage,
    GovernmentSubsidyIntegrityScanRequest,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.alert_workflow import AnomalyApplication

_MAXIMUM_TRANSACTION_ROWS = 10_000
_MAXIMUM_PRIOR_ALERTS_PER_BATCH = 100


class BorrowedGovernmentSubsidyIntegrityUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class MySqlGovernmentSubsidyIntegrityRootFactSource:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_page(
        self,
        request: GovernmentSubsidyIntegrityScanRequest,
    ) -> GovernmentSubsidyIntegrityScanPage:
        with self._connection.cursor() as cursor:
            batches = _load_batches(cursor, request)
            batch_ids = tuple(_positive_integer(row, "batch_id") for row in batches)
            transactions = _load_transactions(cursor, batch_ids)
            previous_revisions = _load_previous_revisions(cursor, batch_ids)
        return _scan_page(request, batches, transactions, previous_revisions)


def project_government_subsidy_integrity_page(
    connection: Any,
    request: GovernmentSubsidyIntegrityScanRequest,
):
    consumer = _projection_consumer(connection)
    try:
        connection.begin()
        result = consumer.scan_page(request)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def _projection_consumer(connection):
    application = AnomalyApplication(
        default_anomaly_registry(),
        MySqlAnomalyRepository(connection),
        BorrowedGovernmentSubsidyIntegrityUnitOfWork,
    )
    return GovernmentSubsidyIntegrityAnomalyConsumer(
        MySqlGovernmentSubsidyIntegrityRootFactSource(connection),
        application,
    )


def _load_batches(cursor, request):
    cursor.execute(
        _BATCH_INTEGRITY_SELECT_SQL,
        (request.after_batch_id, request.limit),
    )
    return _mapping_rows(cursor.fetchall(), "government subsidy batch facts")


def _load_transactions(cursor, batch_ids):
    if not batch_ids:
        return {}
    placeholders = ",".join("%s" for _ in batch_ids)
    cursor.execute(
        _TRANSACTION_INTEGRITY_SELECT_SQL.format(placeholders=placeholders),
        batch_ids + (_MAXIMUM_TRANSACTION_ROWS + 1,),
    )
    rows = _mapping_rows(
        cursor.fetchall(),
        "government subsidy transaction facts",
    )
    if len(rows) > _MAXIMUM_TRANSACTION_ROWS:
        raise ValueError("government subsidy transaction scan exceeded bounded limit")
    return _group_rows(rows, "batch_id")


def _load_previous_revisions(cursor, batch_ids):
    if not batch_ids:
        return {}
    source_identities = tuple(
        f"government-subsidy-batch:{batch_id}" for batch_id in batch_ids
    )
    placeholders = ",".join("%s" for _ in source_identities)
    maximum_rows = len(batch_ids) * _MAXIMUM_PRIOR_ALERTS_PER_BATCH
    cursor.execute(
        _PREVIOUS_ALERT_SELECT_SQL.format(placeholders=placeholders),
        source_identities + (maximum_rows + 1,),
    )
    rows = _mapping_rows(cursor.fetchall(), "previous integrity alerts")
    if len(rows) > maximum_rows:
        raise ValueError("previous integrity alert scan exceeded bounded limit")
    return _previous_revisions_by_batch(rows)


def _scan_page(request, batches, transactions, previous_revisions):
    facts = tuple(
        _root_fact(
            batch,
            transactions.get(_positive_integer(batch, "batch_id"), ()),
            previous_revisions,
        )
        for batch in batches
    )
    next_cursor = facts[-1].batch_id if len(facts) == request.limit else None
    return GovernmentSubsidyIntegrityScanPage(facts, next_cursor)


# Kept cohesive so blockers, revision, and the immutable source coordinate agree.
def _root_fact(batch, transaction_rows, previous_revisions):
    batch_id = _positive_integer(batch, "batch_id")
    revision = _positive_integer(batch, "integrity_revision")
    blockers = tuple(
        sorted(
            set(_batch_blockers(batch))
            | set(_transaction_blockers(transaction_rows))
        )
    )
    source_version = _source_version(batch)
    event_values = {
        "batch": _stable_batch_snapshot(batch),
        "blockers": blockers,
        "transactions": tuple(
            _stable_transaction_snapshot(row) for row in transaction_rows
        ),
    }
    digest = fingerprint_payload(event_values).value
    return GovernmentSubsidyIntegrityRootFact(
        batch_id,
        revision,
        blockers,
        previous_revisions.get(batch_id, ()),
        source_version,
        f"gsi-root:{digest}",
    )


def _batch_blockers(row):
    try:
        return _validated_batch_blockers(row)
    except (TypeError, ValueError):
        return ("batch_money_or_projection_root_invalid",)


def _validated_batch_blockers(row):
    blockers = []
    requested = _nonnegative_integer(row, "requested_total_ntd")
    approved = _nonnegative_integer(row, "approved_total_ntd")
    net_allocated = _integer_value(row.get("ledger_net_allocated_ntd"), "ledger net")
    if requested != _nonnegative_integer(row, "item_requested_total_ntd"):
        blockers.append("requested_total_projection_mismatch")
    if approved != _nonnegative_integer(row, "item_approved_total_ntd"):
        blockers.append("approved_total_projection_mismatch")
    if net_allocated != _nonnegative_integer(row, "net_allocated_ntd"):
        blockers.append("net_allocated_projection_mismatch")
    if _nonnegative_integer(row, "overallocated_item_count"):
        blockers.append("claim_item_allocation_exceeds_approved")
    if _nonnegative_integer(row, "claim_item_count") == 0:
        blockers.append("claim_item_roots_missing")
    blockers.extend(_outstanding_and_status_blockers(row, approved, net_allocated))
    return tuple(blockers)


def _outstanding_and_status_blockers(row, approved, net_allocated):
    blockers = []
    outstanding = _nonnegative_integer(row, "outstanding_ntd")
    if net_allocated < 0 or net_allocated > approved:
        blockers.append("net_allocated_out_of_approved_range")
    if outstanding != approved - net_allocated:
        blockers.append("outstanding_projection_mismatch")
    expected_status = _expected_status(row, approved, net_allocated)
    if _text(row, "account_status") != expected_status:
        blockers.append("batch_status_projection_mismatch")
    return tuple(blockers)


def _expected_status(row, approved, net_allocated):
    if not bool(row.get("submitted")):
        return "draft"
    if not bool(row.get("approved")):
        return "submitted"
    if net_allocated == 0:
        return "approved"
    if net_allocated == approved:
        return "paid"
    return "partially_paid"


def _transaction_blockers(rows):
    blockers = []
    for row in rows:
        blockers.extend(_single_transaction_blockers(row))
    return tuple(blockers)


def _single_transaction_blockers(row):
    try:
        return _validated_transaction_blockers(row)
    except (TypeError, ValueError):
        return ("transaction_allocation_or_receipt_root_invalid",)


def _validated_transaction_blockers(row):
    blockers = []
    amount = _positive_integer(row, "transaction_amount_ntd")
    allocation_total = _nonnegative_integer(row, "allocation_total_ntd")
    allocation_count = _nonnegative_integer(row, "allocation_count")
    if _text(row, "transaction_status") != "succeeded":
        if allocation_count:
            blockers.append("non_succeeded_transaction_has_allocations")
        return tuple(blockers)
    if allocation_total != amount:
        blockers.append("transaction_allocation_total_mismatch")
    if _nonnegative_integer(row, "allocation_kind_mismatch_count"):
        blockers.append("transaction_allocation_kind_mismatch")
    if row.get("idempotency_key") is not None:
        blockers.extend(_formal_transaction_blockers(row, amount, allocation_count))
    return tuple(blockers)


def _formal_transaction_blockers(row, amount, allocation_count):
    blockers = []
    if _nonnegative_integer(row, "projection_event_count") != 1:
        blockers.append("formal_projection_event_missing_or_duplicate")
    elif not _projection_event_matches(row):
        blockers.append("formal_projection_event_contract_mismatch")
    if _nonnegative_integer(row, "apply_receipt_count") != 1:
        blockers.append("formal_apply_receipt_missing_or_duplicate")
    elif not _apply_receipt_matches(row, amount, allocation_count):
        blockers.append("formal_apply_receipt_contract_mismatch")
    return tuple(blockers)


def _projection_event_matches(row):
    expected_version = _optional_integer(row.get("expected_batch_version"))
    resulting_version = _optional_integer(row.get("resulting_batch_version"))
    before_net = _optional_integer(row.get("event_before_net_allocated_ntd"))
    after_net = _optional_integer(row.get("event_after_net_allocated_ntd"))
    amount = _positive_integer(row, "transaction_amount_ntd")
    expected_delta = amount if row.get("transaction_type") == "receipt" else -amount
    return (
        expected_version is not None
        and resulting_version == expected_version + 1
        and _optional_integer(row.get("event_expected_batch_version"))
        == expected_version
        and _optional_integer(row.get("event_resulting_batch_version"))
        == resulting_version
        and before_net is not None
        and after_net is not None
        and after_net - before_net == expected_delta
    )


def _apply_receipt_matches(row, amount, allocation_count):
    return (
        _optional_integer(row.get("receipt_batch_version"))
        == _optional_integer(row.get("resulting_batch_version"))
        and _optional_integer(row.get("receipt_amount_ntd")) == amount
        and _optional_integer(row.get("receipt_allocation_count"))
        == allocation_count
        and row.get("receipt_command_kind") == row.get("transaction_type")
        and row.get("receipt_status") == row.get("event_after_status")
        and _optional_integer(row.get("receipt_outstanding_ntd"))
        == _optional_integer(row.get("event_outstanding_ntd"))
    )


def _source_version(row):
    fields = (
        "integrity_revision",
        "latest_transaction_id",
        "latest_allocation_id",
        "latest_projection_event_id",
        "latest_apply_receipt_id",
        "latest_submission_event_id",
        "latest_approval_event_id",
        "latest_approval_item_id",
    )
    return sum(_nonnegative_integer(row, field) for field in fields)


def _stable_batch_snapshot(row):
    fields = (
        "batch_id",
        "integrity_revision",
        "requested_total_ntd",
        "approved_total_ntd",
        "net_allocated_ntd",
        "outstanding_ntd",
        "account_status",
        "item_requested_total_ntd",
        "item_approved_total_ntd",
        "ledger_net_allocated_ntd",
        "overallocated_item_count",
        "claim_item_count",
        "submitted",
        "approved",
    )
    return {field: _stable_value(row.get(field)) for field in fields}


def _stable_transaction_snapshot(row):
    return {
        field: _stable_value(row.get(field))
        for field in sorted(row)
    }


def _previous_revisions_by_batch(rows):
    grouped: dict[int, set[int]] = {}
    for row in rows:
        source_identity = _text(row, "source_identity")
        batch_id = _batch_id_from_source_identity(source_identity)
        grouped.setdefault(batch_id, set()).add(
            _positive_integer(row, "integrity_revision")
        )
    return {
        batch_id: tuple(sorted(revisions))
        for batch_id, revisions in grouped.items()
    }


def _batch_id_from_source_identity(source_identity):
    prefix = "government-subsidy-batch:"
    if not source_identity.startswith(prefix):
        raise ValueError("government subsidy integrity source identity is invalid")
    return _positive_integer(
        {"batch_id": source_identity.removeprefix(prefix)},
        "batch_id",
    )


def _group_rows(rows, field):
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_positive_integer(row, field), []).append(row)
    return {identity: tuple(values) for identity, values in grouped.items()}


def _mapping_rows(rows, label):
    if not isinstance(rows, (list, tuple)):
        raise TypeError(f"{label} must be a row collection")
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError(f"{label} must contain mapping rows")
    return tuple(rows)


def _positive_integer(row, field):
    value = _integer_value(row.get(field), field)
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _nonnegative_integer(row, field):
    value = _integer_value(row.get(field), field)
    if value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def _optional_integer(value):
    if value is None:
        return None
    return _integer_value(value, "optional integer")


def _integer_value(value, field):
    if isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise TypeError(f"{field} must be an integer")


def _text(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value.strip()


def _stable_value(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


_BATCH_INTEGRITY_SELECT_SQL = """
SELECT account.batch_id,
       account.aggregate_version AS integrity_revision,
       account.requested_total_ntd,
       account.approved_total_ntd,
       account.net_allocated_ntd,
       account.outstanding_ntd,
       account.status AS account_status,
       CASE WHEN batch.submitted_at IS NULL THEN 0 ELSE 1 END AS submitted,
       CASE WHEN batch.approved_at IS NULL THEN 0 ELSE 1 END AS approved,
       COALESCE(items.requested_total_ntd, 0) AS item_requested_total_ntd,
       COALESCE(items.approved_total_ntd, 0) AS item_approved_total_ntd,
       COALESCE(items.overallocated_item_count, 0)
           AS overallocated_item_count,
       COALESCE(items.claim_item_count, 0) AS claim_item_count,
       COALESCE(ledger.net_allocated_ntd, 0) AS ledger_net_allocated_ntd,
       COALESCE(clocks.latest_transaction_id, 0) AS latest_transaction_id,
       COALESCE(clocks.latest_allocation_id, 0) AS latest_allocation_id,
       COALESCE(clocks.latest_projection_event_id, 0)
           AS latest_projection_event_id,
       COALESCE(clocks.latest_apply_receipt_id, 0) AS latest_apply_receipt_id,
       COALESCE(clocks.latest_submission_event_id, 0)
           AS latest_submission_event_id,
       COALESCE(clocks.latest_approval_event_id, 0)
           AS latest_approval_event_id,
       COALESCE(clocks.latest_approval_item_id, 0)
           AS latest_approval_item_id
FROM government_subsidy_batch_accounts account
JOIN subsidy_claim_batches batch ON batch.id = account.batch_id
LEFT JOIN (
    SELECT item.batch_id,
           COUNT(*) AS claim_item_count,
           SUM(item.requested_amount) AS requested_total_ntd,
           SUM(item.approved_amount) AS approved_total_ntd,
           SUM(CASE WHEN COALESCE(allocation.net_allocated_ntd, 0)
                         > item.approved_amount
                    THEN 1 ELSE 0 END) AS overallocated_item_count
    FROM subsidy_claim_batch_items item
    LEFT JOIN (
        SELECT claim_batch_id,
               claim_item_id,
               SUM(CASE
                   WHEN allocation_type = 'receipt' THEN allocated_amount
                   WHEN allocation_type = 'reversal' THEN -allocated_amount
                   ELSE 0 END) AS net_allocated_ntd
        FROM government_subsidy_allocations
        GROUP BY claim_batch_id, claim_item_id
    ) allocation
      ON allocation.claim_batch_id = item.batch_id
     AND allocation.claim_item_id = item.id
    GROUP BY item.batch_id
) items ON items.batch_id = account.batch_id
LEFT JOIN (
    SELECT claim_batch_id AS batch_id,
           SUM(CASE
               WHEN allocation_type = 'receipt' THEN allocated_amount
               WHEN allocation_type = 'reversal' THEN -allocated_amount
               ELSE 0 END) AS net_allocated_ntd
    FROM government_subsidy_allocations
    GROUP BY claim_batch_id
) ledger ON ledger.batch_id = account.batch_id
LEFT JOIN (
    SELECT batch_identity.batch_id,
           (SELECT MAX(id) FROM government_subsidy_transactions
            WHERE claim_batch_id=batch_identity.batch_id)
               AS latest_transaction_id,
           (SELECT MAX(id) FROM government_subsidy_allocations
            WHERE claim_batch_id=batch_identity.batch_id)
               AS latest_allocation_id,
           (SELECT MAX(id) FROM government_subsidy_projection_events
            WHERE batch_id=batch_identity.batch_id)
               AS latest_projection_event_id,
           (SELECT MAX(id) FROM government_subsidy_apply_receipts
            WHERE batch_id=batch_identity.batch_id)
               AS latest_apply_receipt_id,
           (SELECT MAX(id) FROM government_subsidy_claim_submission_events
            WHERE batch_id=batch_identity.batch_id)
               AS latest_submission_event_id,
           (SELECT MAX(id) FROM government_subsidy_claim_approval_events
            WHERE batch_id=batch_identity.batch_id)
               AS latest_approval_event_id,
           (SELECT MAX(item.id)
            FROM government_subsidy_claim_approval_items item
            WHERE item.batch_id=batch_identity.batch_id)
               AS latest_approval_item_id
    FROM government_subsidy_batch_accounts batch_identity
) clocks ON clocks.batch_id = account.batch_id
WHERE account.batch_id > %s
ORDER BY account.batch_id
LIMIT %s
"""

_TRANSACTION_INTEGRITY_SELECT_SQL = """
SELECT txn.id AS transaction_id,
       txn.claim_batch_id AS batch_id,
       txn.transaction_type,
       txn.transaction_status,
       txn.amount AS transaction_amount_ntd,
       txn.idempotency_key,
       txn.expected_batch_version,
       txn.resulting_batch_version,
       COALESCE(allocation.allocation_count, 0) AS allocation_count,
       COALESCE(allocation.allocation_total_ntd, 0)
           AS allocation_total_ntd,
       COALESCE(allocation.kind_mismatch_count, 0)
           AS allocation_kind_mismatch_count,
       COALESCE(projection.projection_event_count, 0)
           AS projection_event_count,
       projection.expected_batch_version AS event_expected_batch_version,
       projection.resulting_batch_version AS event_resulting_batch_version,
       projection.before_net_allocated_ntd AS event_before_net_allocated_ntd,
       projection.after_net_allocated_ntd AS event_after_net_allocated_ntd,
       projection.after_status AS event_after_status,
       projection.outstanding_ntd AS event_outstanding_ntd,
       COALESCE(receipt.apply_receipt_count, 0) AS apply_receipt_count,
       receipt.batch_version AS receipt_batch_version,
       receipt.amount_ntd AS receipt_amount_ntd,
       receipt.allocation_count AS receipt_allocation_count,
       receipt.command_kind AS receipt_command_kind,
       receipt.status AS receipt_status,
       receipt.outstanding_ntd AS receipt_outstanding_ntd
FROM government_subsidy_transactions txn
LEFT JOIN (
    SELECT transaction_id,
           COUNT(*) AS allocation_count,
           SUM(allocated_amount) AS allocation_total_ntd,
           SUM(CASE
               WHEN allocation_type = transaction_type THEN 0 ELSE 1 END)
               AS kind_mismatch_count
    FROM (
        SELECT allocation.transaction_id,
               allocation.allocation_type,
               allocation.allocated_amount,
               owning_transaction.transaction_type
        FROM government_subsidy_allocations allocation
        JOIN government_subsidy_transactions owning_transaction
          ON owning_transaction.id = allocation.transaction_id
    ) allocation_roots
    GROUP BY transaction_id
) allocation ON allocation.transaction_id = txn.id
LEFT JOIN (
    SELECT transaction_id,
           COUNT(*) AS projection_event_count,
           MAX(expected_batch_version) AS expected_batch_version,
           MAX(resulting_batch_version) AS resulting_batch_version,
           MAX(before_net_allocated_ntd) AS before_net_allocated_ntd,
           MAX(after_net_allocated_ntd) AS after_net_allocated_ntd,
           MAX(after_status) AS after_status,
           MAX(outstanding_ntd) AS outstanding_ntd
    FROM government_subsidy_projection_events
    GROUP BY transaction_id
) projection ON projection.transaction_id = txn.id
LEFT JOIN (
    SELECT transaction_id,
           COUNT(*) AS apply_receipt_count,
           MAX(batch_version) AS batch_version,
           MAX(amount_ntd) AS amount_ntd,
           MAX(allocation_count) AS allocation_count,
           MAX(command_kind) AS command_kind,
           MAX(status) AS status,
           MAX(outstanding_ntd) AS outstanding_ntd
    FROM government_subsidy_apply_receipts
    GROUP BY transaction_id
) receipt ON receipt.transaction_id = txn.id
WHERE txn.claim_batch_id IN ({placeholders})
ORDER BY txn.claim_batch_id, txn.id
LIMIT %s
"""

_PREVIOUS_ALERT_SELECT_SQL = """
SELECT source_identity,
       CAST(JSON_UNQUOTE(JSON_EXTRACT(
           display_snapshot,
           '$.integrity_revision'
       )) AS UNSIGNED) AS integrity_revision
FROM anomaly_current_alerts
WHERE definition_code = 'GOVSUB-003'
  AND predicate_active = 1
  AND source_identity IN ({placeholders})
ORDER BY source_identity, fingerprint
LIMIT %s
"""


__all__ = [
    "BorrowedGovernmentSubsidyIntegrityUnitOfWork",
    "MySqlGovernmentSubsidyIntegrityRootFactSource",
    "project_government_subsidy_integrity_page",
]
