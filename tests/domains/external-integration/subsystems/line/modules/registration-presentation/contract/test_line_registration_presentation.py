"""
File: test_line_registration_presentation.py
Description: 驗證 LINE LIFF 客戶登記頁呈現、胎數必填與預覽送出契約。
"""

import json
from pathlib import Path
import re
import subprocess

from domains.case_import.non_citizen_registration import LIFF_SERVICE_TIME_OPTIONS


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_non_citizen_service_choices_match_manual_case_form():
    liff = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    manual = (ROOT / "ui_react/src/components/RegistrationApplications.tsx").read_text(encoding="utf-8")

    for field in ("service_type", "delivery_type", "residence_type", "service_time"):
        liff_select = liff.split(f'id="{field}">', 1)[1].split("</select>", 1)[0]
        manual_select = manual.split(f"value={{manualForm.{field}}}", 1)[1].split("</select>", 1)[0]
        assert re.findall(r'<option value="([^"]+)">', liff_select) == re.findall(
            r'<option value="([^"]+)">', manual_select
        )
    assert tuple(re.findall(
        r'<option value="([^"]+)">', liff.split('id="service_time">', 1)[1].split("</select>", 1)[0]
    )) == LIFF_SERVICE_TIME_OPTIONS
    assert 'type="time"' not in liff


def test_optional_holiday_preference_is_in_registration_fees_section():
    source = (ROOT / "line/static/register.html").read_text(encoding="utf-8")
    before, fees = source.split("💰 5. 費用與同意條款", 1)
    assert 'name="holiday_double_pay"' not in before
    options = re.findall(r'<input[^>]*name="holiday_double_pay"[^>]*>', fees)
    assert [re.search(r'value="([^"]+)"', option)[1] for option in options] == ["是", "否"]
    assert all("required" not in option for option in options)


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
const outcomes = {
  approving: '核准建檔或清除確認中，請查詢原申請。',
  approved: '申請已核准，待審問卷內容已清除。',
  rejected: '申請已拒絕，問卷內容已清除。',
  expired: '申請已到期，問卷內容已清除。',
};
for(const [status, message] of Object.entries(outcomes)){
  renderRegistrationSuccess({...pending,identity_status:status,client_id:10,beclass_record_id:11});
  assert.equal(element('.success-desc').textContent,message+'\n申請編號：42');
  assert(!element('.success-desc').textContent.includes('待工會核准'));
  assert(!element('.success-desc').textContent.includes('10'));
}
for(const invalid of [null,{}, {...pending,registration_id:0},{...pending,registration_id:'42'},
  {...pending,identity_status:null},{...pending,identity_status:'unrecognized'},
  {...pending,identity_status:'bound'},{...pending,identity_status:'existing'},
  {...pending,client_id:10},{...pending,beclass_record_id:11}]){
  element('successCard').style.display='none';element('registerForm').style.display='block';
  assert.throws(()=>renderRegistrationSuccess(invalid),/讀回不完整/);
  assert.equal(element('successCard').style.display,'none');
  assert.equal(element('registerForm').style.display,'block');
}
runtimePage={success_title:'設定成功標題',success_description:'設定成功說明'};
renderRegistrationSuccess(pending);
assert.equal(element('.success-title').textContent,'申請已送出');
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
