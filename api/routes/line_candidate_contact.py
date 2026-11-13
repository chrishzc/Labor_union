"""Verified caregiver-facing LIFF endpoints for candidate-pool responses."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


page_router = APIRouter(tags=["LINE Candidate Contact Page"])


@page_router.get("/line-candidate-contact", include_in_schema=False)
@page_router.get("/line-candidate-contact-customer", include_in_schema=False)
def retired_candidate_contact_page():
    return HTMLResponse(
        '<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>候選聯絡表單已停止受理</title><main><h1>候選聯絡表單已停止受理</h1>'
        '<p>有疑問請直接聯絡工會。</p></main></html>',
        status_code=410,
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["page_router"]
