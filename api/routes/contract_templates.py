"""Authenticated Excel template inspection, immutable saves and explicit activation."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile, Response
from urllib.parse import quote

from api.dependencies.admin_auth import AdminPrincipal, admin_actor_context, require_system_admin
from api.dependencies.contract_templates import get_contract_template_management
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.contract_templates import ActivateTemplateBody, TemplateCatalogView, TemplateMutationView, WorkbookPreviewView
from domains.contract_signing.template_management import TemplateManagementError
from infrastructure.file.contract_template_workbook import MAX_TEMPLATE_BYTES
from subsystems.contract_signing.template_management import ContractTemplateManagement

router = APIRouter(prefix='/api/v1/contract-templates', tags=['Contract templates'])


def _call(operation: Callable, correlation: str):
    try:
        return operation()
    except TemplateManagementError as error:
        status = {'validation': 422, 'forbidden': 403, 'not_found': 404, 'conflict': 409, 'idempotency_mismatch': 409, 'unavailable': 503}.get(error.category, 422)
        raise typed_http_error(status, error.category, error.code, str(error), correlation) from error
    except OSError as error:
        raise typed_http_error(503, 'unavailable', 'contract_template_storage_unavailable', '模板儲存暫時無法使用，請保留目前內容並核對原操作結果。', correlation) from error


def _assignments(raw: str) -> dict[str, str]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate cell')
            result[key] = value
        return result
    try:
        parsed = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(parsed, dict) or len(parsed) > 5000 or not all(isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()):
            raise ValueError('invalid mapping')
        return parsed
    except (ValueError, TypeError) as error:
        raise TemplateManagementError('validation', 'contract_template_assignments_invalid', '欄位映射格式無效或包含重複位置。') from error


def _content(document: UploadFile) -> bytes:
    content = document.file.read(MAX_TEMPLATE_BYTES + 1)
    if len(content) > MAX_TEMPLATE_BYTES:
        raise TemplateManagementError('validation', 'contract_template_size_invalid', '模板超過目前支援的 20 MB。')
    return content


def _source(application: ContractTemplateManagement, template_key: str, document: UploadFile | None, source_version_id: str | None):
    if document is not None:
        return _content(document), document.filename or ''
    if source_version_id:
        content, _mapping, metadata = application.store.content(template_key, source_version_id)
        return content, metadata.filename
    raise TemplateManagementError('validation', 'contract_template_source_required', '請上傳 Excel 或選擇已保存的模板版本。')


def _actor(principal: AdminPrincipal) -> str:
    identity = admin_actor_context(principal).actor_id
    if identity == 'admin:development':
        raise TemplateManagementError('forbidden', 'contract_template_actor_required', '保存或啟用模板需要有效的管理員帳號。')
    return identity


@router.get('/{template_key}', response_model=BaseResponse[TemplateCatalogView])
def query_template_catalog(template_key: str, _principal: AdminPrincipal = Depends(require_system_admin),
                           application: ContractTemplateManagement = Depends(get_contract_template_management)):
    return _call(lambda: BaseResponse(data=TemplateCatalogView.model_validate(application.query(template_key)), message='模板版本已讀取'), 'contract-template-query')


@router.get('/{template_key}/versions/{version_id}', response_model=BaseResponse[WorkbookPreviewView])
def read_template_version(template_key: str, version_id: str, sample: bool = False,
                          _principal: AdminPrincipal = Depends(require_system_admin),
                          application: ContractTemplateManagement = Depends(get_contract_template_management)):
    return _call(lambda: BaseResponse(data=WorkbookPreviewView.model_validate(application.read_version(template_key, version_id, sample=sample)), message='模板內容已讀取'), 'contract-template-version')


@router.get('/{template_key}/versions/{version_id}/download')
def download_template_version(template_key: str, version_id: str,
                              _principal: AdminPrincipal = Depends(require_system_admin),
                              application: ContractTemplateManagement = Depends(get_contract_template_management)):
    def download():
        content, _mapping, metadata = application.store.content(template_key, version_id)
        return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(metadata.filename, safe=''), 'Cache-Control': 'no-store'})
    return _call(download, 'contract-template-download')


@router.post('/{template_key}/inspect', response_model=BaseResponse[WorkbookPreviewView])
def inspect_template(template_key: str, document: UploadFile | None = File(None), worksheet_name: str | None = Form(None),
                     source_version_id: str | None = Form(None, max_length=64),
                     assignments: str = Form('{}', max_length=200000), sample: bool = Form(False),
                     _principal: AdminPrincipal = Depends(require_system_admin),
                     application: ContractTemplateManagement = Depends(get_contract_template_management)):
    def inspect():
        content, filename = _source(application, template_key, document, source_version_id)
        return BaseResponse(data=WorkbookPreviewView.model_validate(application.inspect(template_key, content,
            filename, worksheet_name, _assignments(assignments), sample=sample)), message='模板預覽已完成，尚未保存')
    return _call(inspect, 'contract-template-inspect')


@router.get('/{template_key}/commands/{idempotency_key}', response_model=BaseResponse[TemplateMutationView | None])
def read_template_command(template_key: str, idempotency_key: str,
                          _principal: AdminPrincipal = Depends(require_system_admin),
                          application: ContractTemplateManagement = Depends(get_contract_template_management)):
    def read():
        result = application.receipt(template_key, idempotency_key)
        return BaseResponse(data=None if result is None else TemplateMutationView.model_validate(result), message='原操作結果已核對')
    return _call(read, 'contract-template-command')


@router.post('/{template_key}/versions', response_model=BaseResponse[TemplateMutationView])
def save_template_version(template_key: str, document: UploadFile | None = File(None), worksheet_name: str | None = Form(None),
                          source_version_id: str | None = Form(None, max_length=64),
                          assignments: str = Form(..., max_length=200000), expected_version: int = Form(..., ge=0),
                          idempotency_key: Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=191)] = ...,
                          correlation_id: Annotated[str, Header(alias='X-Correlation-ID', min_length=1, max_length=191)] = ...,
                          principal: AdminPrincipal = Depends(require_system_admin),
                          application: ContractTemplateManagement = Depends(get_contract_template_management)):
    def save():
        content, filename = _source(application, template_key, document, source_version_id)
        return BaseResponse(data=TemplateMutationView.model_validate(application.save(template_key, content,
            filename, worksheet_name, _assignments(assignments), expected_version, _actor(principal), idempotency_key)), message='模板版本已保存，尚未啟用')
    return _call(save, correlation_id)


@router.post('/{template_key}/activate', response_model=BaseResponse[TemplateMutationView])
def activate_template_version(template_key: str, body: ActivateTemplateBody,
                              idempotency_key: Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=191)] = ...,
                              correlation_id: Annotated[str, Header(alias='X-Correlation-ID', min_length=1, max_length=191)] = ...,
                              principal: AdminPrincipal = Depends(require_system_admin),
                              application: ContractTemplateManagement = Depends(get_contract_template_management)):
    return _call(lambda: BaseResponse(data=TemplateMutationView.model_validate(application.activate(template_key, body.version_id,
        body.expected_version, _actor(principal), idempotency_key)), message='模板版本已啟用，既有契約保持原版本'), correlation_id)
