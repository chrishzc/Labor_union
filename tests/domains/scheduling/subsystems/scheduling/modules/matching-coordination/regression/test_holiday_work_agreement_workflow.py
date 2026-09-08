"""Regression coverage for current-plan national-holiday work agreements."""

from contextlib import AbstractContextManager
from datetime import date, datetime, timezone

import pytest

from api.routes.order_schedule_calculation import calculate_schedule
from api.schemas.orders import ScheduleCalculationRequest
from domains.scheduling.holiday_work_agreement import (
    HolidayWorkAgreementDraft,
    HolidayWorkDecision,
    HolidayWorkParticipantDecision,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.holiday_work_agreement_workflow import (
    HolidayWorkAgreementError,
    HolidayWorkAgreementWorkflow,
)


class _Repository:
    def __init__(self) -> None:
        self._stored = None
        self.appended = []

    def load_current_plan(self, case_no, plan_id, *, lock):
        assert case_no == "CASE-HOLIDAY-1"
        assert plan_id == 41
        return {
            "plan": {
                "id": 41,
                "is_active": 1,
                "status": "proposed",
                "version": 7,
                "start_date": date(2026, 2, 27),
                "end_date": date(2026, 3, 3),
            },
            "segments": ({"id": 501}, {"id": 502}),
        }

    def is_holiday(self, holiday_date):
        return holiday_date == date(2026, 3, 2)

    def find_by_idempotency(self, _key, _fingerprint):
        if self._stored is None:
            return None
        return {**self._stored, "replayed": True}

    def append(self, draft, *, idempotency_key, fingerprint, occurred_at):
        self.appended.append((draft, idempotency_key, fingerprint, occurred_at))
        self._stored = {
            "agreement": {
                "id": 73,
                "plan_id": draft.plan_id,
                "holiday_date": draft.holiday_date,
                "plan_version": draft.plan_version,
                "agreement_status": draft.status.value,
            },
            "participants": tuple({
                "participant_role": item.participant_role,
                "segment_id": item.segment_id,
                "decision": item.decision.value,
            } for item in draft.participant_decisions),
            "replayed": False,
        }
        return self._stored


class _UnitOfWork(AbstractContextManager):
    def __init__(self, repository):
        self.matching_holiday_work_agreements = repository
        self.committed = False

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


def _draft(*, version=7, second_decision=HolidayWorkDecision.ACCEPTED):
    return HolidayWorkAgreementDraft(
        case_no="CASE-HOLIDAY-1",
        plan_id=41,
        plan_version=version,
        holiday_date=date(2026, 3, 2),
        participant_decisions=(
            HolidayWorkParticipantDecision("customer", None, HolidayWorkDecision.ACCEPTED),
            HolidayWorkParticipantDecision("caregiver", 501, HolidayWorkDecision.ACCEPTED),
            HolidayWorkParticipantDecision("caregiver", 502, second_decision),
        ),
        actor_id="scheduling-operator",
        reason="電話逐一確認客戶與兩段月嫂對國定假日上班的協調結果。",
    )


def _workflow(repository, unit_of_work):
    return HolidayWorkAgreementWorkflow(
        lambda: unit_of_work,
        lambda: datetime(2026, 2, 27, tzinfo=timezone.utc),
    )


def test_current_plan_preview_apply_binds_every_participant_and_replays():
    repository = _Repository()
    unit_of_work = _UnitOfWork(repository)
    workflow = _workflow(repository, unit_of_work)
    draft = _draft()

    preview = workflow.preview(draft)
    receipt = workflow.apply(
        draft,
        preview.preview_fingerprint,
        IdempotencyKey("holiday-work-41-20260302"),
        CorrelationId("test-holiday-work-41"),
    )

    assert unit_of_work.committed is True
    assert receipt["agreement_status"] == "accepted"
    assert receipt["holiday_date"] == date(2026, 3, 2)
    assert receipt["replayed"] is False
    assert len(repository.appended) == 1

    replay = workflow.apply(
        draft,
        preview.preview_fingerprint,
        IdempotencyKey("holiday-work-41-20260302"),
        CorrelationId("test-holiday-work-41-replay"),
    )
    assert replay["replayed"] is True
    assert len(repository.appended) == 1


def test_missing_participant_or_stale_plan_is_rejected_before_write():
    repository = _Repository()
    unit_of_work = _UnitOfWork(repository)
    workflow = _workflow(repository, unit_of_work)

    missing_segment = HolidayWorkAgreementDraft(
        case_no="CASE-HOLIDAY-1", plan_id=41, plan_version=7,
        holiday_date=date(2026, 3, 2),
        participant_decisions=(
            HolidayWorkParticipantDecision("customer", None, HolidayWorkDecision.ACCEPTED),
            HolidayWorkParticipantDecision("caregiver", 501, HolidayWorkDecision.ACCEPTED),
        ),
        actor_id="scheduling-operator", reason="缺少第二段月嫂的協調結果。",
    )
    with pytest.raises(HolidayWorkAgreementError, match="participants"):
        workflow.preview(missing_segment)
    with pytest.raises(HolidayWorkAgreementError, match="version is stale"):
        workflow.preview(_draft(version=6))
    assert repository.appended == []


def test_holiday_outside_the_current_plan_is_rejected_before_write():
    repository = _Repository()
    unit_of_work = _UnitOfWork(repository)
    workflow = _workflow(repository, unit_of_work)
    draft = HolidayWorkAgreementDraft(
        case_no="CASE-HOLIDAY-1",
        plan_id=41,
        plan_version=7,
        holiday_date=date(2026, 3, 9),
        participant_decisions=_draft().participant_decisions,
        actor_id="scheduling-operator",
        reason="日期不在目前方案內，不得成為上班協議。",
    )

    with pytest.raises(HolidayWorkAgreementError, match="outside"):
        workflow.preview(draft)
    assert repository.appended == []


def test_decline_is_auditable_but_never_becomes_a_work_authorization():
    repository = _Repository()
    unit_of_work = _UnitOfWork(repository)
    workflow = _workflow(repository, unit_of_work)
    draft = _draft(second_decision=HolidayWorkDecision.DECLINED)

    preview = workflow.preview(draft)
    assert preview.as_dict()["agreement_status"] == "declined"
    assert preview.as_dict()["apply_allowed"] is False
    receipt = workflow.apply(
        draft, preview.preview_fingerprint,
        IdempotencyKey("holiday-work-41-20260302-declined"),
        CorrelationId("test-holiday-work-41-declined"),
    )
    assert receipt["agreement_status"] == "declined"


def test_schedule_route_only_uses_current_dual_agreement_to_mark_holiday_work(monkeypatch):
    calls = []

    def _calculate(**kwargs):
        calls.append(kwargs)
        return {
            "actual_start_date": date(2026, 3, 1), "actual_end_date": date(2026, 3, 3),
            "target_service_days": 2, "total_calendar_days": 3, "actual_work_days_count": 2,
            "rest_days_count": 1,
            "national_holidays_found": [{"date": date(2026, 3, 2), "name": "測試國定假日", "is_worked": False}],
            "total_estimated_salary": None,
            "weekly_stats": [{"week_num": 1, "start_date": date(2026, 3, 1), "end_date": date(2026, 3, 3), "work_days": 2, "rest_days": 1, "holiday_days": 1}],
            "day_by_day": [{"date": date(2026, 3, 1), "day_num": 1, "is_work_day": True, "is_rest_day": False, "holiday_name": None}],
        }

    class _Connection:
        def close(self):
            return None

    class _AgreementRepository:
        def __init__(self, _connection):
            pass

        def current_accepted_holiday_dates(self, case_no, start_date, end_date):
            assert (case_no, start_date, end_date) == ("CASE-HOLIDAY-1", date(2026, 3, 1), date(2026, 3, 3))
            return (date(2026, 3, 2),)

    monkeypatch.setattr("api.routes.order_schedule_calculation.attendance_schedule_query.calculate_order_attendance_schedule", _calculate)
    monkeypatch.setattr("api.routes.order_schedule_calculation.MySqlMatchingHolidayWorkAgreementRepository", _AgreementRepository)
    monkeypatch.setattr("api.routes.order_schedule_calculation.get_connection", _Connection)

    calculate_schedule(
        ScheduleCalculationRequest(case_no="CASE-HOLIDAY-1", actual_start_date=date(2026, 3, 1), target_service_days=2, service_mode="週休2日"),
        AdminPrincipal(1, "typed-schedule", "Typed Schedule", "system_admin"),
    )
    assert len(calls) == 2
    assert calls[1]["custom_holiday_rest_dates"] == []
    assert calls[1]["custom_work_dates"] == [date(2026, 3, 2)]
