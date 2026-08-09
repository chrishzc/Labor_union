"""MySQL root-fact scan and atomic projection for GOVSUB-001/002."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    MySqlAnomalyRepository,
)
from subsystems.anomalies.government_subsidy_anomaly_source import (
    GovernmentSubsidyAnomalyConsumer,
    GovernmentSubsidyAnomalyScanPage,
    GovernmentSubsidyAnomalyScanRequest,
    GovernmentSubsidyEligibleBatch,
    GovernmentSubsidyItemOutstanding,
    GovernmentSubsidyReceiptRootFact,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.alert_workflow import AnomalyApplication

_MAXIMUM_PRIOR_AMBIGUOUS_ALERTS_PER_ROW = 100
_MAXIMUM_ELIGIBLE_CLAIM_ITEM_ROWS = 10_000


class BorrowedGovernmentSubsidyAnomalyUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class MySqlGovernmentSubsidyAnomalyRootFactSource:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_page(
        self,
        request: GovernmentSubsidyAnomalyScanRequest,
    ) -> GovernmentSubsidyAnomalyScanPage:
        with self._connection.cursor() as cursor:
            row_facts = _load_bank_rows(cursor, request)
            batches = _load_eligible_batches(cursor)
            previous_batches = _load_previous_ambiguous_batches(
                cursor,
                row_facts,
            )
            source_clock = _load_source_clock(cursor)
        return _scan_page(
            request,
            row_facts,
            batches,
            previous_batches,
            source_clock,
        )


def project_government_subsidy_anomaly_page(
    connection: Any,
    request: GovernmentSubsidyAnomalyScanRequest,
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
        BorrowedGovernmentSubsidyAnomalyUnitOfWork,
    )
    return GovernmentSubsidyAnomalyConsumer(
        MySqlGovernmentSubsidyAnomalyRootFactSource(connection),
        application,
    )


def _scan_page(request, row_facts, batches, previous_batches, source_clock):
    facts = tuple(
        _root_fact(row, batches, previous_batches, source_clock)
        for row in row_facts
    )
    next_cursor = facts[-1].finance_import_row_id if facts else None
    if len(facts) < request.limit:
        next_cursor = None
    return GovernmentSubsidyAnomalyScanPage(facts, next_cursor)


def _load_bank_rows(cursor, request):
    cursor.execute(
        _BANK_ROOT_SELECT_SQL,
        (request.after_finance_import_row_id, request.limit),
    )
    return _mapping_rows(cursor.fetchall(), "finance import root facts")


def _load_eligible_batches(cursor):
    cursor.execute(
        _ELIGIBLE_BATCH_SELECT_SQL,
        (_MAXIMUM_ELIGIBLE_CLAIM_ITEM_ROWS + 1,),
    )
    rows = _mapping_rows(cursor.fetchall(), "government subsidy claim facts")
    if len(rows) > _MAXIMUM_ELIGIBLE_CLAIM_ITEM_ROWS:
        raise ValueError("eligible claim fact scan exceeded bounded limit")
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_positive_integer(row, "batch_id"), []).append(row)
    return tuple(
        _eligible_batch(batch_id, tuple(grouped[batch_id]))
        for batch_id in sorted(grouped)
    )


def _eligible_batch(batch_id, rows):
    outstanding_ntd = _positive_integer(rows[0], "batch_outstanding_ntd")
    if any(
        _positive_integer(row, "batch_outstanding_ntd") != outstanding_ntd
        for row in rows
    ):
        raise ValueError("government_subsidy_claim_facts_invalid")
    items = tuple(_outstanding_item(row) for row in rows)
    if sum(item.outstanding_ntd for item in items) != outstanding_ntd:
        raise ValueError("government_subsidy_claim_facts_invalid")
    return GovernmentSubsidyEligibleBatch(batch_id, outstanding_ntd, items)


def _outstanding_item(row):
    approved = _nonnegative_integer(row, "approved_amount_ntd")
    allocated = _nonnegative_integer(row, "net_allocated_ntd")
    if allocated > approved:
        raise ValueError("government_subsidy_claim_facts_invalid")
    return GovernmentSubsidyItemOutstanding(
        _positive_integer(row, "claim_item_id"),
        approved - allocated,
    )


def _load_previous_ambiguous_batches(cursor, row_facts):
    source_patterns = tuple(
        f"finance-import-row:{_positive_integer(row, 'finance_import_row_id')}"
        ":batch:%"
        for row in row_facts
    )
    if not source_patterns:
        return {}
    predicates = " OR ".join(
        "source_identity LIKE %s" for _ in source_patterns
    )
    maximum_rows = (
        len(source_patterns) * _MAXIMUM_PRIOR_AMBIGUOUS_ALERTS_PER_ROW
    )
    cursor.execute(
        _PREVIOUS_AMBIGUOUS_SELECT_SQL.format(predicates=predicates),
        source_patterns + (maximum_rows + 1,),
    )
    rows = _mapping_rows(cursor.fetchall(), "previous anomaly projections")
    if len(rows) > maximum_rows:
        raise ValueError("previous anomaly projection scan exceeded bounded limit")
    return _previous_batches_by_source(rows)


def _previous_batches_by_source(rows):
    grouped: dict[str, set[int]] = {}
    for row in rows:
        source_identity = _receipt_row_source_identity(
            _text(row, "source_identity")
        )
        snapshot = _json_object(row.get("display_snapshot"))
        grouped.setdefault(source_identity, set()).add(
            _positive_integer(snapshot, "batch_id")
        )
    return {
        identity: tuple(sorted(batch_ids))
        for identity, batch_ids in grouped.items()
    }


def _receipt_row_source_identity(source_identity):
    row_identity, separator, _batch_identity = source_identity.partition(
        ":batch:"
    )
    if not separator:
        raise ValueError("government subsidy anomaly source identity is invalid")
    return row_identity


def _load_source_clock(cursor) -> int:
    cursor.execute(_SOURCE_CLOCK_SELECT_SQL)
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise TypeError("government subsidy source clock must be a mapping")
    return _nonnegative_integer(row, "source_clock")


def _root_fact(row, batches, previous_batches, source_clock):
    row_id = _positive_integer(row, "finance_import_row_id")
    amount_ntd = _incoming_amount(row)
    eligible = tuple(
        batch for batch in batches if amount_ntd <= batch.outstanding_ntd
    )
    source_identity = f"finance-import-row:{row_id}"
    values = _root_values(
        row,
        row_id,
        amount_ntd,
        eligible,
        previous_batches.get(source_identity, ()),
        source_clock,
    )
    values["source_event_identity"] = _source_event_identity(values)
    return GovernmentSubsidyReceiptRootFact(**values)


def _root_values(
    row,
    row_id,
    amount_ntd,
    eligible,
    previous_batch_ids,
    source_clock,
):
    return {
        "finance_import_row_id": row_id,
        "bank_fact_identity": _text(row, "bank_fact_identity"),
        "amount_ntd": amount_ntd,
        "currently_government_subsidy": (
            row.get("classification_type") == "government_subsidy"
        ),
        "succeeded_batch_id": _optional_positive_integer(
            row.get("succeeded_batch_id")
        ),
        "eligible_batches": eligible,
        "previous_ambiguous_batch_ids": previous_batch_ids,
        "source_version": (
            source_clock + _positive_integer(row, "classification_event_id")
        ),
    }


def _source_event_identity(values):
    digest = fingerprint_payload(
        {
            "amount_ntd": values["amount_ntd"],
            "bank_fact_identity": values["bank_fact_identity"],
            "classification": values["currently_government_subsidy"],
            "eligible_batches": _batch_event_snapshot(
                values["eligible_batches"]
            ),
            "succeeded_batch_id": values["succeeded_batch_id"],
            "source_version": values["source_version"],
        }
    ).value
    return f"government-subsidy-root:{digest}"


def _batch_event_snapshot(batches):
    return tuple(
        {
            "batch_id": batch.batch_id,
            "items": tuple(
                {
                    "claim_item_id": item.claim_item_id,
                    "outstanding_ntd": item.outstanding_ntd,
                }
                for item in batch.items
            ),
            "outstanding_ntd": batch.outstanding_ntd,
        }
        for batch in batches
    )


def _incoming_amount(row) -> int:
    if row.get("direction") != "incoming":
        raise ValueError("government_subsidy_bank_fact_invalid")
    credit = _positive_integer(row, "credit")
    debit = row.get("debit")
    if debit is not None and _integer_value(debit, "debit") != 0:
        raise ValueError("government_subsidy_bank_fact_invalid")
    return credit


def _mapping_rows(rows, label):
    if not isinstance(rows, (list, tuple)):
        raise TypeError(f"{label} must be a row collection")
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError(f"{label} must contain mapping rows")
    return tuple(rows)


def _positive_integer(row, field) -> int:
    value = _integer_value(row.get(field), field)
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _nonnegative_integer(row, field) -> int:
    value = _integer_value(row.get(field), field)
    if value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def _integer_value(value, field) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise TypeError(f"{field} must be an integer")


def _optional_positive_integer(value) -> int | None:
    if value is None:
        return None
    return _positive_integer({"value": value}, "value")


def _text(row, field) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value.strip()


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise TypeError("anomaly display snapshot must be an object")
    return parsed


_BANK_ROOT_SELECT_SQL = """
SELECT bank.id AS finance_import_row_id,
       bank.dedup_fingerprint AS bank_fact_identity,
       bank.direction,
       bank.debit,
       bank.credit,
       classification.id AS classification_event_id,
       classification.classification_type,
       receipt.claim_batch_id AS succeeded_batch_id
