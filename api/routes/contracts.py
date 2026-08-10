"""Read-only typed contract context endpoint for one formal assignment."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.admin_auth import require_contract_evidence_reader
from api.dependencies.contract_context import get_contract_context_service
from api.schemas.base import BaseResponse
from infrastructure.mysql.contract_context_repository import MySqlContractContextRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.contract_integration.contract_context import (
    ContractContextAmbiguous,
    ContractContextNotFound,
    ContractContextQueryService,
)

router = APIRouter(prefix="/api/v1/contracts", tags=["Contracts"])


@router.get("/staff/{case_no}", response_model=BaseResponse[dict[str, Any]])
def get_staff_contract_by_case_no(
    case_no: str,
    assignment_id: int | None = Query(default=None, ge=1),
    _=Depends(require_contract_evidence_reader),
    service: ContractContextQueryService = Depends(get_contract_context_service),
):
    try:
        result = service.query(case_no, assignment_id)
    except ContractContextNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ContractContextAmbiguous as error:
        raise HTTPException(422, str(error)) from error
    return BaseResponse(data=result, message="contract context loaded")


def get_staff_contract_context(case_no: str, assignment_id: int | None = None):
    """Compatibility query facade; SQL and selection remain outside the route module."""
    connection = get_connection()
    try:
        service = ContractContextQueryService(MySqlContractContextRepository(connection))
        try:
            return service.query(case_no, assignment_id)
        except ContractContextNotFound as error:
            raise HTTPException(404, str(error)) from error
        except ContractContextAmbiguous as error:
            raise HTTPException(422, str(error)) from error
    finally:
        connection.close()


__all__ = ["get_staff_contract_context", "router"]
