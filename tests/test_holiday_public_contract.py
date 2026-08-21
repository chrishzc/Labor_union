"""
File: test_holiday_public_contract.py
Description: 驗證 Holiday Pydantic closed contract、horizon 與 production transaction 邊界。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas.holidays import HolidayApplyRequest, HolidayPreviewRequest


def test_preview_contract_normalizes_legacy_single_date_to_explicit_horizon():
    request = HolidayPreviewRequest.model_validate(
        {
            "action": "upsert",
            "holiday_date": "2026-10-10",
            "holiday_name": " 國慶日 ",
        }
    )

    assert request.holiday_name == "國慶日"
    assert request.from_date == request.holiday_date == request.to_date


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "upsert", "holiday_date": "2026-10-10"},
        {
            "action": "delete",
            "holiday_date": "2026-10-10",
            "from_date": "2026-10-01",
        },
        {
            "action": "delete",
            "holiday_date": "2026-10-10",
            "unexpected": True,
        },
    ],
)
def test_preview_contract_fails_closed(payload):
    with pytest.raises(ValidationError):
        HolidayPreviewRequest.model_validate(payload)


def test_apply_requires_version_fingerprint_and_trimmed_reason():
    request = HolidayApplyRequest.model_validate(
        {
            "action": "upsert",
            "holiday_date": "2026-10-10",
            "holiday_name": "國慶日",
            "expected_calendar_version": "a" * 64,
            "preview_fingerprint": "b" * 64,
            "reason": " 年度設定 ",
        }
    )
    assert request.reason == "年度設定"


def test_holiday_workflow_has_no_hidden_commit_or_rollback():
    workflow = Path("subsystems/scheduling/holiday_maintenance.py").read_text(
        encoding="utf-8"
    )
    repository = Path(
        "infrastructure/mysql/scheduling_holiday_query.py"
    ).read_text(encoding="utf-8")

    for source in (workflow, repository):
        assert ".commit(" not in source
        assert ".rollback(" not in source
