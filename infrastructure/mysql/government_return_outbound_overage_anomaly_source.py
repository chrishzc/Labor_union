"""Bounded MySQL source for government return outgoing-overage alerts."""

from __future__ import annotations

from typing import Any, Mapping

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.government_return_outbound_overage_anomaly_source import (
    GovernmentReturnOutboundOverageAnomalyConsumer,
    GovernmentReturnOutboundOverageRootFact,
    GovernmentReturnOutboundOverageScanPage,
    GovernmentReturnOutboundOverageScanRequest,
)


class MySqlGovernmentReturnOutboundOverageSource:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_page(self, request: GovernmentReturnOutboundOverageScanRequest) -> GovernmentReturnOutboundOverageScanPage:
        with self._connection.cursor() as cursor:
            cursor.execute(_OUTBOUND_OVERAGE_SQL, (request.after_finance_import_row_id, request.limit))
            rows = cursor.fetchall()
        facts = tuple(_root_fact(row) for row in rows)
        next_row_id = facts[-1].finance_import_row_id if len(facts) == request.limit else None
        return GovernmentReturnOutboundOverageScanPage(facts, next_row_id)


def project_government_return_outbound_overage_page(connection: Any, request: GovernmentReturnOutboundOverageScanRequest):
    application = AnomalyApplication(
        default_anomaly_registry(),
        MySqlAnomalyRepository(connection),
        lambda: AnomalyMySqlUnitOfWork(connection),
    )
    consumer = GovernmentReturnOutboundOverageAnomalyConsumer(
        MySqlGovernmentReturnOutboundOverageSource(connection), application
    )
    return consumer.scan_page(request)


def _root_fact(row: Mapping[str, object]) -> GovernmentReturnOutboundOverageRootFact:
    return GovernmentReturnOutboundOverageRootFact(
        _positive(row, "finance_import_row_id"),
        _text(row, "bank_fact_identity"),
        _text(row, "payable_identity"),
        _text(row, "overpayment_identity"),
        _positive(row, "bank_amount_ntd"),
        _positive(row, "payable_remaining_ntd"),
        _positive(row, "payable_version"),
    )


def _positive(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("government_return_outbound_overage_source_invalid")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError("government_return_outbound_overage_source_invalid")
    return value


_OUTBOUND_OVERAGE_SQL = """
SELECT bank.id AS finance_import_row_id,
       bank.dedup_fingerprint AS bank_fact_identity,
       payable.payable_identity,
       payable.overpayment_identity,
       bank.debit AS bank_amount_ntd,
       payable.remaining_amount_ntd AS payable_remaining_ntd,
       payable.projection_version AS payable_version
FROM finance_import_rows bank
JOIN government_payer_receiving_accounts recipient
  ON recipient.account_number=bank.resolved_counterparty_account
JOIN government_overpayment_return_payables payable
  ON payable.agency_identity=recipient.payer_identity
WHERE bank.id > %s
  AND bank.direction='outgoing'
  AND bank.debit > payable.remaining_amount_ntd
  AND payable.status IN ('payable','partially_paid')
  AND 1 = (
      SELECT COUNT(DISTINCT candidate_payable.payable_identity)
      FROM government_payer_receiving_accounts candidate_recipient
      JOIN government_overpayment_return_payables candidate_payable
        ON candidate_payable.agency_identity=candidate_recipient.payer_identity
      WHERE candidate_recipient.account_number=bank.resolved_counterparty_account
        AND candidate_payable.status IN ('payable','partially_paid')
        AND bank.debit > candidate_payable.remaining_amount_ntd
  )
  AND NOT EXISTS (
      SELECT 1 FROM government_overpayment_return_payouts payout
      WHERE payout.finance_import_row_id=bank.id
  )
ORDER BY bank.id,payable.payable_identity
LIMIT %s
"""
