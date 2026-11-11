"""
File: line_onboarding.py
Description: [RETIRED] 加入好友歡迎訊息設定入口已退役，改由 LINE 官方帳號設定並回傳 410。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies.admin_auth import (
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/line/onboarding", tags=["LINE Onboarding"])

_RETIRED_ONBOARDING_DETAIL = {
    "code": "line_onboarding_welcome_retired",
    "message": "加入好友歡迎訊息已退役，請改於 LINE 官方帳號後台設定。",
}


@router.get("", status_code=410)
def get_onboarding_message(
    _principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> None:
    raise HTTPException(status_code=410, detail=_RETIRED_ONBOARDING_DETAIL)


@router.post("/preview", status_code=410)
def preview_onboarding_message(
    _principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> None:
    raise HTTPException(status_code=410, detail=_RETIRED_ONBOARDING_DETAIL)


@router.put("", status_code=410)
def update_onboarding_message(
    _principal: AdminPrincipal = Depends(require_line_configuration_manager),
) -> None:
    raise HTTPException(status_code=410, detail=_RETIRED_ONBOARDING_DETAIL)


__all__ = [
    "router",
    "get_onboarding_message",
    "preview_onboarding_message",
    "update_onboarding_message",
]
