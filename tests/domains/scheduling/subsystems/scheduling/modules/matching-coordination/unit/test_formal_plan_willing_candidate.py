"""Formal plan selection uses willing-candidate facts and schedule eligibility."""

from datetime import date
from types import SimpleNamespace

import pytest

from subsystems.scheduling import matching_notification_application, matching_plan_workflow
from subsystems.scheduling.segmented_availability_query import _passes_enabled_filters
from infrastructure.mysql.matching_notification_repository import _segment_contact
from domains.scheduling.matching_communication import CaregiverWillingness, CustomerMatchingDecision, MatchingCommunicationConflictError, record_caregiver_willingness


@pytest.mark.parametrize('end_date', [None, date(2026, 12, 4)])
def test_plan_case_lock_does_not_require_manual_planned_end(end_date):
    class Cursor:
        def execute(self, _sql, _parameters):
            pass

        def fetchone(self):
            return {'case_no': 'CASE-INQUIRY', 'status': '洽談中',
                    'start_date': date(2026, 11, 15), 'end_date': end_date}

    matching_plan_workflow._lock_matching_plan_case_root(Cursor(), 'CASE-INQUIRY')


def test_explicit_admin_notice_can_correct_prior_agreement_without_line_decision_context():
    with pytest.raises(MatchingCommunicationConflictError):
        record_caregiver_willingness(CaregiverWillingness.WILLING, CaregiverWillingness.UNWILLING,
                                    plan_is_active=True, recipient_matches=True)
    assert record_caregiver_willingness(CaregiverWillingness.WILLING, CaregiverWillingness.UNWILLING,
                                       plan_is_active=True, recipient_matches=True, allow_correction=True) is CaregiverWillingness.UNWILLING


@pytest.mark.parametrize('decision', [CustomerMatchingDecision.PENDING, CustomerMatchingDecision.CONTACT_REQUESTED])
@pytest.mark.parametrize('prior,target', [
    (CaregiverWillingness.WILLING, CaregiverWillingness.UNWILLING),
    (CaregiverWillingness.UNWILLING, CaregiverWillingness.WILLING),
])
def test_line_consent_can_change_both_ways_before_customer_decision(decision, prior, target):
    assert record_caregiver_willingness(
        prior, target, plan_is_active=True, recipient_matches=True, customer_decision=decision,
    ) is target


def test_line_withdrawal_after_customer_acceptance_is_allowed_but_cannot_be_undone():
    assert record_caregiver_willingness(
        CaregiverWillingness.WILLING, CaregiverWillingness.UNWILLING,
        plan_is_active=True, recipient_matches=True, customer_decision=CustomerMatchingDecision.ACCEPTED,
    ) is CaregiverWillingness.UNWILLING
    with pytest.raises(MatchingCommunicationConflictError):
        record_caregiver_willingness(
            CaregiverWillingness.UNWILLING, CaregiverWillingness.WILLING,
            plan_is_active=True, recipient_matches=True, customer_decision=CustomerMatchingDecision.ACCEPTED,
        )


def test_line_cannot_change_consent_after_customer_declined():
    with pytest.raises(MatchingCommunicationConflictError):
        record_caregiver_willingness(
            CaregiverWillingness.UNWILLING, CaregiverWillingness.WILLING,
            plan_is_active=True, recipient_matches=True, customer_decision=CustomerMatchingDecision.DECLINED,
        )


@pytest.mark.parametrize('prior,explicit,expected', [
    ('willing', None, 'willing'), ('unwilling', None, 'unwilling'),
    (None, None, 'pending'), ('willing', 'unwilling', 'unwilling'),
])
def test_prior_candidate_consent_is_used_without_another_manual_response(prior, explicit, expected):
    row = {'segment_id': 1, 'segment_order': 1, 'staff_id': 2, 'staff_name': 'Synthetic caregiver',
           'staff_line_user_id': None, 'assigned_start_date': '2026-11-02', 'assigned_end_date': '2026-11-06',
           'candidate_willingness': prior}
    responses = {} if explicit is None else {(1, 'caregiver_willingness'): explicit}
    segment = _segment_contact(row, responses, {})
    assert segment.willingness.value == expected
    assert segment.information_1_status is None
    assert segment.information_2_status is None


