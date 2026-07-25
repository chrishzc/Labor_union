"""
================================================================================
檔案名稱: tests/test_calendar_ui_explicit_errors.py
功能說明: 驗證 CalendarUI 顯性錯誤提示、無 db_service 引用與 assignment-schedules REST 端點對齊
================================================================================
"""

import pytest
from pathlib import Path

def test_calendar_ui_decoupled_from_db_service():
    """驗證 ui/pages/03_calendar.py 完全解耦，不再匯入 db_service"""
    file_content = Path("ui/pages/03_calendar.py").read_text(encoding="utf-8")
    assert "from services import db_service" not in file_content
    assert "importlib.reload(db_service)" not in file_content

def test_calendar_ui_uses_assignment_schedules_endpoint():
    """驗證 ui/pages/03_calendar.py 使用 assignment-schedules 休假保存端點"""
    file_content = Path("ui/pages/03_calendar.py").read_text(encoding="utf-8")
    assert "/api/v1/assignment-schedules/" in file_content
    assert "/orders/{target_order['case_no']}/rest-dates" not in file_content
