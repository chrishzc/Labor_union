"""Retired unbounded Client list and direct identity-status mutation entries."""

from fastapi import APIRouter, HTTPException, Path, status

router = APIRouter(prefix="/api/v1/clients", tags=["Clients 客戶名冊"])


@router.get("")
def get_all_clients() -> None:
    """Retired unbounded list; callers must use an owning typed projection."""
    raise _retired(
        code="client_full_list_endpoint_retired",
        message="全量客戶名冊查詢已退役，請改用有界的 owner projection。",
        replacements=("/api/v1/admin/data-browser/sources/clients",),
        correlation_id="client-list-retired",
    )


@router.put("/{client_id}/identity-status")
def update_client_identity_status(
    client_id: int = Path(..., ge=1),
) -> None:
    """Retired direct mutation; HCM correction requires a complete source resubmission."""
    raise _retired(
        code="client_identity_status_direct_update_retired",
        message="客戶身分資格不接受單欄直接修改，請重送完整 HCM 修正來源。",
        replacements=(
            "/api/v1/case-import/hcm/resubmissions/preview",
            "/api/v1/case-import/hcm/resubmissions/apply",
        ),
        correlation_id=f"client-identity-status-retired:{client_id}",
    )


def _retired(
    *, code: str, message: str, replacements: tuple[str, ...], correlation_id: str
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error": {
                "category": "not_found",
                "code": code,
                "message": message,
                "field_errors": [],
                "domain_blockers": [
                    f"replacement_identifier:{replacement}"
                    for replacement in replacements
                ],
                "retryable": False,
                "correlation_id": correlation_id,
                "current_version": None,
            }
        },
    )