def test_matching_preferences_explain_but_do_not_exclude_candidate():
    policy = {
        "region": True,
        "cooking": True,
        "preferred_service_days": True,
        "daily_service_hours": True,
        "enabled_preference_keys": ("custom_preference",),
    }

    assert _passes_enabled_filters(
        {
            "region": True,
            "cooking": True,
            "preferred_service_days": False,
            "daily_service_hours": False,
            "custom_preference": False,
        },
        policy,
    )


def test_formal_single_plan_requires_matching_current_willing_candidate(monkeypatch):
    candidate = SimpleNamespace(
        status="active",
        willingness="willing",
        staff_id=1,
        service_start_date=date(2026, 12, 21),
        service_end_date=date(2027, 1, 9),
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "query_pool",
        lambda *_args, **_kwargs: SimpleNamespace(candidates=(candidate,)),
    )

    matching_plan_workflow._require_current_willing_candidate(
        object(),
        "M3-CUST-20260910-01",
        [
            {
                "staff_id": 1,
                "assigned_start_date": "2026-12-21",
                "assigned_end_date": "2027-01-09",
            }
        ],
    )


def test_formal_single_plan_rejects_non_willing_candidate(monkeypatch):
    monkeypatch.setattr(
        matching_plan_workflow,
        "query_pool",
        lambda *_args, **_kwargs: SimpleNamespace(candidates=()),
    )

    with pytest.raises(ValueError, match="current willing candidate is required"):
        matching_plan_workflow._require_current_willing_candidate(
            object(),
            "M3-CUST-20260910-01",
            [
                {
                    "staff_id": 1,
                    "assigned_start_date": "2026-12-21",
                    "assigned_end_date": "2027-01-09",
                }
            ],
        )


def test_willing_candidate_recommendation_uses_inquiry_period_without_preview_date_gate(monkeypatch):
    captured = {}
    segments = [
        {
            "staff_id": 1,
            "assigned_start_date": "2026-12-21",
            "assigned_end_date": "2027-01-09",
        }
    ]

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {
            "feasibility": "complete",
            "conflicts": [],
            "complete_combinations": [
                [
                    {
                        "segment_index": 0,
                        "staff_id": 1,
                        "start_date": "2026-12-21",
                        "end_date": "2027-01-09",
                    }
                ]
            ],
        }

    monkeypatch.setattr(
        matching_plan_workflow,
        "search_candidate_inquiry_availability",
        fake_search,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: pytest.fail("saved service dates must not gate a candidate recommendation"),
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_run_in_application_uow",
        lambda operation: operation(object(), object()),
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_lock_matching_plan_case_root",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_load_matching_plan_create_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_create_matching_plan_version_in_transaction",
        lambda *_args: {
            "plan_id": 1,
            "case_no": "M3-CUST-20260910-01",
            "version": 1,
            "status": "proposed",
            "result": "created",
            "segments": [{
                "segment_order": 1,
                "staff_id": 1,
                "assigned_start_date": "2026-12-21",
                "assigned_end_date": "2027-01-09",
            }],
        },
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_save_matching_plan_create_receipt",
        lambda *_args: None,
    )

    matching_plan_workflow.create_matching_plan_version(
        "M3-CUST-20260910-01",
        segments,
        "admin",
        "2026-09-11",
        facts_port=object(),
        require_willing_candidate=True,
        event_key="test-willing-candidate-schedule-only",
    )

    assert captured["filter_policy"] == {
        "region": False,
        "cooking": False,
        "preferred_service_days": False,
        "daily_service_hours": False,
    }
    assert captured["segment_drafts"] == [{"staff_id": 1, "start_date": "2026-12-21", "end_date": "2027-01-09"}]