FROM finance_import_rows bank
JOIN finance_import_classification_events classification
  ON classification.id = (
      SELECT MAX(latest.id)
      FROM finance_import_classification_events latest
      WHERE latest.finance_import_row_id = bank.id
  )
LEFT JOIN government_subsidy_transactions receipt
  ON receipt.finance_import_row_id = bank.id
 AND receipt.transaction_type = 'receipt'
 AND receipt.transaction_status = 'succeeded'
WHERE bank.id > %s
  AND EXISTS (
      SELECT 1
      FROM finance_import_classification_events history
      WHERE history.finance_import_row_id = bank.id
        AND history.classification_type = 'government_subsidy'
  )
ORDER BY bank.id
LIMIT %s
"""

_ELIGIBLE_BATCH_SELECT_SQL = """
SELECT account.batch_id,
       account.outstanding_ntd AS batch_outstanding_ntd,
       item.id AS claim_item_id,
       item.approved_amount AS approved_amount_ntd,
       COALESCE(allocation.net_allocated_ntd, 0) AS net_allocated_ntd
FROM government_subsidy_batch_accounts account
JOIN subsidy_claim_batches batch
  ON batch.id = account.batch_id
JOIN subsidy_claim_batch_items item
  ON item.batch_id = account.batch_id
LEFT JOIN (
    SELECT claim_batch_id,
           claim_item_id,
           SUM(
               CASE
                   WHEN allocation_type = 'receipt' THEN allocated_amount
                   WHEN allocation_type = 'reversal' THEN -allocated_amount
                   ELSE 0
               END
           ) AS net_allocated_ntd
    FROM government_subsidy_allocations
    GROUP BY claim_batch_id, claim_item_id
) allocation
  ON allocation.claim_batch_id = item.batch_id
 AND allocation.claim_item_id = item.id
WHERE batch.submitted_at IS NOT NULL
  AND batch.approved_at IS NOT NULL
  AND account.status IN ('approved', 'partially_paid')
  AND account.approved_total_ntd > 0
  AND account.outstanding_ntd > 0
ORDER BY account.batch_id, item.id
LIMIT %s
"""

_PREVIOUS_AMBIGUOUS_SELECT_SQL = """
SELECT source_identity, display_snapshot
FROM anomaly_current_alerts
WHERE definition_code = 'GOVSUB-002'
  AND predicate_active = 1
  AND ({predicates})
ORDER BY source_identity, fingerprint
LIMIT %s
"""

_SOURCE_CLOCK_SELECT_SQL = """
SELECT
    COALESCE((SELECT SUM(aggregate_version)
              FROM government_subsidy_batch_accounts), 0)
  AS source_clock
"""


__all__ = [
    "BorrowedGovernmentSubsidyAnomalyUnitOfWork",
    "MySqlGovernmentSubsidyAnomalyRootFactSource",
    "project_government_subsidy_anomaly_page",
]
