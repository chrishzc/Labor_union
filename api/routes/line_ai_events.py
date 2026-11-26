"""M2 deterministic catalog, curated QA, and feedback readback routes."""

import os
from dataclasses import asdict
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.admin_auth import optional_admin, require_line_configuration_reader
from api.dependencies.line_runtime import get_line_feedback_application
from api.schemas.base import BaseResponse
from api.schemas.line_ai_events import (
    LineNavigationAliasesUpdateRequest,
    LineRouterPreviewRequest,
    LineRouterPreviewView,
)
from api.schemas.line_feedback import (
    LineFeedbackAggregateView,
    LineNavigationCatalogView,
    LineNavigationEntryView,
    LineNavigationRecentRepliesView,
    LineNavigationReplyView,
)
from domains.line.identities import LineUserId
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.ai_router_contracts import Unavailable
from subsystems.line.deterministic_ai_router import DeterministicLineRouter, score_band
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactQuery
from subsystems.line.navigation_catalog import (
    CATALOG_REVISION,
    CATALOG_SOURCE_IDENTITY,
    catalog_entries,
    get_current_revision,
    reset_route_aliases,
    update_route_aliases,
)


router = APIRouter(prefix="/api/v1/line/ai-events", tags=["LINE AI Events"])


@router.post("/router/preview", response_model=BaseResponse[LineRouterPreviewView])
def preview_router(
    request: LineRouterPreviewRequest,
    principal: AdminPrincipal | None = Depends(optional_admin),
):
    if not isinstance(principal, AdminPrincipal):
        _require_development_router_preview()
    router_outcome = DeterministicLineRouter().route(
        request.text, source_event_id=request.source_event_id, score=request.score
    )
    if request.apply_manual_fallback:
        raise HTTPException(status_code=410, detail="manual_fallback_retired")
    return BaseResponse(data=_router_preview_view(
        router_outcome, request.source_event_id, request.score
    ))


@router.get("/catalog", response_model=BaseResponse[LineNavigationCatalogView])
def get_navigation_catalog(
    _: AdminPrincipal = Depends(require_line_configuration_reader),
):
    entries = catalog_entries()
    revision = get_current_revision()
    return BaseResponse(
        data=LineNavigationCatalogView(
            revision=revision,
            entries=tuple(LineNavigationEntryView.model_validate(asdict(entry)) for entry in entries),
        )
    )


