"""
File: test_line_registration_presentation.py
Description: 驗證 LINE LIFF 客戶登記頁呈現、胎數必填與預覽送出契約。
"""

from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest

from domains.case_import.non_citizen_registration import LIFF_SERVICE_TIME_OPTIONS


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


@pytest.mark.parametrize(
    ("path", "kind", "studio", "interruption"),
    [
        pytest.param("/line-registration", "subsidy", False, None, id="subsidy"),
        pytest.param("/line-non-citizen-registration", "non_citizen", False, None, id="non-citizen"),
        pytest.param("/line-non-citizen-registration", "non_citizen", False, "receipt_lost", id="receipt-lost"),
        pytest.param("/line-non-citizen-registration", "non_citizen", False, "conflict", id="receipt-conflict"),
        pytest.param(
            "/line-non-citizen-registration", "non_citizen", False, "conflict_not_received", id="conflict-not-received",
        ),
        pytest.param("/line-non-citizen-registration", "non_citizen", False, "not_received", id="not-received"),
        pytest.param("/line-non-citizen-registration", "non_citizen", False, "reload", id="reload"),
        pytest.param(
            "/api/v1/line/identity/studio-preview/non-citizen-registration?studio_preview=1",
            "non_citizen", True, None, id="studio-preview",
        ),
    ],
)
def test_registration_passbook_controls_and_submission_in_browser(
    path: str, kind: str, studio: bool, interruption: str | None,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from playwright.sync_api import Route, expect, sync_playwright

    from api.routes.line_identity import page_router, public_router

    pages = FastAPI()
    pages.include_router(page_router)
    pages.include_router(public_router)
    origin = "https://registration.example.test"
    registration_api = "/api/v1/line/identity/registration"
    conflict = interruption in {"conflict", "conflict_not_received"}
    requests: list[tuple[str, str | None]] = []
    apply_keys: list[str] = []
    status_requests: list[dict[str, str]] = []
    receipt = {
        "registration_id": 234, "status": "pending", "identity_status": "pending_approval",
        "client_id": None, "beclass_record_id": None, "case_no": None,
    }
    runtime = {
        "revision": "synthetic-revision",
        "theme": {
            "primary_color": "#357abd", "primary_hover_color": "#357abd", "background": "#fff",
            "text_color": "#000", "muted_text_color": "#333", "font_family": "sans-serif",
        },
        "page": {
            "title": "需求調查", "subtitle": "", "submit_button": "送出測試申請",
            "success_title": "提交結果", "loading_text": "處理中", "content": {},
            "fields": [{"id": "gender", "system_field": True, "required": True, "label": "性別",
                        "options": [{"value": "女", "label": "女"}]}],
        },
    }

    def route_request(route: Route) -> None:
        url = urlsplit(route.request.url)
        if route.request.is_navigation_request() and url.netloc == "registration.example.test":
            response = page_client.get(path)
            route.fulfill(status=response.status_code, body=response.content, content_type="text/html; charset=utf-8")
        elif url.path == "/api/config/liff/runtime":
            route.fulfill(json=runtime)
        elif url.path == "/api/v1/line/identity/runtime-config":
            route.fulfill(json={"data": {"liff_id": "synthetic-liff"}})
        elif url.path.startswith(registration_api + "/"):
            endpoint = url.path.removeprefix(registration_api + "/")
            requests.append((endpoint, route.request.post_data if endpoint != "passbook" else None))
            if endpoint == "passbook":
                route.fulfill(json={"data": {"passbook_image_id": "pbk_synthetic_cover"}})
            elif endpoint == "preview":
                route.fulfill(json={"data": {"status": "ready", "expected_binding_version": 0,
                                             "payload_fingerprint": "a" * 64,
                                             "preview_fingerprint": "a" * 64}})
            elif endpoint == "apply":
                apply_keys.append(route.request.headers["idempotency-key"])
                if conflict:
                    route.fulfill(status=409, json={"detail": {"error": {"code": "registration_conflict"}}})
                elif interruption and len(apply_keys) == 1:
                    route.abort()
                else:
                    route.fulfill(json={"data": receipt})
            elif endpoint == "status":
                status_requests.append(route.request.post_data_json)
                if interruption in {"receipt_lost", "conflict"}:
                    route.fulfill(json={"data": receipt})
                elif interruption == "conflict_not_received":
                    route.fulfill(json={"data": {"status": "not_received"}})
                elif len(status_requests) == 1:
                    route.fulfill(status=503, json={"detail": {"code": "registration_unavailable"}})
                elif interruption == "not_received" and len(status_requests) == 2:
                    route.fulfill(json={"data": {"status": "not_received", "registration_id": 234}})
                else:
                    route.fulfill(json={"data": {"status": "not_received"}})
            else:
                route.fulfill(status=404)
        else:
            route.abort()

    with TestClient(pages) as page_client, sync_playwright() as playwright, closing(playwright.chromium.launch()) as browser:
        page = browser.new_page()
        page.route("**/*", route_request)
        page.add_init_script("""
            window.liff = { init: async () => {}, isLoggedIn: () => true, getIDToken: () => 'synthetic-token' };
        """)
        page.goto(origin + path)
        submit = page.locator("#registrationPreviewButton")
        passbook = page.locator("#passbook_cover")
        expect(page.locator("#refund_bank_code")).to_be_visible()
        expect(page.locator("#refund_bank_account")).to_be_visible()
        expect(page.get_by_text("請填入產婦本人銀行帳號。", exact=True)).to_be_visible()
        if kind == "non_citizen":
            expect(page.locator('input[type="file"]')).to_have_count(0)
            expect(page.locator("#passbookPreviewBox")).to_have_count(0)
            expect(page.get_by_text("存摺封面")).to_have_count(0)
        if studio:
            expect(submit).to_have_text("預覽模式")
            expect(submit).to_be_disabled()
            expect(page.locator("#studioPreviewNotice")).to_be_visible()
            page.locator("#registerForm").dispatch_event("submit")
            assert requests == []
            return

        expect(submit).to_have_text("送出測試申請")
        page.wait_for_function("currentIdToken === 'synthetic-token'")
        today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
        for field, value in {
            "name": "合成申請", "phone": "0900000000", "expected_date": today, "service_days": "10",
            "address": "合成地址", "email": "test@example.com", "refund_bank_code": "0000000",
            "refund_bank_account": "0000000000",
        }.items():
            page.locator(f"#{field}").fill(value)
        page.locator('[data-survey="服務時間內是否有其他寶寶"]').fill("無")
        page.locator("#ingredient_purchase").select_option("自行準備")
        for field in ("multi_birth_single", "needs_cooking_no", "agree2", "agree3"):
            page.locator(f"#{field}").check()
        page.locator('label[for="agree1"]').click()
        page.locator("#refundPolicyAccept").click()

        if kind == "non_citizen":
            for field, value in {"city": "新竹市", "birth_date": "1990-01-01",
                                 "service_start_date": today, "notes": "無"}.items():
                page.locator(f"#{field}").fill(value)
            for field, value in {"gender": "女", "service_time": "08:30-12:30 (4小時)",
                                 "residence_type": "電梯大樓", "delivery_type": "自然產",
                                 "service_type": "週休1日"}.items():
                page.locator(f"#{field}").select_option(value)
            for field, valid in (("refund_bank_code", "0000000"), ("refund_bank_account", "0000000000")):
                control = page.locator(f"#{field}")
                for value in ("", "X"):
                    control.fill(value)
                    submit.click()
                    expect(control).to_have_class(re.compile(r"\binvalid\b"))
                    assert requests == []
                control.fill(valid)
        else:
            expect(passbook).to_be_visible()
            assert passbook.evaluate("input => input.required") is True
            submit.click()
            status_message = page.locator("#statusMessage")
            expect(status_message).to_have_text("請上傳存摺封面照片。")
            expect(status_message).to_be_visible()
            assert requests == []
            passbook.set_input_files({
                "name": "synthetic.png", "mimeType": "image/png",
                "buffer": bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
                    "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
                ),
            })
            expect(page.locator("#passbookPreviewImg")).to_be_visible()

        submit.click()
        retry = page.locator("#registrationStatusButton")
        if interruption:
            expect(retry).to_be_enabled()
            expect(retry).to_be_visible()
            expect(submit).to_be_disabled()
            expect(page.locator("#successCard")).to_be_hidden()
            action_label = retry.inner_text()
            if not conflict:
                expect(page.locator("#statusMessage")).to_contain_text("還不知道工會有沒有收到")
            expect(page.locator("#name")).to_have_value("合成申請")
            assert [endpoint for endpoint, _ in requests] == ["preview", "apply"]
            if conflict:
                assert page.evaluate("sessionStorage.getItem('registration-submission:non-citizen')") == apply_keys[0]
            else:
                assert page.evaluate("Object.values(sessionStorage)") == apply_keys

            if interruption == "reload":
                page.reload()

            if not conflict and interruption != "receipt_lost":
                if interruption != "reload":
                    retry.click()
                expect(retry).to_be_enabled()
                expect(retry).to_be_visible()
                expect(submit).to_be_disabled()
                expect(page.locator("#successCard")).to_be_hidden()
                expect(page.locator("#statusMessage")).to_contain_text("還不知道工會有沒有收到")
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status"]

            if interruption == "not_received":
                retry.click()
                expect(retry).to_be_enabled()
                expect(retry).to_be_visible()
                expect(submit).to_be_disabled()
                expect(page.locator("#successCard")).to_be_hidden()
                expect(page.locator("#statusMessage")).to_contain_text("還不知道工會有沒有收到")
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status", "status"]
                page.locator("#name").evaluate("(field) => { field.value = '異動後資料'; }")
            retry.click()
            if interruption == "reload":
                expect(submit).to_be_enabled()
                expect(retry).to_be_hidden()
                expect(page.locator("#successCard")).to_be_hidden()
                expect(page.locator("#statusMessage")).to_contain_text("目前尚未收到")
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status", "status"]
            elif interruption == "conflict_not_received":
                page.wait_for_function("!registrationSubmissionPending")
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status"]
                assert "查詢原申請" in action_label
                expect(page.locator("#statusMessage")).to_contain_text("本次申請未送出")
                expect(page.locator("#statusMessage")).to_contain_text("待審申請")
                expect(retry).to_be_hidden()
                expect(submit).to_be_disabled()
                expect(page.locator("#reapplyButton")).to_be_hidden()
                expect(page.locator("#successCard")).to_be_hidden()
                page.reload()
                expect(page.locator("#statusMessage")).to_contain_text("本次申請未送出")
                expect(retry).to_be_hidden()
                expect(submit).to_be_disabled()
                expect(page.locator("#reapplyButton")).to_be_hidden()
                expect(page.locator("#successCard")).to_be_hidden()
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status", "status"]
                assert len(apply_keys) == 1
                assert page.evaluate("sessionStorage.getItem('registration-submission:non-citizen')") == apply_keys[0]
            elif interruption in {"receipt_lost", "conflict"}:
                expect(page.locator(".success-desc")).to_contain_text("申請編號：234")
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status"]
            else:
                expect(page.locator(".success-desc")).to_contain_text("申請編號：234")
                assert [endpoint for endpoint, _ in requests] == ["preview", "apply", "status", "status", "status", "apply"]
                assert requests[1] == requests[-1]
                assert apply_keys[0] == apply_keys[1]
            assert all(item == {"line_id_token": "synthetic-token", "submission_id": apply_keys[0]} for item in status_requests)
        else:
            expect(page.locator(".success-desc")).to_contain_text("申請編號：234")
            endpoints = [endpoint for endpoint, _ in requests]
            assert endpoints == (["passbook", "preview", "apply"] if kind == "subsidy" else ["preview", "apply"])

        if interruption not in {"reload", "conflict_not_received"}:
            expect(page.locator(".success-title")).to_have_text("申請已收到")
            expect(page.locator(".success-desc")).to_contain_text("您可以關閉頁面")
            expect(retry).to_be_hidden()
        for endpoint, raw_payload in requests:
            if endpoint not in {"apply", "preview"}:
                continue
            assert raw_payload is not None
            payload = json.loads(raw_payload)
            if kind == "non_citizen":
                assert payload["registration_kind"] == "non_citizen"
                assert "passbook_image_id" not in payload
            else:
                assert payload.get("registration_kind", "subsidy") == "subsidy"
                assert payload["passbook_image_id"] == "pbk_synthetic_cover"
            assert payload["survey_details"]["補助款退款:銀行代號+分行代號"] == "0000000"
            assert payload["survey_details"]["銀行帳號"] == "0000000000"


