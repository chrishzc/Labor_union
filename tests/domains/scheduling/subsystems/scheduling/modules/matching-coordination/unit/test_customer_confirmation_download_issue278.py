from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from subsystems.scheduling.customer_confirmation_download import (
    issue_resume_download_token,
    verify_resume_download_token,
)
from infrastructure.mysql.matching_notification_repository import (
    _CURRENT_RESUMES_SQL,
    _current_resumes,
    _resume_previews,
)
from domains.scheduling.matching_communication import MatchingCommunicationConflictError
from domains.scheduling.matching_communication import MatchingPlanReference
from shared_kernel.identities import ActorContext
from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication


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


def test_confirmation_preflight_rejects_entire_package_when_any_resume_is_missing():
    segments = (
        {"staff_id": 100, "staff_name": "王小美"},
        {"staff_id": 200, "staff_name": "李小華"},
    )
    rows = ({"staff_id": 100, "file_id": "cf_" + "a" * 32, "filename": "a.pdf", "version_number": 1, "mime_type": "application/pdf"},)

    with pytest.raises(MatchingCommunicationConflictError, match="李小華"):
        _current_resumes(segments, rows)


def test_current_resume_query_compares_numeric_staff_identity_without_collation_dependency():
    assert "CAST(object.subject_reference AS BINARY)=CAST(segment.staff_id AS BINARY)" in _CURRENT_RESUMES_SQL
    assert "object.subject_reference=CAST(segment.staff_id AS CHAR)" not in _CURRENT_RESUMES_SQL


def test_confirmation_preview_lists_each_resume_and_blocks_send_when_one_is_missing():
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
            "blocker": "月嫂 李小華 尚未上傳履歷 PDF，請先至人員管理完成履歷上傳。",
        },
    )
    assert blockers == ("月嫂 李小華 尚未上傳履歷 PDF，請先至人員管理完成履歷上傳。",)


def test_confirmation_preview_merges_state_and_package_blockers_without_writing():
    plan = MatchingPlanReference("CASE-278", 51, 4)
    state = SimpleNamespace(
        plan=plan,
        plan_is_active=True,
        plan_status="proposed",
        order_status="洽談中",
        all_willing=False,
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
                "caregiver_resumes": ({
                    "staff_id": 100,
                    "staff_name": "王小美",
                    "ready": False,
                    "filename": None,
                    "version": None,
                    "blocker": "月嫂 王小美 尚未上傳履歷 PDF。",
                },),
                "blockers": ("月嫂 王小美 尚未上傳履歷 PDF。",),
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

    assert preview.send_allowed is False
    assert preview.blockers == (
        "仍有月嫂尚未確認願意承接正式方案。",
        "月嫂 王小美 尚未上傳履歷 PDF。",
    )
    assert preview.caregiver_resumes[0].staff_name == "王小美"
