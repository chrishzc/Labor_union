"""Immutable template pairs and an atomic, process-locked Contract Signing head."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

from domains.contract_signing.template_management import TemplateManagementError, TemplateVersion, require_template_key
from subsystems.contract_signing.template_catalog import ContractTemplateVersion, load_approved_template
from subsystems.contract_signing.template_management import TemplateMutationReceipt


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class FileContractTemplateStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _directory(self, key: str) -> Path:
        return self.root / require_template_key(key)

    def _state(self, key: str) -> dict:
        try:
            content = (self._directory(key) / 'catalog.json').read_bytes()
        except FileNotFoundError:
            return {'version': 0, 'active': 'builtin', 'versions': [], 'receipts': {}}
        try:
            state = json.loads(content.decode('utf-8'))
            if not isinstance(state, dict) or not isinstance(state['version'], int) or state['version'] < 0 or not isinstance(state['versions'], list) or not isinstance(state['receipts'], dict):
                raise ValueError('invalid state')
            self._version_path(key, state['active'])
            return state
        except (ValueError, KeyError, TypeError, UnicodeError) as error:
            raise TemplateManagementError('unavailable', 'contract_template_catalog_corrupt', '模板目錄無法驗證，請聯絡管理員。') from error

    def _version_path(self, key: str, version_id: str) -> Path:
        if version_id != 'builtin' and not re.fullmatch(r'v_[0-9a-f]{32}', version_id):
            raise TemplateManagementError('validation', 'contract_template_version_invalid', '模板版本識別無效。')
        return self._directory(key) / version_id

    def _baseline(self, key: str) -> tuple[ContractTemplateVersion, TemplateVersion]:
        reference = self._state(key).get('baseline_reference')
        if reference is not None:
            return self._read_pair(key, reference, logical_version_id='builtin')
        value = load_approved_template(key)
        return value, TemplateVersion('builtin', key, 0, value.template_filename, '', value.template_sha256, value.mapping_sha256, 'system', None)

    def query(self, template_key: str) -> tuple[int, str, tuple[TemplateVersion, ...]]:
        state = self._state(template_key)
        _, baseline = self._baseline(template_key)
        try:
            versions = tuple(TemplateVersion(**row) for row in state['versions'])
        except (TypeError, ValueError) as error:
            raise TemplateManagementError('unavailable', 'contract_template_catalog_corrupt', '模板版本目錄無法讀取。') from error
        return state['version'], state['active'], (baseline, *versions)

    def load_active(self, template_key: str) -> ContractTemplateVersion:
        state = self._state(template_key)
        if state['active'] == 'builtin':
            return self._baseline(template_key)[0]
        return self._read_pair(template_key, state['active'])[0]

    def receipt(self, template_key: str, idempotency_key: str) -> TemplateMutationReceipt | None:
        receipt = self._state(template_key)['receipts'].get(idempotency_key)
        return None if receipt is None else TemplateMutationReceipt(receipt['version_id'], True)

    def load_exact(self, template_key: str, template_sha256: str, mapping_sha256: str) -> ContractTemplateVersion:
        _, _, versions = self.query(template_key)
        for version in versions:
            if version.template_sha256 == template_sha256 and version.mapping_sha256 == mapping_sha256:
                value = self._baseline(template_key)[0] if version.version_id == 'builtin' else self._read_pair(template_key, version.version_id)[0]
                if value.template_sha256 != template_sha256 or value.mapping_sha256 != mapping_sha256:
                    break
                return value
        raise TemplateManagementError('not_found', 'contract_template_historical_version_not_found', '找不到此文件引用的模板版本。')

    def _read_pair(self, key: str, version_id: str, *, logical_version_id: str | None = None) -> tuple[ContractTemplateVersion, TemplateVersion]:
        directory = self._version_path(key, version_id)
        try:
            metadata = TemplateVersion(**json.loads((directory / 'version.json').read_text(encoding='utf-8')))
            content = (directory / 'source.xlsx').read_bytes()
            mapping = (directory / 'mapping.json').read_bytes()
            if metadata.template_key != key or metadata.version_id != (logical_version_id or version_id) or _digest(content) != metadata.template_sha256 or _digest(mapping) != metadata.mapping_sha256:
                raise ValueError('digest mismatch')
        except FileNotFoundError as error:
            raise TemplateManagementError('not_found', 'contract_template_version_not_found', '找不到指定模板版本。') from error
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            raise TemplateManagementError('unavailable', 'contract_template_version_unavailable', '模板版本無法通過完整性驗證。') from error
        return ContractTemplateVersion(key, '客戶服務契約' if key == 'contract_client_copy' else '服務人員委任契約', metadata.filename,
            metadata.template_sha256, metadata.mapping_sha256, directory / 'source.xlsx', directory / 'mapping.json', metadata.version_id, metadata.worksheet_name), metadata

    def content(self, template_key: str, version_id: str) -> tuple[bytes, dict[str, object], TemplateVersion]:
        # A failed save may leave orphan files; only committed versions are visible.
        if version_id not in {version.version_id for version in self.query(template_key)[2]}:
            raise TemplateManagementError('not_found', 'contract_template_version_not_found', '找不到指定模板版本。')
        pair, metadata = self._baseline(template_key) if version_id == 'builtin' else self._read_pair(template_key, version_id)
        mapping = json.loads(pair.mapping_path.read_text(encoding='utf-8'))
        if version_id == 'builtin':
            # Legacy external caches are not exposed in management previews.
            from subsystems.contract_signing.contract_renderer import render_contract_template
            content = render_contract_template(template_path=pair.template_path, mapping_path=pair.mapping_path, facts={})
            # Stable cleaned legacy bytes allow replay of a save sourced from builtin.
            original = ZipFile(BytesIO(pair.template_path.read_bytes()))
            output = BytesIO()
            with original, ZipFile(BytesIO(content)) as source, ZipFile(output, 'w', compression=ZIP_DEFLATED) as target:
                for name in sorted(source.namelist()):
                    info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    target.writestr(info, original.read(name) if name == 'docProps/core.xml' and name in original.namelist() else source.read(name))
            content = output.getvalue()
        else:
            content = pair.template_path.read_bytes()
        return content, mapping, metadata

    @contextmanager
    def _lock(self, key: str):
        directory = self._directory(key)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / '.catalog.lock').open('a+b') as handle:
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _put_version(self, key: str, metadata: TemplateVersion, content: bytes, mapping: bytes, *, storage_id: str | None = None) -> None:
        directory = self._version_path(key, storage_id or metadata.version_id)
        directory.mkdir()
        for name, payload in (('source.xlsx', content), ('mapping.json', mapping), ('version.json', _json(asdict(metadata)))):
            with (directory / name).open('xb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        _sync_directory(directory)
        _sync_directory(directory.parent)

    def _commit(self, key: str, state: dict) -> None:
        directory = self._directory(key)
        descriptor, temporary = tempfile.mkstemp(prefix='.catalog-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(_json(state))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, directory / 'catalog.json')
            _sync_directory(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _replay(self, state: dict, key: str, payload: bytes) -> TemplateMutationReceipt | None:
        receipt = state['receipts'].get(key)
        if receipt is None:
            return None
        if receipt['payload_sha256'] != _digest(payload):
            raise TemplateManagementError('idempotency_mismatch', 'contract_template_idempotency_mismatch', '此操作識別已用於不同內容，請先核對原操作結果。')
        return TemplateMutationReceipt(receipt['version_id'], True)

    @staticmethod
    def _require_mutation(expected_version: int, actor: str, idempotency_key: str, state: dict) -> None:
        if not actor.strip() or not idempotency_key.strip() or len(idempotency_key) > 191:
            raise TemplateManagementError('validation', 'contract_template_actor_or_command_invalid', '模板操作缺少有效操作者或操作識別。')
        if expected_version != state['version']:
            raise TemplateManagementError('conflict', 'contract_template_catalog_stale', '模板目錄已由其他操作更新，請重新讀取後再操作。')

    def save(self, *, template_key: str, content: bytes, mapping: dict[str, object], filename: str,
             worksheet_name: str, expected_version: int, actor: str, idempotency_key: str) -> TemplateMutationReceipt:
        mapping_bytes = _json(mapping)
        payload = _json({'action': 'save', 'template_sha256': _digest(content), 'mapping_sha256': _digest(mapping_bytes),
                         'filename': filename, 'worksheet_name': worksheet_name, 'actor': actor, 'expected_version': expected_version})
        with self._lock(template_key):
            state = self._state(template_key)
            replay = self._replay(state, idempotency_key, payload)
            if replay:
                return replay
            self._require_mutation(expected_version, actor, idempotency_key, state)
            if state.get('baseline_reference') is None:
                base, metadata = self._baseline(template_key)
                reference = 'v_' + uuid4().hex
                self._put_version(template_key, metadata, base.template_path.read_bytes(), base.mapping_path.read_bytes(), storage_id=reference)
                state['baseline_reference'] = reference
            version = TemplateVersion('v_' + uuid4().hex, template_key, len(state['versions']) + 1, filename,
                worksheet_name, _digest(content), _digest(mapping_bytes), actor, datetime.now(timezone.utc).isoformat())
            self._put_version(template_key, version, content, mapping_bytes)
            state['versions'].append(asdict(version))
            state['version'] += 1
            state['receipts'][idempotency_key] = {'payload_sha256': _digest(payload), 'version_id': version.version_id,
                'action': 'save', 'actor': actor, 'created_at': version.created_at, 'catalog_version': state['version']}
            self._commit(template_key, state)
            return TemplateMutationReceipt(version.version_id, False)

    def activate(self, *, template_key: str, version_id: str, expected_version: int,
                 actor: str, idempotency_key: str) -> TemplateMutationReceipt:
        payload = _json({'action': 'activate', 'version_id': version_id, 'actor': actor, 'expected_version': expected_version})
        with self._lock(template_key):
            state = self._state(template_key)
            replay = self._replay(state, idempotency_key, payload)
            if replay:
                return replay
            self._require_mutation(expected_version, actor, idempotency_key, state)
            if version_id not in {version.version_id for version in self.query(template_key)[2]}:
                raise TemplateManagementError('not_found', 'contract_template_version_not_found', '找不到指定模板版本。')
            if version_id == 'builtin':
                self._baseline(template_key)
            else:
                self._read_pair(template_key, version_id)
            state['active'] = version_id
            state['version'] += 1
            state['receipts'][idempotency_key] = {'payload_sha256': _digest(payload), 'version_id': version_id,
                'action': 'activate', 'actor': actor, 'created_at': datetime.now(timezone.utc).isoformat(), 'catalog_version': state['version']}
            self._commit(template_key, state)
            return TemplateMutationReceipt(version_id, False)


def _sync_directory(directory: Path) -> None:
    if os.name != 'nt':
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
