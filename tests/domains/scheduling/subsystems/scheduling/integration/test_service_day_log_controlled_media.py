"""驗證 Baby Log 的受控照片由 Preview 帶入同一 Scheduling Apply UoW。"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.scheduling.service_day_log import ServiceDayLogIntent
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion
from subsystems.scheduling.service_day_log_workflow import (
    ApplyServiceDayLog,
    ControlledServiceDayLogAttachment,
    PreviewServiceDayLog,
    ServiceDayLogResult,
    ServiceDayLogWorkflow,
)


class Repository:
    def __init__(self):
        self.submitted = []

    def load_assignment(self, _staff_id, _assignment_id, _service_date, *, for_update):
        self.for_update = for_update
        return {"case_no": "CASE-1", "requires_cooking": True}

    def load_replay(self, _command):
        return None

    def submit(self, command, assignment):
        self.submitted.append(command)
        return ServiceDayLogResult(1, "CASE-1", 12, "2026-08-16", "寶寶正常", True, "created", command.controlled_file_attachments)


class NoCookingRepository(Repository):
    def load_assignment(self, _staff_id, _assignment_id, _service_date, *, for_update):
        self.for_update = for_update
        return {"case_no": "CASE-1", "requires_cooking": False}


def test_scheduling_attachment_schema_admits_baby_and_meal_photo_kinds():
    schema = Path("db/schema_parts/213_scheduling_service_day_attachment_kind.sql").read_text(
        encoding="utf-8"
    )

    assert "attachment_kind ENUM('meal_photo','baby_log_photo') NOT NULL" in schema


def _attachment(kind="meal_photo"):
    return ControlledServiceDayLogAttachment(
        None,
        "cfs_1234567890abcdef1234567890abcdef",
        "a" * 64,
        kind,
    )


def _command(attachment):
    return PreviewServiceDayLog(
        9,
        "U-caregiver",
        12,
        ServiceDayLogIntent(date(2026, 8, 16), "寶寶正常", ()),
        controlled_file_attachments=(attachment,),
    )


def test_staged_media_is_registered_and_carried_into_log_submit():
    repository = Repository()
    controlled = SimpleNamespace(
        preview=lambda _intent: SimpleNamespace(
            blockers=(), expected_staging_version=ExpectedVersion(1), preview_fingerprint=PreviewFingerprint("b" * 64)
        ),
        apply_borrowed=lambda command: SimpleNamespace(
            readback=SimpleNamespace(file_id="cf_1234567890abcdef1234567890abcdef", applied_at=None)
        ),
    )
    workflow = ServiceDayLogWorkflow(repository, controlled)
    preview_command = _command(_attachment())
    preview = workflow.preview(preview_command)

    result = workflow.apply(
        ApplyServiceDayLog(
            9,
            "U-caregiver",
            12,
            preview_command.intent,
            "service-day-log-1",
            preview.preview_fingerprint,
            controlled_file_attachments=preview_command.controlled_file_attachments,
        )
    )

    assert result.controlled_file_attachments[0].controlled_file_object_id.startswith("cf_")
    assert repository.submitted[0].controlled_file_attachments[0].controlled_file_object_id.startswith("cf_")


def test_stale_staged_media_fails_closed_during_preview():
    repository = Repository()
    controlled = SimpleNamespace(
        preview=lambda _intent: SimpleNamespace(
            blockers=("stale_staging_version",),
        )
    )

    with pytest.raises(ValueError, match="stale_staging_version"):
        ServiceDayLogWorkflow(repository, controlled).preview(_command(_attachment()))


def test_media_is_rejected_when_order_does_not_require_cooking():
    with pytest.raises(ValueError, match="service_day_log_meal_photo_forbidden"):
        ServiceDayLogWorkflow(NoCookingRepository()).preview(_command(_attachment()))


def test_baby_log_photo_is_allowed_on_non_cooking_day():
    attachment = ControlledServiceDayLogAttachment(
        "cf_1234567890abcdef1234567890abcdef",
        "cfs_1234567890abcdef1234567890abcdef",
        "a" * 64,
        "baby_log_photo",
    )
    preview = ServiceDayLogWorkflow(NoCookingRepository()).preview(_command(attachment))

    assert preview.can_apply is True
    assert preview.blockers == ()


def test_baby_log_photo_apply_is_carried_into_scheduling_readback():
    attachment = ControlledServiceDayLogAttachment(
        "cf_1234567890abcdef1234567890abcdef",
        "cfs_1234567890abcdef1234567890abcdef",
        "a" * 64,
        "baby_log_photo",
    )
    repository = NoCookingRepository()
    workflow = ServiceDayLogWorkflow(repository)
    command = _command(attachment)
    preview = workflow.preview(command)

    result = workflow.apply(
        ApplyServiceDayLog(
            9,
            "U-caregiver",
            12,
            command.intent,
            "baby-log-1",
            preview.preview_fingerprint,
            controlled_file_attachments=command.controlled_file_attachments,
        )
    )

    assert result.controlled_file_attachments[0].attachment_kind == "baby_log_photo"
    assert repository.submitted[0].controlled_file_attachments[0].controlled_file_object_id.startswith("cf_")


def test_baby_log_photo_resolves_to_baby_controlled_file_purpose():
    recorded = {}

    def preview(intent):
        recorded["intent"] = intent
        return SimpleNamespace(
            blockers=(),
            expected_staging_version=ExpectedVersion(1),
            preview_fingerprint=PreviewFingerprint("b" * 64),
        )

    controlled = SimpleNamespace(
        preview=preview,
        apply_borrowed=lambda _command: SimpleNamespace(
            readback=SimpleNamespace(
                file_id="cf_1234567890abcdef1234567890abcdef", applied_at=None
            )
        ),
    )
    attachment = _attachment("baby_log_photo")
    command = _command(attachment)

    ServiceDayLogWorkflow(NoCookingRepository(), controlled).preview(command)

    assert recorded["intent"].purpose.value == "baby_log_photo"
    assert recorded["intent"].object_key.endswith("/baby_log_photo/1/" + "a" * 64)


def test_baby_log_photo_does_not_satisfy_cooking_meal_requirement():
    attachment = ControlledServiceDayLogAttachment(
        "cf_1234567890abcdef1234567890abcdef",
        "cfs_1234567890abcdef1234567890abcdef",
        "a" * 64,
        "baby_log_photo",
    )
    preview = ServiceDayLogWorkflow(Repository()).preview(_command(attachment))

    assert preview.can_apply is False
    assert preview.blockers == ("service_day_log_meal_photo_required",)


def test_sequence_is_fail_closed_until_attachment_schema_stores_order():
    attachment = ControlledServiceDayLogAttachment(
        None,
        "cfs_1234567890abcdef1234567890abcdef",
        "a" * 64,
        sequence=2,
    )
    with pytest.raises(ValueError, match="service_day_log_attachment_sequence_unsupported"):
        ServiceDayLogWorkflow(Repository()).preview(_command(attachment))


def test_persisted_single_attachment_reads_back_as_sequence_one():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql, _params):
            return None

        def fetchall(self):
            return [
                {
                    "controlled_file_object_id": "cf_1234567890abcdef1234567890abcdef",
                    "staging_id": "cfs_1234567890abcdef1234567890abcdef",
                    "content_sha256": "a" * 64,
                    "attachment_kind": "meal_photo",
                }
            ]

    class Connection:
        def cursor(self):
            return Cursor()

    from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository

    attachments = MySqlServiceDayLogRepository(Connection())._load_controlled_attachments(1)
    assert len(attachments) == 1
    assert attachments[0].sequence == 1