@router.put("/catalog/{route_key}/aliases", response_model=BaseResponse[LineNavigationCatalogView])
def update_catalog_aliases(
    route_key: str,
    payload: LineNavigationAliasesUpdateRequest,
    _: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        new_revision, entries = update_route_aliases(route_key, list(payload.aliases))
    except KeyError:
        raise HTTPException(status_code=404, detail="route_key_not_found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except OSError as error:
        raise HTTPException(status_code=500, detail=str(error))
    return BaseResponse(
        data=LineNavigationCatalogView(
            revision=new_revision,
            entries=tuple(LineNavigationEntryView.model_validate(asdict(entry)) for entry in entries),
        ),
        message=f"已成功更新「{route_key}」的觸發指令",
    )


@router.post("/catalog/{route_key}/reset", response_model=BaseResponse[LineNavigationCatalogView])
def reset_catalog_aliases(
    route_key: str,
    _: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        new_revision, entries = reset_route_aliases(route_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="route_key_not_found")
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=str(error))
    return BaseResponse(
        data=LineNavigationCatalogView(
            revision=new_revision,
            entries=tuple(LineNavigationEntryView.model_validate(asdict(entry)) for entry in entries),
        ),
        message=f"已將「{route_key}」的觸發指令恢復預設",
    )


@router.get("/qa-catalog", include_in_schema=False)
@router.post("/qa-catalog", include_in_schema=False)
@router.put("/qa-catalog/{qa_id}", include_in_schema=False)
@router.patch("/qa-catalog/{qa_id}/status", include_in_schema=False)
@router.delete("/qa-catalog/{qa_id}", include_in_schema=False)
def retired_file_qa_catalog(
    _: AdminPrincipal = Depends(require_line_configuration_reader),
):
    raise HTTPException(status_code=410, detail="line_file_qa_catalog_retired")


@router.get("/feedback/aggregate", response_model=BaseResponse[LineFeedbackAggregateView])
def get_feedback_aggregate(
    _: AdminPrincipal = Depends(require_line_configuration_reader),
    knowledge_only: bool = False,
):
    now = datetime.now(timezone.utc)
    window_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    catalog_revision = None if knowledge_only else CATALOG_REVISION
    aggregate = get_line_feedback_application().aggregate(catalog_revision, window_start, now)
    return BaseResponse(
        data=LineFeedbackAggregateView(
            catalog_revision=aggregate.catalog_revision,
            window_start=aggregate.window_start.isoformat(),
            window_end=aggregate.window_end.isoformat(),
            resolved_count=aggregate.resolved_count,
            unresolved_count=aggregate.unresolved_count,
            total_count=aggregate.total_count,
            resolved_rate=aggregate.resolved_rate,
        )
    )


@router.get("/replies/recent", response_model=BaseResponse[LineNavigationRecentRepliesView])
def get_recent_navigation_replies(
    _: AdminPrincipal = Depends(require_line_configuration_reader),
    development_line_user_id: str = Query(default="", max_length=191),
):
    """Read server-owned reply identities for the explicit local disposable actor.

    This endpoint never invents a response identity and is intentionally closed
    outside the local development identity-bypass contract.
    """
    actor = development_line_user_id.strip()
    if not _development_identity_fallback_enabled() or not actor:
        raise HTTPException(status_code=403, detail="development_line_identity_required")
    line_user_id = LineUserId(actor)
    with open_line_unit_of_work() as unit_of_work:
        fact = unit_of_work.identity_management.current_fact(
            LineIdentityCurrentFactQuery(line_user_id)
        )
        if fact.root_version is None or not fact.owner_projections:
            raise HTTPException(status_code=403, detail="line_reply_binding_not_current")
        replies = unit_of_work.notification_rules.list_router_replies(actor, limit=5)
    return BaseResponse(
        data=LineNavigationRecentRepliesView(
            items=tuple(
                LineNavigationReplyView(
                    source_response_id=reply.source_response_id,
                    source_event_id=reply.source_event_id,
                    reply_kind=reply.reply_kind,
                    reason_code=reply.reason_code,
                    source_identity=reply.source_identity,
                    source_revision=reply.source_revision,
                )
                for reply in replies
            )
        )
    )


def _development_identity_fallback_enabled() -> bool:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    access_profile = os.getenv("ACCESS_CONTROL_PROFILE", "").strip().lower()
    required = os.getenv("LIFF_REQUIRE_ID_TOKEN", "true").strip().lower()
    return (
        access_profile == "local_auth"
        and app_env in {"development", "dev", "local", "test"}
        and required in {"0", "false", "no", "off"}
    )


def _require_development_router_preview() -> None:
    if not _development_identity_fallback_enabled():
        raise HTTPException(status_code=404, detail="development_router_preview_unavailable")


def _router_preview_view(
    outcome, source_event_id: str, requested_score: int | None = None
):
    kind = outcome.kind.value
    source_identity = getattr(outcome, "source_identity", CATALOG_SOURCE_IDENTITY)
    source_revision = int(getattr(outcome, "source_revision", 1))
    semantic_bucket = str(getattr(outcome, "semantic_bucket", "answer"))
    confidence = int(getattr(outcome, "confidence", requested_score if requested_score is not None else 100))
    outcome_score_band = getattr(outcome, "score_band", None)
    if outcome_score_band is None and isinstance(outcome, Unavailable) and requested_score is not None:
        outcome_score_band = score_band(requested_score)
    route_key = getattr(outcome, "route_key", None)
    return LineRouterPreviewView(
        kind=kind,
        source_event_id=source_event_id,
        source_identity=source_identity,
        source_revision=source_revision,
        semantic_bucket=semantic_bucket,
        confidence=confidence,
        score_band=outcome_score_band,
        reason_code=getattr(outcome, "reason_code", getattr(outcome, "code", None)),
        route_key=route_key,
        options=tuple(getattr(outcome, "options", ())),
        answer_text=getattr(outcome, "text", getattr(outcome, "human_action", None)),
        ticket_id=None,
        apply_ready=False,
    )


__all__ = ["router"]
