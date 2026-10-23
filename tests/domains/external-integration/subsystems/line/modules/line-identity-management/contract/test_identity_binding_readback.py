"""Execute the current binding page against public, isolated response fixtures."""

import json
from pathlib import Path
import subprocess

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())


def _submit(receipt, endpoint='staff', *, preview_status='matched', apply_ok=True):
    page = (ROOT / 'line/static/identity.html').read_text(encoding='utf-8')
    source = page.split('<script>', 1)[1].split('</script>', 1)[0]
    source = source.split('document.getElementById("reauthenticate").addEventListener', 1)[0]
    script = r'''
const vm = require('node:vm');
const settings = SETTINGS, elements = new Map(), calls = [];
const get = id => { if (!elements.has(id)) elements.set(id, {textContent:'', hidden:true, disabled:false}); return elements.get(id); };
const context = vm.createContext({document:{getElementById:get}, console,
  FormData:class { entries(){return [['name','公版測試']][Symbol.iterator]();} },
  fetch:async (url) => {calls.push(url);return url.endsWith('/preview')
    ? {ok:true,json:async()=>({data:{status:settings.preview_status, expected_version:1, preview_fingerprint:'a'.repeat(64), candidate:{currently_bound:false}}})}
    : {ok:settings.apply_ok,json:async()=>({data:settings.receipt, detail:'資料無法核對，請確認輸入內容。'})};}
});
vm.runInContext(SOURCE, context);
context.args = [{preventDefault(){},target:{}},{endpoint:settings.endpoint},{disabled:false},{textContent:'',hidden:true},{hidden:true}];
vm.runInContext('submitForm(...args)',context).then(()=>process.stdout.write(JSON.stringify({
  message:get('message').textContent, help:!get('binding-help').hidden,
  result:context.args[3].textContent, calls
}))).catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('SETTINGS', json.dumps(dict(receipt=receipt, endpoint=endpoint, preview_status=preview_status, apply_ok=apply_ok))).replace('SOURCE', json.dumps(source))
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


@pytest.mark.parametrize('endpoint,status', [('staff','bound'), ('staff','existing'), ('admin','bound'), ('admin','existing')])
def test_verified_binding_receipt_reports_delayed_menu_update(endpoint, status):
    result = _submit({'status':status, 'receipt_identity':'public', 'preview_fingerprint':'a'*64}, endpoint)
    assert '綁定' in result['message']
    assert '專屬選單將稍後更新' in result['result']
    assert not result['help']


def test_failed_binding_offers_explicit_help_without_automatic_contact():
    result = _submit(None, apply_ok=False)
    assert result['help']
    assert len(result['calls']) == 2
    assert '成功' not in result['message']
