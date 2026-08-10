"""Canonical GOVSUB-001/002 root-fact projection rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest


_CONSUMER_IDENTITY = "government-subsidy-anomaly-source-v1"
_MAXIMUM_SCAN_SIZE = 100
_TEXT_MAXIMUM_LENGTH = 191


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyItemOutstanding:
    claim_item_id: int
    outstanding_ntd: int

    def __post_init__(self) -> None:
        require_positive_integer(self.claim_item_id, "claim item id")
        require_nonnegative_integer(self.outstanding_ntd, "item outstanding")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyEligibleBatch:
    batch_id: int
    outstanding_ntd: int
    items: tuple[GovernmentSubsidyItemOutstanding, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.batch_id, "claim batch id")
        require_positive_integer(self.outstanding_ntd, "batch outstanding")
        _validate_items(self.items)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReceiptRootFact:
    finance_import_row_id: int
    bank_fact_identity: str
    amount_ntd: int
    currently_government_subsidy: bool
    succeeded_batch_id: int | None
    eligible_batches: tuple[GovernmentSubsidyEligibleBatch, ...]
    previous_ambiguous_batch_ids: tuple[int, ...]
    source_version: int
    source_event_identity: str

    def __post_init__(self) -> None:
        _validate_receipt_root_identity(self)
        _validate_boolean(self.currently_government_subsidy, "classification")
        _validate_optional_positive_integer(self.succeeded_batch_id, "succeeded batch id")
        _validate_batches(self.eligible_batches)
        _validate_batch_ids(self.previous_ambiguous_batch_ids)
        require_nonnegative_integer(self.source_version, "source version")
        require_canonical_text(self.source_event_identity, "source event identity", _TEXT_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyAnomalyScanRequest:
    limit: int
    after_finance_import_row_id: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("scan limit must be an integer")
        if not 1 <= self.limit <= _MAXIMUM_SCAN_SIZE:
            raise ValueError("scan limit must be between 1 and 100")
        require_nonnegative_integer(self.after_finance_import_row_id, "finance import scan cursor")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyAnomalyScanPage:
    facts: tuple[GovernmentSubsidyReceiptRootFact, ...]
    next_finance_import_row_id: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple):
            raise TypeError("scan facts must be a tuple")
        if any(not isinstance(fact, GovernmentSubsidyReceiptRootFact) for fact in self.facts):
            raise TypeError("scan facts contain an invalid root fact")
        _validate_optional_positive_integer(
            self.next_finance_import_row_id,
            "next finance import scan cursor",
        )


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyAnomalyScanResult:
    projections: tuple[CurrentAlertProjection | None, ...]
    next_finance_import_row_id: int | None


class GovernmentSubsidyAnomalyRootFactSource(Protocol):
    def load_page(
        self,
        request: GovernmentSubsidyAnomalyScanRequest,
    ) -> GovernmentSubsidyAnomalyScanPage: ...


class GovernmentSubsidyAnomalyConsumer:
    def __init__(self, source: GovernmentSubsidyAnomalyRootFactSource, anomaly_application: AnomalyApplication) -> None:
        self._source = source
        self._anomaly_application = anomaly_application

    def scan_page(self, request: GovernmentSubsidyAnomalyScanRequest) -> GovernmentSubsidyAnomalyScanResult:
        page = self._source.load_page(request)
        if len(page.facts) > request.limit:
            raise ValueError("root-fact source exceeded the bounded scan limit")
        projections = tuple(
            self._anomaly_application.project(alert_request)
            for fact in page.facts
            for alert_request in build_government_subsidy_alert_requests(fact)
        )
        return GovernmentSubsidyAnomalyScanResult(projections, page.next_finance_import_row_id)


def build_government_subsidy_alert_requests(
    root_fact: GovernmentSubsidyReceiptRootFact,
) -> tuple[ProjectAlertRequest, ...]:
    unique_batch = _unique_eligible_batch(root_fact)
    requests = [_no_unique_batch_request(root_fact, unique_batch)]
    ambiguous_batch_ids = _ambiguous_batch_ids(root_fact, unique_batch)
    requests.extend(
        _ambiguous_allocation_request(root_fact, unique_batch, batch_id)
        for batch_id in ambiguous_batch_ids
    )
    return tuple(requests)


def _no_unique_batch_request(root_fact, unique_batch):
    active = _needs_review(root_fact) and unique_batch is None
    candidate_ids = tuple(batch.batch_id for batch in root_fact.eligible_batches)
    snapshot = {
        "bank_fact_identity": root_fact.bank_fact_identity,
        "candidate_batch_ids": candidate_ids,
    }
    return _project_request(
        "GOVSUB-001",
        root_fact,
        active,
        {"bank_fact_identity": root_fact.bank_fact_identity},
        snapshot,
        "no-unique-batch",
    )


def _ambiguous_allocation_request(root_fact, unique_batch, batch_id):
    snapshot = _ambiguous_allocation_snapshot(root_fact, unique_batch, batch_id)
    return _project_request(
        "GOVSUB-002",
        root_fact,
        _ambiguous_allocation_is_active(root_fact, unique_batch, batch_id),
        _ambiguous_allocation_fingerprint(root_fact, batch_id),
        snapshot,
        f"batch:{batch_id}",
    )


def _ambiguous_allocation_is_active(root_fact, unique_batch, batch_id):
    return (
        _needs_review(root_fact)
        and unique_batch is not None
        and unique_batch.batch_id == batch_id
        and _allocation_is_ambiguous(root_fact.amount_ntd, unique_batch)
    )


def _ambiguous_allocation_snapshot(root_fact, unique_batch, batch_id):
    item_outstanding = ()
    if unique_batch is not None and unique_batch.batch_id == batch_id:
        item_outstanding = _item_outstanding_snapshot(unique_batch)
    return {
        "bank_fact_identity": root_fact.bank_fact_identity,
        "batch_id": batch_id,
        "item_outstanding": item_outstanding,
    }


def _ambiguous_allocation_fingerprint(root_fact, batch_id):
    return {
        "bank_fact_identity": root_fact.bank_fact_identity,
        "batch_id": str(batch_id),
    }


def _project_request(code, root_fact, active, fingerprint_values, snapshot, partition_suffix):
    source_identity = _alert_source_identity(code, root_fact.finance_import_row_id, partition_suffix)
    return ProjectAlertRequest(
        _desired_state(code, source_identity, root_fact, active, fingerprint_values),
        _projector_event_identity(code, root_fact, active, snapshot),
        _CONSUMER_IDENTITY,
        f"{code}:{source_identity}",
        snapshot,
    )


def _alert_source_identity(code, row_id, partition_suffix):
    row_identity = f"finance-import-row:{row_id}"
    if code == "GOVSUB-002":
        return f"{row_identity}:{partition_suffix}"
    return row_identity


def _desired_state(code, source_identity, root_fact, active, fingerprint_values):
    return DesiredAlertState(
        code,
        source_identity,
        root_fact.source_version,
        active,
        fingerprint_values,
    )


def _projector_event_identity(code, root_fact, active, snapshot):
    digest = fingerprint_payload(
        {
            "active": active,
            "code": code,
            "root_event": root_fact.source_event_identity,
            "snapshot": snapshot,
        }
    ).value
    return f"government-subsidy:{code}:{digest}"


def _unique_eligible_batch(root_fact):
    if len(root_fact.eligible_batches) != 1:
        return None
    return root_fact.eligible_batches[0]


def _needs_review(root_fact) -> bool:
    return root_fact.currently_government_subsidy and root_fact.succeeded_batch_id is None


def _allocation_is_ambiguous(amount_ntd, batch) -> bool:
    positive_items = tuple(item for item in batch.items if item.outstanding_ntd > 0)
    return amount_ntd < batch.outstanding_ntd and len(positive_items) > 1


def _ambiguous_batch_ids(root_fact, unique_batch) -> tuple[int, ...]:
    identities = set(root_fact.previous_ambiguous_batch_ids)
    if unique_batch is not None:
        identities.add(unique_batch.batch_id)
    if root_fact.succeeded_batch_id is not None:
        identities.add(root_fact.succeeded_batch_id)
    return tuple(sorted(identities))


def _item_outstanding_snapshot(batch):
    return tuple(
        {"claim_item_id": item.claim_item_id, "outstanding_ntd": item.outstanding_ntd}
        for item in batch.items
        if item.outstanding_ntd > 0
    )


def _validate_items(items) -> None:
    if not isinstance(items, tuple):
        raise TypeError("batch items must be a tuple")
    if any(not isinstance(item, GovernmentSubsidyItemOutstanding) for item in items):
        raise TypeError("batch items contain an invalid root fact")
    identities = tuple(item.claim_item_id for item in items)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("claim items must be sorted and unique")


def _validate_batches(batches) -> None:
    if not isinstance(batches, tuple):
        raise TypeError("eligible batches must be a tuple")
    if any(not isinstance(batch, GovernmentSubsidyEligibleBatch) for batch in batches):
        raise TypeError("eligible batches contain an invalid root fact")
    _validate_batch_ids(tuple(batch.batch_id for batch in batches))


def _validate_batch_ids(batch_ids) -> None:
    if not isinstance(batch_ids, tuple):
        raise TypeError("batch identities must be a tuple")
    if batch_ids != tuple(sorted(set(batch_ids))):
        raise ValueError("batch identities must be sorted and unique")
    for batch_id in batch_ids:
        require_positive_integer(batch_id, "claim batch id")


def _validate_optional_positive_integer(value, field) -> None:
    if value is not None:
        require_positive_integer(value, field)


def _validate_receipt_root_identity(root_fact) -> None:
    require_positive_integer(root_fact.finance_import_row_id, "finance import row id")
    require_canonical_text(root_fact.bank_fact_identity, "bank fact identity", _TEXT_MAXIMUM_LENGTH)
    require_positive_integer(root_fact.amount_ntd, "bank amount")


def _validate_boolean(value, field) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be bool")


__all__ = [
    "GovernmentSubsidyAnomalyConsumer",
    "GovernmentSubsidyAnomalyRootFactSource",
    "GovernmentSubsidyAnomalyScanPage",
    "GovernmentSubsidyAnomalyScanRequest",
    "GovernmentSubsidyAnomalyScanResult",
    "GovernmentSubsidyEligibleBatch",
    "GovernmentSubsidyItemOutstanding",
    "GovernmentSubsidyReceiptRootFact",
    "build_government_subsidy_alert_requests",
]
