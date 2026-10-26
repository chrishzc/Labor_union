"""Verify the LINE LIFF customer registration presentation contract."""

import json
from pathlib import Path
import subprocess


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_runtime_copy_describes_review_instead_of_promising_matching():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    runtime_function = "function applyRuntime(runtime)" + source.split("function applyRuntime(runtime)", 1)[1].split("function applySystemField", 1)[0]
    settings = json.loads((ROOT / "config/liff_settings.json").read_text(encoding="utf-8"))
    runtime = {"theme": settings["theme"], "page": settings["pages"]["registration"]}
    runtime["page"].update(subtitle="測試副標題", submit_button="設定送出文字", success_title="設定成功標題")
    script = r"""
const nodes = new Map();
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


def test_success_readback_requires_a_real_receipt_and_keeps_existing_registration_outcomes():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    renderer = "function renderRegistrationSuccess(receipt)" + source.split(
        "function renderRegistrationSuccess(receipt)", 1
    )[1].split("function requireRegistrationPreview", 1)[0]
    script = r'''
const assert = require('node:assert/strict');
const nodes = new Map();
const element = id => {if(!nodes.has(id))nodes.set(id,{style:{display:'block'},textContent:''});return nodes.get(id)};
const document={getElementById:element,querySelector:element};
let runtimePage = null;
''' + renderer + r'''
const pending={registration_id:42,identity_status:'pending_approval',client_id:null,beclass_record_id:null};
renderRegistrationSuccess(pending);
assert.equal(element('.success-desc').textContent,'申請已送出，待工會核准。\n申請編號：42');
assert.equal(element('.success-title').textContent,'申請已送出');
assert.equal(element('successCard').style.display,'block');
assert.equal(element('registerForm').style.display,'none');
for(const status of ['bound','existing']){
  renderRegistrationSuccess({...pending,identity_status:status,client_id:10,beclass_record_id:11});
  assert.equal(element('.success-desc').textContent,'登記資料已提交。\n申請編號：42');
  assert(!element('.success-desc').textContent.includes('待工會核准'));
  assert(!element('.success-desc').textContent.includes('10'));
}
for(const invalid of [null,{}, {...pending,registration_id:0},{...pending,registration_id:'42'},
  {...pending,identity_status:null},{...pending,identity_status:'unrecognized'},
  {...pending,client_id:10},{...pending,beclass_record_id:11}]){
  element('successCard').style.display='none';element('registerForm').style.display='block';
  assert.throws(()=>renderRegistrationSuccess(invalid),/讀回不完整/);
  assert.equal(element('successCard').style.display,'none');
  assert.equal(element('registerForm').style.display,'block');
}
runtimePage={success_title:'設定成功標題',success_description:'設定成功說明'};
renderRegistrationSuccess(pending);
assert.equal(element('.success-title').textContent,'設定成功標題');
assert.equal(element('.success-desc').textContent,'設定成功說明\n申請已送出，待工會核准。\n申請編號：42');
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
    assert '"uri": "?entry=registration"' in source or '"uri":"?entry=registration"' in source
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
    assert "const code = detail?.code || detail?.error?.code || result?.error?.code;" in source
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

    assert "請先點選「已確實詳閱退費原則」閱讀內容" in source
    assert "並在彈窗按下「已閱讀並同意」後，才能完成勾選及送出。" in source
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
