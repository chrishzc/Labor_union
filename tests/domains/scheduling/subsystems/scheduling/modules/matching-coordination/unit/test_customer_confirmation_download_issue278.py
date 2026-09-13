import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from subsystems.scheduling import candidate_contact_pool_workflow as candidate_workflow

from subsystems.scheduling.customer_confirmation_download import (
    issue_resume_download_token,
    verify_resume_download_token,
)
from infrastructure.mysql.matching_notification_repository import (
    _CURRENT_RESUMES_SQL,
    _current_resumes,
    _json_ints,
    _resume_previews,
)
from domains.scheduling.matching_communication import MatchingPlanReference
from shared_kernel.identities import ActorContext
from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
from subsystems.scheduling.matching_line_cards import customer_confirmation_card


def test_confirmation_download_token_is_file_scoped_and_expires(monkeypatch):
    monkeypatch.setenv("MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET", "test-secret")
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    token = issue_resume_download_token(
        case_no="CASE-278", plan_id=51, staff_id=100,
        file_id="cf_" + "a" * 32, now=now,
    )

    assert verify_resume_download_token(token, now=now)["file_id"] == "cf_" + "a" * 32
    with pytest.raises(ValueError, match="expired"):
        verify_resume_download_token(token, now=now + timedelta(days=8))


def test_confirmation_package_omits_missing_resume_without_blocking_other_content():
    segments = (
        {"staff_id": 100, "staff_name": "王小美"},
        {"staff_id": 200, "staff_name": "李小華"},
    )
    rows = ({"staff_id": 100, "file_id": "cf_" + "a" * 32, "filename": "a.pdf", "version_number": 1, "mime_type": "application/pdf"},)

    assert _current_resumes(segments, rows) == ({
        "staff_id": 100,
        "staff_name": "王小美",
        "file_id": "cf_" + "a" * 32,
        "filename": "a.pdf",
        "version": 1,
    },)


def test_weekly_projection_reads_seeded_chinese_rest_day_names():
    assert _json_ints('["週六", "週日", 0, "週日"]') == (5, 6, 0)


def test_candidate_weekly_preview_exposes_only_public_projection(monkeypatch):
    closed = []
    connection = object()
    monkeypatch.setattr(candidate_workflow, "get_connection", lambda: connection)
    monkeypatch.setattr(candidate_workflow, "_close", lambda value: closed.append(value))
    monkeypatch.setattr(
        candidate_workflow,
        "MySqlMatchingNotificationRepository",
        lambda value: type(
            "Repository",
            (),
            {
                "candidate_weekly_service_preview": lambda self, case_no, candidate_id: (
                    {
                        "week_number": "10-1",
                        "serial_number": 1,
                        "case_no": case_no,
                        "employer_name": "江家綺",
                        "staff_name": "王美華",
                        "week_start_date": "2026-10-05",
                        "week_end_date": "2026-10-11",
                        "service_hours_per_day": 8,
                        "weekly_work_days": 5,
                        "weekly_hours": 40,
                    },
                )
            },
        )(),
    )

    result = candidate_workflow.preview_weekly_service("CASE-1", 3)

    assert result == {
        "case_no": "CASE-1",
        "candidate_id": 3,
        "rows": (
            {
                "serial_number": 1,
                "staff_name": "王美華",
                "week_start_date": "2026-10-05",
                "week_end_date": "2026-10-11",
                "service_hours_per_day": 8,
                "weekly_work_days": 5,
                "weekly_hours": 40,
            },
        ),
    }
    assert closed == [connection]


def test_confirmation_card_without_resume_keeps_customer_decision_action():
    payload = json.loads(customer_confirmation_card(
        "CASE-278",
        ({"id": 100, "name": "王小美"},),
        (),
        (),
        ({"week_number": 1, "case_no": "CASE-278"},),
        {},
        "decision-token",
        "請確認配對方案。",
    ))

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "下載履歷 PDF" not in serialized
    assert "接受此配對" in serialized


