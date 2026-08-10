"""MySQL root-fact scan and atomic projection for GOVSUB-004."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.government_subsidy_reversal_anomaly_source import (
    GovernmentSubsidyReversalAllocationRootFact,
    GovernmentSubsidyReversalAnomalyConsumer,
    GovernmentSubsidyReversalRootFact,
    GovernmentSubsidyReversalScanPage,
    GovernmentSubsidyReversalScanRequest,
    GovernmentSubsidySourceReceiptRootFact,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.alert_workflow import AnomalyApplication

_SOURCE_RECEIPT_TARGET_PREFIX = "government-subsidy-receipt:"
_SOURCE_COORDINATE_MARKER = ":source-receipt:"
_MAXIMUM_PRIOR_ALERTS_PER_ROW = 100
_MAXIMUM_SOURCE_ALLOCATION_ROWS = 10_000


class BorrowedGovernmentSubsidyReversalAnomalyUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class MySqlGovernmentSubsidyReversalRootFactSource:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_page(
        self,
        request: GovernmentSubsidyReversalScanRequest,
    ) -> GovernmentSubsidyReversalScanPage:
        with self._connection.cursor() as cursor:
            bank_rows = _load_bank_rows(cursor, request)
            target_receipt_ids = _target_source_receipt_ids(bank_rows)
            receipts = _load_source_receipts(cursor, target_receipt_ids)
            previous = _load_previous_coordinates(cursor, bank_rows)
            source_clock = _load_source_clock(cursor)
        return _scan_page(request, bank_rows, receipts, previous, source_clock)


def project_government_subsidy_reversal_anomaly_page(
    connection: Any,
    request: GovernmentSubsidyReversalScanRequest,
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
        BorrowedGovernmentSubsidyReversalAnomalyUnitOfWork,
    )
    return GovernmentSubsidyReversalAnomalyConsumer(
        MySqlGovernmentSubsidyReversalRootFactSource(connection),
        application,
    )


def _scan_page(request, bank_rows, receipts, previous, source_clock):
    facts = tuple(
        _root_fact(row, receipts, previous, source_clock)
        for row in bank_rows
    )
    next_cursor = facts[-1].finance_import_row_id if facts else None
    if len(facts) < request.limit:
        next_cursor = None
    return GovernmentSubsidyReversalScanPage(facts, next_cursor)


def _load_bank_rows(cursor, request):
    cursor.execute(
        _BANK_ROOT_SELECT_SQL,
        (request.after_finance_import_row_id, request.limit),
    )
    return _mapping_rows(cursor.fetchall(), "government reversal bank roots")


def _target_source_receipt_ids(rows) -> tuple[int, ...]:
    identities = {
        identity
        for row in rows
        for identity in (
            _classified_source_receipt_id(row),
            _optional_positive_integer(row.get("successful_source_receipt_id")),
        )
        if identity is not None
    }
    return tuple(sorted(identities))


def _load_source_receipts(cursor, receipt_ids):
    if not receipt_ids:
        return {}
    placeholders = ",".join("%s" for _ in receipt_ids)
    cursor.execute(
        _SOURCE_RECEIPTS_SELECT_SQL.format(placeholders=placeholders),
        receipt_ids + (_MAXIMUM_SOURCE_ALLOCATION_ROWS + 1,),
    )
    rows = _mapping_rows(cursor.fetchall(), "government receipt allocation roots")
    if len(rows) > _MAXIMUM_SOURCE_ALLOCATION_ROWS:
        raise ValueError("source receipt allocation scan exceeded bounded limit")
    return _source_receipts_by_identity(rows)


def _source_receipts_by_identity(rows):
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_positive_integer(row, "source_receipt_id"), []).append(row)
    return {
        receipt_id: _source_receipt(receipt_id, tuple(grouped[receipt_id]))
        for receipt_id in sorted(grouped)
    }


def _source_receipt(receipt_id, rows):
    first = rows[0]
    allocations = tuple(
        _source_allocation(row)
        for row in rows
        if row.get("allocation_id") is not None
    )
    return GovernmentSubsidySourceReceiptRootFact(
        receipt_id,
        _text(first, "transaction_type"),
        _text(first, "transaction_status"),
        _positive_integer(first, "source_receipt_amount_ntd"),
        allocations,
    )


def _source_allocation(row):
    return GovernmentSubsidyReversalAllocationRootFact(
        _positive_integer(row, "allocation_id"),
        _positive_integer(row, "allocated_ntd"),
        _nonnegative_integer(row, "reversed_ntd"),
    )


def _load_previous_coordinates(cursor, bank_rows):
    patterns = tuple(
        f"finance-import-row:{_positive_integer(row, 'finance_import_row_id')}"
        f"{_SOURCE_COORDINATE_MARKER}%"
        for row in bank_rows
    )
    if not patterns:
        return {}
    predicates = " OR ".join("source_identity LIKE %s" for _ in patterns)
    maximum_rows = len(patterns) * _MAXIMUM_PRIOR_ALERTS_PER_ROW
    cursor.execute(
        _PREVIOUS_ALERTS_SELECT_SQL.format(predicates=predicates),
        patterns + (maximum_rows + 1,),
    )
    rows = _mapping_rows(cursor.fetchall(), "previous reversal alert roots")
    if len(rows) > maximum_rows:
        raise ValueError("previous reversal alert scan exceeded bounded limit")
    return _previous_coordinates_by_row(rows)


def _previous_coordinates_by_row(rows):
    grouped: dict[int, set[str]] = {}
    for row in rows:
        row_id, coordinate = _parse_source_identity(
            _text(row, "source_identity")
        )
        grouped.setdefault(row_id, set()).add(coordinate)
    return {
        row_id: tuple(sorted(coordinates))
        for row_id, coordinates in grouped.items()
    }


def _parse_source_identity(source_identity):
    prefix, separator, coordinate = source_identity.partition(
        _SOURCE_COORDINATE_MARKER
    )
    if not separator or not coordinate:
        raise ValueError("government reversal anomaly source identity is invalid")
    row_value = prefix.removeprefix("finance-import-row:")
    if not row_value.isdigit() or int(row_value) <= 0:
        raise ValueError("government reversal anomaly source identity is invalid")
    return int(row_value), coordinate


def _load_source_clock(cursor) -> int:
    cursor.execute(_SOURCE_CLOCK_SELECT_SQL)
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise TypeError("government reversal source clock must be a mapping")
    return _nonnegative_integer(row, "source_clock")


# Kept cohesive so one bank root and its immutable receipt coordinates cannot drift.
def _root_fact(row, receipts, previous, source_clock):
    row_id = _positive_integer(row, "finance_import_row_id")
    classified_source_id = _classified_source_receipt_id(row)
    successful_source_id = _optional_positive_integer(
        row.get("successful_source_receipt_id")
    )
    selected_source_id = successful_source_id or classified_source_id
    values = {
        "finance_import_row_id": row_id,
        "reversal_bank_fact_identity": _text(row, "bank_fact_identity"),
        "amount_ntd": _outgoing_amount(row),
        "currently_government_subsidy": (
            row.get("classification_type") == "government_subsidy"
        ),
        "classified_source_receipt_id": classified_source_id,
        "successful_reversal_source_receipt_id": successful_source_id,
        "source_receipt": receipts.get(selected_source_id),
        "previous_source_receipt_coordinates": previous.get(row_id, ()),
        "source_version": source_clock,
    }
    values["source_event_identity"] = _source_event_identity(values)
    return GovernmentSubsidyReversalRootFact(**values)


def _classified_source_receipt_id(row) -> int | None:
    targets = _json_text_tuple(row.get("target_identities"))
    matching = tuple(
        target.removeprefix(_SOURCE_RECEIPT_TARGET_PREFIX)
        for target in targets
        if target.startswith(_SOURCE_RECEIPT_TARGET_PREFIX)
    )
    if len(matching) != 1:
        return None
    identity = matching[0]
    if not identity.isdigit() or int(identity) <= 0:
        return None
    return int(identity)


def _source_event_identity(values):
    digest = fingerprint_payload(
        {
            "amount_ntd": values["amount_ntd"],
            "bank_fact_identity": values["reversal_bank_fact_identity"],
            "classified_source_receipt_id": values["classified_source_receipt_id"],
            "currently_government_subsidy": values[
                "currently_government_subsidy"
            ],
            "previous_coordinates": values[
                "previous_source_receipt_coordinates"
            ],
            "source_receipt": _source_receipt_payload(values["source_receipt"]),
            "source_version": values["source_version"],
            "successful_source_receipt_id": values[
                "successful_reversal_source_receipt_id"
            ],
        }
    ).value
    return f"government-subsidy-reversal-root:{digest}"


def _source_receipt_payload(receipt):
    if receipt is None:
        return None
    return {
        "allocations": tuple(
            {
                "allocated_ntd": item.allocated_ntd,
                "allocation_id": item.allocation_id,
                "reversed_ntd": item.reversed_ntd,
            }
            for item in receipt.allocations
        ),
        "amount_ntd": receipt.amount_ntd,
        "source_receipt_id": receipt.source_receipt_id,
        "transaction_status": receipt.transaction_status,
        "transaction_type": receipt.transaction_type,
    }


def _outgoing_amount(row) -> int:
    if row.get("direction") != "outgoing":
        raise ValueError("government_subsidy_bank_fact_invalid")
    debit = _money_integer(row.get("debit"), "debit")
    credit = _money_integer(row.get("credit"), "credit")
    if debit <= 0 or credit != 0:
        raise ValueError("government_subsidy_bank_fact_invalid")
    return debit


def _mapping_rows(rows, label):
    if not isinstance(rows, (list, tuple)):
        raise TypeError(f"{label} must be a row collection")
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError(f"{label} must contain mapping rows")
    return tuple(rows)


def _json_text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, (list, tuple)):
        return ()
    if any(not isinstance(item, str) for item in parsed):
        return ()
    return tuple(parsed)


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


def _money_integer(value, field) -> int:
    if value is None:
        return 0
    return _integer_value(value, field)


def _optional_positive_integer(value) -> int | None:
    if value is None:
        return None
    return _positive_integer({"value": value}, "value")


def _text(row, field) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value.strip()


_BANK_ROOT_SELECT_SQL = """
SELECT bank.id AS finance_import_row_id,
       bank.dedup_fingerprint AS bank_fact_identity,
       bank.direction,
       bank.debit,
       bank.credit,
       classification.id AS classification_event_id,
       classification.classification_type,
       classification.target_identities,
       reversal.reversal_of_transaction_id AS successful_source_receipt_id
