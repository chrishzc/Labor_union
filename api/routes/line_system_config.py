"""Validated configuration APIs for LINE, LIFF and customer service clients."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from pydantic import BaseModel, ValidationError

from api.schemas.line_config import (
    CustomerServiceConfig,
    LiffField,
    LiffPage,
    LiffSettingsConfig,
    LiffTheme,
    LineMenusConfig,
    MessageTemplate,
    MessageTemplatePreviewRequest,
    MessageTemplatesConfig,
    RichMenuDefinition,
)
from services.json_config_service import (
    find_by_id,
    read_config,
    upsert_by_id,
    write_config,
)


router = APIRouter(prefix="/api/config", tags=["System Config"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
T = TypeVar("T", bound=BaseModel)


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


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------
@router.get("/message-templates", response_model=MessageTemplatesConfig)
def get_message_templates():
    return _read("message_templates", MessageTemplatesConfig)


@router.put("/message-templates", response_model=MessageTemplatesConfig)
def replace_message_templates(payload: MessageTemplatesConfig):
    _save("message_templates", payload)
    return payload


@router.post(
    "/message-templates",
    response_model=MessageTemplate,
    status_code=status.HTTP_201_CREATED,
)
def create_message_template(payload: MessageTemplate):
    config = _read("message_templates", MessageTemplatesConfig)
    if find_by_id(config.templates, payload.id):
        raise HTTPException(status_code=409, detail="Template id already exists")
    config.templates.append(payload)
    validated = MessageTemplatesConfig.model_validate(config)
    _save("message_templates", validated)
    return payload


@router.get("/message-templates/{template_id}", response_model=MessageTemplate)
def get_message_template(template_id: str):
    config = _read("message_templates", MessageTemplatesConfig)
    item = find_by_id(config.templates, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Template not found")
    return item


@router.put("/message-templates/{template_id}", response_model=MessageTemplate)
def update_message_template(template_id: str, payload: MessageTemplate):
    if payload.id != template_id:
        raise HTTPException(status_code=400, detail="Path id and payload id must match")
    config = _read("message_templates", MessageTemplatesConfig)
    if not find_by_id(config.templates, template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    config.templates = upsert_by_id(config.templates, payload)
    _save("message_templates", MessageTemplatesConfig.model_validate(config))
    return payload


@router.delete("/message-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_template(template_id: str):
    config = _read("message_templates", MessageTemplatesConfig)
    original_count = len(config.templates)
    config.templates = [item for item in config.templates if item.id != template_id]
    if len(config.templates) == original_count:
        raise HTTPException(status_code=404, detail="Template not found")
    _save("message_templates", MessageTemplatesConfig.model_validate(config))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/message-templates/{template_id}/preview")
def preview_message_template(template_id: str, payload: MessageTemplatePreviewRequest):
    item = get_message_template(template_id)
    if item.message_type == "flex":
        return {"message_type": "flex", "content": item.content}
    rendered = str(item.content)
    for variable in item.variables:
        if variable.required and variable.name not in payload.variables:
            raise HTTPException(status_code=422, detail=f"Missing variable: {variable.name}")
        rendered = rendered.replace(
            "{" + variable.name + "}", payload.variables.get(variable.name, "")
        )
    return {"message_type": "text", "content": rendered}


# ---------------------------------------------------------------------------
# Rich menus
# ---------------------------------------------------------------------------
@router.get("/line-menus", response_model=LineMenusConfig)
def get_line_menus():
    return _read("line_menus", LineMenusConfig)


@router.put("/line-menus", response_model=LineMenusConfig)
def replace_line_menus(payload: LineMenusConfig):
    _save("line_menus", payload)
    return payload


@router.post("/line-menus", response_model=RichMenuDefinition, status_code=201)
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


@router.put("/line-menus/{menu_id}", response_model=RichMenuDefinition)
def update_line_menu(menu_id: str, payload: RichMenuDefinition):
    if payload.id != menu_id:
        raise HTTPException(status_code=400, detail="Path id and payload id must match")
    config = _read("line_menus", LineMenusConfig)
    if not find_by_id(config.menus, menu_id):
        raise HTTPException(status_code=404, detail="Menu not found")
    config.menus = upsert_by_id(config.menus, payload)
    _save("line_menus", LineMenusConfig.model_validate(config))
    return payload


@router.delete("/line-menus/{menu_id}", status_code=204)
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


@router.post("/line-menus/{menu_id}/preview")
def preview_line_menu(menu_id: str):
    return {"status": "valid", "menu": get_line_menu(menu_id)}


@router.post("/line-menus/{menu_id}/publish", status_code=202)
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
@router.get("/liff", response_model=LiffSettingsConfig)
def get_liff_config():
    return _read("liff", LiffSettingsConfig)


@router.put("/liff", response_model=LiffSettingsConfig)
def replace_liff_config(payload: LiffSettingsConfig):
    _save("liff", payload)
    return payload


@router.put("/liff/theme", response_model=LiffTheme)
def update_liff_theme(payload: LiffTheme):
    config = _read("liff", LiffSettingsConfig)
    config.theme = payload
    _save("liff", config)
    return payload


@router.put("/liff/pages/{page_id}", response_model=LiffPage)
def update_liff_page(page_id: str, payload: LiffPage):
    config = _read("liff", LiffSettingsConfig)
    config.pages[page_id] = payload
    _save("liff", LiffSettingsConfig.model_validate(config))
    return payload


@router.post("/liff/pages/{page_id}/fields", response_model=LiffField, status_code=201)
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


@router.put("/liff/pages/{page_id}/fields/{field_id}", response_model=LiffField)
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


@router.delete("/liff/pages/{page_id}/fields/{field_id}", status_code=204)
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


@router.put("/customer-service", response_model=CustomerServiceConfig)
def update_customer_service_config(payload: CustomerServiceConfig):
    _save("customer_service", payload)
    return payload
