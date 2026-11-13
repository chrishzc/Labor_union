"""Execute the current binding page against public, isolated response fixtures."""

import json
from pathlib import Path
import subprocess

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())


def _submit(receipt, endpoint='staff', *, preview_status='matched', apply_http=200, detail=None):
    page = (ROOT / 'line/static/identity.html').read_text(encoding='utf-8')
    source = page.split('<script>', 1)[1].split('</script>', 1)[0]
    source = source.split('document.getElementById("reauthenticate").addEventListener', 1)[0]
    script = r'''
const vm = require('node:vm');
const settings = SETTINGS, elements = new Map(), calls = [];
const get = id => { if (!elements.has(id)) elements.set(id, {
  textContent:'', hidden:true, disabled:false, querySelector:()=>({focus(){}})
}); return elements.get(id); };
const context = vm.createContext({document:{getElementById:get}, console,
  FormData:class { entries(){return [['name','公版測試']][Symbol.iterator]();} },
  fetch:async (url) => {calls.push(url);return url.endsWith('/preview')
    ? {ok:true,json:async()=>({data:{status:settings.preview_status, expected_version:1, preview_fingerprint:'a'.repeat(64), candidate:{currently_bound:false}}})}
    : {ok:settings.apply_http===200,status:settings.apply_http,json:async()=>({data:settings.receipt, detail:settings.detail})};}
});
vm.runInContext(SOURCE, context);
context.args = [{preventDefault(){},target:{}},
  vm.runInContext('Object.values(definitions)', context).find(d=>d.endpoint===settings.endpoint),
  {disabled:false},{textContent:'',hidden:true}];
vm.runInContext('submitForm(...args)',context).then(()=>process.stdout.write(JSON.stringify({
  message:get('message').textContent, help:!get('binding-help').hidden,
  result:context.args[3].textContent, calls, reauthenticate:!get('reauthenticate').hidden,
  staff_mismatch:!get('staff-binding-mismatch').hidden, form_hidden:!!context.args[0].target.hidden
}))).catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('SETTINGS', json.dumps(dict(receipt=receipt, endpoint=endpoint, preview_status=preview_status, apply_http=apply_http, detail=detail))).replace('SOURCE', json.dumps(source))
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
    assert result['help']


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


def test_customer_review_receipt_describes_retaining_previous_binding():
    result = _submit({
        'status': 'pending_review', 'review_request_id': 7,
        'receipt_identity': 'public', 'preview_fingerprint': 'a' * 64,
    }, 'customer', preview_status='requires_review')
    assert result['message'] == '重新綁定申請已送出'
    assert result['result'] == '審核編號：7。請等待工會確認。核准前會保留原綁定。'


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
