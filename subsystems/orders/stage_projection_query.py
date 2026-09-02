"""
File: stage_projection_query.py
Description: 依生命週期範圍讀取跨 owner 根事實，產生 Orders 七階段與十一作業步驟投影。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
from typing import Literal, Mapping, Protocol

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.current_projection import AssignmentLifecycleStatus, project_service_period_status
from shared_kernel.clock import BusinessClock, SystemBusinessClock
from shared_kernel.validation import require_canonical_text, require_positive_integer


MAXIMUM_PAGE_SIZE = 200
StageStatus = Literal["not_started", "in_progress", "blocked", "completed", "unavailable"]

_ROW_FIELDS = frozenset({
    "case_no", "lifecycle_status", "replacement_resume_step", "order_version", "order_updated_at",
    "import_receipt_id", "import_created_at", "imported_terms_complete",
    "terms_event_id", "terms_version", "terms_created_at", "candidate_pool_id", "candidate_pool_created_at",
    "candidate_pool_candidate_count", "candidate_pool_contacted_count", "candidate_pool_contacted_at",
    "candidate_pool_replied_count", "candidate_pool_replied_at", "matching_plan_id", "matching_plan_version",
    "matching_plan_status", "matching_created_at", "matching_customer_decision", "matching_customer_decision_at",
    "willingness_contact_attempt_count", "willingness_count", "willingness_replied_count",
    "willingness_accepted_count", "willingness_contacted_at", "willingness_replied_at",
    "resume_attempt_count", "resume_sent_count", "resume_sent_at", "matching_segment_count", "staff_contract_sent_count",
    "staff_contract_sent_at", "staff_contract_signed_count", "staff_contract_signed_at",
    "client_contract_sent_count", "client_contract_sent_at", "client_contract_signed_count",
    "client_contract_signed_at", "contract_event_id", "contract_created_at",
    "finance_version", "deposit_obligation_count", "deposit_open_count", "deposit_updated_at",
    "confirmed_version_id", "confirmed_version", "confirmed_at", "scheduling_version",
    "assignment_count", "assignment_active_count", "assignment_completed_count", "assignment_updated_at",
    "assignment_first_service_date", "assignment_last_service_date", "service_start_seconds",
    "service_end_seconds", "service_end_day_offset",
    "service_completion_identity", "service_completed_at", "client_obligation_count", "client_open_count",
    "client_updated_at", "staff_obligation_count", "staff_open_count", "staff_payables_version", "staff_updated_at",
})


class OrderStageProjectionContractError(ValueError):
    """代表 projection repository 或跨 owner identity 不符合 closed contract。"""


class OrderStageProjectionRepository(Protocol):
    def fetch_page(
        self, *, after_case_no: str | None, page_size: int,
        lifecycle_scope: OrderLifecycleScope,
    ) -> tuple[Mapping[str, object], ...]: ...


@dataclass(frozen=True)
class StageProjectionQuery:
    page_size: int
    after_case_no: str | None = None
    lifecycle_scope: OrderLifecycleScope = OrderLifecycleScope.ALL

    def __post_init__(self) -> None:
        require_positive_integer(self.page_size, "page_size")
        if self.page_size > MAXIMUM_PAGE_SIZE:
            raise ValueError("page_size must not exceed 200")
        if self.after_case_no is not None:
            require_canonical_text(self.after_case_no, "after_case_no", 50)
        if not isinstance(self.lifecycle_scope, OrderLifecycleScope):
            raise TypeError("lifecycle_scope must be an OrderLifecycleScope")


@dataclass(frozen=True)
class SourceLineage:
    owner: str
    identity: str | None
    version: int | None


@dataclass(frozen=True)
class ProjectionNotice:
    code: str
    message: str


@dataclass(frozen=True)
class AvailableAction:
    action_id: str
    method: Literal["GET"]
    path: str


@dataclass(frozen=True)
class SettlementProjection:
    code: Literal["service_completion", "client_settlement", "staff_payout"]
    status: StageStatus
    source: SourceLineage
    occurred_at: datetime | None
    availability_reason: str | None


@dataclass(frozen=True)
class StageProjection:
    ordinal: int
    code: str
    label: str
    owner: str
    status: StageStatus
    source: SourceLineage
    occurred_at: datetime | None
    blockers: tuple[ProjectionNotice, ...]
    warnings: tuple[ProjectionNotice, ...]
    available_actions: tuple[AvailableAction, ...]
    availability_reason: str | None
    settlement: tuple[SettlementProjection, ...] = ()


@dataclass(frozen=True)
class SopStepProjection:
    ordinal: int
    code: str
    label: str
    owner: str
    status: StageStatus
    occurred_at: datetime | None
    blockers: tuple[ProjectionNotice, ...]
    warnings: tuple[ProjectionNotice, ...]
    available_actions: tuple[AvailableAction, ...]
    availability_reason: str | None


@dataclass(frozen=True)
class OrderOperationalTimeline:
    case_no: str
    base_revision: int
    lifecycle_status: OrderLifecycleStatus
    replacement_resume_step_ordinal: int | None
    current_stage_code: str | None
    current_step_ordinal: int | None
    stages: tuple[StageProjection, ...]
    sop_steps: tuple[SopStepProjection, ...]
    projection_digest: str


@dataclass(frozen=True)
class OrderOperationalTimelinePage:
    items: tuple[OrderOperationalTimeline, ...]
    stage_counts: Mapping[str, int]
    next_cursor: str | None
    etag: str


class OrderStageProjectionQueryService:
    def __init__(self, repository: OrderStageProjectionRepository, clock: BusinessClock | None = None) -> None:
        self._repository = repository
        self._clock = clock or SystemBusinessClock()

    def query(self, request: StageProjectionQuery) -> OrderOperationalTimelinePage:
        rows = self._repository.fetch_page(
            after_case_no=request.after_case_no,
            page_size=request.page_size,
            lifecycle_scope=request.lifecycle_scope,
        )
        if not isinstance(rows, tuple) or len(rows) > request.page_size + 1:
            raise OrderStageProjectionContractError("repository page is not bounded")
        evaluated_at = self._clock.now()
        items = tuple(_timeline(row, evaluated_at) for row in rows[: request.page_size])
        identities = tuple(item.case_no for item in items)
        identity_keys = tuple(identity.casefold() for identity in identities)
        if identity_keys != tuple(sorted(identity_keys)) or len(identity_keys) != len(set(identity_keys)):
            raise OrderStageProjectionContractError("case page identity is duplicate or unordered")
        next_cursor = items[-1].case_no if len(rows) > request.page_size else None
        counts = {code: 0 for code in _STAGE_CODES}
        for item in items:
            if item.current_stage_code is not None:
                counts[item.current_stage_code] += 1
        etag = _digest({"items": [_timeline_payload(item) for item in items], "next_cursor": next_cursor})
        return OrderOperationalTimelinePage(items, counts, next_cursor, etag)


_STAGE_CODES = (
    "intake_terms", "matching_willingness", "client_review", "contract_deposit",
    "date_confirmation", "active_service", "settlement_payout",
)


def _timeline(row: object, evaluated_at: datetime) -> OrderOperationalTimeline:
    if not isinstance(row, Mapping) or set(row) != _ROW_FIELDS:
        raise OrderStageProjectionContractError("repository row fields are not canonical")
    case_no = _text(row, "case_no", 50)
    lifecycle_status = _lifecycle_status(row)
    replacement_resume_step = _replacement_resume_step(row)
    order_version = _nonnegative_int(row, "order_version")
    stages = _stages(row, case_no, evaluated_at)
    steps = _steps(row, case_no, stages)
    current_step_ordinal = _current_step(
        lifecycle_status,
        steps,
        replacement_resume_step,
    )
    current_stage_code = (
        None
        if current_step_ordinal is None
        else stages[_stage_ordinal_for_step(current_step_ordinal) - 1].code
    )
    payload = {
        "case_no": case_no,
        "base_revision": order_version,
        "lifecycle_status": lifecycle_status.value,
        "current_stage_code": current_stage_code,
        "current_step_ordinal": current_step_ordinal,
        "stages": [_stage_payload(stage) for stage in stages],
        "sop_steps": [_step_payload(step) for step in steps],
    }
    return OrderOperationalTimeline(
        case_no,
        order_version,
        lifecycle_status,
        replacement_resume_step,
        current_stage_code,
        current_step_ordinal,
        stages,
        steps,
        _digest(payload),
    )


def _stages(row: Mapping[str, object], case_no: str, evaluated_at: datetime) -> tuple[StageProjection, ...]:
    intake = _intake_stage(row, case_no)
    matching = _matching_stage(row, case_no)
    review = _client_review_stage(row, case_no)
    contract = _contract_stage(row, case_no)
    dates = _date_stage(row, case_no)
    service = _service_stage(row, case_no, evaluated_at)
    settlement = _settlement_stage(row, case_no)
    return intake, matching, review, contract, dates, service, settlement


def _intake_stage(row: Mapping[str, object], case_no: str) -> StageProjection:
    imported = row["import_receipt_id"] is not None
    imported_terms_complete = _binary_flag(row, "imported_terms_complete")
    terms = row["terms_event_id"] is not None or (imported and imported_terms_complete)
    source = _source("Case Import / Orders", "case-import-and-terms", _maximum_version(row, "order_version", "terms_version"))
    if imported and terms:
        return _stage(1, "intake_terms", "進件與補件", "Case Import / Orders", "completed", source, _latest(row, "import_created_at", "terms_created_at"), actions=(_get("orders.terms.query", f"/api/v1/orders/{case_no}/terms"),))
    if imported or terms:
        missing = "orders_terms_missing" if imported else "case_import_receipt_missing"
        return _stage(1, "intake_terms", "進件與補件", "Case Import / Orders", "in_progress", source, _latest(row, "import_created_at", "terms_created_at"), blockers=(_notice(missing, "進件與條款根事實尚未同時齊備。"),), actions=(_get("orders.terms.query", f"/api/v1/orders/{case_no}/terms"),))
    return _unavailable_stage(1, "intake_terms", "進件與補件", "Case Import / Orders", "case_import_and_terms_lineage_missing")


def _matching_stage(row: Mapping[str, object], case_no: str) -> StageProjection:
    plan_id = row["matching_plan_id"]
    status = row["matching_plan_status"]
    customer_decision = row["matching_customer_decision"]
    candidate_pool_id = _optional_int(row, "candidate_pool_id")
    candidate_count = _nonnegative_int(row, "candidate_pool_candidate_count")
    if plan_id is not None and (isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0):
        raise OrderStageProjectionContractError("matching_plan_id must be a positive integer")
    if plan_id is not None and status not in {"draft", "proposed", "accepted", "rejected", "superseded", "cancelled"}:
        raise OrderStageProjectionContractError("matching_plan_status is outside the closed contract")
    if customer_decision not in {None, "pending", "accepted", "rejected"}:
        raise OrderStageProjectionContractError("matching customer decision is outside the closed contract")
    willingness_count = _nonnegative_int(row, "willingness_count")
    replied_count = _nonnegative_int(row, "willingness_replied_count")
    accepted_count = _nonnegative_int(row, "willingness_accepted_count")
    if replied_count > willingness_count or accepted_count > replied_count:
        raise OrderStageProjectionContractError("willingness counts are inconsistent")
    source = _source("Assignments / Scheduling", f"caregiver-matching-plan:{plan_id}" if plan_id is not None else None, _optional_int(row, "matching_plan_version"))
    if plan_id is None and candidate_pool_id is not None and candidate_count:
        return _stage(
            2,
            "matching_willingness",
            "媒合與徵詢意願",
            "Assignments / Scheduling",
            "in_progress",
            _source("Assignments / Scheduling", f"candidate-contact-pool:{candidate_pool_id}", None),
            _optional_datetime(row, "candidate_pool_created_at"),
            warnings=(_notice("formal_matching_plan_not_created", "候選聯繫與意願確認完成後，才能建立正式媒合方案。"),),
            actions=(_get("orders.assignment_plan.query", f"/api/v1/orders/{case_no}/assignment-plan"),),
        )
    if plan_id is None:
        return _unavailable_stage(2, "matching_willingness", "媒合與徵詢意願", "Assignments / Scheduling", "matching_plan_lineage_missing")
    if customer_decision == "accepted" or status == "accepted":
        projected: StageStatus = "completed"
        blockers: tuple[ProjectionNotice, ...] = ()
    elif customer_decision == "rejected" or status in {"rejected", "cancelled"}:
        projected = "blocked"
        blockers = (_notice("matching_plan_not_accepted", "目前媒合方案已拒絕或取消。"),)
    else:
        projected = "in_progress"
        blockers = ()
    warnings = () if willingness_count else (_notice("willingness_evidence_missing", "沒有可用的候選意願根事實。"),)
    return _stage(2, "matching_willingness", "媒合與徵詢意願", "Assignments / Scheduling", projected, source, _optional_datetime(row, "matching_created_at"), blockers=blockers, warnings=warnings, actions=(_get("orders.assignment_plan.query", f"/api/v1/orders/{case_no}/assignment-plan"),))


def _client_review_stage(row: Mapping[str, object], case_no: str) -> StageProjection:
    plan_id = row["matching_plan_id"]
    resume_sent_count = _nonnegative_int(row, "resume_sent_count")
    if plan_id is None:
        return _unavailable_stage(3, "client_review", "推薦客戶與確認", "Assignments / Customer Decision", "formal_recommendation_projection_missing")
    accepted = row["matching_customer_decision"] == "accepted" or row["matching_plan_status"] == "accepted"
    status: StageStatus = "completed" if accepted and resume_sent_count else "in_progress" if accepted or resume_sent_count else "not_started"
    source = _source("Assignments / Customer Decision", f"caregiver-matching-plan:{plan_id}", _optional_int(row, "matching_plan_version"))
    return _stage(3, "client_review", "推薦客戶與確認", "Assignments / Customer Decision", status, source, _latest(row, "resume_sent_at", "matching_customer_decision_at"), actions=(_get("orders.assignment_plan.query", f"/api/v1/orders/{case_no}/assignment-plan"),))


def _contract_stage(row: Mapping[str, object], case_no: str) -> StageProjection:
    contract = row["contract_event_id"] is not None
    deposits = _nonnegative_int(row, "deposit_obligation_count")
    open_deposits = _nonnegative_int(row, "deposit_open_count")
    source = _source("Contract Signing / Client Finance", "contract-and-deposit", _maximum_version(row, "order_version", "finance_version"))
    if contract and deposits and not open_deposits:
        status: StageStatus = "completed"
        blockers = ()
    elif contract or deposits:
        status = "blocked" if open_deposits else "in_progress"
        blockers = (_notice("deposit_not_settled", "客戶定金 obligation 尚未結清。"),) if open_deposits else ()
    else:
        return _unavailable_stage(4, "contract_deposit", "雙邊簽約與定金", "Contract Signing / Client Finance", "contract_and_deposit_lineage_missing")
    return _stage(4, "contract_deposit", "雙邊簽約與定金", "Contract Signing / Client Finance", status, source, _latest(row, "contract_created_at", "deposit_updated_at"), blockers=blockers, actions=(_get("orders.contract_completion.query", f"/api/v1/orders/{case_no}/contract-completion"),))


def _date_stage(row: Mapping[str, object], case_no: str) -> StageProjection:
    version_id = row["confirmed_version_id"]
    source = _source("Orders / Scheduling", f"confirmed-service-date-version:{version_id}" if version_id is not None else None, _optional_int(row, "confirmed_version"))
    if version_id is None:
        return _unavailable_stage(5, "date_confirmation", "確認實際服務日期", "Orders / Scheduling", "confirmed_service_date_lineage_missing")
    return _stage(5, "date_confirmation", "確認實際服務日期", "Orders / Scheduling", "completed", source, _optional_datetime(row, "confirmed_at"), actions=(_get("orders.service_dates.query", f"/api/v1/orders/{case_no}/service-dates"),))


def _service_stage(row: Mapping[str, object], case_no: str, evaluated_at: datetime) -> StageProjection:
    count = _nonnegative_int(row, "assignment_count")
    version = _optional_int(row, "scheduling_version")
    source = _source("Scheduling / Orders", f"scheduling-aggregate:{case_no}" if version is not None else None, version)
    if not count:
        return _unavailable_stage(6, "active_service", "正式服務履約", "Scheduling / Orders", "formal_assignment_lineage_missing")
    first_service_date = _optional_date(row, "assignment_first_service_date")
    last_service_date = _optional_date(row, "assignment_last_service_date")
    service_terms = _service_time_terms(row)
    if first_service_date is None or last_service_date is None or service_terms is None:
        return _unavailable_stage(6, "active_service", "正式服務履約", "Scheduling / Orders", "official_service_period_missing")
    lifecycle = project_service_period_status(
        first_service_date=first_service_date,
        last_service_date=last_service_date,
        service_time_terms=service_terms,
        evaluated_at=evaluated_at,
    )
    status_by_lifecycle: Mapping[AssignmentLifecycleStatus, StageStatus] = {
        AssignmentLifecycleStatus.PLANNED: "not_started",
        AssignmentLifecycleStatus.ACTIVE: "in_progress",
        AssignmentLifecycleStatus.COMPLETED: "completed",
    }
    status = status_by_lifecycle[lifecycle]
    return _stage(6, "active_service", "正式服務履約", "Scheduling / Orders", status, source, _optional_datetime(row, "assignment_updated_at"), actions=(_get("orders.assignment_plan.query", f"/api/v1/orders/{case_no}/assignment-plan"),))


def _settlement_stage(row: Mapping[str, object], case_no: str) -> StageProjection:
    service = _settlement_part("service_completion", "Orders", row["service_completion_identity"], 1 if row["service_completion_identity"] is not None else None, _optional_datetime(row, "service_completed_at"), None)
    client = _obligation_part("client_settlement", "Client Finance", row, "client_obligation_count", "client_open_count", "finance_version", "client_updated_at")
    staff = _obligation_part("staff_payout", "Staff Payables", row, "staff_obligation_count", "staff_open_count", "staff_payables_version", "staff_updated_at")
    parts = (service, client, staff)
    statuses = {part.status for part in parts}
    if statuses == {"completed"}:
        status: StageStatus = "completed"
    elif "blocked" in statuses:
        status = "blocked"
    elif "completed" in statuses or "in_progress" in statuses:
        status = "in_progress"
    else:
        status = "unavailable"
    blockers = tuple(
        _notice(
            f"{part.code}_not_complete",
            f"{part.source.owner} 子投影尚未完成。",
        )
        for part in parts
        if part.status == "blocked"
    )
    return _stage(7, "settlement_payout", "完工結案與請款", "Orders / Client Finance / Staff Payables", status, _source("Cross-domain read coordinator", f"order-settlement:{case_no}", _nonnegative_int(row, "order_version")), _latest(row, "service_completed_at", "client_updated_at", "staff_updated_at"), blockers=blockers, settlement=parts)


def _obligation_part(code: str, owner: str, row: Mapping[str, object], count_field: str, open_field: str, version_field: str, at_field: str) -> SettlementProjection:
    count = _nonnegative_int(row, count_field)
    open_count = _nonnegative_int(row, open_field)
    if open_count > count:
        raise OrderStageProjectionContractError("obligation counts are inconsistent")
    if not count:
        return SettlementProjection(code, "unavailable", _source(owner, None, _optional_int(row, version_field)), None, "obligation_projection_missing")  # type: ignore[arg-type]
    status: StageStatus = "blocked" if open_count else "completed"
    return SettlementProjection(code, status, _source(owner, f"{code}-obligations", _optional_int(row, version_field)), _optional_datetime(row, at_field), None)  # type: ignore[arg-type]


def _settlement_part(code: str, owner: str, identity: object, version: int | None, at: datetime | None, reason: str | None) -> SettlementProjection:
    if identity is None:
        return SettlementProjection(code, "unavailable", _source(owner, None, version), None, reason or "service_completion_projection_missing")  # type: ignore[arg-type]
    return SettlementProjection(code, "completed", _source(owner, str(identity), version), at, None)  # type: ignore[arg-type]


def _steps(row: Mapping[str, object], case_no: str, stages: tuple[StageProjection, ...]) -> tuple[SopStepProjection, ...]:
    stage = {item.code: item for item in stages}
    plan_id = row["matching_plan_id"]
    candidate_pool_id = _optional_int(row, "candidate_pool_id")
    candidate_count = _nonnegative_int(row, "candidate_pool_candidate_count")
    pool_contacted_count = _nonnegative_int(row, "candidate_pool_contacted_count")
    pool_replied_count = _nonnegative_int(row, "candidate_pool_replied_count")
    pool_contacted_at = _optional_datetime(row, "candidate_pool_contacted_at")
    pool_replied_at = _optional_datetime(row, "candidate_pool_replied_at")
    contact_attempt_count = _nonnegative_int(row, "willingness_contact_attempt_count")
    contacted_count = _nonnegative_int(row, "willingness_count")
    replied_count = _nonnegative_int(row, "willingness_replied_count")
    accepted_count = _nonnegative_int(row, "willingness_accepted_count")
    resume_attempt_count = _nonnegative_int(row, "resume_attempt_count")
    resume_sent_count = _nonnegative_int(row, "resume_sent_count")
    segment_count = _nonnegative_int(row, "matching_segment_count")
    staff_sent_count = _nonnegative_int(row, "staff_contract_sent_count")
    staff_signed_count = _nonnegative_int(row, "staff_contract_signed_count")
    client_sent_count = _nonnegative_int(row, "client_contract_sent_count")
    client_signed_count = _nonnegative_int(row, "client_contract_signed_count")
    if (
        pool_contacted_count > candidate_count
        or pool_replied_count > candidate_count
        or contacted_count > contact_attempt_count
        or replied_count > contact_attempt_count
        or accepted_count > replied_count
        or staff_sent_count > segment_count
        or staff_signed_count > segment_count
        or client_sent_count > 1
        or resume_sent_count > resume_attempt_count
        or client_signed_count > 1
    ):
        raise OrderStageProjectionContractError("SOP owner fact counts are inconsistent")
    contact_status: StageStatus = (
        "completed"
        if candidate_count and pool_contacted_count >= candidate_count and pool_contacted_at is not None
        else "in_progress"
        if pool_contacted_count
        else "not_started"
        if candidate_pool_id is not None
        else "unavailable"
    )
    reply_status: StageStatus = (
        "completed"
        if candidate_count and pool_replied_count >= candidate_count
        else "in_progress"
        if pool_replied_count
        else "not_started"
        if candidate_pool_id is not None
        else "unavailable"
    )
    pool_status: StageStatus = "completed" if candidate_count else "in_progress" if candidate_pool_id is not None else "unavailable"
    recommendation_status: StageStatus = "completed" if resume_sent_count else "in_progress" if resume_attempt_count or accepted_count else "not_started" if plan_id is not None else "unavailable"
    staff_contract_status: StageStatus = "completed" if segment_count and staff_signed_count == segment_count else "in_progress" if staff_sent_count or staff_signed_count else "not_started" if plan_id is not None else "unavailable"
    client_contract_status: StageStatus = "completed" if client_signed_count else "in_progress" if client_sent_count else "not_started" if plan_id is not None else "unavailable"
    deposit_count = _nonnegative_int(row, "deposit_obligation_count")
    deposit_status: StageStatus = "completed" if deposit_count and not _nonnegative_int(row, "deposit_open_count") else "blocked" if deposit_count else "unavailable"
    return (
        _step_from_stage(1, "intake_validation", "進件報名與資料完整性驗證", stage["intake_terms"]),
        _standalone_step(2, "matching_pool", "媒合月嫂候選人加入意願池", "Assignments / Scheduling", pool_status, _optional_datetime(row, "matching_created_at"), "matching_plan_lineage_missing" if pool_status == "unavailable" else None),
        _standalone_step(3, "caregiver_line_delivery", "發送訂單資訊詢問月嫂意願（LINE 或人工確認）", "Assignments / LINE Delivery", contact_status, pool_contacted_at, "candidate_contact_pool_missing" if contact_status == "unavailable" else None),
        _standalone_step(4, "caregiver_willingness_reply", "月嫂回傳接案意願", "Assignments / LINE", reply_status, pool_replied_at, "candidate_contact_pool_missing" if reply_status == "unavailable" else None),
        _step_from_stage(5, "formal_recommendation", "寄送月嫂履歷給客戶確認", stage["client_review"]),
        _standalone_step(6, "caregiver_contract", "產生月嫂服務契約並留存簽回（寄送或人工確認）", "Contract Signing", staff_contract_status, _latest(row, "staff_contract_signed_at", "staff_contract_sent_at"), "staff_contract_signing_lineage_missing" if staff_contract_status == "unavailable" else None),
        _standalone_step(7, "deposit_settlement", "客戶定金核銷（訂單成立）", "Client Finance", deposit_status, _optional_datetime(row, "deposit_updated_at"), "deposit_obligation_missing" if deposit_status == "unavailable" else None, blockers=(_notice("deposit_not_settled", "定金 obligation 尚未結清。"),) if deposit_status == "blocked" else ()),
        _standalone_step(8, "client_contract", "產生客戶契約並留存簽回（寄送或人工確認）", "Contract Signing / Orders", client_contract_status, _latest(row, "client_contract_signed_at", "client_contract_sent_at"), "client_contract_signing_lineage_missing" if client_contract_status == "unavailable" else None),
        _step_from_stage(9, "confirmed_service_dates", "確認事前服務日期（精算）", stage["date_confirmation"]),
        _step_from_stage(10, "formal_service", "轉換正式排班與服務履約", stage["active_service"]),
        _step_from_stage(11, "settlement_close", "完工驗收、時數核對與尾款／薪資結清", stage["settlement_payout"]),
    )
def _step_from_stage(ordinal: int, code: str, label: str, stage: StageProjection) -> SopStepProjection:
    return SopStepProjection(ordinal, code, label, stage.owner, stage.status, stage.occurred_at, stage.blockers, stage.warnings, stage.available_actions, stage.availability_reason)


def _standalone_step(ordinal: int, code: str, label: str, owner: str, status: StageStatus, occurred_at: datetime | None, reason: str | None, *, blockers: tuple[ProjectionNotice, ...] = ()) -> SopStepProjection:
    return SopStepProjection(ordinal, code, label, owner, status, occurred_at, blockers, (), (), reason)


def _stage(ordinal: int, code: str, label: str, owner: str, status: StageStatus, source: SourceLineage, occurred_at: datetime | None, *, blockers: tuple[ProjectionNotice, ...] = (), warnings: tuple[ProjectionNotice, ...] = (), actions: tuple[AvailableAction, ...] = (), availability_reason: str | None = None, settlement: tuple[SettlementProjection, ...] = ()) -> StageProjection:
    return StageProjection(ordinal, code, label, owner, status, source, occurred_at, blockers, warnings, actions, availability_reason, settlement)


def _unavailable_stage(ordinal: int, code: str, label: str, owner: str, reason: str) -> StageProjection:
    return _stage(ordinal, code, label, owner, "unavailable", _source(owner, None, None), None, availability_reason=reason)


def _source(owner: str, identity: str | None, version: int | None) -> SourceLineage:
    return SourceLineage(owner, identity, version)


def _notice(code: str, message: str) -> ProjectionNotice:
    return ProjectionNotice(code, message)


def _get(action_id: str, path: str) -> AvailableAction:
    return AvailableAction(action_id, "GET", path)


def _lifecycle_status(row: Mapping[str, object]) -> OrderLifecycleStatus:
    try:
        return OrderLifecycleStatus(row["lifecycle_status"])
    except (TypeError, ValueError) as exc:
        raise OrderStageProjectionContractError(
            "lifecycle_status is outside the closed contract"
        ) from exc


def _replacement_resume_step(row: Mapping[str, object]) -> int | None:
    value = row["replacement_resume_step"]
    if value is None:
        return None
    try:
        return {"step_2": 2, "step_3": 3, "step_4": 4}[str(value)]
    except KeyError as exc:
        raise OrderStageProjectionContractError(
            "replacement_resume_step is outside the closed contract"
        ) from exc


def _text(row: Mapping[str, object], field: str, maximum: int) -> str:
    try:
        return require_canonical_text(row[field], field, maximum)
    except ValueError as exc:
        raise OrderStageProjectionContractError(str(exc)) from exc


def _nonnegative_int(row: Mapping[str, object], field: str) -> int:
    value = row[field]
    if isinstance(value, Decimal):
        if value < 0 or value != value.to_integral_value():
            raise OrderStageProjectionContractError(f"{field} must be a nonnegative integer")
        return int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OrderStageProjectionContractError(f"{field} must be a nonnegative integer")
    return value


def _binary_flag(row: Mapping[str, object], field: str) -> bool:
    value = _nonnegative_int(row, field)
    if value not in {0, 1}:
        raise OrderStageProjectionContractError(f"{field} must be zero or one")
    return bool(value)


def _optional_int(row: Mapping[str, object], field: str) -> int | None:
    return None if row[field] is None else _nonnegative_int(row, field)


def _optional_datetime(row: Mapping[str, object], field: str) -> datetime | None:
    value = row[field]
    if value is not None and not isinstance(value, datetime):
        raise OrderStageProjectionContractError(f"{field} must be datetime or None")
    return value


def _optional_date(row: Mapping[str, object], field: str) -> date | None:
    value = row[field]
    if value is not None and type(value) is not date:
        raise OrderStageProjectionContractError(f"{field} must be date or None")
    return value


def _service_time_terms(row: Mapping[str, object]) -> ServiceTimeTerms | None:
    values = (row["service_start_seconds"], row["service_end_seconds"], row["service_end_day_offset"])
    if all(value is None for value in values):
        return ServiceTimeTerms(None, None, None)
    if any(value is None for value in values):
        raise OrderStageProjectionContractError("service time tuple is partial")
    start = _seconds_to_time(_nonnegative_int(row, "service_start_seconds"), "service_start_seconds")
    end = _seconds_to_time(_nonnegative_int(row, "service_end_seconds"), "service_end_seconds")
    offset = _nonnegative_int(row, "service_end_day_offset")
    try:
        return ServiceTimeTerms(start, end, offset)
    except (TypeError, ValueError) as exc:
        raise OrderStageProjectionContractError(str(exc)) from exc


def _seconds_to_time(value: int, field: str) -> time:
    if value >= 86_400:
        raise OrderStageProjectionContractError(f"{field} must be within one day")
    return time(value // 3_600, value % 3_600 // 60, value % 60)


def _latest(row: Mapping[str, object], *fields: str) -> datetime | None:
    values = tuple(value for value in (_optional_datetime(row, field) for field in fields) if value is not None)
    return max(values) if values else None


def _maximum_version(row: Mapping[str, object], *fields: str) -> int | None:
    values = tuple(value for value in (_optional_int(row, field) for field in fields) if value is not None)
    return max(values) if values else None


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default).encode()).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported projection value: {type(value).__name__}")


def _stage_payload(stage: StageProjection) -> dict[str, object]:
    return {"ordinal": stage.ordinal, "code": stage.code, "label": stage.label, "owner": stage.owner, "status": stage.status, "source": vars(stage.source), "occurred_at": stage.occurred_at, "blockers": [vars(item) for item in stage.blockers], "warnings": [vars(item) for item in stage.warnings], "available_actions": [vars(item) for item in stage.available_actions], "availability_reason": stage.availability_reason, "settlement": [{**vars(item), "source": vars(item.source)} for item in stage.settlement]}


def _step_payload(step: SopStepProjection) -> dict[str, object]:
    return {"ordinal": step.ordinal, "code": step.code, "label": step.label, "owner": step.owner, "status": step.status, "occurred_at": step.occurred_at, "blockers": [vars(item) for item in step.blockers], "warnings": [vars(item) for item in step.warnings], "available_actions": [vars(item) for item in step.available_actions], "availability_reason": step.availability_reason}


def _timeline_payload(item: OrderOperationalTimeline) -> dict[str, object]:
    return {
        "case_no": item.case_no,
        "base_revision": item.base_revision,
        "lifecycle_status": item.lifecycle_status.value,
        "current_stage_code": item.current_stage_code,
        "current_step_ordinal": item.current_step_ordinal,
        "projection_digest": item.projection_digest,
    }


def _stage_ordinal_for_step(step: int) -> int:
    if isinstance(step, bool) or not isinstance(step, int):
        raise TypeError("current SOP step must be an integer")
    if step == 1:
        return 1
    if 2 <= step <= 4:
        return 2
    if step == 5:
        return 3
    if 6 <= step <= 8:
        return 4
    if step == 9:
        return 5
    if step == 10:
        return 6
    if step == 11:
        return 7
    raise ValueError("current SOP step is outside the closed contract")


def _current_step(
    lifecycle_status: OrderLifecycleStatus,
    steps: tuple[SopStepProjection, ...],
    replacement_resume_step: int | None,
) -> int | None:
    if lifecycle_status is OrderLifecycleStatus.CANCELLED:
        return None
    fixed_ordinal = {
        OrderLifecycleStatus.PENDING_COMPLETION: 1,
        OrderLifecycleStatus.COMPLETED: 11,
        OrderLifecycleStatus.HISTORICAL_UNSERVED: 9,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED: 11,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED: 11,
    }.get(lifecycle_status)
    if fixed_ordinal is not None:
        return fixed_ordinal
    service_step = steps[9]
    if service_step.status == "completed":
        return 11
    if (
        service_step.status == "in_progress"
        or lifecycle_status
        in {
            OrderLifecycleStatus.IN_SERVICE,
            OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        }
    ):
        return 10
    floor = (
        replacement_resume_step
        if lifecycle_status is OrderLifecycleStatus.ESTABLISHED
        and replacement_resume_step is not None
        else 6
        if lifecycle_status is OrderLifecycleStatus.ESTABLISHED
        else 1
    )
    bounded = steps[floor - 1 :]
    if floor == 1 and all(step.status == "unavailable" for step in bounded):
        return None
    current = next((step for step in bounded if step.status != "completed"), None)
    return bounded[-1].ordinal if current is None else current.ordinal


__all__ = ["MAXIMUM_PAGE_SIZE", "OrderOperationalTimelinePage", "OrderStageProjectionContractError", "OrderStageProjectionQueryService", "OrderStageProjectionRepository", "StageProjectionQuery"]
