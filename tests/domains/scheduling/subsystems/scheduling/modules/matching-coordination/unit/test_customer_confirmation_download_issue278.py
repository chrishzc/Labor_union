import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from subsystems.scheduling import candidate_contact_pool_workflow as candidate_workflow

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
                "candidate_weekly_service_preview": lambda self, case_no, candidate_id: {
                    "required_service_days": 15, "projected_service_days": 5,
                    "date_basis": "planned", "staff_id": 100, "rows": (
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
                )}
            },
        )(),
    )

    monkeypatch.setattr(candidate_workflow, "search_candidate_inquiry_availability", lambda *args, **kwargs: {"conflicts": []})
    result = candidate_workflow.preview_weekly_service("CASE-1", 3)

    assert result == {
        "case_no": "CASE-1",
        "candidate_id": 3,
        "required_service_days": 15, "projected_service_days": 5,
        "date_basis": "planned",
        "warnings": ("目前日期可提供 5 天，與約定 15 天不符；請協調休假／服務日期後重新確認。",),
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
        "decision-token",
        "請確認配對方案。",
    ))

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "下載履歷 PDF" not in serialized
    assert "接受此配對" in serialized


def test_current_resume_query_compares_numeric_staff_identity_without_collation_dependency():
    assert "CAST(object.subject_reference AS BINARY)=CAST(segment.staff_id AS BINARY)" in _CURRENT_RESUMES_SQL
    assert "object.subject_reference=CAST(segment.staff_id AS CHAR)" not in _CURRENT_RESUMES_SQL


def test_confirmation_preview_reports_missing_resume():
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
            "blocker": "月嫂 李小華 未附履歷 PDF，請先上傳。",
        },
    )
    assert blockers == ("月嫂 李小華 未附履歷 PDF，請先上傳。",)


@pytest.mark.parametrize("hours_per_day,work_days", [(8, 5), (8.5, 1)])
@pytest.mark.parametrize("line_bound", [True, False])
@pytest.mark.parametrize("has_resume", [True, False])
def test_confirmation_preview_is_readable_with_or_without_line_binding(hours_per_day, work_days, line_bound, has_resume):
    plan = MatchingPlanReference("CASE-278", 51, 4)
    state = SimpleNamespace(
        plan=plan,
        plan_is_active=True,
        plan_status="proposed",
        order_status="洽談中",
        replacement_matching_open=False,
        all_willing=True,
        customer_decision="pending",
        customer_line_user_id=object() if line_bound else None,
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
                "order_information_1": ({"segment_id": 71, "staff_id": 100, "staff_name": "王小美", "text": "訂單資訊－1",
                    "line_sections": ({"title": "客戶付款約定", "rows": (("客戶應付總額", "NT$ 48,000"),)},)},),
                "order_information_2": ({"segment_id": 71, "staff_id": 100, "staff_name": "王小美", "text": "訂單資訊－2",
                    "line_sections": ({"title": "飲食與照護需求", "rows": (("飲食習慣", "清淡"),)},)},),
                "weekly_service_rows": ({"serial_number": 1, "staff_name": "王小美", "week_start_date": "2026-09-14", "week_end_date": "2026-09-20", "service_hours_per_day": hours_per_day, "weekly_work_days": work_days, "weekly_hours": hours_per_day * work_days},),
                "caregiver_resumes": ({
                    "staff_id": 100,
                    "staff_name": "王小美",
                    "ready": has_resume,
                    "filename": "demo.pdf" if has_resume else None,
                    "version": 1 if has_resume else None,
                    "blocker": None if has_resume else "月嫂 王小美 尚未上傳履歷 PDF。",
                },),
                "resume_files": ({"file_id": "demo"},) if has_resume else (),
                "blockers": (),
            }

    class UnitOfWork:
        matching_notifications = Notifications()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def render_resume(file_id, budget):
        assert (file_id, budget) == ("demo", 4)
        return (b"page1", b"page2")

    application = MatchingNotificationApplication(
        UnitOfWork,
        lambda: datetime(2026, 9, 12, tzinfo=timezone.utc),
        availability_validator=lambda _state: None,
        resume_page_renderer=render_resume,
    )

    preview = application.preview_customer_confirmation(
        ActorContext("admin:7", ("line.matching.read",)),
        plan,
        include_resume_images=True,
    )

    binding_blockers = () if line_bound else ("客戶尚未完成 LINE 綁定。",)
    resume_blockers = () if has_resume else ("月嫂 王小美 尚未上傳履歷 PDF。",)
    assert preview.blockers == (*binding_blockers, *resume_blockers)
    assert preview.send_allowed is (line_bound and has_resume)
    assert preview.resume_images == ((b"page1", b"page2") if has_resume else ())
    assert preview.caregiver_resumes[0].staff_name == "王小美"
    assert preview.order_information_1[0].text == "訂單資訊－1"
    assert preview.order_information_1[0].line_sections[0].rows == (("客戶應付總額", "NT$ 48,000"),)
    assert preview.order_information_2[0].line_sections[0].rows == (("飲食習慣", "清淡"),)
    assert preview.weekly_service_rows[0].weekly_hours == hours_per_day * work_days


def test_download_matching_confirmation_resume_is_retired_410():
    from fastapi import HTTPException
    from api.routes.matches import download_matching_confirmation_resume

    with pytest.raises(HTTPException) as exc:
        download_matching_confirmation_resume("mcf_test_token")
    assert exc.value.status_code == 410
    assert "退役" in str(exc.value.detail)


def test_liff_resume_page_and_download_are_retired():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import matches

    app = FastAPI()
    app.include_router(matches.resume_page_router)
    app.include_router(matches.resume_router)
    client = TestClient(app)
    assert client.get("/line-matching-resume").status_code == 410
    assert client.post("/api/v1/line/matching-resume/download", json={}).status_code == 410
