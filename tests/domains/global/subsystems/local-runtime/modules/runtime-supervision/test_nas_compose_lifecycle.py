"""Opt-in lifecycle rehearsal against local Docker and an already-built image.

Never builds/pushes images, opens host ports, reads real .env files, removes
volumes, or connects to NAS. Both source and restore targets are created here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import ipaddress

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[7]
COMPOSE = ROOT / 'deployment/nas/compose.yaml'
PROBE = Path(__file__).with_name('nas_lifecycle_probe.py')
IMAGE = 'chris23144638/cecec:nas-secure-20261020'
BASE_SERVICES = {'initialize', 'db', 'configure-security', 'redis', 'management-api'}
OS_ENV = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATHEXT', 'SYSTEMDRIVE',
          'COMSPEC', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'LOCALAPPDATA', 'APPDATA',
          'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA'}


class LocalDocker:
    def __init__(self):
        self.env = {k: v for k, v in os.environ.items() if k.upper() in OS_ENV}
        endpoint = self.run('context', 'inspect', '--format', '{{(index .Endpoints "docker").Host}}').strip()
        if not (endpoint.startswith('npipe://') or endpoint == 'unix:///var/run/docker.sock'):
            raise AssertionError('Lifecycle rehearsal requires a local Docker endpoint')
        self.env['DOCKER_HOST'] = endpoint
        self.env['COMPOSE_DISABLE_ENV_FILE'] = '1'

    def run(self, *args, source=None, timeout=60, success=True):
        result = subprocess.run(['docker', *map(str, args)], cwd=ROOT, env=self.env,
            input=source, encoding='utf-8', errors='replace', capture_output=True, timeout=timeout)
        if success and result.returncode:
            # Deliberately avoid raw CLI/driver output or process arguments.
            raise AssertionError(f'Docker {args[0]} failed with exit={result.returncode}')
        return result.stdout if success else result


class IsolatedProject:
    def __init__(self, docker, project, directory):
        if not project.startswith('lu-nas-life-') or directory.exists():
            raise AssertionError('A fresh lifecycle namespace is required')
        self.docker, self.project, self.directory = docker, project, directory
        self.data_root = directory / 'storage'
        self.env_file = directory / 'lifecycle.env'
        self.volumes = sorted(yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))['volumes'])
        directory.mkdir(parents=True)
        for name in ['app-data', 'controlled-files', 'line-media', 'knowledge']:
            (self.data_root / name).mkdir(parents=True)
        # Refuse namespace reuse before any mutation.
        existing = docker.run('ps', '-a', '--filter', f'label=com.docker.compose.project={project}', '--format', '{{.ID}}')
        if existing.strip() or docker.run('volume', 'ls', '--filter', f'label=com.docker.compose.project={project}', '--format', '{{.Name}}').strip():
            raise AssertionError('Lifecycle namespace is already in use')
        network_ids = docker.run('network', 'ls', '-q').split()
        networks = json.loads(docker.run('network', 'inspect', *network_ids))
        occupied = [ipaddress.ip_network(c['Subnet']) for n in networks
                    for c in (n['IPAM'].get('Config') or []) if c.get('Subnet')]
        available = [ipaddress.ip_network(f'172.31.{i}.0/29') for i in range(249, 149, -1)
                     if not any(ipaddress.ip_network(f'172.31.{i}.0/29').overlaps(n)
                                for n in occupied if n.version == 4)]
        subnet, management_tunnel, line_tunnel = available[:3]
        # Old retained rehearsals may exhaust Docker's automatic /16 pools.
        # Use fresh explicit subnets for this fixture only; never prune others.
        private = [ipaddress.ip_network(f'10.241.{i}.0/24') for i in range(250, 99, -1)
                   if not any(ipaddress.ip_network(f'10.241.{i}.0/24').overlaps(n)
                              for n in occupied if n.version == 4)]
        docker.run('network', 'create', '--internal', '--subnet', str(private.pop(0)),
                   '--label', 'labor-union.lifecycle=1', project + '_data')
        self.network_id = docker.run('network', 'inspect', project + '_data', '--format', '{{.Id}}').strip()
        fixed = {'data', 'management-egress', 'management-tunnel', 'line-tunnel'}
        model = yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))
        self.network_override = directory / 'isolated-networks.yaml'
        self.network_override.write_text(yaml.safe_dump({'networks': {
            name: {'ipam': {'config': [{'subnet': str(private.pop(0))}]}}
            for name in model['networks'] if name not in fixed}}), encoding='utf-8')
        self.values = {'COMPOSE_PROJECT_NAME': project, 'NAS_IMAGE': IMAGE,
            'NAS_DATA_ROOT': self.data_root.as_posix(), 'NAS_BIND_IP': '127.0.0.1',
            'NAS_MANAGEMENT_HOSTNAME': 'lifecycle.invalid', 'NAS_PROXY_SUBNET': str(subnet),
            'NAS_PROXY_API_IP': str(subnet.network_address + 2), 'COMPOSE_PROFILES': '',
            'NAS_PROXY_RUNTIME_SCRIPT': (ROOT / 'scripts/nas_appliance.py').as_posix(),
            'NAS_TUNNEL_MANAGEMENT_SUBNET': str(management_tunnel),
            'NAS_TUNNEL_MANAGEMENT_PROXY_IP': str(management_tunnel.network_address + 2),
            'NAS_TUNNEL_MANAGEMENT_API_IP': str(management_tunnel.network_address + 3),
            'NAS_TUNNEL_LINE_SUBNET': str(line_tunnel),
            'NAS_TUNNEL_LINE_PROXY_IP': str(line_tunnel.network_address + 2),
            'NAS_TUNNEL_LINE_API_IP': str(line_tunnel.network_address + 3),
            'MYSQL_IMAGE': 'mysql:8.0.46', 'REDIS_IMAGE': 'redis:7-alpine'}
        self.write_env()

    def write_env(self):
        self.env_file.write_text(''.join(f'{k}={v}\n' for k, v in self.values.items()), encoding='utf-8')

    def compose(self, *args, override=None, success=True, timeout=210):
        cmd = ['compose', '--project-directory', str(COMPOSE.parent), '--env-file', str(self.env_file),
               '-p', self.project, '-f', str(COMPOSE), '-f', str(self.network_override)]
        if override:
            cmd += ['-f', str(override)]
        return self.docker.run(*cmd, *args, success=success, timeout=timeout)

    def up(self, *args, override=None, success=True):
        return self.compose('up', '-d', '--no-build', '--pull', 'never', '--wait',
                            '--wait-timeout', '180', *args, override=override, success=success)

    def container(self, service):
        return f'{self.project}-{service}-1'

    def metadata(self, service):
        fields = '{{json .State}}'
        state = json.loads(self.docker.run('inspect', '--format', fields, self.container(service)))
        return {'status': state['Status'], 'exit': state['ExitCode'],
                'health': state.get('Health', {}).get('Status'), 'oom': state['OOMKilled']}

    def ready(self):
        # --wait is not a replacement for verifying one-shot completion and health.
        for service in BASE_SERVICES:
            state = self.metadata(service)
            if service in {'initialize', 'configure-security'}:
                assert state['status'] == 'exited' and state['exit'] == 0, (service, state)
            else:
                assert state['status'] == 'running' and not state['oom'], (service, state)
                if service != 'redis':
                    assert state['health'] == 'healthy', (service, state)
        assert self.docker.run('network', 'inspect', self.project + '_data', '--format', '{{.Id}}').strip() == self.network_id
        assert self.docker.run('network', 'inspect', self.project + '_data', '--format', '{{.Internal}}').strip() == 'true'

    def probe(self, action):
        code = PROBE.read_text(encoding='utf-8')
        output = self.docker.run('exec', '-i', '-e', 'NAS_LIFECYCLE_FIXTURE=1',
            self.container('management-api'), 'python', '-', action, source=code, success=False)
        if output.returncode:
            raise AssertionError(f'Persistence probe failed: {output.stdout.strip()}')
        result = json.loads(output.stdout)
        assert result['status'] == 'passed'

    def helper(self, code, *, backup, restore=False):
        args = ['run', '--rm', '-i', '--network', 'none', '--read-only', '--memory', '256m',
                '--entrypoint', 'python']
        for volume in self.volumes:
            name = self.project + '_' + volume
            if restore:
                self.docker.run('volume', 'create', '--label', f'com.docker.compose.project={self.project}',
                                '--label', f'com.docker.compose.volume={volume}', name)
            labels = json.loads(self.docker.run('volume', 'inspect', name, '--format', '{{json .Labels}}'))
            assert labels.get('com.docker.compose.project') == self.project
            args += ['--mount', f'type=volume,source={name},target=/volumes/{volume}' + ('' if restore else ',readonly')]
        args += ['--mount', f'type=bind,source={self.data_root},target=/files' + ('' if restore else ',readonly'),
                 '--mount', f'type=bind,source={backup},target=/backup' + (',readonly' if restore else ''), IMAGE, '-']
        self.docker.run(*args, source=code, timeout=180)

    def backup(self, backup):
        assert all(self.metadata(s)['status'] == 'exited' for s in BASE_SERVICES)
        assert self.metadata('db')['exit'] == 0, 'MySQL must stop cleanly before a physical backup'
        backup.mkdir()
        code = '''import hashlib,json,tarfile
from pathlib import Path
names=NAMES
for name in names:
    with tarfile.open('/backup/'+name+'.tar.gz','w:gz') as archive:
        archive.add('/volumes/'+name,arcname='.')
with tarfile.open('/backup/files.tar.gz','w:gz') as archive:
    for name in ['app-data','controlled-files','line-media','knowledge']:
        archive.add('/files/'+name,arcname=name)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/backup').glob('*.tar.gz')}
Path('/backup/manifest.json').write_text(json.dumps(manifest))
'''.replace('NAMES', repr(self.volumes))
        self.helper(code, backup=backup)

    def restore(self, backup):
        # The only restore targets are empty, newly-created test volumes and dirs.
        # Archives were just produced locally; no imported archive is accepted.
        code = '''import hashlib,json,tarfile
from pathlib import Path,PurePosixPath
manifest=json.loads(Path('/backup/manifest.json').read_text())
for name,digest in manifest.items():
    assert hashlib.sha256(Path('/backup',name).read_bytes()).hexdigest()==digest
def extract(name,target):
    with tarfile.open('/backup/'+name,'r:gz') as archive:
        for member in archive.getmembers():
            path=PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
        archive.extractall(target,filter='fully_trusted')
for name in NAMES:
    assert not any(Path('/volumes',name).iterdir())
    extract(name+'.tar.gz','/volumes/'+name)
for name in ['app-data','controlled-files','line-media','knowledge']:
    assert not any(Path('/files',name).iterdir())
extract('files.tar.gz','/files')
'''.replace('NAMES', repr(self.volumes))
        self.helper(code, backup=backup, restore=True)


@pytest.mark.skipif(os.getenv('NAS_LIFECYCLE_TEST') != '1', reason='explicit local Docker opt-in required')
def test_existing_image_restart_recreate_update_rollback_and_cold_restore():
    docker = LocalDocker()
    metadata = json.loads(docker.run('image', 'inspect', IMAGE))[0]
    pinned = next(d for d in metadata['RepoDigests'] if d.startswith('chris23144638/cecec@sha256:'))
    # No pull/build occurs in this test; missing prerequisites fail explicitly.
    docker.run('image', 'inspect', 'mysql:8.0.46', 'redis:7-alpine', '--format', '{{.Id}}')
    run_id = uuid4().hex[:10]
    root = ROOT / 'scratch' / ('nas-lifecycle-' + run_id)
    root.mkdir()
    source = IsolatedProject(docker, 'lu-nas-life-' + run_id, root / 'source')
    restored = None
    phases = []

    def passed(name):
        phases.append(name)
        print(f'PASS {name}', flush=True)

    try:
        source.up()
        source.ready()
        source.probe('seed')
        passed('fresh start; root + staff enrollment; persisted sessions; scoped authorization')

        source.compose('stop', '--timeout', '30')
        source.up()
        source.ready()
        source.probe('verify')
        passed('whole-project stop and dependency-ordered start')

        old_id = docker.run('inspect', '--format', '{{.Id}}', source.container('management-api')).strip()
        source.compose('stop', '--timeout', '30')
        source.up('--force-recreate')
        source.ready()
        assert docker.run('inspect', '--format', '{{.Id}}', source.container('management-api')).strip() != old_id
        source.probe('verify')
        passed('container recreation keeps accounts, MFA, credentials, files and data network')

        source.values['NAS_IMAGE'] = pinned
        source.write_env()
        source.compose('stop', '--timeout', '30')
        source.up()
        source.ready()
        source.probe('verify')
        passed('tag-to-digest update operation (identical application bytes)')

        broken = root / 'candidate-failure.yaml'
        broken.write_text(yaml.safe_dump({'services': {'management-api': {
            'command': ['python', '-c', 'raise SystemExit(17)'], 'restart': 'no'}}}), encoding='utf-8')
        failure = source.up('--no-deps', 'management-api', override=broken, success=False)
        assert failure.returncode != 0
        assert source.metadata('management-api')['exit'] == 17
        source.values['NAS_IMAGE'] = IMAGE
        source.write_env()
        source.up('--no-deps', 'management-api')
        source.ready()
        source.probe('verify')
        passed('injected candidate startup failure is detected; application rollback restores service')

        source.compose('stop', '--timeout', '30')
        backup = root / 'cold-backup'
        source.backup(backup)
        passed('cold backup of every named volume and all four file roots')

        restored = IsolatedProject(docker, 'lu-nas-life-' + run_id + '-restore', root / 'restore')
        restored.restore(backup)
        restored.up()
        restored.ready()
        restored.probe('login')
        passed('restore into new volumes; original root + staff TOTP login and file readback')
    finally:
        states = {}
        for project in [source, restored]:
            if project is not None:
                result = project.compose('stop', '--timeout', '30', success=False, timeout=65)
                states[project.project] = {'stopped': result.returncode == 0}
        (root / 'result.json').write_text(json.dumps({'phases_passed': phases,
            'image_id': metadata['Id'], 'update_image': pinned,
            'distinct_application_versions_tested': False,
            'projects': states, 'nas_accessed': False, 'images_built_or_pushed': False}, indent=2), encoding='utf-8')
        print(f'Isolated evidence retained: {root}', flush=True)
