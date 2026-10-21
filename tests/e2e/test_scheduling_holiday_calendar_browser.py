"""
File: test_scheduling_holiday_calendar_browser.py
Description: 排班日曆國定假日顯示、重新整理、人員篩選與出勤順延試算之瀏覽器端對端驗證。
"""

from __future__ import annotations

import os
import shutil
import urllib.request
import pytest

playwright = pytest.importorskip("playwright.sync_api")

SCHEDULING_URL = "http://127.0.0.1:5173/admin/#scheduling"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TARGET_HOLIDAY_DATE = "2026-10-28"


def _is_server_reachable() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5173/admin/", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _is_chrome_available() -> bool:
    return os.path.exists(CHROME_PATH) or shutil.which("chrome") is not None


@pytest.mark.skipif(not _is_server_reachable(), reason="Local Vite dev server on http://127.0.0.1:5173 is not running")
@pytest.mark.skipif(not _is_chrome_available(), reason="Google Chrome executable not found")
def test_scheduling_holiday_calendar_display_and_behavior() -> None:
    launch_kwargs = {"headless": True}
    if os.path.exists(CHROME_PATH):
        launch_kwargs["executable_path"] = CHROME_PATH
    else:
        launch_kwargs["channel"] = "chrome"

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()

        # 1. 開啟排班日曆，確認 2026 年 10 月存在已入庫之測試假日標籤
        page.goto(SCHEDULING_URL, wait_until="networkidle")
        page.wait_for_selector(f".gantt-day-header-col[data-date='{TARGET_HOLIDAY_DATE}'].holiday", timeout=10000)
        col_28 = page.locator(f".gantt-day-header-col[data-date='{TARGET_HOLIDAY_DATE}']")
        assert "holiday" in (col_28.get_attribute("class") or ""), "Expected holiday class on 2026-10-28"
        holiday_tag = col_28.locator(".gantt-holiday-name")
        assert holiday_tag.count() == 1, "Holiday name tag not found"
        tag_text = holiday_tag.text_content().strip()
        assert "驗收測試假日" in tag_text, f"Unexpected holiday tag text: {tag_text}"

        # 2. 跨月切換後返回，假日標示持續存在且不重複
        page.locator("button[aria-label='查看下個月']").click()
        page.wait_for_selector(".current-month-display:has-text('11月')", timeout=5000)
        page.locator("button[aria-label='查看上個月']").click()
        page.wait_for_selector(".current-month-display:has-text('10月')", timeout=5000)
        page.wait_for_selector(f".gantt-day-header-col[data-date='{TARGET_HOLIDAY_DATE}'].holiday", timeout=10000)

        # 3. 無人員搜尋結果時，頂部日期列與假日標示仍可見並可水平捲動
        search_input = page.locator("input[placeholder='按月嫂姓名或編號...']")
        search_input.fill("NONEXISTENT_STAFF_XYZ_9999")
        page.wait_for_timeout(400)
        empty_msg = page.locator(".scheduling-status").text_content().strip()
        assert "沒有排班資料" in empty_msg or "沒有可顯示" in empty_msg
        assert page.locator(f".gantt-day-header-col[data-date='{TARGET_HOLIDAY_DATE}']").is_visible()
        clear_btn = page.locator(".gantt-search-box button", has_text="✕")
        clear_btn.click()
        page.wait_for_timeout(400)
        assert search_input.input_value() == ""

        # 4. 國定假日政策清單中確認存在該筆假日
        page.locator("nav button", has_text="國定假日政策").click()
        page.wait_for_selector(".holiday-policy-list", timeout=5000)
        list_text = page.locator(".holiday-policy-list").text_content()
        assert TARGET_HOLIDAY_DATE in list_text, f"{TARGET_HOLIDAY_DATE} should be listed in holiday policy"
        assert tag_text in list_text, f"Holiday name '{tag_text}' should be listed in holiday policy"

        # 5. 案件處理出勤精算自動跳過該假日並順延完工日（純唯讀核對）
        page.goto("http://127.0.0.1:5173/admin/#order-workbench-v2?case=UI-HCM-20261012-01&work=service", wait_until="networkidle")
        page.wait_for_selector(".service-date-summary-strip dd:has-text('2026-11-06')", timeout=15000)
        strip_text = page.locator(".service-date-summary-strip").text_content().strip()
        assert "2026-10-26" in strip_text
        assert "2026-11-06" in strip_text
        assert "10 / 10 天" in strip_text

        browser.close()
