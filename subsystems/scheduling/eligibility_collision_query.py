"""
File: eligibility_collision_query.py
Description: 產生 Scheduling 月嫂資格、占用衝突與覆蓋的唯讀 typed projection。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from shared_kernel.clock import BusinessClock
from shared_kernel.validation import require_canonical_text, require_positive_integer


class QualificationCheckState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class EligibilityState(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class AvailabilityState(StrEnum):
    AVAILABLE = "available"
    BLOCKED = "blocked"
    REQUIRES_REVIEW = "requires_review"
    UNKNOWN = "unknown"


class CoverageState(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    REQUIRES_REVIEW = "requires_review"
    UNAVAILABLE = "unavailable"


class CollisionKind(StrEnum):
    ASSIGNMENT_INTERVAL = "assignment_interval"
    OFFICIAL_SCHEDULE = "official_schedule"
    WAITING_DEPOSIT_LOCK = "waiting_deposit_lock"
    SEVEN_DAY_BUFFER = "seven_day_buffer"
    STAFF_UNAVAILABILITY = "staff_unavailability"
    LEGACY_SCHEDULE = "legacy_schedule"
    DATA_INTEGRITY = "data_integrity"


class CollisionSeverity(StrEnum):
    HARD_BLOCK = "hard_block"
    REQUIRES_REVIEW = "requires_review"


class TemporalFactState(StrEnum):
    """描述 temporal fact 是否能在 request.as_of 建立可信快照。"""

    VALID = "valid"
    FUTURE = "future"
    UNKNOWN = "unknown"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class SchedulingEligibilityCollisionQuery:
    case_no: str
    as_of: date
    staff_id: int | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if type(self.as_of) is not date:
            raise TypeError("as_of must be a date")
        if self.staff_id is not None:
            require_positive_integer(self.staff_id, "staff id")


@dataclass(frozen=True, slots=True)
class SchedulingPreferenceFact:
    preference_key: str
    order_fact_key: str | None
    comparison_operator: str
    value: object
    source_version: int | None = None
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingCaseFacts:
    case_no: str
    status: str
    start_date: date | None
    end_date: date | None
    service_days: int | None
    service_hours_per_day: int | None
    requires_cooking: bool | None
    location_text: str | None
    scheduling_version: int | None
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingStaffFacts:
    staff_id: int
    status: str | None
    lifecycle_state: str | None
    regions: tuple[str, ...] = ()
    cooking_skills: tuple[str, ...] = ()
    preferences: tuple[SchedulingPreferenceFact, ...] = ()


@dataclass(frozen=True, slots=True)
class SchedulingAssignmentFact:
    assignment_id: int
    case_no: str
    staff_id: int
    start_date: date | None
    end_date: date | None
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingScheduleFact:
    schedule_id: int
    case_no: str | None
    assignment_id: int | None
    staff_id: int
    work_date: date | None
    is_work_day: bool
    effective: bool
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingBufferFact:
    buffer_id: int
    assignment_id: int | None
    case_no: str | None
    staff_id: int
    buffer_date: date | None
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingLockFact:
    lock_day_id: int
    lock_id: int
    segment_id: int | None
    case_no: str | None
    staff_id: int
    lock_date: date | None
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingUnavailabilityFact:
    block_id: int
    staff_id: int
    kind: str
    start_date: date | None
    end_date: date | None
    temporal_state: TemporalFactState | str = TemporalFactState.VALID


@dataclass(frozen=True, slots=True)
class SchedulingEligibilityCollisionFacts:
    case: SchedulingCaseFacts | None
    staff: tuple[SchedulingStaffFacts, ...]
    assignments: tuple[SchedulingAssignmentFact, ...] = ()
    schedules: tuple[SchedulingScheduleFact, ...] = ()
    buffers: tuple[SchedulingBufferFact, ...] = ()
    locks: tuple[SchedulingLockFact, ...] = ()
    unavailability: tuple[SchedulingUnavailabilityFact, ...] = ()
    partial_data: tuple[str, ...] = ()


class SchedulingEligibilityCollisionFactsPort(Protocol):
    def load_facts(
        self, request: SchedulingEligibilityCollisionQuery
    ) -> SchedulingEligibilityCollisionFacts: ...


@dataclass(frozen=True, slots=True)
class QualificationCheckResult:
    code: str
    status: QualificationCheckState
    owner: str
    source_identity: str
    source_version: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class CollisionResult:
    kind: CollisionKind
    severity: CollisionSeverity
    staff_id: int
    case_no: str | None
    assignment_id: int | None
    source_id: int | None
    collision_date: date | None
    start_date: date | None
    end_date: date | None
    owner: str
    source_identity: str
    detail: str


@dataclass(frozen=True, slots=True)
class CoverageResult:
    start_date: date | None
    end_date: date | None
    required_day_count: int | None
    available_day_count: int | None
    missing_dates: tuple[date, ...]
    review_dates: tuple[date, ...]
    status: CoverageState


@dataclass(frozen=True, slots=True)
class StaffEligibilityCollisionResult:
    staff_id: int
    eligibility: EligibilityState
    availability: AvailabilityState
    qualification_checks: tuple[QualificationCheckResult, ...]
    collisions: tuple[CollisionResult, ...]
    coverage: CoverageResult
    partial_data: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EligibilityCollisionProjection:
    case_no: str
    case_status: str
    as_of: date
    evaluated_at: datetime
    scheduling_version: int | None
    staff: tuple[StaffEligibilityCollisionResult, ...]
    partial_data: tuple[str, ...]


class EligibilityCollisionQueryError(ValueError):
    """Stable query error that the transport layer maps to a typed response."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class SchedulingEligibilityCollisionQueryWorkflow:
    def __init__(
        self,
        repository: SchedulingEligibilityCollisionFactsPort,
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def query(
        self, request: SchedulingEligibilityCollisionQuery
    ) -> EligibilityCollisionProjection:
        if not isinstance(request, SchedulingEligibilityCollisionQuery):
            raise TypeError("scheduling eligibility collision request is invalid")
        evaluated_at = self._clock.now()
        if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
            raise TypeError("business clock must return an aware datetime")

        facts = self._repository.load_facts(request)
        if not isinstance(facts, SchedulingEligibilityCollisionFacts):
            raise TypeError("scheduling eligibility collision facts are invalid")
        if facts.case is None:
            raise EligibilityCollisionQueryError("case_not_found", "case was not found")

        snapshot_available = request.as_of == evaluated_at.date()
        facts = _scope_temporal_facts(facts, request.as_of)
        case_state = _temporal_state(facts.case.temporal_state)
        if case_state is TemporalFactState.FUTURE:
            raise EligibilityCollisionQueryError("case_not_found", "case was not found")
        if case_state is not TemporalFactState.VALID:
            raise EligibilityCollisionQueryError(
                "case_temporal_data_unavailable",
                "case temporal facts are unavailable for as_of",
            )

        selected_staff = self._select_staff(facts.staff, request.staff_id)
        period, period_issues = _case_period(facts.case)
        shared_partial = set(facts.partial_data) | set(period_issues)
        if not snapshot_available:
            shared_partial.add("historical_as_of_snapshot_unavailable")
        results = tuple(
            self._project_staff(
                staff,
                facts,
                period,
                request.case_no,
                shared_partial,
                snapshot_available,
            )
            for staff in selected_staff
        )
        return EligibilityCollisionProjection(
            case_no=facts.case.case_no,
            case_status=facts.case.status if snapshot_available else "unavailable",
            as_of=request.as_of,
            evaluated_at=evaluated_at,
            scheduling_version=facts.case.scheduling_version if snapshot_available else None,
            staff=results,
            partial_data=tuple(sorted(shared_partial)),
        )

    @staticmethod
    def _select_staff(
        staff: tuple[SchedulingStaffFacts, ...], staff_id: int | None
    ) -> tuple[SchedulingStaffFacts, ...]:
        if staff_id is None:
            return tuple(sorted(staff, key=lambda item: item.staff_id))
        selected = tuple(item for item in staff if item.staff_id == staff_id)
        if not selected:
            raise EligibilityCollisionQueryError("staff_not_found", "staff was not found")
        return selected

    def _project_staff(
        self,
        staff: SchedulingStaffFacts,
        facts: SchedulingEligibilityCollisionFacts,
        period: tuple[date, date] | None,
        case_no: str,
        shared_partial: set[str],
        snapshot_available: bool,
    ) -> StaffEligibilityCollisionResult:
        local_partial = set(shared_partial)
        checks = _qualification_checks(staff, facts.case, local_partial)
        if not snapshot_available:
            checks = tuple(
                QualificationCheckResult(
                    code=check.code,
                    status=QualificationCheckState.UNKNOWN,
                    owner=check.owner,
                    source_identity=check.source_identity,
                    source_version=None,
                    detail="指定 as_of 沒有可驗證的歷史快照。",
                )
                for check in checks
            )
            return StaffEligibilityCollisionResult(
                staff_id=staff.staff_id,
                eligibility=EligibilityState.UNAVAILABLE,
                availability=AvailabilityState.UNKNOWN,
                qualification_checks=checks,
                collisions=(),
                coverage=CoverageResult(
                    start_date=None,
                    end_date=None,
                    required_day_count=None,
                    available_day_count=None,
                    missing_dates=(),
                    review_dates=(),
                    status=CoverageState.UNAVAILABLE,
                ),
                partial_data=tuple(sorted(local_partial)),
            )
        collisions = _collisions(staff.staff_id, case_no, period, facts, local_partial)
        coverage = _coverage(period, collisions, bool(local_partial))
        if period is None:
            availability = AvailabilityState.UNKNOWN
        elif any(item.severity is CollisionSeverity.HARD_BLOCK for item in collisions):
            availability = AvailabilityState.BLOCKED
        elif local_partial:
            availability = AvailabilityState.REQUIRES_REVIEW
        elif any(item.severity is CollisionSeverity.REQUIRES_REVIEW for item in collisions):
            availability = AvailabilityState.REQUIRES_REVIEW
        else:
            availability = AvailabilityState.AVAILABLE

        if any(item.status is QualificationCheckState.FAIL for item in checks):
            eligibility = EligibilityState.INELIGIBLE
        elif any(item.status is QualificationCheckState.UNKNOWN for item in checks):
            eligibility = EligibilityState.PARTIAL
        elif local_partial:
            eligibility = EligibilityState.PARTIAL
        else:
            eligibility = EligibilityState.ELIGIBLE

        if staff.status != "active" or staff.lifecycle_state != "active":
            eligibility = EligibilityState.INELIGIBLE
        return StaffEligibilityCollisionResult(
            staff_id=staff.staff_id,
            eligibility=eligibility,
            availability=availability,
            qualification_checks=checks,
            collisions=collisions,
            coverage=coverage,
            partial_data=tuple(sorted(local_partial)),
        )


def _scope_temporal_facts(
    facts: SchedulingEligibilityCollisionFacts,
    as_of: date,
) -> SchedulingEligibilityCollisionFacts:
    """Exclude future facts and surface unknown/invalid rows as partial data.

    Repository adapters classify rows before constructing facts.  Keeping this
    second guard in the subsystem prevents an alternate port or a test double
    from bypassing the as-of boundary.
    """

    partial_data = set(facts.partial_data)

    def scope_items(items: tuple[Any, ...], kind: str) -> tuple[Any, ...]:
        scoped: list[Any] = []
        for item in items:
            state = _temporal_state(getattr(item, "temporal_state", TemporalFactState.VALID))
            if state is TemporalFactState.VALID:
                scoped.append(item)
            elif state is TemporalFactState.FUTURE:
                continue
            else:
                partial_data.add(f"{kind}_temporal_{state.value}")
        return tuple(scoped)

    case = facts.case
    if case is not None:
        case_state = _temporal_state(case.temporal_state)
        if case_state is not TemporalFactState.VALID:
            return SchedulingEligibilityCollisionFacts(
                case=case,
                staff=(),
                partial_data=tuple(sorted(partial_data | {f"case_temporal_{case_state.value}"})),
            )

    staff: list[SchedulingStaffFacts] = []
    for item in facts.staff:
        preferences = scope_items(item.preferences, "staff_preference")
        staff.append(
            SchedulingStaffFacts(
                staff_id=item.staff_id,
                status=item.status,
                lifecycle_state=item.lifecycle_state,
                regions=item.regions,
                cooking_skills=item.cooking_skills,
                preferences=preferences,
            )
        )

    return SchedulingEligibilityCollisionFacts(
        case=case,
        staff=tuple(staff),
        assignments=scope_items(facts.assignments, "assignment"),
        schedules=scope_items(facts.schedules, "schedule"),
        buffers=scope_items(facts.buffers, "buffer"),
        locks=scope_items(facts.locks, "waiting_lock"),
        unavailability=scope_items(facts.unavailability, "staff_unavailability"),
        partial_data=tuple(sorted(partial_data)),
    )


def _temporal_state(value: TemporalFactState | str) -> TemporalFactState:
    try:
        return TemporalFactState(value)
    except (TypeError, ValueError):
        return TemporalFactState.INVALID


def _case_period(
    case: SchedulingCaseFacts,
) -> tuple[tuple[date, date] | None, tuple[str, ...]]:
    issues: set[str] = set()
    if case.start_date is None or case.end_date is None:
        return None, ("case_service_period_missing",)
    if type(case.start_date) is not date or type(case.end_date) is not date:
        return None, ("case_service_period_invalid",)
    if case.start_date > case.end_date:
        return None, ("case_service_period_inverted",)
    day_count = (case.end_date - case.start_date).days + 1
    if day_count > 366:
        issues.add("case_service_period_exceeds_projection_window")
    if case.service_days is None or case.service_days <= 0:
        issues.add("case_service_days_missing")
    elif case.service_days != day_count:
        issues.add("case_service_days_mismatch")
    return (case.start_date, case.end_date), tuple(sorted(issues))


def _qualification_checks(
    staff: SchedulingStaffFacts,
    case: SchedulingCaseFacts,
    partial_data: set[str],
) -> tuple[QualificationCheckResult, ...]:
    checks: list[QualificationCheckResult] = []
    lifecycle_status = (
        QualificationCheckState.PASS
        if staff.status == "active" and staff.lifecycle_state == "active"
        else QualificationCheckState.FAIL
    )
    checks.append(
        QualificationCheckResult(
            "active_lifecycle",
            lifecycle_status,
            "Staff",
            f"staff:{staff.staff_id}:lifecycle",
            None,
            "人員目前可供排班" if lifecycle_status is QualificationCheckState.PASS else "人員不是可用 active 狀態",
        )
    )

    location = (case.location_text or "").strip()
    if not location and not staff.regions:
        status = QualificationCheckState.UNKNOWN
        partial_data.add("case_location_missing")
        partial_data.add("staff_regions_missing")
        detail = "案件服務地點與人員服務區域皆缺少，無法判斷服務區域"
    elif not location:
        status = QualificationCheckState.UNKNOWN
        partial_data.add("case_location_missing")
        detail = "案件服務地點缺少，無法判斷服務區域"
    elif not staff.regions:
        status = QualificationCheckState.UNKNOWN
        partial_data.add("staff_regions_missing")
        detail = "人員服務區域缺少，無法判斷服務區域"
    else:
        normalized_location = location.casefold()
        matched = any(
            region.casefold() in normalized_location
            or normalized_location in region.casefold()
            for region in staff.regions
            if region.strip()
        )
        status = QualificationCheckState.PASS if matched else QualificationCheckState.FAIL
        detail = "服務區域符合" if matched else "服務區域不符合"
    checks.append(
        QualificationCheckResult(
            "service_region",
            status,
            "Staff Matching Preferences",
            f"staff:{staff.staff_id}:regions",
            None,
            detail,
        )
    )

    if case.requires_cooking is None:
        cooking_status = QualificationCheckState.UNKNOWN
        partial_data.add("case_cooking_requirement_missing")
        cooking_detail = "案件下廚需求缺少"
    elif not case.requires_cooking:
        cooking_status = QualificationCheckState.PASS
        cooking_detail = "案件不要求下廚"
    elif not staff.cooking_skills:
        cooking_status = QualificationCheckState.UNKNOWN
        partial_data.add("staff_cooking_skills_missing")
        cooking_detail = "人員料理能力缺少"
    else:
        cooking_status = QualificationCheckState.PASS
        cooking_detail = "人員具備料理能力資料"
    checks.append(
        QualificationCheckResult(
            "cooking_requirement",
            cooking_status,
            "Orders / Staff",
            f"case:{case.case_no}:cooking",
            None,
            cooking_detail,
        )
    )

    checks.extend(
        _preference_check(
            staff,
            case,
            preference_key="preferred_service_days",
            order_value=case.service_days,
            partial_data=partial_data,
        )
    )
    checks.extend(
        _preference_check(
            staff,
            case,
            preference_key="daily_service_hours",
            order_value=case.service_hours_per_day,
            partial_data=partial_data,
        )
    )
    return tuple(checks)


def _preference_check(
    staff: SchedulingStaffFacts,
    case: SchedulingCaseFacts,
    *,
    preference_key: str,
    order_value: int | None,
    partial_data: set[str],
) -> tuple[QualificationCheckResult, ...]:
    fact = next(
        (item for item in staff.preferences if item.preference_key == preference_key),
        None,
    )
    source_identity = f"staff:{staff.staff_id}:preference:{preference_key}"
    if order_value is None or order_value <= 0:
        partial_data.add(f"case_{preference_key}_missing")
        return (
            QualificationCheckResult(
                preference_key,
                QualificationCheckState.UNKNOWN,
                "Staff Matching Preferences",
                f"case:{case.case_no}:{preference_key}",
                None,
                "案件需求資料缺少",
            ),
        )
    if fact is None:
        partial_data.add(f"staff_{preference_key}_missing")
        return (
            QualificationCheckResult(
                preference_key,
                QualificationCheckState.UNKNOWN,
                "Staff Matching Preferences",
                source_identity,
                None,
                "人員偏好資料缺少",
            ),
        )
    matched = _preference_matches(fact, order_value)
    if matched is None:
        partial_data.add(f"staff_{preference_key}_invalid")
        status = QualificationCheckState.UNKNOWN
        detail = "人員偏好資料格式無法判斷"
    else:
        status = QualificationCheckState.PASS if matched else QualificationCheckState.FAIL
        detail = "人員偏好符合案件需求" if matched else "人員偏好不符合案件需求"
    return (
        QualificationCheckResult(
            preference_key,
            status,
            "Staff Matching Preferences",
            source_identity,
            fact.source_version,
            detail,
        ),
    )


def _preference_matches(fact: SchedulingPreferenceFact, required: int) -> bool | None:
    if fact.comparison_operator == "range_with_tolerance":
        if not isinstance(fact.value, Mapping):
            return None
        minimum = fact.value.get("minimum")
        maximum = fact.value.get("maximum")
        if not _positive_int_or_zero(minimum) or not _positive_int_or_zero(maximum):
            return None
        return minimum <= required <= maximum
    if fact.comparison_operator == "contains_integer":
        if not isinstance(fact.value, Mapping):
            return None
        values = fact.value.get("values")
        if not isinstance(values, (list, tuple)) or any(
            not _positive_int_or_zero(value) for value in values
        ):
            return None
        return required in values
    return None


def _positive_int_or_zero(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _collisions(
    staff_id: int,
    case_no: str,
    period: tuple[date, date] | None,
    facts: SchedulingEligibilityCollisionFacts,
    partial_data: set[str],
) -> tuple[CollisionResult, ...]:
    if period is None:
        return ()
    window_start, window_end = period
    collisions: list[CollisionResult] = []

    for assignment in facts.assignments:
        if assignment.staff_id != staff_id or assignment.case_no == case_no:
            continue
        if not _valid_interval(assignment.start_date, assignment.end_date):
            partial_data.add("assignment_interval_missing_or_invalid")
            collisions.append(
                _data_integrity_collision(
                    staff_id,
                    "assignment_interval",
                    assignment.assignment_id,
                    "其他案件 assignment 日期缺少或無效",
                )
            )
            continue
        overlap = _overlap(assignment.start_date, assignment.end_date, period)
        if overlap is None:
            continue
        start, end = overlap
        for collision_date in _iter_dates(start, end):
            collisions.append(
                CollisionResult(
                    CollisionKind.ASSIGNMENT_INTERVAL,
                    CollisionSeverity.HARD_BLOCK,
                    staff_id,
                    assignment.case_no,
                    assignment.assignment_id,
                    assignment.assignment_id,
                    collision_date,
                    start,
                    end,
                    "Scheduling",
                    f"assignment:{assignment.assignment_id}",
                    "其他案件正式指派檔期占用",
                )
            )

    for schedule in facts.schedules:
        if (
            schedule.staff_id != staff_id
            or not schedule.is_work_day
            or not schedule.effective
            or schedule.case_no == case_no
        ):
            continue
        if schedule.work_date is None or not window_start <= schedule.work_date <= window_end:
            partial_data.add("schedule_date_missing_or_invalid")
            collisions.append(
                _data_integrity_collision(
                    staff_id,
                    "schedule",
                    schedule.schedule_id,
                    "其他排班的工作日期缺少或無效",
                )
            )
            continue
        kind = (
            CollisionKind.LEGACY_SCHEDULE
            if schedule.assignment_id is None
            else CollisionKind.OFFICIAL_SCHEDULE
        )
        severity = (
            CollisionSeverity.REQUIRES_REVIEW
            if kind is CollisionKind.LEGACY_SCHEDULE
            else CollisionSeverity.HARD_BLOCK
        )
        collisions.append(
            CollisionResult(
                kind,
                severity,
                staff_id,
                schedule.case_no,
                schedule.assignment_id,
                schedule.schedule_id,
                schedule.work_date,
                schedule.work_date,
                schedule.work_date,
                "Scheduling",
                f"staff_schedule:{schedule.schedule_id}",
                "其他案件正式工作日占用" if kind is CollisionKind.OFFICIAL_SCHEDULE else "缺少 assignment lineage 的歷史排班需人工覆核",
            )
        )

    for buffer in facts.buffers:
        if buffer.staff_id != staff_id or buffer.case_no == case_no:
            continue
        if buffer.buffer_date is None or not window_start <= buffer.buffer_date <= window_end:
            partial_data.add("buffer_date_missing_or_invalid")
            collisions.append(
                _data_integrity_collision(
                    staff_id,
                    "buffer",
                    buffer.buffer_id,
                    "七日 buffer 日期缺少或無效",
                )
            )
            continue
        collisions.append(
            CollisionResult(
                CollisionKind.SEVEN_DAY_BUFFER,
                CollisionSeverity.REQUIRES_REVIEW,
                staff_id,
                buffer.case_no,
                buffer.assignment_id,
                buffer.buffer_id,
                buffer.buffer_date,
                buffer.buffer_date,
                buffer.buffer_date,
                "Scheduling",
                f"scheduling_buffer_days:{buffer.buffer_id}",
                "其他案件七日 buffer；需人工確認後才能承接",
            )
        )

    for lock in facts.locks:
        if lock.staff_id != staff_id or lock.case_no == case_no:
            continue
        if lock.lock_date is None or not window_start <= lock.lock_date <= window_end:
            partial_data.add("waiting_lock_date_missing_or_invalid")
            collisions.append(
                _data_integrity_collision(
                    staff_id,
                    "waiting_lock",
                    lock.lock_day_id,
                    "等待訂金鎖日期缺少或無效",
                )
            )
            continue
        collisions.append(
            CollisionResult(
                CollisionKind.WAITING_DEPOSIT_LOCK,
                CollisionSeverity.HARD_BLOCK,
                staff_id,
                lock.case_no,
                None,
                lock.lock_day_id,
                lock.lock_date,
                lock.lock_date,
                lock.lock_date,
                "Scheduling",
                f"caregiver_availability_lock_days:{lock.lock_day_id}",
                "其他案件等待訂金檔期鎖占用",
            )
        )

    for block in facts.unavailability:
        if block.staff_id != staff_id:
            continue
        if not _valid_interval(block.start_date, block.end_date, allow_open_end=True):
            partial_data.add("staff_unavailability_interval_missing_or_invalid")
            collisions.append(
                _data_integrity_collision(
                    staff_id,
                    "staff_unavailability",
                    block.block_id,
                    "不可服務期間日期缺少或無效",
                )
            )
            continue
        overlap = _overlap(block.start_date, block.end_date, period)
        if overlap is None:
            continue
        start, end = overlap
        for collision_date in _iter_dates(start, end):
            collisions.append(
                CollisionResult(
                    CollisionKind.STAFF_UNAVAILABILITY,
                    CollisionSeverity.HARD_BLOCK,
                    staff_id,
                    None,
                    None,
                    block.block_id,
                    collision_date,
                    start,
                    end,
                    "Scheduling Staff Availability",
                    f"scheduling_staff_unavailability_blocks:{block.block_id}",
                    "人員在該日為長假或暫停接案",
                )
            )

    return _dedupe_collisions(collisions)


def _data_integrity_collision(
    staff_id: int,
    source_kind: str,
    source_id: int | None,
    detail: str,
) -> CollisionResult:
    return CollisionResult(
        CollisionKind.DATA_INTEGRITY,
        CollisionSeverity.HARD_BLOCK,
        staff_id,
        None,
        None,
        source_id,
        None,
        None,
        None,
        "Scheduling",
        f"data_integrity:{source_kind}:{source_id or 'unknown'}",
        detail,
    )


def _dedupe_collisions(
    collisions: list[CollisionResult],
) -> tuple[CollisionResult, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[CollisionResult] = []
    for item in collisions:
        key = (
            item.kind,
            item.severity,
            item.staff_id,
            item.case_no,
            item.assignment_id,
            item.source_id,
            item.collision_date,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.collision_date or date.max,
                item.kind.value,
                item.source_id or 0,
            ),
        )
    )


def _coverage(
    period: tuple[date, date] | None,
    collisions: tuple[CollisionResult, ...],
    partial_data: bool = False,
) -> CoverageResult:
    if period is None:
        return CoverageResult(
            None,
            None,
            None,
            None,
            (),
            (),
            CoverageState.UNAVAILABLE,
        )
    start, end = period
    required = tuple(_iter_dates(start, end))
    hard = {
        item.collision_date
        for item in collisions
        if item.severity is CollisionSeverity.HARD_BLOCK and item.collision_date is not None
    }
    review = {
        item.collision_date
        for item in collisions
        if item.severity is CollisionSeverity.REQUIRES_REVIEW and item.collision_date is not None
    }
    missing = tuple(item for item in required if item in hard)
    review_dates = tuple(item for item in required if item in review and item not in hard)
    if missing:
        status = CoverageState.INCOMPLETE
    elif review_dates or partial_data:
        status = CoverageState.REQUIRES_REVIEW
    else:
        status = CoverageState.COMPLETE
    return CoverageResult(
        start,
        end,
        len(required),
        len(required) - len(missing),
        missing,
        review_dates,
        status,
    )


def _overlap(
    start: date | None,
    end: date | None,
    period: tuple[date, date],
) -> tuple[date, date] | None:
    if type(start) is not date:
        return None
    if end is None:
        end = period[1]
    if type(end) is not date or start > end:
        return None
    overlap_start = max(start, period[0])
    overlap_end = min(end, period[1])
    return None if overlap_start > overlap_end else (overlap_start, overlap_end)


def _valid_interval(
    start: date | None,
    end: date | None,
    *,
    allow_open_end: bool = False,
) -> bool:
    if type(start) is not date:
        return False
    if end is None:
        return allow_open_end
    return type(end) is date and start <= end


def _iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


__all__ = [
    "AvailabilityState",
    "CollisionKind",
    "CollisionResult",
    "CollisionSeverity",
    "CoverageResult",
    "CoverageState",
    "EligibilityCollisionProjection",
    "EligibilityCollisionQueryError",
    "EligibilityState",
    "QualificationCheckResult",
    "QualificationCheckState",
    "SchedulingAssignmentFact",
    "SchedulingBufferFact",
    "SchedulingCaseFacts",
    "SchedulingEligibilityCollisionFacts",
    "SchedulingEligibilityCollisionFactsPort",
    "SchedulingEligibilityCollisionQuery",
    "SchedulingEligibilityCollisionQueryWorkflow",
    "SchedulingLockFact",
    "SchedulingPreferenceFact",
    "SchedulingScheduleFact",
    "SchedulingStaffFacts",
    "SchedulingUnavailabilityFact",
    "StaffEligibilityCollisionResult",
    "TemporalFactState",
]