FROM finance_import_rows bank
JOIN finance_import_classification_events classification
  ON classification.id = (
      SELECT MAX(latest.id)
      FROM finance_import_classification_events latest
      WHERE latest.finance_import_row_id = bank.id
  )
LEFT JOIN government_subsidy_transactions reversal
  ON reversal.finance_import_row_id = bank.id
 AND reversal.transaction_type = 'reversal'
 AND reversal.transaction_status = 'succeeded'
WHERE bank.id > %s
  AND bank.direction = 'outgoing'
  AND EXISTS (
      SELECT 1
      FROM finance_import_classification_events history
      WHERE history.finance_import_row_id = bank.id
        AND history.classification_type = 'government_subsidy'
  )
ORDER BY bank.id
LIMIT %s
"""

_SOURCE_RECEIPTS_SELECT_SQL = """
SELECT receipt.id AS source_receipt_id,
       receipt.transaction_type,
       receipt.transaction_status,
       receipt.amount AS source_receipt_amount_ntd,
       allocation.id AS allocation_id,
       allocation.allocated_amount AS allocated_ntd,
       COALESCE(SUM(reversal.allocated_amount), 0) AS reversed_ntd
FROM government_subsidy_transactions receipt
LEFT JOIN government_subsidy_allocations allocation
  ON allocation.transaction_id = receipt.id
 AND allocation.claim_batch_id = receipt.claim_batch_id
 AND allocation.allocation_type = 'receipt'
