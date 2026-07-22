"""Validated configuration APIs for LINE, LIFF and customer service clients."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ValidationError

from api.schemas.line_config import (
    CustomerServiceConfig,
    LiffField,
    LiffPage,
    LiffSettingsConfig,
    LiffTheme,
    LineMenusConfig,
    MessageTemplate,
    MessageTemplateDraftPreviewRequest,
    MessageTemplatePreviewRequest,
    MessageTemplatesConfig,
    MessageSchedulesConfig,
    RichMenuDefinition,
)
from services.json_config_service import (
    config_revision,
    find_by_id,
    read_config,
    upsert_by_id,
    write_config,
)
from api.dependencies.admin_auth import require_line_manager, require_line_viewer


router = APIRouter(
    prefix="/api/config",
    tags=["System Config"],
    dependencies=[Depends(require_line_viewer)],
)
public_router = APIRouter(prefix="/api/config", tags=["Public LINE Config"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
T = TypeVar("T", bound=BaseModel)
MESSAGE_TEMPLATE_LOCK = threading.RLock()


def _read(name: str, model: type[T]) -> T:
    try:
        return read_config(name, model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Configuration {name} not found") from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"Invalid stored configuration: {exc}") from exc


def _save(name: str, value: BaseModel) -> None:
    try:
        write_config(name, value)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to save configuration: {exc}") from exc


def _publish_rich_menus() -> None:
    subprocess.run(
        ["uv", "run", "python", "line/setup_rich_menus.py"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def _normalize_revision(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    return normalized.strip('"')


def _require_message_template_revision(if_match: str | None) -> None:
    """Reject stale UI drafts while preserving older clients without If-Match."""
    expected = _normalize_revision(if_match)
    if expected and expected != config_revision("message_templates"):
        raise HTTPException(
            status_code=409,
            detail="訊息範本已被其他人修改，請重新載入後再儲存",
        )


def _template_schedule_references(template_id: str) -> list[dict[str, int | str]]:
    schedules = _read("message_schedules", MessageSchedulesConfig)
    return [
        {"schedule_id": schedule.id, "schedule_name": schedule.name, "day": step.day}
        for schedule in schedules.schedules
        if schedule.enabled
        for step in schedule.steps
        if step.template_id == template_id
    ]


def _validate_scheduled_template_availability(config: MessageTemplatesConfig) -> None:
    available = {item.id for item in config.templates if item.enabled}
    schedules = _read("message_schedules", MessageSchedulesConfig)
    missing = sorted(
        {
            step.template_id
            for schedule in schedules.schedules
            if schedule.enabled
            for step in schedule.steps
            if step.template_id not in available
        }
    )
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"啟用中的排程仍引用下列缺少或停用的範本：{', '.join(missing)}",
        )


def _render_message_template(item: MessageTemplate, variables: dict[str, str]) -> dict:
    if item.message_type == "flex":
        return {"message_type": "flex", "content": item.content}
    rendered = str(item.content)
    for variable in item.variables:
        if variable.required and variable.name not in variables:
            raise HTTPException(status_code=422, detail=f"Missing variable: {variable.name}")
        rendered = rendered.replace(
            "{" + variable.name + "}", variables.get(variable.name, "")
        )
    return {"message_type": "text", "content": rendered}


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------
@router.get("/message-templates", response_model=MessageTemplatesConfig)
def get_message_templates():
    return _read("message_templates", MessageTemplatesConfig)


@router.get("/message-templates/state")
def get_message_templates_state():
    return {
        "revision": config_revision("message_templates"),
        "config": _read("message_templates", MessageTemplatesConfig),
    }


@router.post("/message-templates/preview")
def preview_message_template_draft(payload: MessageTemplateDraftPreviewRequest):
    return _render_message_template(payload.template, payload.variables)


@router.put("/message-templates", response_model=MessageTemplatesConfig, dependencies=[Depends(require_line_manager)])
def replace_message_templates(
    payload: MessageTemplatesConfig,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    with MESSAGE_TEMPLATE_LOCK:
        _require_message_template_revision(if_match)
        _validate_scheduled_template_availability(payload)
        _save("message_templates", payload)
    request.state.audit_action = "line.message_templates.replace"
    request.state.audit_resource_type = "line_message_templates"
    request.state.audit_details = {"template_count": len(payload.templates)}
    return payload


@router.post(
    "/message-templates",
    response_model=MessageTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_line_manager)],
)
def create_message_template(
    payload: MessageTemplate,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    with MESSAGE_TEMPLATE_LOCK:
        _require_message_template_revision(if_match)
        config = _read("message_templates", MessageTemplatesConfig)
        if find_by_id(config.templates, payload.id):
            raise HTTPException(status_code=409, detail="Template id already exists")
        config.templates.append(payload)
        validated = MessageTemplatesConfig.model_validate(config)
        _save("message_templates", validated)
    request.state.audit_action = "line.message_template.create"
    request.state.audit_resource_type = "line_message_template"
    request.state.audit_resource_id = payload.id
    request.state.audit_details = {
        "name": payload.name,
        "category": payload.category,
        "message_type": payload.message_type,
        "enabled": payload.enabled,
    }
    return payload


@router.get("/message-templates/{template_id}", response_model=MessageTemplate)
def get_message_template(template_id: str):
    config = _read("message_templates", MessageTemplatesConfig)
    item = find_by_id(config.templates, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Template not found")
    return item


@router.put("/message-templates/{template_id}", response_model=MessageTemplate, dependencies=[Depends(require_line_manager)])
def update_message_template(
    template_id: str,
    payload: MessageTemplate,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    if payload.id != template_id:
        raise HTTPException(status_code=400, detail="Path id and payload id must match")
    with MESSAGE_TEMPLATE_LOCK:
        _require_message_template_revision(if_match)
        config = _read("message_templates", MessageTemplatesConfig)
        if not find_by_id(config.templates, template_id):
            raise HTTPException(status_code=404, detail="Template not found")
        if not payload.enabled:
            references = _template_schedule_references(template_id)
            if references:
                labels = ", ".join(
                    f"{item['schedule_name']} D+{item['day']}" for item in references
                )
                raise HTTPException(
                    status_code=409,
                    detail=f"此範本仍被啟用中的排程引用，無法停用：{labels}",
                )
        config.templates = upsert_by_id(config.templates, payload)
        _save("message_templates", MessageTemplatesConfig.model_validate(config))
    request.state.audit_action = "line.message_template.update"
    request.state.audit_resource_type = "line_message_template"
    request.state.audit_resource_id = template_id
    request.state.audit_details = {
        "name": payload.name,
        "category": payload.category,
        "message_type": payload.message_type,
        "enabled": payload.enabled,
    }
    return payload


@router.delete("/message-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_line_manager)])
def delete_message_template(
    template_id: str,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    with MESSAGE_TEMPLATE_LOCK:
        _require_message_template_revision(if_match)
        config = _read("message_templates", MessageTemplatesConfig)
        original_count = len(config.templates)
        config.templates = [item for item in config.templates if item.id != template_id]
        if len(config.templates) == original_count:
            raise HTTPException(status_code=404, detail="Template not found")
        references = _template_schedule_references(template_id)
        if references:
            labels = ", ".join(
                f"{item['schedule_name']} D+{item['day']}" for item in references
            )
            raise HTTPException(
                status_code=409,
                detail=f"此範本仍被啟用中的排程引用，無法刪除：{labels}",
            )
        _save("message_templates", MessageTemplatesConfig.model_validate(config))
    request.state.audit_action = "line.message_template.delete"
    request.state.audit_resource_type = "line_message_template"
    request.state.audit_resource_id = template_id
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/message-templates/{template_id}/preview", dependencies=[Depends(require_line_manager)])
def preview_message_template(template_id: str, payload: MessageTemplatePreviewRequest):
    item = get_message_template(template_id)
    return _render_message_template(item, payload.variables)


# ---------------------------------------------------------------------------
# Scheduled messages
# ---------------------------------------------------------------------------
@router.get("/message-schedules", response_model=MessageSchedulesConfig)
def get_message_schedules():
    return _read("message_schedules", MessageSchedulesConfig)


@router.put("/message-schedules", response_model=MessageSchedulesConfig, dependencies=[Depends(require_line_manager)])
def replace_message_schedules(payload: MessageSchedulesConfig):
    templates = _read("message_templates", MessageTemplatesConfig)
    enabled_template_ids = {item.id for item in templates.templates if item.enabled}
    missing = sorted({step.template_id for item in payload.schedules for step in item.steps} - enabled_template_ids)
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown or disabled templates: {', '.join(missing)}")
    _save("message_schedules", payload)
    return payload


# ---------------------------------------------------------------------------
# Rich menus
# ---------------------------------------------------------------------------
@router.get("/line-menus", response_model=LineMenusConfig)
def get_line_menus():
    return _read("line_menus", LineMenusConfig)


@router.put("/line-menus", response_model=LineMenusConfig, dependencies=[Depends(require_line_manager)])
def replace_line_menus(payload: LineMenusConfig):
    _save("line_menus", payload)
    return payload


@router.post("/line-menus", response_model=RichMenuDefinition, status_code=201, dependencies=[Depends(require_line_manager)])
def create_line_menu(payload: RichMenuDefinition):
    config = _read("line_menus", LineMenusConfig)
    if find_by_id(config.menus, payload.id):
        raise HTTPException(status_code=409, detail="Menu id already exists")
    config.menus.append(payload)
    _save("line_menus", LineMenusConfig.model_validate(config))
    return payload


@router.get("/line-menus/{menu_id}", response_model=RichMenuDefinition)
def get_line_menu(menu_id: str):
    config = _read("line_menus", LineMenusConfig)
    item = find_by_id(config.menus, menu_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menu not found")
    return item


@router.put("/line-menus/{menu_id}", response_model=RichMenuDefinition, dependencies=[Depends(require_line_manager)])
def update_line_menu(menu_id: str, payload: RichMenuDefinition):
    if payload.id != menu_id:
        raise HTTPException(status_code=400, detail="Path id and payload id must match")
    config = _read("line_menus", LineMenusConfig)
    if not find_by_id(config.menus, menu_id):
        raise HTTPException(status_code=404, detail="Menu not found")
    config.menus = upsert_by_id(config.menus, payload)
    _save("line_menus", LineMenusConfig.model_validate(config))
    return payload


@router.delete("/line-menus/{menu_id}", status_code=204, dependencies=[Depends(require_line_manager)])
def delete_line_menu(menu_id: str):
    config = _read("line_menus", LineMenusConfig)
    item = find_by_id(config.menus, menu_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menu not found")
    if item.set_as_default:
        raise HTTPException(status_code=409, detail="Default menu cannot be deleted")
    config.menus = [menu for menu in config.menus if menu.id != menu_id]
    _save("line_menus", LineMenusConfig.model_validate(config))
    return Response(status_code=204)


@router.post("/line-menus/{menu_id}/preview", dependencies=[Depends(require_line_manager)])
def preview_line_menu(menu_id: str):
    return {"status": "valid", "menu": get_line_menu(menu_id)}


@router.post("/line-menus/{menu_id}/publish", status_code=202, dependencies=[Depends(require_line_manager)])
def publish_line_menu(menu_id: str, background_tasks: BackgroundTasks):
    menu = get_line_menu(menu_id)
    if not menu.enabled:
        raise HTTPException(status_code=409, detail="Disabled menu cannot be published")
    # The current publisher synchronizes all enabled menus in one operation.
    background_tasks.add_task(_publish_rich_menus)
    return {"status": "accepted", "menu_id": menu_id}


# ---------------------------------------------------------------------------
# LIFF settings and dynamic fields
# ---------------------------------------------------------------------------
@public_router.get("/liff", response_model=LiffSettingsConfig)
def get_liff_config():
    return _read("liff", LiffSettingsConfig)


@router.put("/liff", response_model=LiffSettingsConfig, dependencies=[Depends(require_line_manager)])
def replace_liff_config(payload: LiffSettingsConfig):
    _save("liff", payload)
    return payload


@router.put("/liff/theme", response_model=LiffTheme, dependencies=[Depends(require_line_manager)])
def update_liff_theme(payload: LiffTheme):
    config = _read("liff", LiffSettingsConfig)
    config.theme = payload
    _save("liff", config)
    return payload


@router.put("/liff/pages/{page_id}", response_model=LiffPage, dependencies=[Depends(require_line_manager)])
def update_liff_page(page_id: str, payload: LiffPage):
    config = _read("liff", LiffSettingsConfig)
    config.pages[page_id] = payload
    _save("liff", LiffSettingsConfig.model_validate(config))
    return payload


@router.post("/liff/pages/{page_id}/fields", response_model=LiffField, status_code=201, dependencies=[Depends(require_line_manager)])
def create_liff_field(page_id: str, payload: LiffField):
    config = _read("liff", LiffSettingsConfig)
    page = config.pages.get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="LIFF page not found")
    if find_by_id(page.fields, payload.id):
        raise HTTPException(status_code=409, detail="Field id already exists")
    page.fields.append(payload)
    page.fields.sort(key=lambda field: field.order)
    _save("liff", LiffSettingsConfig.model_validate(config))
    return payload


@router.put("/liff/pages/{page_id}/fields/{field_id}", response_model=LiffField, dependencies=[Depends(require_line_manager)])
def update_liff_field(page_id: str, field_id: str, payload: LiffField):
    if payload.id != field_id:
        raise HTTPException(status_code=400, detail="Path id and payload id must match")
    config = _read("liff", LiffSettingsConfig)
    page = config.pages.get(page_id)
    if not page or not find_by_id(page.fields, field_id):
        raise HTTPException(status_code=404, detail="LIFF field not found")
    page.fields = upsert_by_id(page.fields, payload)
    page.fields.sort(key=lambda field: field.order)
    _save("liff", LiffSettingsConfig.model_validate(config))
    return payload


@router.delete("/liff/pages/{page_id}/fields/{field_id}", status_code=204, dependencies=[Depends(require_line_manager)])
def delete_liff_field(page_id: str, field_id: str):
    config = _read("liff", LiffSettingsConfig)
    page = config.pages.get(page_id)
    field = find_by_id(page.fields, field_id) if page else None
    if not field:
        raise HTTPException(status_code=404, detail="LIFF field not found")
    if field.system_field:
        raise HTTPException(status_code=409, detail="System field cannot be deleted")
    page.fields = [item for item in page.fields if item.id != field_id]
    _save("liff", LiffSettingsConfig.model_validate(config))
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Customer service static settings
# ---------------------------------------------------------------------------
@router.get("/customer-service", response_model=CustomerServiceConfig)
def get_customer_service_config():
    return _read("customer_service", CustomerServiceConfig)


@router.put("/customer-service", response_model=CustomerServiceConfig, dependencies=[Depends(require_line_manager)])
def update_customer_service_config(payload: CustomerServiceConfig):
    _save("customer_service", payload)
    return payload