@pytest.mark.parametrize("reason", ["assignment", "staff_unavailability", "active_lock"])
def test_recommendation_still_blocks_real_candidate_period_conflicts(monkeypatch, reason):
    monkeypatch.setattr(
        matching_plan_workflow, "search_candidate_inquiry_availability",
        lambda **_kwargs: {"feasibility": "complete", "conflicts": [{"reason_code": reason, "work_date": "2026-11-15"}, {"reason_code": "buffer", "work_date": "2026-11-16"}],
                          "complete_combinations": [[{"segment_index": 0, "staff_id": 1,
                                                      "start_date": "2026-11-05", "end_date": "2026-11-24"}]]},
    )
    with pytest.raises(matching_plan_workflow.MatchingPlanAvailabilityConflict) as caught:
        matching_plan_workflow._validate_current_availability(
            "PREVIEW-DATE-DRIFT", [{"staff_id": 1, "assigned_start_date": "2026-11-05", "assigned_end_date": "2026-11-24"}],
            "2026-10-13", object(), True,
        )
    assert caught.value.conflicts == ((reason, '2026-11-15'),)


def test_recommendation_api_explains_actual_occupancy_and_repair_routes(monkeypatch):
    from fastapi import HTTPException
    from api.routes import matches
    def conflict(**_kwargs):
        raise matching_plan_workflow.MatchingPlanAvailabilityConflict((('active_lock', '2026-11-15'),))
    monkeypatch.setattr(matches, 'create_matching_plan_version', conflict)
    with pytest.raises(HTTPException) as caught:
        matches.create_matching_plan_version_route(
            case_no='TEST-CONFLICT', segments=[{'staff_id': 1}], created_by='operator',
            as_of='2026-10-15', event_key='test-conflict', principal=SimpleNamespace(username='operator'),
        )
    error = caught.value.detail['error']
    assert caught.value.status_code == 409
    assert error['code'] == 'matching_plan_staff_occupancy_conflict'
    assert '其他案件保留' in error['message']
    assert '2026-11-15' in error['message']
    assert '返回尋找人選' in error['message']
    assert '調整日期' in error['message']


def test_formal_plan_notification_distinguishes_date_drift_from_schedule_conflict(monkeypatch):
    state = SimpleNamespace(
        plan=SimpleNamespace(case_no="CASE-DATE-DRIFT"),
        segments=(
            SimpleNamespace(
                staff_id=1,
                assigned_start_date=date(2026, 12, 1),
                assigned_end_date=date(2026, 12, 20),
            ),
        ),
    )

    monkeypatch.setattr(
        matching_notification_application,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: {"feasibility": "partial", "conflicts": []},
    )
    with pytest.raises(
        matching_notification_application.MatchingPlanDateMismatchError
    ):
        matching_notification_application._validate_availability(state, object())

    monkeypatch.setattr(
        matching_notification_application,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: {
            "feasibility": "partial",
            "conflicts": [{"date": "2026-12-05"}],
        },
    )
    with pytest.raises(
        matching_notification_application.MatchingDecisionNotReadyError
    ):
        matching_notification_application._validate_availability(state, object())

    assert matching_notification_application._availability_blocker(
        matching_notification_application.MatchingPlanDateMismatchError()
    ) == "正式方案日期與目前案件服務日期不一致，請重新建立方案。"
    assert matching_notification_application._availability_blocker(
        matching_notification_application.MatchingDecisionNotReadyError()
    ) == "正式方案中的月嫂目前檔期已有衝突，請重新確認。"


def test_multi_caregiver_plan_fresh_check_does_not_reapply_discovery_preferences(monkeypatch):
    captured = {}
    segments = [
        {
            "staff_id": 1,
            "assigned_start_date": "2026-12-21",
            "assigned_end_date": "2026-12-22",
        },
        {
            "staff_id": 2,
            "assigned_start_date": "2026-12-23",
            "assigned_end_date": "2026-12-24",
        },
    ]

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {
            "feasibility": "complete",
            "conflicts": [],
            "complete_combinations": [[
                {
                    "segment_index": index,
                    "staff_id": segment["staff_id"],
                    "start_date": segment["assigned_start_date"],
                    "end_date": segment["assigned_end_date"],
                }
                for index, segment in enumerate(segments)
            ]],
        }

    monkeypatch.setattr(
        matching_plan_workflow,
        "search_segmented_caregiver_availability",
        fake_search,
    )

    matching_plan_workflow._validate_current_availability(
        "MULTI-1",
        segments,
        "2026-09-12",
        object(),
        False,
    )

    assert captured["filter_policy"] == {
        "region": False,
        "cooking": False,
        "preferred_service_days": False,
        "daily_service_hours": False,
    }
    assert captured["include_candidate_options"] is False


