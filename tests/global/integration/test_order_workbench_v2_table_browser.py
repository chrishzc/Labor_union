"""
File: test_order_workbench_v2_table_browser.py
Description: 待辦看板清單式改版之瀏覽器端對端驗證；唯讀檢驗緊湊表格、搜尋篩選、抽屜開關與降級狀態。
"""

from __future__ import annotations

import os
import shutil
import urllib.request
import pytest

playwright = pytest.importorskip("playwright.sync_api")

BASE_URL = os.getenv("LABOR_UNION_BROWSER_BASE_URL", "").rstrip("/")
WORKBENCH_URL = f"{BASE_URL}/admin/#order-workbench-v2"
CHROME_PATH = os.getenv("LABOR_UNION_BROWSER_EXECUTABLE", r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def _is_server_reachable() -> bool:
    if not BASE_URL:
        return False
    try:
        with urllib.request.urlopen(f"{BASE_URL}/admin/", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _is_chrome_available() -> bool:
    return os.path.exists(CHROME_PATH) or shutil.which("chrome") is not None


@pytest.mark.skipif(not _is_server_reachable(), reason="requires an explicit ready LABOR_UNION_BROWSER_BASE_URL with synthetic fixtures")
@pytest.mark.skipif(not _is_chrome_available(), reason="Google Chrome executable not found")
def test_order_workbench_v2_table_layout_and_navigation() -> None:
    launch_kwargs = {"headless": True}
    if os.path.exists(CHROME_PATH):
        launch_kwargs["executable_path"] = CHROME_PATH
    else:
        launch_kwargs["channel"] = "chrome"

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()
        page.goto(WORKBENCH_URL, wait_until="networkidle")
        page.wait_for_selector(".order-v2-table", timeout=10000)
        page.get_by_text("合成驗收客戶", exact=True).wait_for()

        # 1. 欄位結構完整
        headers = [th.text_content().strip() for th in page.locator(".order-v2-table th").all()]
        assert headers == ['案件編號', '客戶姓名', '約定服務期間', '指派月嫂', '目前待辦', '提醒', '操作']

        # 2. 存在進行中案件列且無重複編號
        rows = page.locator(".order-v2-case-entry").all()
        assert len(rows) > 0, "Expected at least 1 in-progress case row"
        case_ids = [r.locator(".order-v2-case-number").text_content().strip() for r in rows]
        assert len(case_ids) == len(set(case_ids)), "Duplicate case numbers detected in table"

        # 3. 抽屜開啟與安全返回
        first_row = rows[0]
        c_no = first_row.locator(".order-v2-case-number").text_content().strip()
        first_row.locator(".order-v2-case-number").click()
        page.wait_for_selector(".order-case-page", timeout=5000)
        assert c_no in page.locator("p.order-case-eyebrow", has_text="案件").text_content()
        page.locator("button.order-case-back").click()
        page.wait_for_selector(".order-v2-table", timeout=5000)

        # 4. 關鍵字搜尋與清除還原
        search_input = page.locator("input[aria-label='搜尋案件編號或姓名']")
        search_input.fill(c_no)
        page.wait_for_timeout(300)
        assert len(page.locator(".order-v2-case-entry").all()) == 1

        page.locator("button", has_text="清除篩選").click()
        page.wait_for_timeout(300)
        assert len(page.locator(".order-v2-case-entry").all()) == len(rows)
        page.get_by_text("合成驗收客戶", exact=True).wait_for()
        playwright.expect(page.get_by_role("button", name="重新整理", exact=True)).to_be_enabled()

        browser.close()
