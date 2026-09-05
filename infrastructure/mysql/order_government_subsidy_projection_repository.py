"""MySQL read adapter for the Order -> Government Subsidy Workbench projection."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from domains.government_subsidy.ledger import GovernmentSubsidyBatchStatus
from domains.government_subsidy.overpayment import GovernmentSubsidyOverpaymentStatus
from shared_kernel.validation import require_canonical_text
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyClaimItemProjectionFact,
    GovernmentSubsidyOrderProjectionFacts,
    GovernmentSubsidyOverpaymentProjectionFact,
    GovernmentSubsidyProjectionContractError,
)


class MySqlOrderGovernmentSubsidyProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def query_order_projection_facts(
        self,
        case_nos: tuple[str, ...],
    ) -> tuple[GovernmentSubsidyOrderProjectionFacts, ...]:
        if not isinstance(case_nos, tuple):
            raise TypeError("case_nos must be a tuple")
        if not case_nos:
            return ()
        for case_no in case_nos:
            require_canonical_text(case_no, "case_no", 50)
        if len({case_no.casefold() for case_no in case_nos}) != len(case_nos):
            raise GovernmentSubsidyProjectionContractError(
                "requested case numbers are duplicate"
            )

        placeholders = ",".join("%s" for _ in case_nos)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ORDER_SUBSIDY_FACTS_SELECT_SQL.format(placeholders=placeholders),
                case_nos,
            )
            rows = cursor.fetchall()

        builders: dict[str, _CaseFactsBuilder] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise GovernmentSubsidyProjectionContractError(
                    "Government Subsidy projection row is invalid"
                )
            case_no = _required_text(row, "case_no")
            key = case_no.casefold()
            identity_status = _optional_text(row.get("identity_status"))
            builder = builders.get(key)
            if builder is None:
                builder = _CaseFactsBuilder(case_no, identity_status)
                builders[key] = builder
            elif builder.case_no != case_no or builder.identity_status != identity_status:
                raise GovernmentSubsidyProjectionContractError(
                    "order identity facts are inconsistent"
                )

            if row.get("claim_item_id") is None:
                continue

            claim = GovernmentSubsidyClaimItemProjectionFact(
                item_id=_positive_int(row, "claim_item_id"),
                batch_id=_positive_int(row, "batch_id"),
                batch_version=_nonnegative_int(row, "batch_version"),
                status=GovernmentSubsidyBatchStatus(
                    _required_text(row, "batch_status")
                ),
                claimed_hours=_nonnegative_integer_amount(row, "claimed_hours"),
                unit_price_ntd=_nonnegative_integer_amount(row, "unit_price_ntd"),
                requested_amount_ntd=_nonnegative_integer_amount(
                    row, "requested_amount_ntd"
                ),
                approved_amount_ntd=_nonnegative_integer_amount(
                    row, "approved_amount_ntd"
                ),
                net_allocated_ntd=_nonnegative_integer_amount(
                    row, "net_allocated_ntd"
                ),
                submitted_at=_optional_datetime(row.get("submitted_at")),
                approved_at=_optional_datetime(row.get("approved_at")),
            )
            builder.add_claim(claim)

            if row.get("overpayment_identity") is not None:
                overpayment = GovernmentSubsidyOverpaymentProjectionFact(
                    identity=_required_text(row, "overpayment_identity"),
                    batch_id=claim.batch_id,
                    status=GovernmentSubsidyOverpaymentStatus(
                        _required_text(row, "overpayment_status")
                    ),
                    remaining_amount_ntd=_nonnegative_integer_amount(
                        row, "overpayment_remaining_ntd"
                    ),
                    version=_nonnegative_int(row, "overpayment_version"),
                )
                builder.add_overpayment(overpayment)

        requested_keys = tuple(case_no.casefold() for case_no in case_nos)
        if set(builders) != set(requested_keys):
            raise GovernmentSubsidyProjectionContractError(
                "normal order facts are missing from Government Subsidy projection query"
            )
        return tuple(builders[key].build() for key in requested_keys)


class _CaseFactsBuilder:
    def __init__(self, case_no: str, identity_status: str | None) -> None:
        self.case_no = case_no
        self.identity_status = identity_status
        self.claims: dict[int, GovernmentSubsidyClaimItemProjectionFact] = {}
        self.overpayments: dict[str, GovernmentSubsidyOverpaymentProjectionFact] = {}

    def add_claim(self, fact: GovernmentSubsidyClaimItemProjectionFact) -> None:
        existing = self.claims.get(fact.item_id)
        if existing is not None and existing != fact:
            raise GovernmentSubsidyProjectionContractError(
                "claim item projection facts are inconsistent"
            )
        self.claims[fact.item_id] = fact

    def add_overpayment(
        self,
        fact: GovernmentSubsidyOverpaymentProjectionFact,
    ) -> None:
        key = fact.identity.casefold()
        existing = self.overpayments.get(key)
        if existing is not None and existing != fact:
            raise GovernmentSubsidyProjectionContractError(
                "overpayment projection facts are inconsistent"
            )
        self.overpayments[key] = fact

    def build(self) -> GovernmentSubsidyOrderProjectionFacts:
        return GovernmentSubsidyOrderProjectionFacts(
            case_no=self.case_no,
            identity_status=self.identity_status,
            claim_items=tuple(
                sorted(
                    self.claims.values(),
                    key=lambda item: (item.batch_id, item.item_id),
                )
            ),
            overpayments=tuple(
                sorted(
                    self.overpayments.values(),
                    key=lambda item: (item.batch_id, item.identity.casefold()),
                )
            ),
        )


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GovernmentSubsidyProjectionContractError(f"{key} must be canonical text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GovernmentSubsidyProjectionContractError(
            "identity_status must be text when present"
        )
    text = value.strip()
    return text or None


def _positive_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GovernmentSubsidyProjectionContractError(f"{key} must be positive")
    return value


def _nonnegative_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GovernmentSubsidyProjectionContractError(f"{key} must be nonnegative")
    return value


def _nonnegative_integer_amount(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    try:
        decimal_value = Decimal(str(value))
    except Exception as error:
        raise GovernmentSubsidyProjectionContractError(
            f"{key} must be an integer amount"
        ) from error
    if (
        not decimal_value.is_finite()
        or decimal_value != decimal_value.to_integral_value()
        or decimal_value < 0
    ):
        raise GovernmentSubsidyProjectionContractError(
            f"{key} must be a nonnegative integer amount"
        )
    return int(decimal_value)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise GovernmentSubsidyProjectionContractError(
            "Government Subsidy event timestamp must be datetime"
        )
    return value


_ORDER_SUBSIDY_FACTS_SELECT_SQL = """
SELECT
    o.case_no AS case_no,
    c.identity_status AS identity_status,
    i.id AS claim_item_id,
    i.batch_id AS batch_id,
    account.aggregate_version AS batch_version,
    account.status AS batch_status,
    i.claimed_hours AS claimed_hours,
    i.unit_price AS unit_price_ntd,
    i.requested_amount AS requested_amount_ntd,
    i.approved_amount AS approved_amount_ntd,
    COALESCE(receipts.net_amount, 0) + COALESCE(offsets.offset_amount, 0)
        AS net_allocated_ntd,
    batch.submitted_at AS submitted_at,
    batch.approved_at AS approved_at,
    overpayment.overpayment_identity AS overpayment_identity,
    overpayment.status AS overpayment_status,
    overpayment.remaining_amount_ntd AS overpayment_remaining_ntd,
    overpayment.projection_version AS overpayment_version
