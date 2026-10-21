"""Opt-in: isolated existing image + read-only proxy patch, never a real Tunnel."""
import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

HERE = Path(__file__).parent
ROOT = HERE.parents[6]


@pytest.mark.skipif(os.getenv('NAS_TUNNEL_DOCKER_TEST') != '1', reason='explicit local disposable Docker opt-in')
def test_two_origin_networks_retained_login_and_line_worker_last():
    spec = importlib.util.spec_from_file_location('nas_tunnel_lifecycle', HERE / 'test_nas_compose_lifecycle.py')
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    docker = helpers.LocalDocker()
    directory = ROOT / 'scratch' / ('nas-tunnel-test-' + uuid4().hex[:10])
    directory.mkdir()
    source = helpers.IsolatedProject(docker, 'lu-nas-life-tunnel-' + uuid4().hex[:10], directory / 'project')
    source.values.update(LINE_CHANNEL_SECRET='fixture-line-secret-never-real',
                         LINE_CHANNEL_ACCESS_TOKEN='fixture-provider-token-never-real',
                         LINE_LOGIN_CHANNEL_ID='1234567890', LINE_LIFF_ID='1234567890-fixture')
    source.write_env()
    # No internet on any test network; even accidental provider effects cannot leave.
    override = directory / 'no-egress.yaml'
    override.write_text(yaml.safe_dump({'networks': {name: {'internal': True}
                        for name in ['management-egress','line-egress','tunnel-egress']}}), encoding='utf-8')
    phases = []

    def passed(name):
        phases.append(name)
        print('PASS ' + name, flush=True)

    def origin(peer, network, address=None):
        code = r'''
import base64,hashlib,hmac,json,os,ssl,struct,time,urllib.request,urllib.error
from pathlib import Path
import sys
peer=sys.argv[1]
fixture=None
if peer!='line':
    fixture=json.loads(Path('/fixture/.nas-lifecycle-fixture.json').read_text())
    # The fixture is deliberately root-only; load it, then use an unprivileged client.
    os.setgroups([]); os.setgid(1000); os.setuid(1000)
context=ssl.create_default_context(cafile='/run/private-ca/ca.pem')
def request(path,expected=200,token=None,body=None,signature=None):
    host='line.example.invalid' if peer=='line' else ('lifecycle.invalid:19443' if peer=='lan' else 'admin.example.invalid')
    service='line-api' if peer=='line' else 'management-api'
    headers={'Host':host,'Origin':'https://'+host,'X-Forwarded-Proto':'https','X-Forwarded-For':'203.0.113.8',
             'Cf-Access-Authenticated-User-Email':'root@example.invalid','Cf-Access-Jwt-Assertion':'forged-not-a-login'}
    if token: headers['Authorization']='Bearer '+token
    if body is not None: headers['Content-Type']='application/json'
    if signature is not None: headers['X-Line-Signature']=signature
    q=urllib.request.Request('https://'+service+':8443'+path,headers=headers,data=body)
    try: response=urllib.request.urlopen(q,context=context,timeout=12)
    except urllib.error.HTTPError as error: response=error
    with response:
        assert response.status==expected, 'unexpected HTTP status '+str(response.status)
        data=response.read()
        return json.loads(data) if response.headers.get_content_type()=='application/json' else data
if peer=='line':
    request('/health')
    request('/admin/',404)
    request('/api/v1/admin/accounts',404)
    payload=json.dumps({'destination':'fixture','events':[]},separators=(',',':')).encode()
    request('/webhook/line',401,body=payload,signature='invalid-signature')
    signature=base64.b64encode(hmac.new(b'fixture-line-secret-never-real',payload,hashlib.sha256).digest()).decode()
    result=request('/webhook/line',body=payload,signature=signature)
    assert result['status']=='ok'
else:
    request('/health')
    request('/api/v1/admin/auth/me',401)
    request('/api/v1/admin/accounts',403,token=fixture['staff']['token'])
    request('/api/v1/admin/accounts',token=fixture['root']['token'])
    assert not request('/api/v1/admin/auth/me',token=fixture['staff']['token'])['data']['is_root']
    # Enrollment and earlier logins consumed this period. Respect replay protection;
    # this bounded clock wait is test-only, not a production retry or keepalive.
    time.sleep((int(time.time())//30+1)*30-time.time()+0.2)
    for role in ['root','staff']:
        account=fixture[role]
        challenge=request('/api/v1/admin/auth/login/challenges',body=json.dumps({
            'username':account['username'],'password':account['password']}).encode())['data']
        secret=account['seed']
        key=base64.b32decode(secret+'='*((8-len(secret)%8)%8))
        digest=hmac.new(key,struct.pack('>Q',int(time.time())//30),hashlib.sha1).digest()
        offset=digest[-1]&15
        factor=str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
        session=request('/api/v1/admin/auth/login/challenges/'+challenge['challenge_id']+'/verify',body=json.dumps({
            'challenge_token':challenge['challenge_token'],'factor_code':factor}).encode())['data']
        assert session['admin']['id']==account['id'] and session['admin']['is_root']==(role=='root')
    assert not request('/api/v1/admin/setup')['required']
    assert b'<html' in request('/admin/').lower()
print('origin_verified')
'''
        args=['run','--rm','-i','--pull','never','--network',source.project+'_'+network,
              '--user','1000:1000' if peer=='line' else '0:0','--read-only','--memory','128m',
              '--mount',f'type=volume,source={source.project}_private-ca,target=/run/private-ca,readonly']
        if address: args += ['--ip',address]
        if peer != 'line': args += ['--mount',f'type=bind,source={source.data_root / "app-data"},target=/fixture,readonly']
        args += ['--entrypoint','python',helpers.IMAGE,'-',peer]
        result=docker.run(*args,source=code,success=False,timeout=90)
        assert result.returncode==0, 'synthetic origin probe failed: '+result.stderr[-500:]
        assert result.stdout.strip()=='origin_verified'

    try:
        started = source.up(override=override, success=False)
        assert started.returncode == 0, started.stderr[-1800:]
        source.ready()
        source.probe('seed')
        passed('fresh isolated DB; real root/staff TOTP login, original roles and file sentinels')
        source.compose('up','-d','--no-deps','--no-build','--pull','never','--wait','--wait-timeout','90',
                       'line-api',override=override)
        origin('admin','management-tunnel',source.values['NAS_TUNNEL_MANAGEMENT_PROXY_IP'])
        origin('lan','management-egress')
        passed('actual password/TOTP login at external and original LAN Host; roles retained; forged Access identity cannot log in')
        origin('line','line-tunnel',source.values['NAS_TUNNEL_LINE_PROXY_IP'])
        passed('LINE API excludes admin; invalid signature rejected; signed empty webhook accepted without provider effects')
        # Each connector origin network must be unable to resolve the other API.
        for network,forbidden in [('management-tunnel','line-api'),('line-tunnel','management-api')]:
            code='import socket,sys\ntry: socket.getaddrinfo(sys.argv[1],8443)\nexcept socket.gaierror: print("isolated")\nelse: raise SystemExit(2)'
            result=docker.run('run','--rm','--network',source.project+'_'+network,'--read-only','--memory','64m',
                              '--entrypoint','python',helpers.IMAGE,'-c',code,forbidden)
            assert result.strip()=='isolated'
        passed('origin networks isolate opposite API and do not expose database network')
        source.compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','--wait','--wait-timeout','90',
                       'management-api','line-api',override=override)
        # Canonical data/session readback, followed by actual fresh TOTP logins
        # for both original actors via the external Host after recreation.
        source.probe('verify')
        origin('admin','management-tunnel',source.values['NAS_TUNNEL_MANAGEMENT_PROXY_IP'])
        passed('preserve-data API recreation; same original accounts, TOTP, sessions and files')
        # Last operation is check-only, never a provider delivery/work cycle.
        result=source.compose('run','--rm','--no-deps','-T','line-worker',override=override,success=False,timeout=45)
        assert result.returncode==0, 'LINE Worker check-only failed'
        passed('LINE Worker last; existing independent machine token check only')
    finally:
        stopped=source.compose('--profile','line','stop','--timeout','25',override=override,success=False,timeout=65)
        (directory/'result.json').write_text(json.dumps({'phases_passed':phases,'containers_stopped':stopped.returncode==0,
            'actual_cloudflare_access':'not_run','token_used':False,'nas_accessed':False,
            'images_built_or_pushed':False},indent=2)+'\n',encoding='utf-8')