class _FormalPlanFacts:
    def __init__(self, *, occupied: bool = False):
        self._occupied = occupied

    def load_case_facts(self, case_no):
        return {
            "order": {
                "case_no": case_no,
                "status": "洽談中",
                "start_date": "2026-12-01",
                "end_date": "2026-12-20",
                "service_days": 20,
                "scheduling_version": 1,
            },
            # Stage 5 creates the formal plan before later service-date
            # confirmation. Its schedule revalidation must still be usable.
            "confirmed_service_dates": [],
            "staff_rows": [{"id": 1, "name": "測試月嫂"}],
            "assignments": [],
            "schedule_rows": [],
            "legacy_schedule_rows": [],
            "buffer_rows": [],
            "active_lock_rows": [],
            "waiting_buffer_rows": [],
            "staff_unavailability_rows": (
                [
                    {
                        "id": 1,
                        "staff_id": 1,
                        "start_date": "2026-12-10",
                        "end_date": "2026-12-10",
                    }
                ]
                if self._occupied
                else []
            ),
        }


def test_current_willing_candidate_creates_plan_without_candidate_display_dates(monkeypatch):
    candidate = SimpleNamespace(
        status="active",
        willingness="willing",
        staff_id=1,
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 20),
    )
    segments = [
        {
            "staff_id": 1,
            "start_date": "2026-12-01",
            "end_date": "2026-12-20",
        }
    ]
    monkeypatch.setattr(
        matching_plan_workflow,
        "query_pool",
        lambda *_args, **_kwargs: SimpleNamespace(candidates=(candidate,)),
    )

    def persist(_connection, _cursor, case_no, normalized, _actor, _signature, requires_willing):
        assert requires_willing is True
        matching_plan_workflow._require_current_willing_candidate(
            object(), case_no, normalized
        )
        return {"result": "created"}

    monkeypatch.setattr(
        matching_plan_workflow,
        "_create_matching_plan_version_in_transaction",
        persist,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_run_in_application_uow",
        lambda operation: operation(object(), object()),
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_lock_matching_plan_case_root",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_load_matching_plan_create_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_load_matching_plan_create_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_save_matching_plan_create_receipt",
        lambda *_args: None,
    )

    result = matching_plan_workflow.create_matching_plan_version(
        "CASE-2026-S05",
        segments,
        "operator",
        "2026-09-11",
        facts_port=_FormalPlanFacts(),
        require_willing_candidate=True,
        event_key="test-willing-candidate-without-display-dates",
    )
    assert result["result"] == "created"


def test_formal_plan_still_rejects_current_schedule_conflict(monkeypatch):
    monkeypatch.setattr(
        matching_plan_workflow,
        "_run_in_application_uow",
        lambda operation: operation(object(), object()),
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_lock_matching_plan_case_root",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_load_matching_plan_create_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_create_matching_plan_version_in_transaction",
        lambda *_args: pytest.fail("conflicted plan must not enter persistence"),
    )

    with pytest.raises(matching_plan_workflow.MatchingPlanAvailabilityConflict):
        matching_plan_workflow.create_matching_plan_version(
            "CASE-2026-S05",
            [
                {
                    "staff_id": 1,
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-20",
                }
            ],
            "operator",
            "2026-09-11",
            facts_port=_FormalPlanFacts(occupied=True),
            require_willing_candidate=True,
            event_key="test-formal-plan-schedule-conflict",
        )


def test_formal_plan_notification_revalidates_schedule_without_candidate_preferences(monkeypatch):
    captured = {}
    state = SimpleNamespace(
        plan=SimpleNamespace(case_no="M3-CUST-20260910-01"),
        segments=(
            SimpleNamespace(
                staff_id=1,
                assigned_start_date=date(2026, 12, 21),
                assigned_end_date=date(2027, 1, 9),
            ),
        ),
    )

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {"feasibility": "complete", "conflicts": []}

    monkeypatch.setattr(
        matching_notification_application,
        "search_segmented_caregiver_availability",
        fake_search,
    )

    matching_notification_application._validate_availability(state, object())

    assert captured["filter_policy"] == {
        "region": False,
        "cooking": False,
        "preferred_service_days": False,
        "daily_service_hours": False,
    }
    assert captured["include_candidate_options"] is False
