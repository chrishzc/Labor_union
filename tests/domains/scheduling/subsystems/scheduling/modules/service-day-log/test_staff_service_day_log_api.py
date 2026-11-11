"""File: test_staff_service_day_log_api.py
Description: 驗證月嫂寶寶日誌 API 已依 2026-11-10 裁決全數退役並回傳 410 GONE。"""

import pytest
from fastapi import HTTPException

from api.routes import staff_service_day_logs


def test_service_day_log_endpoints_are_retired() -> None:
    for handler, args in (
        (staff_service_day_logs.retired_direct_service_day_log, ()),
        (staff_service_day_logs.preview_service_day_log, ()),
        (staff_service_day_logs.apply_service_day_log, ()),
        (staff_service_day_logs.service_day_log_options, ()),
        (staff_service_day_logs.query_service_day_log, ()),
    ):
        with pytest.raises(HTTPException) as captured:
            handler(*args)
        assert captured.value.status_code == 410
        assert captured.value.detail["code"] == "service_day_log_retired"