def test_non_citizen_service_choices_match_manual_case_form():
    liff = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    manual = (ROOT / "ui_react/src/components/RegistrationApplications.tsx").read_text(encoding="utf-8")

    for field in ("delivery_type", "residence_type", "service_time"):
        liff_select = liff.split(f'id="{field}">', 1)[1].split("</select>", 1)[0]
        manual_select = manual.split(f"value={{manualForm.{field}}}", 1)[1].split("</select>", 1)[0]
        assert re.findall(r'<option value="([^"]+)">', liff_select) == re.findall(
            r'<option value="([^"]+)">', manual_select
        )
    liff_service_type = liff.split('id="service_type">', 1)[1].split("</select>", 1)[0]
    manual_service_type = manual.split("value={manualForm.service_type}", 1)[1].split("</select>", 1)[0]
    assert re.findall(r'<option value="([^"]+)">', liff_service_type) == ["週休1日", "週休2日"]
    assert "連續服務" not in liff_service_type
    assert re.findall(r'<option value="([^"]+)">', manual_service_type) == ["連續服務", "週休1日", "週休2日"]
    assert tuple(re.findall(
        r'<option value="([^"]+)">', liff.split('id="service_time">', 1)[1].split("</select>", 1)[0]
    )) == LIFF_SERVICE_TIME_OPTIONS
    assert 'type="time"' not in liff


