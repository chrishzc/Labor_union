"""Container-side fixture for the opt-in, local-only NAS lifecycle test.

Credentials are generated inside the disposable application container and kept
only in its isolated /data bind. No credential, response body or raw exception
is printed. This is a persistence oracle, not a business-data seeder.
"""
from __future__ import annotations

import hashlib
import base64
import hmac
import json
import os
from pathlib import Path
import secrets
import ssl
import socket
import sys
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://management-api:8443'
FIXTURE = Path('/data/.nas-lifecycle-fixture.json')


def request(path, body=None, *, token=None, status=200):
    headers = {'Origin': BASE}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(BASE + path, headers=headers,
        data=None if body is None else json.dumps(body).encode())
    context = ssl.create_default_context(cafile='/run/private-ca/ca.pem')
    try:
        response = urllib.request.urlopen(req, context=context, timeout=15)
    except urllib.error.HTTPError as error:
        if error.code == status:
            return {}
        raise RuntimeError(f'HTTP {error.code} at {path}') from None
    with response:
        if response.status != status:
            raise RuntimeError(f'unexpected status at {path}')
        return json.loads(response.read())


def totp_code(seed):
    key = base64.b32decode(seed + '=' * (-len(seed) % 8))
    digest = hmac.digest(key, struct.pack('>Q', int(time.time()) // 30), 'sha1')
    offset = digest[-1] & 15
    value = int.from_bytes(digest[offset:offset + 4], 'big') & 0x7fffffff
    return f'{value % 1000000:06d}'


def enroll(username, password):
    challenge = request('/api/v1/admin/auth/login/challenges',
        {'username': username, 'password': password})['data']
    if challenge['challenge_type'] != 'mfa_enrollment':
        raise RuntimeError('fixture must start without a factor')
    seed = urllib.parse.parse_qs(urllib.parse.urlparse(challenge['provisioning_uri']).query)['secret'][0]
    recovery = request('/api/v1/admin/auth/enrollment/challenges/' + challenge['challenge_id'] + '/verify',
        {'challenge_token': challenge['challenge_token'], 'totp_code': totp_code(seed)})['data']['recovery_codes']
    # Enrollment consumes this TOTP time step. A real recovery factor avoids
    # waiting for a clock boundary or bypassing the replay-protection rule.
    challenge = request('/api/v1/admin/auth/login/challenges',
        {'username': username, 'password': password})['data']
    session = request('/api/v1/admin/auth/login/challenges/' + challenge['challenge_id'] + '/verify',
        {'challenge_token': challenge['challenge_token'], 'factor_code': recovery[0]})['data']
    return {'username': username, 'password': password, 'seed': seed,
            'token': session['access_token'], 'id': session['admin']['id']}


def stable_database_digest():
    from infrastructure.mysql.mysql_adapter import get_connection
    conn = get_connection('access')
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id,username,password_hash,display_name,enabled,access_control_version FROM admin_users ORDER BY id')
            users = cur.fetchall()
            cur.execute('SELECT singleton_key,admin_user_id FROM admin_root_account')
            root = cur.fetchall()
            cur.execute('SELECT id,admin_user_id,seed_ciphertext,encryption_key_version,factor_state FROM admin_totp_factors ORDER BY id')
            factors = cur.fetchall()
        return hashlib.sha256(repr((users, root, factors)).encode()).hexdigest()
    finally:
        conn.close()


def stable_files_digest():
    roots = ['/settings', '/run/db-management', '/run/db-access', '/run/db-maintenance',
             '/run/worker-verifiers', '/run/api-tls', '/run/private-ca', '/run/db-ca']
    files = {}
    for root in roots:
        for path in sorted(Path(root).rglob('*')):
            if path.is_file():
                files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for root in ['/data', '/data/controlled-files', '/data/media', '/data/knowledge']:
        path = Path(root) / '.nas-lifecycle-sentinel'
        files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def run(action):
    if os.getenv('NAS_LIFECYCLE_FIXTURE') != '1':
        raise RuntimeError('local lifecycle fixture opt-in required')
    from dotenv import dotenv_values
    for key, value in dotenv_values('/settings/app.env').items():
        if value is not None:
            os.environ[key] = value
    if action == 'seed':
        if FIXTURE.exists():
            raise RuntimeError('fixture already exists')
        password = secrets.token_urlsafe(32)
        request('/api/v1/admin/setup', {'username': 'lifecycle_root',
            'display_name': 'Lifecycle root fixture', 'password': password}, status=201)
        root = enroll('lifecycle_root', password)
        worker_password = secrets.token_urlsafe(32)
        request('/api/v1/admin/accounts', {'username': 'lifecycle_staff',
            'display_name': 'Lifecycle staff fixture', 'password': worker_password,
            'reason': 'Disposable local lifecycle verification',
            'idempotency_key': secrets.token_urlsafe(24)}, token=root['token'], status=201)
        staff = enroll('lifecycle_staff', worker_password)
        for folder in ['/data', '/data/controlled-files', '/data/media', '/data/knowledge']:
            (Path(folder) / '.nas-lifecycle-sentinel').write_bytes(secrets.token_bytes(1024))
        fixture = {'root': root, 'staff': staff,
                   'database': stable_database_digest(), 'files': stable_files_digest()}
        FIXTURE.write_text(json.dumps(fixture), encoding='utf-8')
        FIXTURE.chmod(0o600)
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    with socket.create_connection(('redis', 6379), timeout=5) as redis:
        redis.sendall(b'*1\r\n$4\r\nPING\r\n')
        if redis.recv(64) != b'+PONG\r\n':
            raise RuntimeError('Redis ping failed')
    for role in ['root', 'staff']:
        account = fixture[role]
        principal = request('/api/v1/admin/auth/me', token=account['token'])['data']
        if principal['id'] != account['id'] or principal['is_root'] != (role == 'root'):
            raise RuntimeError('persisted principal mismatch')
    request('/api/v1/admin/accounts', token=fixture['staff']['token'], status=403)
    if request('/api/v1/admin/setup')['required']:
        raise RuntimeError('first-root setup unexpectedly reopened')
    if stable_database_digest() != fixture['database'] or stable_files_digest() != fixture['files']:
        raise RuntimeError('persisted account, MFA, credential or file changed')
    if action == 'login':
        for role in ['root', 'staff']:
            account = fixture[role]
            challenge = request('/api/v1/admin/auth/login/challenges',
                {'username': account['username'], 'password': account['password']})['data']
            session = request('/api/v1/admin/auth/login/challenges/' + challenge['challenge_id'] + '/verify',
                {'challenge_token': challenge['challenge_token'],
                 'factor_code': totp_code(account['seed'])})['data']
            if session['admin']['id'] != account['id']:
                raise RuntimeError('MFA login identity mismatch')
    print(json.dumps({'status': 'passed', 'check': action,
                      'claims': ['accounts', 'mfa_state', 'sessions', 'root_only_account_center',
                                 'setup_closed', 'credentials', 'files', 'redis_ping']}))


if __name__ == '__main__':
    try:
        run(sys.argv[1])
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1) from None
