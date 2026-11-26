"""Browser coverage of the Studio's real UI with synthetic FAQ API responses."""

import copy
import os
import re
from urllib.parse import urlsplit

import pytest


pytestmark = pytest.mark.skipif(not os.environ.get("FAQ_E2E_URL"), reason="requires the isolated Studio web server")


def test_faq_01_playwright_add_preview_publish_reopen():
    from playwright.sync_api import expect, sync_playwright

    records = {"draft_revision": 0, "published_revision": None, "draft_layout": {"categories": []}, "published_layout": None}
    answer = {"qa_id": "CI-FAQ", "version": 2, "category": "服務異動", "question": "如何調整服務？", "answer": "請聯絡工會確認可調整時間。"}
    receipts = {}
    operation_reads = []
    unprefixed_faq_requests = []

    def dispatch(route):
        request = route.request
        method, url_path = request.method, urlsplit(request.url).path
        path = url_path.split("/api/v1", 1)[-1]
        if not url_path.startswith("/trial/") and path.startswith(("/line/faq-layout", "/line/service-help/faq")):
            unprefixed_faq_requests.append(url_path)
            return route.fulfill(status=500, json={"error": "required deployment prefix missing"})

        def ok(data, status=200):
            route.fulfill(status=status, json={"data": data})

        def problem(code, status):
            route.fulfill(status=status, json={"detail": {"error": {"code": code}}})

        if path == "/line/service-help/faq":
            return ok({"items": [answer], "categories": [answer["category"]], "next_cursor": None})
        if path.startswith(("/knowledge/items", "/knowledge/indexes")):
            return route.fulfill(json=[])
        if path == "/line/faq-layout" and method == "GET":
            return ok(records)
        if path.startswith("/line/faq-layout/operations/"):
            key = path.rsplit("/", 1)[-1]
            operation_reads.append(key)
            receipt = receipts.get(key)
            return ok(receipt) if receipt else problem("faq_operation_not_found", 404)
        if not path.startswith("/line/faq-layout/"):
            return ok({})

        body = request.post_data_json
        action = path.rsplit("/", 1)[-1]
        if action == "preview":
            if body["mode"] == "published":
                assert "layout" not in body
                source = records["published_layout"]
            else:
                source = body["layout"]
            card = next((row for row in (source or {"categories": []})["categories"] if row["category_id"] == body["category_id"]), None)
            if not card:
                return problem("faq_category_not_published", 404)
            view = {key: card[key] for key in ("category_id", "title", "description", "footer_label")}
            view["buttons"] = [
                {"qa_id": answer["qa_id"], "label": question["label"] or answer["question"],
                 "question": answer["question"], "answer": answer["answer"]} for question in card["questions"]
            ]
            return ok({"view": view, "issues": []})

        key = request.headers["idempotency-key"]
        assert request.headers["x-correlation-id"] == key
        assert body["expected_revision"] == records["draft_revision"]
        assert key not in receipts
        records["draft_revision"] += 1
        receipt = {"operation_id": key, "draft_revision": records["draft_revision"]}
        if action == "categories":
            category_id = "category-ci"
            records["draft_layout"]["categories"].append({
                "category_id": category_id, "name": body["name"], "title": body["name"], "description": "",
                "footer_label": "", "questions": [],
            })
            receipt["category_id"] = category_id
        elif action == "draft":
            records["draft_layout"] = body["layout"]
        elif action == "publish":
            assert records["draft_layout"]["categories"][0]["questions"]
            records["published_layout"] = copy.deepcopy(records["draft_layout"])
            records["published_revision"] = records["draft_revision"]
            receipt["published_revision"] = records["published_revision"]
        else:
            raise AssertionError(action)
        receipts[key] = receipt
        if action == "publish":
            return route.abort()
        return ok(receipt)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script("sessionStorage.setItem('union_admin_session_token', 'synthetic-ci-session')")
        page.route(re.compile(r"^http://[^/]+/(?:trial/)?api/v1/"), dispatch)
        page.goto(os.environ["FAQ_E2E_URL"] + "/#line-ai-events")
        page.get_by_role("button", name="LINE 聊天室版面").click()
        page.get_by_role("button", name="＋ 新增分類").click()
        page.get_by_role("textbox", name="分類名稱").fill("服務異動")
        page.get_by_role("button", name="建立分類").click()
        title = page.get_by_role("textbox", name="卡片標題")
        expect(title).to_be_focused()
        expect(title).to_have_value("服務異動")
        preview = page.get_by_role("region", name="手機預覽")
        preview.get_by_role("button", name="服務異動").click()
        expect(preview.get_by_role("heading", name="服務異動")).to_be_visible()
        preview.get_by_role("button", name="已發布").click()
        expect(preview.get_by_text("尚未發布", exact=True)).to_be_visible()
        expect(preview.get_by_role("button", name="服務異動")).to_have_count(0)
        preview.get_by_role("button", name="草稿", exact=True).click()
        page.get_by_label("加入已發布題目").select_option(value="CI-FAQ")
        page.get_by_role("button", name="儲存版面草稿").click()
        expect(page.get_by_text("已儲存版面草稿。")).to_be_visible()
        page.get_by_role("button", name="發布聊天室版面").click()
        expect(page.get_by_text("已發布聊天室版面。")).to_be_visible()

        page.reload()
        page.get_by_role("button", name="LINE 聊天室版面").click()
        preview.get_by_role("button", name="已發布").click()
        preview.get_by_role("button", name="服務異動").click()
        preview.get_by_role("button", name=answer["question"]).click()
        expect(preview.get_by_text(answer["answer"])).to_be_visible()
        assert len(receipts) == 3
        assert operation_reads == [next(key for key, receipt in receipts.items() if "published_revision" in receipt)]
        assert unprefixed_faq_requests == []
        browser.close()