def test_current_resume_query_compares_numeric_staff_identity_without_collation_dependency():
    assert "CAST(object.subject_reference AS BINARY)=CAST(segment.staff_id AS BINARY)" in _CURRENT_RESUMES_SQL
    assert "object.subject_reference=CAST(segment.staff_id AS CHAR)" not in _CURRENT_RESUMES_SQL


def test_confirmation_preview_lists_missing_resume_as_non_blocking_manual_notice():
    segments = (
        {"staff_id": 100, "staff_name": "王小美"},
        {"staff_id": 200, "staff_name": "李小華"},
    )
    rows = ({
        "staff_id": 100,
        "file_id": "cf_" + "a" * 32,
        "filename": "王小美履歷.pdf",
        "version_number": 2,
        "mime_type": "application/pdf",
    },)

    previews, blockers = _resume_previews(segments, rows)

    assert previews == (
        {
            "staff_id": 100,
            "staff_name": "王小美",
            "ready": True,
            "filename": "王小美履歷.pdf",
            "version": 2,
            "blocker": None,
        },
        {
            "staff_id": 200,
            "staff_name": "李小華",
            "ready": False,
            "filename": None,
            "version": None,
            "blocker": "月嫂 李小華 未附履歷；確認資訊仍可寄送，請由公會人員另行透過 LINE 傳送履歷。",
        },
    )
    assert blockers == ("月嫂 李小華 未附履歷；確認資訊仍可寄送，請由公會人員另行透過 LINE 傳送履歷。",)


def test_confirmation_preview_allows_send_when_only_resume_is_missing():
    plan = MatchingPlanReference("CASE-278", 51, 4)
    state = SimpleNamespace(
        plan=plan,
        plan_is_active=True,
        plan_status="proposed",
        order_status="洽談中",
        all_willing=True,
        customer_profiles_are_available=False,
        customer_line_user_id=object(),
    )

    class Notifications:
        def get_contact_state(self, case_no, plan_id, *, lock):
            assert (case_no, plan_id, lock) == ("CASE-278", 51, False)
            return state

        def customer_confirmation_preview(self, case_no, plan_id):
            assert (case_no, plan_id) == ("CASE-278", 51)
            return {
                "order_information_1_ready": True,
                "order_information_2_ready": True,
                "weekly_service_ready": True,
                "weekly_service_row_count": 2,
                "order_information_1": ({"segment_id": 71, "staff_id": 100, "staff_name": "王小美", "text": "訂單資訊－1"},),
                "order_information_2": ({"segment_id": 71, "staff_id": 100, "staff_name": "王小美", "text": "訂單資訊－2"},),
                "weekly_service_rows": ({"serial_number": 1, "staff_name": "王小美", "week_start_date": "2026-09-14", "week_end_date": "2026-09-20", "service_hours_per_day": 8, "weekly_work_days": 5, "weekly_hours": 40},),
                "caregiver_resumes": ({
                    "staff_id": 100,
                    "staff_name": "王小美",
                    "ready": False,
                    "filename": None,
                    "version": None,
                    "blocker": "月嫂 王小美 尚未上傳履歷 PDF。",
                },),
                "blockers": (),
            }

    class UnitOfWork:
        matching_notifications = Notifications()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    application = MatchingNotificationApplication(
        UnitOfWork,
        lambda: datetime(2026, 9, 12, tzinfo=timezone.utc),
        availability_validator=lambda _state: None,
    )

    preview = application.preview_customer_confirmation(
        ActorContext("admin:7", ("line.matching.read",)),
        plan,
    )

    assert preview.send_allowed is True
    assert preview.blockers == ()
    assert preview.caregiver_resumes[0].staff_name == "王小美"
    assert preview.order_information_1[0].text == "訂單資訊－1"
    assert preview.weekly_service_rows[0].weekly_hours == 40
