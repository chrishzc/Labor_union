from typing import Annotated
from fastapi import APIRouter,Depends,Header,HTTPException,Path
from pydantic import BaseModel,ConfigDict,Field
from api.dependencies.admin_auth import admin_actor_context, require_system_admin
from api.dependencies.client_deposit_skip import Application,get_client_deposit_skip_application
from api.schemas.base import BaseResponse
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId,ExpectedVersion,IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.deposit_skip_workflow import DepositSkipApplyRequest,DepositSkipError,DepositSkipSelection
router=APIRouter(prefix="/api/v1/orders/{case_no}/client-finance/deposit-skip",tags=["Client Finance"])
class ApplyBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_account_version:int=Field(ge=0)
    preview_fingerprint:str=Field(pattern=r"^[0-9a-f]{64}$")
    reason:str=Field(min_length=1,max_length=500)
def _payload(c):return {"case_no":c.case_no,"expected_account_version":c.expected_account_version,"resulting_account_version":c.resulting_account_version,"deposit_required_ntd":c.deposit_required_ntd,"deposit_net_received_ntd":c.deposit_net_received_ntd,"unpaid_progression_allowed":c.override_active,"mutates":c.mutates,"blockers":list(c.blockers),"preview_fingerprint":c.fingerprint.value}
@router.post("/preview")
def preview(case_no:str=Path(...),_:AdminPrincipal=Depends(require_system_admin),application:Application=Depends(get_client_deposit_skip_application)):
    return BaseResponse(data=_payload(application.preview(DepositSkipSelection(case_no))),message="成功產生訂金未付人工放行預覽")
@router.post("/apply")
def apply(body:ApplyBody,case_no:str=Path(...),idempotency_key:Annotated[str,Header(alias="Idempotency-Key")]=...,correlation_id:Annotated[str,Header(alias="X-Correlation-ID")]=...,principal:AdminPrincipal=Depends(require_system_admin),application:Application=Depends(get_client_deposit_skip_application)):
    correlation=CorrelationId(correlation_id)
    try:r=application.apply(DepositSkipApplyRequest(DepositSkipSelection(case_no),ExpectedVersion(body.expected_account_version),PreviewFingerprint(body.preview_fingerprint),IdempotencyKey(idempotency_key),admin_actor_context(principal),body.reason.strip(),correlation))
    except DepositSkipError as e:raise HTTPException(409,detail={"category":e.error.category.value,"code":e.error.code,"message":e.error.message,"domain_blockers":list(e.error.domain_blockers),"correlation_id":correlation.value}) from e
    return BaseResponse(data={"case_no":r.case_no,"account_version":r.account_version,"unpaid_progression_allowed":r.unpaid_progression_allowed,"replayed":r.replayed},message="已允許在訂金未付時推進")
