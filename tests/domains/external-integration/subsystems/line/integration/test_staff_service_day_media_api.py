"""驗證月嫂餐食照片先進入 Scheduling 受控檔案 staging。"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from api.routes import staff_service_day_media
from domains.line.identities import LineUserId


class Upload:
    def __init__(self, content: bytes, content_type: str, filename: str = "meal.png") -> None:
        self._content = content
        self.content_type = content_type
        self.filename = filename

    async def read(self, _limit: int) -> bytes:
        return self._content


def _dependencies(recorded):
    class ControlledFiles:
        def stage(self, command):
            recorded["stage"] = command
            return SimpleNamespace(
                staging_id="cfs_1234567890abcdef1234567890abcdef",
                mime_type=command.mime_type,
                size_bytes=len(command.content),
                sha256_digest="a" * 64,
                expires_at=SimpleNamespace(isoformat=lambda: "2026-08-16T01:00:00+00:00"),
                replayed=False,
            )

    class Logs:
        def preview(self, command):
            recorded["preview"] = command
            return SimpleNamespace(case_no="CASE-44", requires_cooking=True)

    return ControlledFiles(), Logs()


def test_upload_meal_photo_stages_controlled_file_for_bound_assignment(monkeypatch) -> None:
    recorded = {}
    controlled_files, logs = _dependencies(recorded)
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))
    monkeypatch.setattr(staff_service_day_media, "_verified_staff_identity", lambda _payload: (8, "U-caregiver"))

    response = asyncio.run(
        staff_service_day_media.upload_service_day_meal_photo(
            photo=Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png"),
            flow_id="flow",
            line_id_token="token",
            development_line_user_id="",
            assignment_id=71,
            service_date=date(2026, 8, 16),
            idempotency_key="meal-photo-1",
            controlled_file_workflow=controlled_files,
            service_day_log_application=logs,
        )
    )

    assert response.data["staging_id"].startswith("cfs_")
    assert response.data["sha256_digest"] == "a" * 64
    assert recorded["stage"].owner.value == "scheduling"
    assert recorded["stage"].purpose.value == "meal_photo"
    assert recorded["stage"].subject_reference == "CASE-44"
    assert recorded["preview"].assignment_id == 71


def test_upload_baby_log_photo_stages_scheduling_baby_log_purpose(monkeypatch) -> None:
    recorded = {}
    controlled_files, logs = _dependencies(recorded)
    logs.preview = lambda _command: SimpleNamespace(case_no="CASE-44", requires_cooking=False)
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))
    monkeypatch.setattr(staff_service_day_media, "_verified_staff_identity", lambda _payload: (8, "U-caregiver"))

    response = asyncio.run(
        staff_service_day_media.upload_service_day_meal_photo(
            photo=Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png", "baby.png"),
            flow_id="flow",
            line_id_token="token",
            development_line_user_id="",
            assignment_id=71,
            service_date=date(2026, 8, 16),
            attachment_kind="baby_log_photo",
            idempotency_key="baby-photo-1",
            controlled_file_workflow=controlled_files,
            service_day_log_application=logs,
        )
    )

    assert response.data["outcome"] == "created"
    assert recorded["stage"].purpose.value == "baby_log_photo"
    assert "/baby_log_photo/1/" in recorded["stage"].object_key


def test_upload_meal_photo_rejects_assignment_without_cooking_before_staging(monkeypatch) -> None:
    recorded = {}
    controlled_files, logs = _dependencies(recorded)
    logs.preview = lambda _command: SimpleNamespace(case_no="CASE-44", requires_cooking=False)
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))
    monkeypatch.setattr(staff_service_day_media, "_verified_staff_identity", lambda _payload: (8, "U-caregiver"))

    with pytest.raises(staff_service_day_media.HTTPException) as captured:
        asyncio.run(
            staff_service_day_media.upload_service_day_meal_photo(
                photo=Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png"),
                flow_id="flow",
                line_id_token="token",
                development_line_user_id="",
                assignment_id=71,
                service_date=date(2026, 8, 16),
                idempotency_key="meal-photo-forbidden",
                controlled_file_workflow=controlled_files,
                service_day_log_application=logs,
            )
        )

    assert captured.value.status_code == 422
    assert captured.value.detail["code"] == "service_day_log_meal_photo_forbidden"
    assert "stage" not in recorded


def test_upload_meal_photo_maps_staging_idempotency_conflict_to_409(monkeypatch) -> None:
    class ConflictingControlledFiles:
        def stage(self, _command):
            raise RuntimeError("controlled_file_staging_idempotency_conflict")

    logs = SimpleNamespace(preview=lambda _command: SimpleNamespace(case_no="CASE-44", requires_cooking=True))
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))
    monkeypatch.setattr(staff_service_day_media, "_verified_staff_identity", lambda _payload: (8, "U-caregiver"))

    with pytest.raises(staff_service_day_media.HTTPException) as captured:
        asyncio.run(
            staff_service_day_media.upload_service_day_meal_photo(
                photo=Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png"),
                flow_id="flow",
                line_id_token="token",
                development_line_user_id="",
                assignment_id=71,
                service_date=date(2026, 8, 16),
                idempotency_key="meal-photo-conflict",
                controlled_file_workflow=ConflictingControlledFiles(),
                service_day_log_application=logs,
            )
        )

    assert captured.value.status_code == 409
    assert captured.value.detail["code"] == "controlled_file_staging_idempotency_conflict"


def test_same_key_different_assignment_canonical_payload_is_closed_409(monkeypatch) -> None:
    recorded = {"commands": []}

    class SameKeyControlledFiles:
        def stage(self, command):
            recorded["commands"].append(command)
            if len(recorded["commands"]) == 1:
                return SimpleNamespace(
                    staging_id="cfs_1234567890abcdef1234567890abcdef",
                    mime_type=command.mime_type,
                    size_bytes=len(command.content),
                    sha256_digest="a" * 64,
                    expires_at=SimpleNamespace(
                        isoformat=lambda: "2026-08-16T01:00:00+00:00"
                    ),
                    replayed=False,
                )
            raise RuntimeError("controlled_file_staging_idempotency_conflict")

    logs = SimpleNamespace(
        preview=lambda _command: SimpleNamespace(case_no="CASE-44", requires_cooking=True)
    )
    monkeypatch.setattr(
        staff_service_day_media,
        "_verified_line_user_id",
        lambda _payload: LineUserId("U-caregiver"),
    )
    monkeypatch.setattr(
        staff_service_day_media,
        "_verified_staff_identity",
        lambda _payload: (8, "U-caregiver"),
    )
    controlled_files = SameKeyControlledFiles()

    first = asyncio.run(
        staff_service_day_media.upload_service_day_meal_photo(
            photo=Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png"),
            flow_id="flow",
            line_id_token="token",
            development_line_user_id="",
            assignment_id=71,
            service_date=date(2026, 8, 16),
            idempotency_key="meal-photo-same-key",
            controlled_file_workflow=controlled_files,
            service_day_log_application=logs,
        )
    )
    assert first.data["outcome"] == "created"

    with pytest.raises(staff_service_day_media.HTTPException) as captured:
        asyncio.run(
            staff_service_day_media.upload_service_day_meal_photo(
                photo=Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png"),
                flow_id="flow",
                line_id_token="token",
                development_line_user_id="",
                assignment_id=72,
                service_date=date(2026, 8, 16),
                idempotency_key="meal-photo-same-key",
                controlled_file_workflow=controlled_files,
                service_day_log_application=logs,
            )
        )

    assert captured.value.status_code == 409
    assert captured.value.detail["code"] == "controlled_file_staging_idempotency_conflict"
    assert recorded["commands"][0].idempotency_key.value == recorded["commands"][1].idempotency_key.value
    assert recorded["commands"][0].object_key != recorded["commands"][1].object_key


def test_upload_meal_photo_rejects_declared_type_that_does_not_match_bytes(monkeypatch) -> None:
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))
    monkeypatch.setattr(staff_service_day_media, "_verified_staff_identity", lambda _payload: (_ for _ in ()).throw(AssertionError("invalid media must not resolve assignment")))

    with pytest.raises(staff_service_day_media.HTTPException) as captured:
        asyncio.run(
            staff_service_day_media.upload_service_day_meal_photo(
                photo=Upload(b"not-an-image", "image/jpeg"),
                flow_id="flow",
                line_id_token="token",
                development_line_user_id="",
                assignment_id=71,
                service_date=date(2026, 8, 16),
                idempotency_key="meal-photo-invalid",
                controlled_file_workflow=object(),
                service_day_log_application=object(),
            )
        )

    assert captured.value.status_code == 422
    assert captured.value.detail["code"] == "service_day_meal_photo_content_type_invalid"
