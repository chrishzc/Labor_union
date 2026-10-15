"""Authenticated Client Finance single-case account Query/Apply."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from api.dependencies.admin_auth import require_registry_writer
from api.dependencies.legacy_virtual_account_import import get_case_virtual_account_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.case_virtual_account import CaseVirtualAccountApplyBody, CaseVirtualAccountReceiptView, CaseVirtualAccountView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.case_virtual_account import CaseVirtualAccountApplication, CaseVirtualAccountError


router = APIRouter(prefix="/api/v1/admin/client-finance/cases/{case_no}/virtual-account", tags=["Client Finance"])
_Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


def _run(operation):
    try:
        return BaseResponse(data=asdict(operation()), message="虛擬帳號資料")
    except CaseVirtualAccountError as exc:
        category = {404: "not_found", 503: "unavailable"}.get(exc.status, "conflict")
        raise typed_http_error(exc.status, category, exc.code, str(exc), "case-virtual-account") from exc
    except ValueError as exc:
        raise typed_http_error(422, "validation", "case_virtual_account_invalid", str(exc), "case-virtual-account") from exc


@router.get("", response_model=BaseResponse[CaseVirtualAccountView])
def query_case_account(case_no: str, principal: AdminPrincipal = Depends(require_registry_writer), application: CaseVirtualAccountApplication = Depends(get_case_virtual_account_application)):
    return _run(lambda: application.query(case_no))


@router.post("/apply", response_model=BaseResponse[CaseVirtualAccountReceiptView])
def apply_case_account(case_no: str, body: CaseVirtualAccountApplyBody, idempotency_key: _Key, principal: AdminPrincipal = Depends(require_registry_writer), application: CaseVirtualAccountApplication = Depends(get_case_virtual_account_application)):
    return _run(lambda: application.apply(case_no, body.virtual_account, body.expected_mapping_ids, idempotency_key, str(principal.username)))