FROM orders o
JOIN clients c ON c.id = o.client_id
LEFT JOIN subsidy_claim_batch_items i ON i.case_no = o.case_no
LEFT JOIN subsidy_claim_batches batch ON batch.id = i.batch_id
LEFT JOIN government_subsidy_batch_accounts account
    ON account.batch_id = i.batch_id
LEFT JOIN (
    SELECT
        claim_item_id,
        claim_batch_id,
        SUM(
            CASE
                WHEN allocation_type = 'receipt' THEN allocated_amount
                WHEN allocation_type = 'reversal' THEN -allocated_amount
                ELSE 0
            END
        ) AS net_amount
    FROM government_subsidy_allocations
    GROUP BY claim_item_id, claim_batch_id
) receipts
    ON receipts.claim_item_id = i.id
    AND receipts.claim_batch_id = i.batch_id
LEFT JOIN (
    SELECT
        claim_item_id,
        claim_batch_id,
        SUM(allocated_amount_ntd) AS offset_amount
    FROM government_subsidy_overpayment_offsets
    GROUP BY claim_item_id, claim_batch_id
) offsets
    ON offsets.claim_item_id = i.id
    AND offsets.claim_batch_id = i.batch_id
LEFT JOIN (
    SELECT
        transaction.claim_batch_id,
        root.overpayment_identity,
        root.status,
        root.remaining_amount_ntd,
        root.projection_version
    FROM government_subsidy_overpayments root
    JOIN government_subsidy_transactions transaction
        ON transaction.id = root.source_transaction_id
) overpayment
    ON overpayment.claim_batch_id = i.batch_id
WHERE o.case_no IN ({placeholders})
ORDER BY o.case_no, i.batch_id, i.id, overpayment.overpayment_identity
"""


__all__ = ["MySqlOrderGovernmentSubsidyProjectionRepository"]
