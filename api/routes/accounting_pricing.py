"""
File: accounting_pricing.py
Description: 驗證帳務計價政策與個案計價命令路由，目錄唯讀查詢接入受控快取並於提交後失效。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.accounting_pricing import (
    get_pricing_application,
    invalidate_pricing_catalog_cache,
    query_cached_pricing_catalog_view,
)
from api.error_contracts import typed_http_error
from api.schemas.accounting_pricing import (
    CasePricingApplyBody, CasePricingPreviewBody, CasePricingPreviewView, CasePricingView,
    PricingCatalogView, PricingImpactView, PricingReceiptView, CasePricingTermsBody, SavePricingPolicyBody,
)
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.pricing_configuration import PricingConfigurationApplication, PricingConflict


LOGGER = logging.getLogger("labor_union.api.routes.accounting_pricing")
router = APIRouter(prefix="/api/v1/accounting-pricing", tags=["Accounting Pricing"])
Application = Annotated[PricingConfigurationApplication, Depends(get_pricing_application)]
Principal = Annotated[AdminPrincipal, Depends(require_system_admin)]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


def _error(error):
    if isinstance(error, OperationalError):
        if error.args and error.args[0] in {1205, 1213}:
            return typed_http_error(409, "conflict", "pricing_write_conflict", "資料正在變更，請重新查詢後再儲存。", "pricing")
        return typed_http_error(503, "unavailable", "pricing_storage_unavailable", "計價資料暫時無法讀取，請稍後重試。", "pricing")
    if isinstance(error, IntegrityError):
        return typed_http_error(409, "conflict", "pricing_write_conflict", "資料已變更或操作識別重複，請重新查詢。", "pricing")
    code = getattr(error, "code", str(error))
    conflict = isinstance(error, PricingConflict)
    return typed_http_error(409 if conflict else 422, "conflict" if conflict else "validation",
        code, "資料已變更，請重新查詢後再儲存。" if conflict else "計價資料不完整或不符合規則。", "pricing")


def _case_view(facts, impact):
    return CasePricingView(case_no=facts.case_no, revision=facts.revision, source=facts.source,
        terms=CasePricingTermsBody.model_validate(facts.terms), impact=PricingImpactView.model_validate(impact))


@router.get("", response_model=BaseResponse[PricingCatalogView])
def query_catalog(request: Request, principal: Principal):
    del principal
    try:
        return BaseResponse(data=query_cached_pricing_catalog_view(request), message="帳務參數版本")
    except (ValueError, OperationalError) as error:
        raise _error(error) from error


@router.post("/policies", response_model=BaseResponse[PricingReceiptView])
def save_policy(body: SavePricingPolicyBody, principal: Principal, application: Application, key: CommandKey):
    try:
        revision = application.save_policy(body.policy.domain(), body.expected_revision, principal.username, body.reason.strip(), key)
    except (ValueError, IntegrityError, OperationalError) as error:
        raise _error(error) from error
    try:
        invalidate_pricing_catalog_cache()
    except Exception:
        LOGGER.exception("Pricing catalog cache invalidation failed after committed save")
    return BaseResponse(data=PricingReceiptView(revision=revision), message="新政策版本已儲存")


@router.get("/cases/{case_no}", response_model=BaseResponse[CasePricingView])
def query_case(case_no: str, principal: Principal, application: Application):
    del principal
    try:
        facts, impact = application.query_case(case_no)
        return BaseResponse(data=_case_view(facts, impact), message="本案計價設定")
    except (ValueError, OperationalError) as error:
        raise _error(error) from error


@router.post("/cases/{case_no}/preview", response_model=BaseResponse[CasePricingPreviewView])
def preview_case(case_no: str, body: CasePricingPreviewBody, principal: Principal, application: Application):
    del principal
    try:
        preview = application.preview_case(case_no, body.terms.domain(), body.expected_revision)
        return BaseResponse(data=CasePricingPreviewView(current=_case_view(preview.facts, preview.before),
            candidate=CasePricingTermsBody.model_validate(preview.candidate),
            before=PricingImpactView.model_validate(preview.before), after=PricingImpactView.model_validate(preview.after),
            preview_fingerprint=preview.fingerprint), message="個案計價影響預覽")
    except (ValueError, OperationalError) as error:
        raise _error(error) from error


@router.post("/cases/{case_no}/apply", response_model=BaseResponse[PricingReceiptView])
def apply_case(case_no: str, body: CasePricingApplyBody, principal: Principal, application: Application, key: CommandKey):
    try:
        revision = application.apply_case(case_no, body.terms.domain(), body.expected_revision,
            body.preview_fingerprint, principal.username, body.reason.strip(), key)
        return BaseResponse(data=PricingReceiptView(revision=revision), message="本案人工計價已儲存")
    except (ValueError, IntegrityError, OperationalError) as error:
        raise _error(error) from error
