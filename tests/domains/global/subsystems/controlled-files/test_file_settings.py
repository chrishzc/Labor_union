"""File settings persist separately from business data; paths never switch storage."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_persisted_admin
from api.routes import controlled_files, file_settings
from infrastructure.runtime.file_transfer_settings import (
    FileSettingsError, file_read_capacity, file_settings_view, file_transfer_settings, save_file_settings,
)
from subsystems.access.authentication_session import AdminPrincipal


@pytest.fixture
def settings_environment(monkeypatch, tmp_path):
    path = tmp_path / 'config/file-settings.json'
    monkeypatch.setenv('FILE_SETTINGS_PATH', str(path))
    monkeypatch.setenv('CONTROLLED_FILE_STORAGE_ROOT', str(tmp_path / 'existing-files'))
    for name in ('FILE_PHOTO_MAX_BYTES', 'FILE_RESUME_MAX_BYTES', 'FILE_TRANSFER_TIMEOUT_SECONDS'):
        monkeypatch.delenv(name, raising=False)
    return path


def body(**changes):
    return dict(expected_version=0, photo_max_bytes=30 * 1048576, resume_max_bytes=40 * 1048576,
                timeout_seconds=60, **changes)


def client(root=True):
    app = FastAPI(); app.include_router(file_settings.router); app.include_router(controlled_files.router)
    app.dependency_overrides[require_persisted_admin] = lambda: AdminPrincipal(1, 'operator', 'operator', 'system_admin', is_root=root)
    return TestClient(app)


def test_real_query_save_readback_and_readonly_runtime_path(settings_environment, monkeypatch, tmp_path):
    with client() as api:
        initial = api.get('/api/v1/storage/settings').json()['data']
        assert initial['version'] == 0 and initial['timeout_seconds'] == 60
        assert initial['container_root'] == str((tmp_path / 'existing-files').resolve())
        assert 'nas_path' not in initial
        assert not settings_environment.exists()  # Query has no persistence effect.
        saved = api.put('/api/v1/storage/settings', json=body())
        assert saved.status_code == 200, saved.text
        value = saved.json()['data']
        assert value['version'] == 1
        assert value['container_root'] == initial['container_root']
        assert not (tmp_path / 'existing-files').exists()
        assert api.get('/api/v1/storage/settings').json()['data'] == value
        assert api.get('/api/v1/storage/transfer-settings').json()['data']['photo_max_bytes'] == 30 * 1048576
    monkeypatch.setenv('FILE_PHOTO_MAX_BYTES', '1')
    assert file_transfer_settings().photo_max_bytes == 30 * 1048576
    assert 'nas_path' not in json.loads(settings_environment.read_text(encoding='utf-8'))


def test_nonroot_cannot_read_or_save_paths_but_can_read_upload_limits(settings_environment):
    with client(root=False) as api:
        assert api.get('/api/v1/storage/settings').status_code == 403
        assert api.put('/api/v1/storage/settings', json=body()).status_code == 403
        assert api.get('/api/v1/storage/transfer-settings').status_code == 200
    assert not settings_environment.exists()


def test_stale_update_is_closed_and_cannot_overwrite(settings_environment):
    save_file_settings(**body())
    before = settings_environment.read_bytes()
    with client() as api:
        response = api.put('/api/v1/storage/settings', json=body())
        assert response.status_code == 409
        assert response.json()['detail']['error']['code'] == 'file_settings_stale'
    assert settings_environment.read_bytes() == before


def test_simultaneous_saves_have_one_winner(settings_environment):
    barrier = Barrier(2)
    def save():
        barrier.wait()
        try:
            save_file_settings(**body()); return 'saved'
        except FileSettingsError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(), range(2)))
    assert results.count('saved') == 1
    assert set(results) <= {'saved', 'file_settings_stale', 'file_settings_busy'}
    assert file_settings_view()['version'] == 1


@pytest.mark.parametrize('changes', [
    {'nas_path': '/volume1/other'}, {'container_root': '/other'},
    {'photo_max_bytes': 0}, {'timeout_seconds': -1}, {'photo_max_bytes': True}, {'unexpected': 'value'},
])
def test_invalid_settings_never_replace_file(settings_environment, changes):
    payload = body(); payload.update(changes)
    with client() as api:
        assert api.put('/api/v1/storage/settings', json=payload).status_code == 422
    assert not settings_environment.exists()


def test_corrupt_settings_do_not_fall_back_to_environment(settings_environment):
    settings_environment.parent.mkdir()
    settings_environment.write_text('{broken', encoding='utf-8')
    with client() as api:
        assert api.get('/api/v1/storage/settings').status_code == 503
    assert settings_environment.read_text(encoding='utf-8') == '{broken'


def test_old_path_note_does_not_become_the_runtime_storage_path(settings_environment):
    save_file_settings(**body())
    stored = json.loads(settings_environment.read_text(encoding='utf-8'))
    stored['nas_path'] = '/old-requested-folder'
    settings_environment.write_text(json.dumps(stored), encoding='utf-8')
    value = file_settings_view()
    assert value['container_root'] != '/old-requested-folder'
    assert 'nas_path' not in value and value['photo_max_bytes'] == body()['photo_max_bytes']


def test_unconfigured_storage_path_is_not_invented(settings_environment, monkeypatch):
    monkeypatch.delenv('CONTROLLED_FILE_STORAGE_ROOT')
    assert file_settings_view()['container_root'] is None
    assert not settings_environment.exists()


def test_lower_upload_limit_keeps_previous_large_files_readable(settings_environment, tmp_path):
    from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
    save_file_settings(**body())
    files = tmp_path / 'files'; files.mkdir()
    store = FileSystemControlledFileStorage(files, max_staging_bytes=file_read_capacity(), max_read_bytes=file_read_capacity())
    content = b'x' * (20 * 1048576 + 1)
    staged = store.put_staged(idempotency_key='retained-file', filename='large.pdf', mime_type='application/pdf', content=content)
    payload = body(); payload.update(expected_version=1, photo_max_bytes=1, resume_max_bytes=1, timeout_seconds=0)
    save_file_settings(**payload)
    fresh_store = FileSystemControlledFileStorage(files, max_staging_bytes=file_read_capacity(), max_read_bytes=file_read_capacity())
    assert fresh_store.read_registered_staged(staged.staging_id, expected_sha256=staged.sha256_digest).content == content
    assert file_transfer_settings().photo_max_bytes == 1
    assert file_transfer_settings().timeout_seconds == 0
