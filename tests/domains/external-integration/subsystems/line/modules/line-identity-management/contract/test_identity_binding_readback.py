"""Execute the current binding page against public, isolated response fixtures."""

import json
from pathlib import Path
import subprocess

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())


def _submit(receipt, endpoint='staff', *, preview_status='matched', apply_http=200, detail=None, recovered=None):
    page = (ROOT / 'line/static/identity.html').read_text(encoding='utf-8')
    source = page.split('<script>', 1)[1].split('</script>', 1)[0]
    source = source.split('document.getElementById("reauthenticate").addEventListener', 1)[0]
    script = r'''
const vm = require('node:vm');
const settings = SETTINGS, elements = new Map(), calls = [];
const get = id => { if (!elements.has(id)) elements.set(id, {
  textContent:'', hidden:true, disabled:false, querySelector:()=>({focus(){}})
}); return elements.get(id); };

const session = new Map(), bodies = [];
const context = vm.createContext({document:{getElementById:get}, console, AbortController, setTimeout, clearTimeout,
  crypto:{randomUUID:()=> '065a0b1e-2005-470b-a6d4-83159d3f22f7'},
  sessionStorage:{getItem:k=>session.get(k), setItem:(k,v)=>session.set(k,v), removeItem:k=>session.delete(k)},
  FormData:class { entries(){return [['name','公版測試']][Symbol.iterator]();} },
  fetch:async (url, options) => {
    calls.push(url);
    bodies.push(JSON.parse(options.body));
    if (url.endsWith('/binding-result')) return {ok:true,json:async()=>({data:settings.recovered})};
    return url.endsWith('/preview')
    ? {ok:true,json:async()=>({data:{status:settings.preview_status, expected_version:1, preview_fingerprint:'a'.repeat(64), candidate:{currently_bound:false}}})}
    : {ok:settings.apply_http===200,status:settings.apply_http,json:async()=>({data:settings.receipt, detail:settings.detail})};}
});
vm.runInContext(SOURCE, context);
context.args = [{preventDefault(){},target:{}},
  vm.runInContext('Object.values(definitions)', context).find(d=>d.endpoint===settings.endpoint),
  {disabled:false},{textContent:'',hidden:true}];

(async () => {
  vm.runInContext('flowId = "receipt-flow"; idToken = "fixture-token"', context);
  await vm.runInContext('submitForm(...args)', context);
  const stored = [...session.values()].map(value=>JSON.parse(value));
  const lookupAfterApply = !get('binding-result-lookup').hidden;
  if (settings.recovered) {
    vm.runInContext('pendingBinding = null; bindingResultUnknown = false;', context);
    await vm.runInContext('recoverPendingBinding(args[1])', context);
  }
  process.stdout.write(JSON.stringify({
  message:get('message').textContent, help:!get('binding-help').hidden,
  result:context.args[3].textContent, calls, reauthenticate:!get('reauthenticate').hidden,
    staff_mismatch:!get('staff-binding-mismatch').hidden, form_hidden:!!context.args[0].target.hidden,
    lookup_after_apply:lookupAfterApply, lookup:!get('binding-result-lookup').hidden,
    stored, remaining:session.size, bodies,
  }));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('SETTINGS', json.dumps(dict(receipt=receipt, endpoint=endpoint, preview_status=preview_status, apply_http=apply_http, detail=detail, recovered=recovered))).replace('SOURCE', json.dumps(source))
    result = subprocess.run(['node'], input=script, text=True, encoding='utf-8', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('receipt', [None, {}, {'status':'unknown'},
    {'status':'bound'}, {'status':'pending_review', 'review_request_id':7},
    {'status':'bound', 'receipt_identity':'public', 'preview_fingerprint':'b'*64}])
def test_incomplete_or_mismatched_receipt_never_claims_binding_success(receipt):
    result = _submit(receipt)
    assert '成功' not in result['message']
    assert result['result'] == ''
    assert result['lookup']


@pytest.mark.parametrize('endpoint,role,menu', [('staff','月嫂','月嫂選單'), ('admin','工會人員','工會選單')])
@pytest.mark.parametrize('status', ['bound', 'existing'])
def test_verified_binding_receipt_uses_role_and_distinguishes_new_and_existing(endpoint, role, menu, status):
    result = _submit({'status':status, 'receipt_identity':'public', 'preview_fingerprint':'a'*64}, endpoint)
    if status == 'bound':
        assert result['message'] == f'{role}身分綁定成功'
        assert f'系統會稍後更新{menu}' in result['result']
        assert ('切換月嫂' in result['result']) is (endpoint == 'staff')
    else:
        assert result['message'] == f'{role}身分已完成綁定'
        assert '可直接返回 LINE 使用' in result['result']
        assert '更新' not in result['result']
    assert not result['help']


def test_obsolete_customer_review_receipt_does_not_claim_success():
    result = _submit({
        'status': 'pending_review', 'review_request_id': 7,
        'receipt_identity': 'public', 'preview_fingerprint': 'a' * 64,
    }, 'customer', preview_status='requires_review')
    assert '綁定結果讀回不完整' in result['message']
    assert result['result'] == ''


def test_staff_mismatch_offers_readable_help_without_automatic_contact():
    result = _submit(None, preview_status='not_found', apply_http=404, detail={'error': {
        'code': 'line_identity_match_not_found',
        'message': '找不到匹配資訊，請檢查輸入內容是否正確或聯繫工會人員',
    }})
    assert result['help']
    assert result['staff_mismatch']
    assert result['form_hidden']
    assert len(result['calls']) == 2
    assert result['message'] == ''


def test_missing_flow_is_not_shown_as_a_staff_data_mismatch():
    result = _submit(None, apply_http=404, detail={'error': {
        'code': 'line_identity_match_not_found',
        'message': '找不到 LINE 身分驗證流程',
    }})
    assert not result['staff_mismatch']
    assert not result['form_hidden']


def test_expired_flow_and_expired_login_have_different_recovery_copy():
    expired = _submit(None, apply_http=410, detail='LINE identity flow has expired')
    assert expired['message'] == '綁定連結已失效，請返回 LINE 重新開啟綁定頁面。'
    assert not expired['reauthenticate']
    login = _submit(None, apply_http=401, detail={
        'code': 'liff_id_token_invalid',
        'message': 'LINE 登入狀態已失效或與此 LIFF 不一致，請重新登入 LINE。',
    })
    assert '重新登入 LINE' in login['message']
    assert login['reauthenticate']


@pytest.mark.parametrize("endpoint,purpose", [
    ("customer", "customer_binding"), ("staff", "staff_verification"), ("admin", "admin_binding"),
])
def test_unknown_binding_reads_original_attempt_before_any_new_apply(endpoint, purpose):
    result = _submit(None, endpoint, apply_http=503,
                     recovered={"status": "bound", "receipt_identity": "line-binding:fixture:1"})
    assert result["lookup_after_apply"]
    assert [path.rsplit("/", 1)[-1] for path in result["calls"]] == ["preview", "apply", "binding-result"]
    attempt = {"flow_id": "receipt-flow", "purpose": purpose, "attempt_id": result["bodies"][1]["attempt_id"]}
    assert result["stored"] == [attempt]
    assert result["bodies"][2] == {**attempt, "line_id_token": "fixture-token"}
    assert "綁定成功" in result["message"]
    assert result["remaining"] == 0 and not result["lookup"]


def test_missing_original_binding_receipt_keeps_attempt_unconfirmed():
    result = _submit(None, "staff", apply_http=503, recovered={"status": "unconfirmed"})
    assert "尚未確認" in result["message"]
    assert result["remaining"] == 1 and result["lookup"]
    assert result["calls"][-1].endswith("/binding-result")
    assert sum(url.endswith("/apply") for url in result["calls"]) == 1


@pytest.mark.parametrize("detail,lookup", [
    ({"error": {"code": "line_identity_binding_conflict", "message": "此月嫂已綁定其他 LINE 帳號"}}, False),
    ("unexpected_service_conflict", True),
])
def test_known_binding_conflict_releases_form_but_unknown_conflict_retains_lookup(detail, lookup):
    result = _submit(None, "staff", apply_http=409, detail=detail)
    assert result["lookup"] is lookup
    assert result["remaining"] == int(lookup)
    assert result["help"] is (not lookup)
