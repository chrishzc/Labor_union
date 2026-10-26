"""Admin-only query and human confirmation of government-funded recovery."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.subsidy_advance_settlement import get_advance_settlement_application
from api.schemas.base import BaseResponse
from api.schemas.subsidy_advance_settlement import (
    AdvanceSettlementApplyBody, AdvanceSettlementPageView,
    AdvanceSettlementPreviewView, AdvanceSettlementReceiptView,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.client_finance.subsidy_advance_settlement import (
    AdvanceSettlementApplication, AdvanceSettlementCommand, AdvanceSettlementConflict,
)

def _read_only_legacy_recovery(request: Request,principal=Depends(require_system_admin)):
    if request.method=='POST':
        from api.error_contracts import typed_http_error
        raise typed_http_error(410,'validation','subsidy_period_recovery_required',
            '代墊回收已改由政府整期入款核銷同步處理。','subsidy-period')


router = APIRouter(prefix='/api/v1/client-finance/subsidy-advance-recoveries', tags=['Client Finance'],dependencies=[Depends(_read_only_legacy_recovery)])
Application = Annotated[AdvanceSettlementApplication, Depends(get_advance_settlement_application)]
Admin = Annotated[AdminPrincipal, Depends(require_system_admin)]


def _call(action):
    try:
        return BaseResponse(data=action())
    except AdvanceSettlementConflict as error:
        category = (ErrorCategory.NOT_FOUND if error.code == 'subsidy_advance_not_found' else
                    ErrorCategory.IDEMPOTENCY_MISMATCH if error.code == 'idempotency_mismatch' else ErrorCategory.CONFLICT)
        raise _http_error(404 if category is ErrorCategory.NOT_FOUND else 409, category, error.code) from error
    except IntegrityError as error:
        if error.args and error.args[0] == 1062:
            raise _http_error(409, ErrorCategory.CONFLICT, 'subsidy_advance_write_conflict') from error
        raise
    except OperationalError as error:
        if error.args and error.args[0] in (1205, 1213):
            raise _http_error(503, ErrorCategory.UNAVAILABLE, 'transaction_temporarily_unavailable') from error
        raise


def _http_error(status, category, code):
    error = TypedError(category, code, '墊款資料已變更或不符合銷帳條件，請重新查詢。',
                       CorrelationId('subsidy-advance-settlement'), retryable=category is ErrorCategory.UNAVAILABLE)
    payload = asdict(error)
    payload['category'] = error.category.value
    payload['correlation_id'] = error.correlation_id.value
    return HTTPException(status, detail={'error': payload})


@router.get('', response_model=BaseResponse[AdvanceSettlementPageView])
def query_advance_settlements(application: Application, principal: Admin,
                              after_id: int = Query(0, ge=0), page_size: int = Query(100, ge=1, le=100),
                              search: str | None = Query(None, max_length=100)):
    return _call(lambda: application.query(after_id, search.strip() if search else None, page_size))


@router.post('/{advance_id}/preview', response_model=BaseResponse[AdvanceSettlementPreviewView])
def preview_advance_settlement(application: Application, principal: Admin,
                               advance_id: int = Path(..., gt=0)):
    return _call(lambda: asdict(application.preview(advance_id)))


@router.post('/{advance_id}/apply', response_model=BaseResponse[AdvanceSettlementReceiptView])
def apply_advance_settlement(body: AdvanceSettlementApplyBody, application: Application, principal: Admin,
                             idempotency_key: Annotated[str, Header(alias='Idempotency-Key', pattern=r'^[a-z0-9][a-z0-9._:-]{0,190}$')],
                             advance_id: int = Path(..., gt=0)):
    command = AdvanceSettlementCommand(advance_id, body.expected_account_version,
                                      body.expected_batch_version, body.preview_fingerprint,
                                      idempotency_key, principal.username, body.reason)
    return _call(lambda: application.apply(command))
