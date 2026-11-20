"""Authenticated bounded read of current import fields across HCM and BeClass."""
from fastapi import APIRouter, Depends, Query

from api.dependencies.admin_auth import require_admin
from api.dependencies.import_field_issues import get_import_field_issues_query
from api.schemas.base import BaseResponse
from api.schemas.import_field_issues import ImportFieldIssuePageView

router = APIRouter(prefix="/api/v1/case-import", tags=["Case Import"])


@router.get("/field-issues", response_model=BaseResponse[ImportFieldIssuePageView])
def query_import_field_issues(page: int = Query(1, ge=1),
                              page_size: int = Query(20, ge=1, le=100),
                              case_no: str | None = Query(None, min_length=1, max_length=50, pattern=r"\S"),
                              principal=Depends(require_admin),
                              application=Depends(get_import_field_issues_query)):
    del principal
    return BaseResponse(data=application.query_page(page, page_size, case_no).as_dict(),
                        message="目前進件欄位待補正資料")
