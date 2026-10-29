"""Operator boundary: immutable source, verified backup copy and bounded switch."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import subprocess

import pytest
import yaml

from scripts import update_nas_database as nas

ROOT = Path(__file__).resolve().parents[7]


@pytest.fixture
def complete_backup(tmp_path):
    for name, value in {"project-name.txt": "fixture", "project-directory.txt": "/volume1/fixture",
                        "compose.yaml": "services: {}", ".env": "NAS_IMAGE=old\n",
                        "database.sql": "synthetic", "mysql-data.tar.gz": "synthetic"}.items():
        (tmp_path / name).write_text(value, encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text("".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
        for p in tmp_path.iterdir()), encoding="utf-8")
    (tmp_path / "COMPLETE").write_text("complete", encoding="utf-8")
    return tmp_path


def test_accepts_complete_matching_cold_backup(complete_backup):
    assert "mysql-data.tar.gz" in nas.verify_backup(complete_backup, "fixture", "/volume1/fixture")


@pytest.mark.parametrize("failure", ["incomplete", "modified", "foreign", "traversal"])
def test_backup_failure_never_mutates_existing_files(complete_backup, failure):
    if failure == "incomplete": (complete_backup / "COMPLETE").unlink()
    if failure == "modified": (complete_backup / "database.sql").write_text("tampered")
    if failure == "traversal": (complete_backup / "SHA256SUMS").write_text("0" * 64 + "  ../outside\n")
    before = {p.name: p.read_bytes() for p in complete_backup.iterdir()}
    with pytest.raises(nas.UpgradeBlocked):
        nas.verify_backup(complete_backup, "other" if failure == "foreign" else "fixture", "/volume1/fixture")
    assert before == {p.name: p.read_bytes() for p in complete_backup.iterdir()}


@pytest.mark.parametrize("fault", ["running", "wrong_owner", "original_volume", "port", "network"])
def test_source_and_helper_guards_reject_cross_boundary_operations(fault):
    info = {"Config": {"Labels": {"labor-union.upgrade": "fixture"}},
            "HostConfig": {"NetworkMode": "none", "PortBindings": {}},
            "Mounts": [{"Destination": "/var/lib/mysql", "Name": "new"}], "State": {"Running": False}}
    context = {"helper": "helper", "run_id": "fixture", "new_volume": "new", "old_volume": "old"}
    if fault == "wrong_owner": info["Config"]["Labels"]["labor-union.upgrade"] = "other"
    if fault == "original_volume": info["Mounts"][0]["Name"] = "old"
    if fault == "port": info["HostConfig"]["PortBindings"] = {"3306/tcp": [{"HostPort": "3306"}]}
    if fault == "network": info["HostConfig"]["NetworkMode"] = "host"
    if fault == "running":
        docker = SimpleNamespace(request=lambda *_: [{"State": "running"}])
        with pytest.raises(nas.UpgradeBlocked, match="original_project_must_remain_stopped"):
            nas.original_stopped(docker, "fixture")
    else:
        with pytest.raises(nas.UpgradeBlocked):
            nas.guarded_helper(SimpleNamespace(inspect=lambda _: info), context)


def test_environment_is_data_and_does_not_execute_shell(tmp_path):
    file = tmp_path / ".env"
    file.write_text('NAS_IMAGE=old\nOTHER=$(create-secret-file)\n')
    assert nas.env_value(file, "NAS_IMAGE") == "old"
    assert list(tmp_path.iterdir()) == [file]


def test_switch_changes_only_image_and_mysql_volume_preserves_env_bytes(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    run_id = "20261027T030000Z"
    folder = project / "database-upgrades" / run_id
    folder.mkdir(parents=True)
    original_env = b'# comments\r\nNAS_IMAGE=old\r\nLINE_SECRET=synthetic-only\r\nCOMPOSE_PROFILES=\r\n'
    (project / ".env").write_bytes(original_env)
    model = {"services": {"db": {"image": "mysql:same", "volumes": ["mysql-data:/var/lib/mysql"]},
                           "management-api": {"ports": [], "networks": ["existing"]}},
             "networks": {"existing": {"external": True}}, "volumes": {"mysql-data": None, "settings": None}}
    (project / "compose.yaml").write_text(yaml.safe_dump(model))
    context = {"run_id": run_id, "project": "fixture", "project_dir": "/volume1/fixture", "image_tag": "new",
               "new_volume": "fixture_mysql-upgrade", "old_volume": "fixture_mysql-data",
               "before_env": nas.digest(project / ".env"), "before_compose": nas.digest(project / "compose.yaml")}
    nas.save(folder / "context.json", context)
    nas.save(folder / "verified.json", {"run_id": run_id, "status": "verified", "new_volume": context["new_volume"]})
    real_path = Path
    monkeypatch.setattr(nas, "Path", lambda *p: project if p == ("/deployment",) else real_path(*p))
    monkeypatch.setattr(nas, "Docker", lambda: object())
    monkeypatch.setattr(nas, "original_stopped", lambda *_: None)
    monkeypatch.setattr(nas, "guarded_helper", lambda *_: {"State": {"Running": False}})
    nas.switch(SimpleNamespace(run_id=run_id, project_dir="/volume1/fixture", image="new"))
    assert (project / ".env").read_bytes() == original_env.replace(b"NAS_IMAGE=old", b"NAS_IMAGE=new")
    actual = yaml.safe_load((project / "compose.yaml").read_text())
    assert actual["services"] == model["services"]
    assert actual["networks"] == model["networks"]
    assert actual["volumes"]["settings"] is None
    assert actual["volumes"]["mysql-data"] == {"external": True, "name": "fixture_mysql-upgrade"}
    assert (folder / "switched.json").exists()
    with pytest.raises(nas.UpgradeBlocked, match="already_switched"):
        nas.switch(SimpleNamespace(run_id=run_id, project_dir="/volume1/fixture", image="new"))


def test_restore_rejects_an_existing_nonempty_copy(tmp_path, monkeypatch):
    (tmp_path / "sentinel").write_bytes(b"must survive")
    real_path = Path
    monkeypatch.setattr(nas, "Path", lambda *p: tmp_path if p == ("/clone-data",) else real_path(*p))
    with pytest.raises(nas.UpgradeBlocked, match="clone_volume_not_empty"):
        nas.extract_copy()
    assert (tmp_path / "sentinel").read_bytes() == b"must survive"


def test_rejects_unsupported_backfill_candidate_before_connecting(tmp_path, monkeypatch):
    context = tmp_path / 'context.json'
    context.write_text(json.dumps({'candidate': 'lu_nas_candidate_invalid'}))
    real_path = Path
    monkeypatch.setattr(nas, 'Path', lambda *p: context if p == ('/upgrade/context.json',) else real_path(*p))
    monkeypatch.setattr(nas, 'Docker', lambda: pytest.fail('namespace must be checked before any Docker access'))
    with pytest.raises(nas.UpgradeBlocked, match='candidate_namespace_invalid'):
        nas.run_copy_upgrade()


def test_switch_freeze_rejects_source_restart_even_when_volume_and_image_are_unchanged():
    info = {'Id': 'source-id', 'Image': 'same-image', 'Config': {'Labels': {'com.docker.compose.project': 'fixture'}},
            'State': {'ExitCode': 0, 'OOMKilled': False, 'StartedAt': 'later', 'FinishedAt': 'later'},
            'Mounts': [{'Destination': '/var/lib/mysql', 'Type': 'volume', 'Name': 'original-volume'}]}
    docker = SimpleNamespace(request=lambda *_: [{'State': 'exited'}], inspect=lambda _: info)
    context = {'old_volume': 'original-volume', 'mysql_image': 'same-image', 'original_db_id': 'source-id',
               'original_started_at': 'before', 'original_finished_at': 'before'}
    with pytest.raises(nas.UpgradeBlocked, match='original_database_restarted_during_upgrade'):
        nas.original_stopped(docker, 'fixture', context)


def test_post_upgrade_uses_the_tuple_cursor_schema_contract_and_checks_all_profiles(tmp_path, monkeypatch):
    from scripts import update_local_database as updater
    from scripts import compact_fresh_schema, verify_validation_schema_manifest
    from infrastructure.mysql import nas_permissions
    import pymysql
    import os

    context = {'candidate': 'lu_test_valid_candidate', 'database': 'lu_test_nas_preview', 'helper': 'fixture-helper',
               'run_id': 'fixture', 'new_volume': 'new'}
    (tmp_path / 'context.json').write_text(json.dumps(context))
    (tmp_path / 'password').write_text('synthetic-independent-password-not-a-secret')
    real_path = Path
    def mapped_path(*parts):
        if parts == ('/upgrade/context.json',): return tmp_path / 'context.json'
        if parts == ('/upgrade/verified.json',): return tmp_path / 'verified.json'
        if parts == ('/mysql-secrets/root-password',): return tmp_path / 'password'
        if parts and parts[0] == '/profiles': return tmp_path / 'password'
        if parts == ('/tmp/nas-upgrade-bin',): return tmp_path / 'bin'
        return real_path(*parts)
    monkeypatch.setattr(nas, 'Path', mapped_path)
    monkeypatch.setattr(nas, 'Docker', lambda: object())
    monkeypatch.setattr(nas, 'guarded_helper', lambda *_: None)
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    monkeypatch.setattr(updater, 'update_local_database', lambda **_: {'status': 'completed'})
    monkeypatch.setattr(compact_fresh_schema, 'load_compact_plan', lambda: {'expected': {'tables': ['fixture'], 'views': []}})
    class Cursor:
        def __init__(self, dictionary): self.dictionary = dictionary
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def fetchall(self): return [{'table_name': 'fixture'}] if self.dictionary else [('fixture',)]
    class Connection:
        def __init__(self, dictionary): self.dictionary = dictionary
        def cursor(self): return Cursor(self.dictionary)
        def close(self): pass
    def connect(**kw):
        if str(kw.get('user', '')).startswith('fixture_'):
            # Reuse PyMySQL's CA construction, which supports the existing MySQL
            # certificates; do not substitute a new strict SSLContext here.
            assert kw['ssl'] == {'ca': '/tls/ca.pem', 'check_hostname': False}
        return Connection(kw.get('cursorclass') == pymysql.cursors.DictCursor)
    monkeypatch.setattr(pymysql, 'connect', connect)
    def tuple_schema_contract(cursor, *_):
        assert {row[0] for row in cursor.fetchall()} == {'fixture'}
        return []
    monkeypatch.setattr(verify_validation_schema_manifest, 'verify_database_objects', tuple_schema_contract)
    accounts = {profile: 'fixture_' + profile for profile in nas_permissions.PROFILES}
    monkeypatch.setattr(nas_permissions, 'install_permissions', lambda *_: {'accounts': accounts})
    checked = []
    monkeypatch.setattr(nas_permissions, 'verify_runtime_permissions', lambda _, profile, *a, **kw: checked.append(profile))
    nas.run_copy_upgrade()
    assert set(checked) == set(nas_permissions.PROFILES)
    assert json.loads((tmp_path / 'verified.json').read_text())['status'] == 'verified'


@pytest.fixture
def dsm_wrapper(tmp_path, monkeypatch):
    if os.name == 'nt' or os.getuid() != 0:
        pytest.skip('DSM wrapper requires Linux root')
    project, backup, bin_dir = [tmp_path / name for name in ('project', 'backup', 'bin')]
    for path in (project, backup, bin_dir): path.mkdir()
    (project / '.env').write_text('COMPOSE_PROJECT_NAME=fixture\nUNUSED=$(touch SHOULD_NOT_EXIST)\n')
    (project / 'compose.yaml').write_text('services: {}\n')
    (project / 'update_nas_database.py').write_text('# fixture only\n')
    script = project / 'upgrade-database.sh'
    script.write_bytes((ROOT / 'deployment/nas/upgrade-database.sh').read_bytes())
    executable = bin_dir / 'docker'
    executable.write_text('''#!/usr/bin/env python
import json,os,sys
a=sys.argv[1:]
with open(os.environ['TRACE'], 'a') as f: f.write(json.dumps(a)+'\\n')
if a[:2]==['image','inspect']: print('sha256:fixture')
elif a[0]=='run':
    assert a[a.index('--network')+1]=='none'
    assert '--read-only' in a and '--rm' in a
    assert a[a.index('--entrypoint')+1]=='python'
    assert '/opt/nas-upgrade.py' in a
    print('{"status":"prepared","fixture":true}')
else: sys.exit(90)
''')
    executable.chmod(0o700)
    trace = tmp_path / 'trace.jsonl'
    monkeypatch.setenv('TRACE', str(trace))
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    def run(*args):
        return subprocess.run(['bash', str(script), *args], capture_output=True, text=True, timeout=10)
    return project, backup, trace, run


def test_dsm_wrapper_is_noninteractive_and_passes_only_the_scoped_maintenance_mounts(dsm_wrapper):
    project, backup, trace, run = dsm_wrapper
    result = run('--prepare', '--backup-dir', str(backup))
    assert result.returncode == 0, result.stdout
    commands = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [command[0] for command in commands] == ['image', 'run']
    command = commands[-1]
    mounts = [command[i+1] for i, value in enumerate(command) if value == '--mount']
    assert len(mounts) == 4
    assert 'type=bind,source='+str(backup)+',target=/backup,readonly' in mounts
    assert command[command.index('--project-dir')+1] == str(project)
    assert command[command.index('--upgrade-timeout')+1] == '900'
    assert not (project / 'SHOULD_NOT_EXIST').exists()


@pytest.mark.parametrize('arguments', [('--apply',), ('--switch', '--run-id', '../foreign'),
                                       ('--prepare', '--timeout-seconds', '1')])
def test_dsm_wrapper_rejects_invalid_modes_identifiers_and_time_bounds_before_docker(dsm_wrapper, arguments):
    _, _, trace, run = dsm_wrapper
    assert run(*arguments).returncode == 2
    assert not trace.exists()
