"""NAS public proxy -> real private HTTPS; synthetic identities/repositories, real files.

Standalone unittest entry supports the admitted Linux runtime without new packages.
It does not claim real MySQL, NAS ACL or LINE-provider verification.
"""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
import uvicorn
from fastapi import FastAPI

from api.dependencies.line_media_proxy import get_line_media_client
from api.dependencies.service_day_logs import get_service_day_log_application
from api.dependencies.service_day_media import get_controlled_file_workflow
from api.routes import line_media_proxy, private_line_media, staff_service_day_media, staff_service_day_logs
from domains.line.identities import LineUserId
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.http.line_media_client import LineMediaClient, LineMediaError
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError
from infrastructure.runtime.worker_credentials import prepare_credentials
from subsystems.controlled_files.contracts import ControlledFileStorageError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion
from subsystems.controlled_files.workflow import ControlledFileWorkflowError, ControlledFileOwner
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogApplication, ServiceDayLogResult


DAY = date(2026, 10, 19)
PUBLIC = "/api/v1/line/staff-self-service"
PRIVATE = "/internal/v1/line-media"
PNG = b"\x89PNG\r\n\x1a\nsynthetic-photo"


class MediaFixture:
    def __init__(self, root):
        self.storage = FileSystemControlledFileStorage(root, settle_seconds=0)
        self.staged = {}

    def stage(self, command):
        result = self.storage.put_staged(idempotency_key=command.idempotency_key.value,
            filename=command.filename, mime_type=command.mime_type, content=command.content)
        self.staged[result.staging_id] = (command, result)
        return result

    def preview(self, intent):
        pair = self.staged.get(intent.staging_id)
        if pair is None:
            raise ControlledFileWorkflowError("controlled_file_not_found", "missing")
        source, result = pair
        if any(getattr(source, field) != getattr(intent, field) for field in
               ("owner", "purpose", "subject_reference", "object_key", "logical_folder")):
            raise ControlledFileWorkflowError("controlled_file_owner_mismatch", "wrong scope")
        self.storage.read_registered_staged(result.staging_id, expected_sha256=result.sha256_digest)
        return SimpleNamespace(blockers=(), expected_staging_version=ExpectedVersion(1),
                               preview_fingerprint=PreviewFingerprint("a" * 64))

    def apply_borrowed(self, command):
        self.preview(command.intent)
        return SimpleNamespace(readback=SimpleNamespace(file_id="cf_" + "1" * 32, applied_at=None))

    def readback(self, file_id):
        command, _ = next(iter(self.staged.values()))
        return SimpleNamespace(owner=command.owner, purpose=command.purpose,
                               subject_reference=command.subject_reference)

    def download(self, file_id):
        _, result = next(iter(self.staged.values()))
        stored = self.storage.read_registered_staged(result.staging_id, expected_sha256=result.sha256_digest)
        return SimpleNamespace(content=stored.content, content_type=result.mime_type)


class LogFixture:
    def __init__(self):
        self.results = {}; self.submits = 0; self.commits = 0

    def load_assignment(self, staff_id, assignment_id, service_date, *, for_update):
        if staff_id != 9 or assignment_id != 12 or service_date != DAY:
            raise ValueError("service_day_assignment_not_visible")
        return {"case_no": "PRIVATE-PHOTO-CASE", "requires_cooking": False}

    def load_replay(self, command):
        result = self.results.get(command.idempotency_key)
        return replace(result, outcome="existing") if result else None

    def submit(self, command, assignment):
        self.submits += 1
        result = ServiceDayLogResult(1, assignment['case_no'], 12, DAY.isoformat(),
            command.intent.baby_log_text, False, "created", command.controlled_file_attachments)
        self.results[command.idempotency_key] = result
        return result

    def load_for_staff(self, log_id, staff_id, line_user_id):
        return (replace(next(iter(self.results.values())), outcome="existing")
                if self.results and (log_id, staff_id, line_user_id) == (1, 9, "U-owner") else None)

    @contextmanager
    def uow(self):
        yield SimpleNamespace(commit=lambda: setattr(self, "commits", self.commits + 1))


class PrivateLineMediaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        files = self.root / 'private'; files.mkdir()
        self.media, self.logs = MediaFixture(files), LogFixture()
        self.application = ServiceDayLogApplication(self.logs, self.logs.uow, self.media)
        self.backend = FastAPI(); self.backend.include_router(private_line_media.router)
        from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
        self.backend.add_middleware(CorrelationBoundaryMiddleware)
        install_typed_error_handlers(self.backend)
        from api.routes.private_operations import router as runtime_router
        self.backend.include_router(runtime_router)
        self.backend.dependency_overrides[get_controlled_file_workflow] = lambda: self.media
        self.backend.dependency_overrides[get_service_day_log_application] = lambda: self.application
        prepare_credentials(self.root / 'credentials')
        self.token = (self.root / 'credentials/line-media-proxy/token').read_text().strip()
        self.env = patch.dict(os.environ, {
            'APP_ENV': 'production', 'INTERNAL_SERVICE_AUTH_MODE': 'nas_service_token',
            'INTERNAL_SERVICE_CREDENTIALS_FILE': str(self.root / 'credentials/api/verifiers.json'),
            'LIFF_REQUIRE_ID_TOKEN': 'true',
            'FILE_SETTINGS_PATH': str(self.root / 'file-settings.json'),
        }); self.env.start()
        self.patches = []
        # Keep the real token-verification error handling and current binding path.
        def verify(token):
            if token not in {'owner-token', 'other-token'}:
                raise InvalidLiffTokenError('invalid synthetic credential')
            return SimpleNamespace(line_user_id=LineUserId('U-owner' if token == 'owner-token' else 'U-other'))
        @contextmanager
        def bindings():
            yield SimpleNamespace(customer_service=SimpleNamespace(staff_subject=lambda user:
                {'staff_id': 9 if user == 'U-owner' else 10}))
        for target, value in (
            ('api.routes.line_staff_self_service.get_liff_token_verifier', lambda: SimpleNamespace(verify=verify)),
            ('api.routes.staff_service_day_logs.open_line_unit_of_work', bindings),
            ('infrastructure.mysql.line_unit_of_work.open_line_unit_of_work', bindings),
        ):
            p = patch(target, value); p.start(); self.patches.append(p)
        # Generate the same strict private certificate chain used by NAS, in test temp only.
        from scripts import nas_security_runtime as runtime
        def write(path, content, mode=0o400):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        with patch.object(runtime, 'CA', self.root/'ca'), patch.object(runtime, 'API_TLS', self.root/'tls'), patch.object(runtime, '_write', write):
            runtime._prepare_api_tls()
        self.sock = socket.socket(); self.sock.bind(('127.0.0.1', 0))
        port = self.sock.getsockname()[1]
        config = uvicorn.Config(self.backend, log_level='critical', lifespan='off',
            ssl_certfile=str(self.root/'tls/management-api/server-cert.pem'),
            ssl_keyfile=str(self.root/'tls/management-api/server-key.pem'))
        self.server = uvicorn.Server(config)
        self.task = asyncio.create_task(self.server.serve(sockets=[self.sock]))
        for _ in range(100):
            if self.server.started: break
            await asyncio.sleep(.01)
        self.assertTrue(self.server.started)
        self.base = f'https://management-api:{port}'
        self.client = LineMediaClient(self.base, str(self.root/'credentials/line-media-proxy/token'), str(self.root/'ca/ca.pem'))
        from api.nas_apps import line_app
        self.public = line_app()
        self.public.dependency_overrides[get_line_media_client] = lambda: self.client

    async def asyncTearDown(self):
        self.server.should_exit = True
        await asyncio.wait_for(self.task, 5)
        for p in reversed(self.patches): p.stop()
        self.env.stop(); self.temp.cleanup()

    def caller(self):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.public), base_url='https://line-api')

    async def photo(self, caller, **fields):
        return await caller.post(PUBLIC+'/service-day-media', data={
            'line_id_token':'owner-token', 'assignment_id':'12', 'service_date':DAY.isoformat(),
            'attachment_kind':'baby_log_photo', **fields}, files={'photo':('photo.png', PNG, 'image/png')},
            headers={'Idempotency-Key':'private-photo-upload'})

    async def test_configured_settings_and_capacity_over_real_private_https(self):
        from infrastructure.runtime.file_transfer_settings import save_file_settings
        save_file_settings(expected_version=0, photo_max_bytes=100, resume_max_bytes=2048,
                           timeout_seconds=900)
        with patch.dict(os.environ, {'FILE_PHOTO_MAX_BYTES': '1', 'FILE_TRANSFER_TIMEOUT_SECONDS': '60'}):
            async with self.caller() as caller:
                response = await caller.post(PUBLIC + '/service-day-media/settings', json={'line_id_token': 'owner-token'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['data']['photo_max_bytes'], 100)
                self.assertEqual(response.json()['data']['timeout_seconds'], 900)
                self.assertEqual(self.client._timeout_seconds, 900)
                denied = await caller.post(PUBLIC + '/service-day-media/settings', json={'line_id_token': 'invalid-token'})
                self.assertEqual(denied.status_code, 401)
                oversized = await caller.post(PUBLIC + '/service-day-media',
                    data={'line_id_token':'owner-token','assignment_id':'12','service_date':DAY.isoformat(), 'attachment_kind':'baby_log_photo'},
                    files={'photo':('photo.png', PNG + b'x'*100, 'image/png')}, headers={'Idempotency-Key':'over-capacity'})
                self.assertEqual(oversized.status_code, 422)
                self.assertIn('100 bytes', oversized.text)
        self.assertFalse(self.media.staged)

    async def test_https_upload_preview_apply_readback_replay_and_real_private_bytes(self):
        async with self.caller() as c:
            upload = await self.photo(c); self.assertEqual(upload.status_code, 200, upload.text)
            again = await self.photo(c); self.assertEqual(again.json()['data']['outcome'], 'existing')
            media = upload.json()['data']
            verified = self.media.storage.read_registered_staged(media['staging_id'], expected_sha256=media['sha256_digest'])
            self.assertEqual(verified.content, PNG)
            body = {'line_id_token':'owner-token','assignment_id':12,'service_date':DAY.isoformat(),
                'baby_log_text':'synthetic diary','controlled_file_attachments':[{
                    'staging_id':media['staging_id'], 'sha256_digest':media['sha256_digest'],
                    'attachment_kind':'baby_log_photo'}]}
            preview = await c.post(PUBLIC+'/service-day-logs/preview', json=body)
            self.assertEqual(preview.status_code, 200, preview.text)
            apply = {**body,'preview_fingerprint':preview.json()['data']['preview_fingerprint']}
            stale=await c.post(PUBLIC+'/service-day-logs/apply',json={**apply,'preview_fingerprint':'0'*64},
                               headers={'Idempotency-Key':'stale-log'})
            self.assertEqual(stale.status_code,409,stale.text)
            self.assertEqual(self.logs.commits,0)
            for _ in range(2):
                response = await c.post(PUBLIC+'/service-day-logs/apply', json=apply, headers={'Idempotency-Key':'private-log'})
                self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.logs.submits, 1)
            read = await c.post(PUBLIC+'/service-day-logs/1/query',json={'line_id_token':'owner-token'})
            self.assertEqual(read.status_code, 200)
            self.assertEqual(read.json()['data']['baby_log_text'], 'synthetic diary')
            path=PUBLIC+'/service-day-logs/1/photos/cf_'+('1'*32)+'/download'
            photo=await c.post(path,json={'line_id_token':'owner-token'})
            self.assertEqual(photo.status_code,200,photo.text)
            self.assertEqual(photo.content,PNG)
            self.assertEqual(photo.headers['cache-control'],'private, no-store')
            self.assertEqual(photo.headers['x-content-type-options'],'nosniff')
            other_photo=await c.post(path,json={'line_id_token':'other-token'})
            self.assertEqual(other_photo.status_code,404)
            unrelated=await c.post(path.replace('cf_'+('1'*32),'cf_'+('2'*32)),json={'line_id_token':'owner-token'})
            self.assertEqual(unrelated.status_code,404)
            with patch.object(self.media,'readback',lambda _:SimpleNamespace(owner=ControlledFileOwner.STAFF)), patch.object(self.media,'download',side_effect=AssertionError('must not open an internal file')):
                forbidden=await c.post(path,json={'line_id_token':'owner-token'})
                self.assertEqual(forbidden.status_code,404)
            with patch.object(self.media,'download',side_effect=ControlledFileStorageError('controlled_file_read_denied','synthetic permission failure',retryable=False)):
                unavailable=await c.post(path,json={'line_id_token':'owner-token'})
                self.assertEqual(unavailable.status_code,503)
            other = await c.post(PUBLIC+'/service-day-logs/1/query',json={'line_id_token':'other-token'})
            self.assertEqual(other.status_code, 404)
            self.assertEqual(self.logs.commits, 2)

    async def test_identity_scope_and_forged_request_fail_before_file_write(self):
        async with self.caller() as c:
            for fields, status in (({'line_id_token':''},401), ({'line_id_token':'invalid'},401),
                                    ({'line_id_token':'other-token'},422), ({'assignment_id':'13'},422),
                                    ({'service_date':'2026-10-20'},422), ({'attachment_kind':'meal_photo'},422)):
                response = await self.photo(c, **fields)
                self.assertEqual(response.status_code,status,response.text)
            self.assertFalse(self.media.staged)
            bad = await c.post(PUBLIC+'/service-day-logs/preview', json={'line_id_token':'owner-token',
                'assignment_id':12,'service_date':DAY.isoformat(),'baby_log_text':'test','staff_id':10})
            self.assertEqual(bad.status_code,422)
            self.assertEqual(self.logs.commits,0)

    async def test_private_machine_scope_and_missing_original_token(self):
        import ssl
        context=ssl.create_default_context(cafile=str(self.root/'ca/ca.pem'))
        async with httpx.AsyncClient(base_url=self.base,verify=context,trust_env=False) as c:
            body={'line_id_token':'owner-token','assignment_id':12,'service_date':DAY.isoformat(),'baby_log_text':'test'}
            missing=await c.post(PRIVATE+'/service-day-logs/preview',json=body)
            self.assertEqual(missing.status_code,401)
            wrong=(self.root/'credentials/line-worker/token').read_text().strip()
            response=await c.post(PRIVATE+'/service-day-logs/preview',json=body,headers={'Authorization':'Bearer '+wrong})
            self.assertEqual(response.status_code,403)
            response=await c.post(PRIVATE+'/service-day-logs/preview',json={**body,'line_id_token':'','flow_id':'claimed-flow'},headers={'Authorization':'Bearer '+self.token})
            self.assertEqual(response.status_code,401)
            for path in ('/internal/v1/runtime/check', '/internal/v1/runtime/durable-jobs/run-once'):
                response=await c.post(path,json={},headers={'Authorization':'Bearer '+self.token})
                self.assertEqual(response.status_code,403,response.text)
        # No private endpoints, filesystem listing, generic download or delete on public origin.
        async with self.caller() as c:
            for path in (PRIVATE+'/service-day-media', '/api/v1/storage/files', '/api/v1/admin/accounts'):
                self.assertEqual((await c.get(path)).status_code,404)
            self.assertEqual((await c.delete(PUBLIC+'/service-day-logs/1')).status_code,404)
        registry=self.root/'credentials/api/verifiers.json'
        data=json.loads(registry.read_text()); del data['services']['line-media-proxy']
        registry.chmod(0o600)  # Test owner simulates explicit credential revocation.
        registry.write_text(json.dumps(data))
        with self.assertRaises(LineMediaError) as revoked:
            await self.client.preview(body)
        self.assertEqual(revoked.exception.status_code,503)

    async def test_invalid_type_size_and_staging_reference_do_not_commit(self):
        fields={'line_id_token':'owner-token','assignment_id':'12','service_date':DAY.isoformat(),
                'attachment_kind':'baby_log_photo'}
        async with self.caller() as c:
            for content, mime in ((b'%PDF-invalid', 'application/pdf'), (PNG+b'x'*(10*1024*1024), 'image/png')):
                result=await c.post(PUBLIC+'/service-day-media',data=fields,
                    files={'photo':('bad',content,mime)},headers={'Idempotency-Key':'bad-upload'})
                self.assertEqual(result.status_code,422,result.text)
            body={'line_id_token':'owner-token','assignment_id':12,'service_date':DAY.isoformat(),
                'baby_log_text':'test','controlled_file_attachments':[{'staging_id':'cfs_'+'9'*32,
                'sha256_digest':'a'*64,'attachment_kind':'baby_log_photo'}]}
            response=await c.post(PUBLIC+'/service-day-logs/preview',json=body)
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.logs.commits,0)
        self.assertFalse(self.media.staged)

    async def test_untrusted_tls_and_plaintext_are_rejected(self):
        with self.assertRaises(LineMediaError):
            LineMediaClient('http://management-api',str(self.root/'credentials/line-media-proxy/token'),str(self.root/'ca/ca.pem'))
        # OS roots do not trust the private test CA: actual TLS connection fails.
        import ssl
        untrusted=LineMediaClient(self.base,str(self.root/'credentials/line-media-proxy/token'),
                                  ssl.get_default_verify_paths().cafile)
        with self.assertRaises(LineMediaError):
            await untrusted.preview({'line_id_token':'owner-token'})
        self.assertFalse(self.media.staged)

    async def test_unavailable_private_service_never_falls_back_to_local_storage(self):
        self.public.dependency_overrides.pop(get_line_media_client)
        with patch.dict(os.environ, {'LINE_MEDIA_API_BASE_URL':'','LINE_MEDIA_SERVICE_TOKEN_FILE':'','LINE_MEDIA_API_CA_FILE':''}):
            async with self.caller() as c:
                response=await self.photo(c)
        self.assertEqual(response.status_code,503)
        self.assertFalse(self.media.staged)

    async def test_z_line_worker_cli_only_checks_startup_authentication(self):
        import sys
        before=(self.logs.commits,self.logs.submits,len(self.media.staged))
        env={**os.environ,'INTERNAL_API_BASE_URL':self.base,
            'INTERNAL_SERVICE_TOKEN_FILE':str(self.root/'credentials/line-worker/token'),
            'INTERNAL_API_CA_FILE':str(self.root/'ca/ca.pem'),'INTERNAL_API_MAX_ATTEMPTS':'1'}
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','scripts.run_line_worker','--check',
            env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await asyncio.wait_for(process.communicate(),20)
        self.assertEqual(process.returncode,0)
        self.assertIn(b'no work cycle executed',stdout)
        self.assertEqual(before,(self.logs.commits,self.logs.submits,len(self.media.staged)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
