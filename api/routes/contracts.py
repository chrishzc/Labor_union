"""Read-only typed contract context endpoint for one formal assignment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.admin_auth import require_contract_evidence_reader
from api.dependencies.contract_context import get_contract_context_service
from api.error_contracts import internal_query_error
from api.schemas.base import BaseResponse
from api.schemas.contract_context import ContractContextView
from subsystems.contract_integration.contract_context import (
    ContractContextAmbiguous,
    ContractContextContractError,
    ContractContextNotFound,
    ContractContextQueryService,
)

router = APIRouter(prefix="/api/v1/contracts", tags=["Contracts"])


@router.get("/staff/{case_no}", response_model=BaseResponse[ContractContextView])
def get_staff_contract_by_case_no(
    case_no: str,
    assignment_id: int | None = Query(default=None, ge=1),
    _=Depends(require_contract_evidence_reader),
    service: ContractContextQueryService = Depends(get_contract_context_service),
) -> BaseResponse[ContractContextView]:
    try:
        result = service.query(case_no, assignment_id)
    except ContractContextNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ContractContextAmbiguous as error:
        raise HTTPException(422, str(error)) from error
    except ContractContextContractError as error:
        raise internal_query_error(
            "contract_context_projection_invalid",
            "契約內容查詢資料無效。",
            case_no,
        ) from error
    return BaseResponse(
        data=ContractContextView.from_projection(result),
        message="contract context loaded",
    )

__all__ = ["router"]