LEFT JOIN government_subsidy_allocations reversal
  ON reversal.reversal_of_allocation_id = allocation.id
 AND reversal.claim_batch_id = allocation.claim_batch_id
 AND reversal.allocation_type = 'reversal'
WHERE receipt.id IN ({placeholders})
GROUP BY receipt.id,
         receipt.transaction_type,
         receipt.transaction_status,
         receipt.amount,
         allocation.id,
         allocation.allocated_amount
ORDER BY receipt.id, allocation.id
LIMIT %s
"""

_PREVIOUS_ALERTS_SELECT_SQL = """
SELECT source_identity
FROM anomaly_current_alerts
WHERE definition_code = 'GOVSUB-004'
  AND predicate_active = 1
  AND ({predicates})
ORDER BY source_identity
LIMIT %s
"""

_SOURCE_CLOCK_SELECT_SQL = """
SELECT
    COALESCE((SELECT SUM(id)
              FROM finance_import_classification_events), 0)
  + COALESCE((SELECT SUM(id)
              FROM government_subsidy_transactions), 0)
  + COALESCE((SELECT SUM(id)
              FROM government_subsidy_allocations), 0)
  AS source_clock
"""


__all__ = [
    "BorrowedGovernmentSubsidyReversalAnomalyUnitOfWork",
    "MySqlGovernmentSubsidyReversalRootFactSource",
    "project_government_subsidy_reversal_anomaly_page",
]