def test_optional_holiday_preference_is_in_registration_fees_section():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    before, fees = source.split("💰 5. 費用與同意條款", 1)
    assert 'id="holiday_double_pay"' not in before
    preference = re.search(r'<select[^>]*id="holiday_double_pay"[^>]*>(.*?)</select>', fees, re.S)
    assert preference is not None
    assert "required" not in preference[0]
    assert 'data-survey="三節假日是否願意支付雙倍薪水"' in preference[0]
    assert re.findall(r'<option value="([^"]*)">', preference[1]) == ["", "是", "否"]
    serializer = source.split("// 處理具名的表單欄位", 1)[1].split("// 處理單選 Radio", 1)[0]
    script = r'''
const assert = require('node:assert/strict');
const key = '三節假日是否願意支付雙倍薪水';
for (const [value, expected] of [['是', {[key]: '是'}], ['否', {[key]: '否'}], ['', {}]]) {
    const surveyDetails = {};
    const document = {
        querySelectorAll(selectors) {
            assert(selectors.split(', ').includes('select[data-survey]'));
            return [{value, getAttribute(name) { assert.equal(name, 'data-survey'); return key; }}];
        },
    };
''' + serializer + r'''
    assert.deepEqual(surveyDetails, expected);
}
'''
    subprocess.run(["node"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)


def test_runtime_copy_describes_review_instead_of_promising_matching():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    runtime_function = "function applyRuntime(runtime)" + source.split("function applyRuntime(runtime)", 1)[1].split("function applySystemField", 1)[0]
    settings = json.loads((ROOT / "config/liff_settings.json").read_text(encoding="utf-8"))
    runtime = {"theme": settings["theme"], "page": settings["pages"]["registration"]}
    runtime["page"].update(subtitle="測試副標題", submit_button="設定送出文字", success_title="設定成功標題")
    script = r"""
const nodes = new Map();
const isNonCitizen = false;
const nonCitizenFields = [];
function element(id) {if (!nodes.has(id)) nodes.set(id, {}); return nodes.get(id);}
const document = {documentElement: {style: {setProperty(){}}}, body: {style: {}}, getElementById: element, querySelector: element};
function applySystemField() {}
function renderCustomFields() {}
""" + runtime_function + "\napplyRuntime(" + json.dumps(runtime, ensure_ascii=False) + ");\nconsole.log(JSON.stringify([element('.subtitle').textContent,element('registrationPreviewButton').textContent,element('.success-title').textContent]));"
    result = subprocess.run(["node"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)
    assert json.loads(result.stdout) == ["測試副標題", "設定送出文字", "設定成功標題"]
    assert "即刻啟動媒合" not in source
    assert "【市府案件已建立】" not in source
    assert "預填案件編號：${caseNo}（待工會核對）" in source


def test_success_readback_requires_a_real_receipt_and_renders_current_registration_outcomes():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    renderer = "function renderRegistrationSuccess(receipt)" + source.split(
        "function renderRegistrationSuccess(receipt)", 1
    )[1].split("function requireRegistrationPreview", 1)[0]
    preview_validator = "function requireRegistrationPreview(data)" + source.split(
        "function requireRegistrationPreview(data)", 1
    )[1].split("function registrationErrorMessage", 1)[0]
    error_renderer = "function registrationErrorMessage(result, status)" + source.split(
        "function registrationErrorMessage(result, status)", 1
    )[1].split("</script>", 1)[0]
    script = r'''
const assert = require('node:assert/strict');
const nodes = new Map();
const element = id => {if(!nodes.has(id))nodes.set(id,{style:{display:'block'},textContent:''});return nodes.get(id)};
const document={getElementById:element,querySelector:element};
let runtimePage = null;
let registrationResultUnknown = true;
let pendingRegistrationApply = {body:'synthetic'};
''' + renderer + preview_validator + error_renderer + r'''
assert.equal(registrationErrorMessage({detail:{code:'internal_preview_error',message:'請確認姓名。'}},422),'請確認姓名。');
assert(!registrationErrorMessage({detail:'internal_preview_error'},422).includes('internal_preview_error'));
const preview={status:'ready',expected_binding_version:0,payload_fingerprint:'a'.repeat(64),preview_fingerprint:'b'.repeat(64)};
assert.equal(requireRegistrationPreview(preview),preview);
assert.throws(()=>requireRegistrationPreview({...preview,status:'pending'}),/這次沒有送出/);
const pending={registration_id:42,status:'pending',identity_status:'pending_approval',client_id:null,beclass_record_id:null,case_no:null,expires_at_utc:'2026-12-10T03:00:00Z'};
renderRegistrationSuccess(pending);
assert.equal(element('.success-desc').textContent,'您可以關閉頁面，後續由工會審核。\n申請編號：42');
assert.equal(element('.success-title').textContent,'申請已收到');
assert.equal(element('successCard').style.display,'block');
assert.equal(element('registerForm').style.display,'none');
assert.equal(registrationResultUnknown,false);
assert.equal(pendingRegistrationApply,null);
const outcomes = {
  approving: '工會正在處理這筆申請，您可以關閉頁面。',
  approved: '工會已核准你的申請。',
  rejected: '這次申請沒有通過。你可以聯絡工會，或重新申請。',
  expired: '這份申請已到期。請按「重新申請」。',
};
for(const [status, message] of Object.entries(outcomes)){
  renderRegistrationSuccess({...pending,status,identity_status:status,client_id:10,beclass_record_id:11});
  assert.equal(element('.success-desc').textContent,message+'\n申請編號：42');
  assert.equal(element('reapplyButton').style.display, ['rejected','expired'].includes(status) ? 'block' : 'none');
  assert(!element('.success-desc').textContent.includes('待工會核准'));
  assert(!element('.success-desc').textContent.includes('10'));
}
for(const invalid of [null,{}, {...pending,registration_id:0},{...pending,registration_id:'42'},
  {...pending,identity_status:null},{...pending,identity_status:'unrecognized'},
  {...pending,identity_status:'bound'},{...pending,identity_status:'existing'},
  {...pending,status:'not_received'},{...pending,case_no:'A115001'},{...pending,client_id:10},{...pending,beclass_record_id:11}]){
  element('successCard').style.display='none';element('registerForm').style.display='block';
  assert.throws(()=>renderRegistrationSuccess(invalid),/讀回不完整/);
  assert.equal(element('successCard').style.display,'none');
  assert.equal(element('registerForm').style.display,'block');
}
runtimePage={success_title:'設定成功標題',success_description:'設定成功說明'};
renderRegistrationSuccess(pending);
assert.equal(element('.success-title').textContent,'申請已收到');
assert.equal(element('.success-desc').textContent,'您可以關閉頁面，後續由工會審核。\n設定成功說明\n申請編號：42');
renderRegistrationSuccess({...pending,status:'expired',identity_status:'expired'});
assert(!element('.success-desc').textContent.includes('設定成功說明'));
console.log('registration receipt rendering passed');
'''
    result = subprocess.run(["node"], input=script, capture_output=True, text=True,
                            encoding="utf-8", timeout=10, check=True)
    assert "registration receipt rendering passed" in result.stdout


def test_default_service_registration_menu_uses_the_canonical_identity_entry() -> None:
    source = (ROOT / "config" / "line_menu.json").read_text(encoding="utf-8")
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")

    assert (
        '"id": "service_registration"' in source
        or '"id":"service_registration"' in source
        or '"id": "client_service"' in source
        or '"id":"client_service"' in source
    )
    assert ('"uri": "?entry=gateway"' in source or '"uri":"?entry=gateway"' in source or '"uri": "?entry=registration"' in source or '"uri":"?entry=registration"' in source)
    assert '"uri": "?target=registration"' not in source and '"uri":"?target=registration"' not in source
    assert '"uri_source": "liff"' in source or '"uri_source":"liff"' in source
    assert 'return entry === "registration";' in identity


def test_registration_page_uses_only_canonical_identity_endpoints() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in source
    assert "/api/v1/line/identity/registration/preview" in source
    assert "/api/v1/line/identity/registration/apply" in source
    assert "function canUseDevelopmentIdentityFallback(error)" not in source
    assert 'development_line_user_id: ""' in source
    assert "developmentLineUserId" not in source
    assert "/api/v1/line/identity/registration/status" in source
    assert "errorCode === 'registration_conflict'" in source
    assert "/api/line/register" not in source
    assert "/api/line/config" not in source


def test_registration_form_normalizes_fullwidth_taiwan_ids_and_keeps_identity_optional() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")
    validation_function = "function normalizeTaiwanId(value)" + source.split(
        "function normalizeTaiwanId(value)", 1
    )[1].split("function validateRegistrationForm()", 1)[0]

    def id_is_valid(value: str) -> bool:
        result = subprocess.run(
            ["node", "-e", f"{validation_function}\nconsole.log(isValidTaiwanId({json.dumps(value)}));"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "true"

    assert id_is_valid("A123456789")
    assert id_is_valid("Ａ１２３４５６７８９")
    assert id_is_valid("ａ１２３４５６７８９")
    assert not id_is_valid("A123456788")
    assert "請輸入有效身分證字號" in source
    assert "startsWith('O')" not in source
    assert 'placeholder="身分證，例如: A123456789"' in source
    assert 'id="id_number" required' not in source
    assert 'class="form-label required">身分證字號</label>' not in source
    assert "請填寫身分證字號。" not in source
    assert "新竹市市民身分證" not in source

    for field_id in ("name", "phone", "address", "expected_date", "service_days"):
        assert f'id="{field_id}" required' in source
    assert 'class="form-label required">服務時間內是否有其他大寶/寶寶</label>' in source
    assert 'data-survey="服務時間內是否有其他寶寶" required' in source
    assert "請填寫服務時間內是否有其他大寶或寶寶" in source
    assert 'class="form-label required">是否需要下廚</label>' in source
    assert 'name="needs_cooking" value="需要下廚"' in source
    assert 'name="needs_cooking" value="不需要下廚"' in source
    assert "input[name=\"needs_cooking\"]:checked" in source
    assert "請選擇是否需要下廚。" in source
    assert "'needs_cooking': '是否需要下廚：'" in source
    assert ".checkbox-item > label.required::after" in source
    for agreement in ("agree1", "agree2", "agree3"):
        assert f'<input type="checkbox" id="{agreement}" required><label for="{agreement}" class="required">' in source


def test_registration_bank_code_help_links_to_the_official_lookup_without_changing_survey_key() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert 'class="form-label required">補助款退款銀行代號加分行</label>' in source
    assert 'id="refund_bank_code" inputmode="numeric" maxlength="7"' in source
    assert 'data-survey="補助款退款:銀行代號+分行代號"' in source
    assert 'class="form-label required">銀行帳號</label>' in source
    assert 'id="refund_bank_account" data-survey="銀行帳號" required' in source
    assert "請輸入 7 位數字" in source
    assert "請輸入補助款退款銀行代號加分行。" in source
    assert "請輸入銀行帳號。" in source
    assert "!/^\\d{7}$/.test(refundBankCodeValue)" in source
    assert "https://www.fisc.com.tw/TC/Service?CAID=51254999-5d15-4ddf-8e54-4b2cdb2a8399" in source


def test_registration_refund_confirmation_requires_visible_reading_guidance() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert "點選「已確實詳閱退費原則」" in source
    assert "讀完後按「已閱讀並同意」，即可勾選並送出。" in source
    assert "if (!refundPolicyAccepted)" in source
    assert "refundPolicyAccepted = true;" in source
    assert "if (!agree1.checked || !refundPolicyAccepted)" in source


def test_registration_initialization_error_disables_every_form_control() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")
    failure_source = source.split("function showInitializationError(error)", 1)[1].split(
        'document.addEventListener("DOMContentLoaded"', 1
    )[0]

    assert "status.textContent = error.message || '頁面初始化失敗，請回到 LINE 重新開啟。';" in failure_source
    assert (
        "#registerForm input, #registerForm select, #registerForm textarea, "
        "#registerForm button"
    ) in failure_source
    assert "control => control.disabled = true" in failure_source


def test_service_days_rejects_fractional_input_without_truncating_or_changing_the_previous_integer():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    guard = "function setupServiceDaysIntegerInput()" + source.split(
        "function setupServiceDaysIntegerInput()", 1
    )[1].split("function setupIdNumberAutoUppercase()", 1)[0]
    script = r'''
const assert = require('node:assert/strict');
const handlers = new Map();
const input = {value: '30', validity: {badInput: false}, addEventListener: (kind, fn) => handlers.set(kind, fn)};
const document = {getElementById: () => input};
let error = '';
function setFieldError(control, message) {assert.equal(control, input); error = message;}
''' + guard + r'''
setupServiceDaysIntegerInput();
for (const text of ['.', '1.5', ',', '1e2', '-1']) {
  let prevented = false;
  handlers.get('beforeinput')({data: text, preventDefault(){prevented = true;}});
  assert.equal(prevented, true);
  assert.equal(input.value, '30');
}
for (const text of ['1.5', '1,5', '1e2', '-1']) {
  let prevented = false;
  handlers.get('paste')({clipboardData: {getData: () => text}, preventDefault(){prevented = true;}});
  assert.equal(prevented, true);
  assert.equal(input.value, '30');
}
input.value = '1.5'; handlers.get('input')();
assert.equal(input.value, '30'); assert.match(error, /整數/);
input.value = '31'; handlers.get('input')();
assert.equal(input.value, '31'); assert.equal(error, '');
input.value = ''; input.validity.badInput = true; handlers.get('input')();
assert.equal(input.value, '31'); assert.match(error, /整數/);
input.validity.badInput = false; input.value = ''; handlers.get('input')();
assert.equal(input.value, ''); assert.equal(error, '');
let prevented = false;
handlers.get('paste')({clipboardData: {getData: () => '45'}, preventDefault(){prevented = true;}});
assert.equal(prevented, false);
console.log('integer service day input contract passed');
'''
    result = subprocess.run(["node"], input=script, capture_output=True, text=True,
                            encoding="utf-8", timeout=10, check=True)
    assert "integer service day input contract passed" in result.stdout


def test_registration_form_requires_closed_single_or_twins_choice_shared_by_both_forms() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert "胎數 (第一胎、第二胎...)" not in source
    assert 'placeholder="例如: 第一胎"' not in source
    assert 'data-survey="特殊計費:胎數"' not in source
    assert 'id="baby_info"' not in source
    assert "請填寫寶寶資訊" not in source
    assert 'id="line_id"' not in source
    assert "尚未設定 LINE ID" not in source
    assert "'baby_info'" not in source.split("const nonCitizenFields = [", 1)[1].split("]", 1)[0]
    assert "'line_id'" not in source.split("const nonCitizenFields = [", 1)[1].split("]", 1)[0]
    assert "payload.baby_info = surveyDetails['特殊計費:胎數'];" in source
    non_citizen_section = source.split('<section id="nonCitizenServiceFields"', 1)[1].split("</section>", 1)[0]
    assert 'name="multi_birth_count"' not in non_citizen_section
    after_non_citizen = source.split("</section>", 1)[1]
    assert 'name="multi_birth_count"' in after_non_citizen
    assert 'id="multi_birth_single"' in after_non_citizen
    assert 'value="單胞胎"' in after_non_citizen
    assert 'value="雙胞胎"' in after_non_citizen
    assert '<label for="multi_birth_single">單胞胎<span id="registrationSingleRate">' in after_non_citizen
    assert '<label for="multi_birth_twins">雙胞胎<span id="registrationTwinsRate">' in after_non_citizen
    assert "請選擇胎數（單胞胎／雙胞胎）。" in source
    assert "'multi_birth_count': '特殊計費:胎數'" in source
    assert "'multi_birth_count'" in source.split("const radioGroups = [", 1)[1].split("]", 1)[0]

    validation_fn = "function validateRegistrationForm()" + source.split(
        "function validateRegistrationForm()", 1
    )[1].split('document.getElementById("registerForm")', 1)[0]
    helper_fn = "function normalizePhone(value)" + (
        source.split("function normalizePhone(value)", 1)[1].split("function validateRegistrationForm()", 1)[0]
    )
    script = r'''
const assert = require('node:assert/strict');
let birthSelected = null;
const byId = new Map();
function makeControl(id, value='') {
  const err = { textContent: '', classList: { toggle() {}, remove() {} } };
  const ctrl = {
    id, value, checked: false,
    classList: { toggle() {}, remove() {} },
    scrollIntoView() {}, focus() {},
    closest() { return { querySelector(sel) { return sel === '.field-error' ? err : { textContent: id }; }, appendChild() {} }; }
  };
  byId.set(id, ctrl);
  return ctrl;
}
['name','id_number','birth_date','phone','tel','email','city','zip_code','address','expected_date','service_days','refund_bank_code','refund_bank_account','multi_birth_single','needs_cooking_yes'].forEach(id => makeControl(id));
['service_start_date','service_time','residence_type','delivery_type','service_type','notes','gender','city'].forEach(id => makeControl(id, '已填寫'));
byId.get('service_time').value = '09:00-17:00 (8小時)';
byId.get('birth_date').value = '1990-01-01';
byId.get('name').value = '測試';
byId.get('phone').value = '0912345678';
byId.get('email').value = 'ok@example.com';
byId.get('address').value = '新竹市';
byId.get('expected_date').value = new Date().toISOString().slice(0, 10);
byId.get('service_days').value = '10';
byId.get('refund_bank_code').value = '0000000';
byId.get('refund_bank_account').value = '00000001';
const passbookCover = makeControl('passbook_cover'); passbookCover.files = [{ size: 1024, type: 'image/png' }];
const agree1 = makeControl('agree1'); agree1.checked = true;
const agree2 = makeControl('agree2'); agree2.checked = true;
const agree3 = makeControl('agree3'); agree3.checked = true;
const otherBabies = makeControl('other_babies', '無');
const ingredientPurchase = makeControl('ingredient_purchase', '自行準備');
const needsCooking = makeControl('needs_cooking_checked', '需要下廚'); needsCooking.checked = true;
let refundPolicyAccepted = true;
let uploadedPassbookFile = { size: 1024 };
let uploadedPassbookImageId = 'pbk_synthetic';
let isNonCitizen = false;
let nonCitizenFields = ['service_start_date', 'service_time', 'residence_type', 'delivery_type', 'service_type', 'notes'];
let runtimePage = null;
const document = {
  getElementById: id => byId.get(id),
  querySelector(sel) {
    if (sel === 'input[name="multi_birth_count"]:checked') return birthSelected;
    if (sel === 'input[name="needs_cooking"]:checked') return needsCooking;
    if (sel === '[data-survey="服務時間內是否有其他寶寶"]') return otherBabies;
    return null;
  },
  querySelectorAll() { return []; },
  createElement() { return { className: '', textContent: '', classList: { toggle() {} } }; }
};
''' + helper_fn + "\n" + validation_fn + r'''
for (const nonCitizenFlag of [false, true]) {
  isNonCitizen = nonCitizenFlag;
  birthSelected = null;
  const invalid = validateRegistrationForm();
  assert.equal(invalid.ok, false);
  assert.equal(invalid.message, '請選擇胎數（單胞胎／雙胞胎）。');
  birthSelected = { value: nonCitizenFlag ? '雙胞胎' : '單胞胎', checked: true };
  const valid = validateRegistrationForm();
  assert.equal(valid.ok, true);
  for (const answer of ['', '其他']) {
    ingredientPurchase.value = answer;
    const invalidPurchase = validateRegistrationForm();
    assert.equal(invalidPurchase.ok, false);
    assert.equal(invalidPurchase.message, '請選擇代購食材方式。');
  }
  for (const answer of ['需月嫂代購(實報實銷)', '自行準備']) {
    ingredientPurchase.value = answer;
    assert.equal(validateRegistrationForm().ok, true);
  }
}
console.log('multi_birth_count validation contract passed');
'''
    result = subprocess.run(["node"], input=script, capture_output=True, text=True,
                            encoding="utf-8", timeout=10, check=True)
    assert "multi_birth_count validation contract passed" in result.stdout

    apply_fn = "function applySystemField(field, inputId)" + source.split(
        "function applySystemField(field, inputId)", 1
    )[1].split("function renderCustomFields(", 1)[0]
    runtime_script = apply_fn + r'''
let isNonCitizen = true;
const document = { getElementById: () => null };
applySystemField({ id: 'baby_info', label: '寶寶資訊', required: true, placeholder: 'ignored' }, 'baby_info');
applySystemField({ id: 'line_id', label: 'LINE ID', required: true, placeholder: 'ignored' }, 'line_id');
console.log('missing dom system field safely skipped');
'''
    runtime_res = subprocess.run(["node"], input=runtime_script, capture_output=True, text=True,
                                 encoding="utf-8", timeout=10, check=True)
    assert "missing dom system field safely skipped" in runtime_res.stdout


def test_multi_select_survey_labels_display_multi_choice_hint() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")
    groups = re.findall(
        r'<div class="form-group">\s*<label class="form-label[^"]*">([^<]+)</label>(.*?)</div>\s*(?=<div class="form-group">|<div id="customFieldsSection"|<!-- Section)',
        source,
        re.S,
    )
    multi_labels = [label for label, body in groups if "data-survey-array" in body]
    assert multi_labels == [
        "洗澡水準備 (可複選)",
        "可以接受中藥補品 (可複選)",
        "料理用油 (可接受種類) (可複選)",
        "烹煮與加熱工具 (請勾選家中有的設備) (可複選)",
    ]
    assert '<label class="form-label">確認條款</label>' in source

    render_fn = "function renderCustomFields(fields)" + source.split(
        "function renderCustomFields(fields)", 1
    )[1].split("function collectCustomFields()", 1)[0]
    script = r'''
const assert = require('node:assert/strict');
const container = { children: [], replaceChildren() { this.children = []; }, appendChild(node) { this.children.push(node); } };
const section = { style: { display: 'none' } };
const title = { textContent: '' };
const makeElement = tag => ({
    tag,
    className: '',
    textContent: '',
    type: '',
    value: '',
    id: '',
    htmlFor: '',
    required: false,
    placeholder: '',
    dataset: {},
    children: [],
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); },
});
const document = {
    getElementById(id) {
        if (id === 'customFieldsSection') return section;
        if (id === 'customFieldsContainer') return container;
        if (id === 'customFieldsTitle') return title;
        return null;
    },
    createElement: makeElement,
};
let runtimePage = { content: {} };
''' + render_fn + r'''
renderCustomFields([
    { id: 'multi_new', label: '其他複選需求', type: 'multiple_choice', required: false, order: 1, options: [{ value: 'A', label: 'A' }] },
    { id: 'multi_existing', label: '已有標註 (可複選)', type: 'multiple_choice', required: false, order: 2, options: [{ value: 'B', label: 'B' }] },
    { id: 'single_one', label: '單選需求', type: 'single_choice', required: false, order: 3, options: [{ value: 'C', label: 'C' }] },
]);
assert.equal(container.children[0].children[0].textContent, '其他複選需求 (可複選)');
assert.equal(container.children[1].children[0].textContent, '已有標註 (可複選)');
assert.equal(container.children[2].children[0].textContent, '單選需求');
console.log('custom field multi-select label contract passed');
'''
    result = subprocess.run(["node"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)
    assert "custom field multi-select label contract passed" in result.stdout
