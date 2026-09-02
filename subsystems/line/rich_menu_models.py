"""
File: rich_menu_models.py
Description: LINE Rich Menu 規格模型、外觀、動作與清單驗證契約。
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class MenuBounds(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class MenuAction(BaseModel):
    type: Literal["message", "uri", "postback"]
    text: str | None = None
    uri: str | None = None
    uri_source: Literal["literal", "liff"] = "literal"
    data: str | None = None

    @model_validator(mode="after")
    def validate_action_value(self):
        if self.type == "message" and not self.text:
            raise ValueError("message action requires text")
        if self.type == "uri" and self.uri_source == "literal" and not self.uri:
            raise ValueError("literal uri action requires uri")
        if self.type == "uri" and self.uri_source == "literal" and self.uri:
            if urlparse(self.uri).scheme.lower() not in {"http", "https"}:
                raise ValueError("literal uri action only supports http or https")
        if self.type == "postback" and not self.data:
            raise ValueError("postback action requires data")
        return self


class RichMenuButton(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=30)
    text_color: str = "#FFFFFF"
    background_color: str = "#4A90E2"
    border_radius: int = Field(default=0, ge=0, le=160)
    bounds: MenuBounds
    action: MenuAction


class RichMenuSize(BaseModel):
    width: Literal[2500] = 2500
    height: Literal[843, 1686] = 843


class RichMenuAppearance(BaseModel):
    background_color: str = "#F5F5F5"
    image_mode: Literal["generated", "uploaded"] = "generated"
    image_path: str | None = None
    image_asset_id: int | None = Field(default=None, ge=1)
    image_asset_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    image_asset_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_uploaded_image(self):
        refs = (self.image_asset_id, self.image_asset_sha256, self.image_asset_version)
        if self.image_mode == "uploaded":
            if self.image_path is not None:
                raise ValueError("uploaded image mode forbids raw image paths")
            if any(value is None for value in refs):
                raise ValueError("uploaded image mode requires an exact media asset reference")
        elif any(value is not None for value in refs):
            raise ValueError("generated image mode forbids media asset references")
        return self


class RichMenuDefinition(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=300)
    audience_role: Literal["customer", "staff", "union_staff", "union_staff_page"]
    rich_menu_alias_id: str | None = Field(default=None, min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    enabled: bool = True
    selected: bool = True
    set_as_default: bool = False
    chat_bar_text: str = Field(min_length=1, max_length=14)
    size: RichMenuSize = RichMenuSize()
    appearance: RichMenuAppearance = RichMenuAppearance()
    buttons: list[RichMenuButton] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_buttons(self):
        ids = [button.id for button in self.buttons]
        if len(ids) != len(set(ids)):
            raise ValueError("rich menu button ids must be unique")
        for button in self.buttons:
            if button.bounds.x + button.bounds.width > self.size.width:
                raise ValueError(f"button {button.id} exceeds menu width")
            if button.bounds.y + button.bounds.height > self.size.height:
                raise ValueError(f"button {button.id} exceeds menu height")
        for index, button in enumerate(self.buttons):
            for other in self.buttons[index + 1 :]:
                separated = button.bounds.x + button.bounds.width <= other.bounds.x or other.bounds.x + other.bounds.width <= button.bounds.x or button.bounds.y + button.bounds.height <= other.bounds.y or other.bounds.y + other.bounds.height <= button.bounds.y
                if not separated:
                    raise ValueError(f"buttons {button.id} and {other.id} overlap")
        if self.set_as_default and self.audience_role != "customer":
            raise ValueError("only the customer menu can be the default menu")
        return self


class LineMenusConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    menus: list[RichMenuDefinition]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.id for item in self.menus]
        if len(ids) != len(set(ids)):
            raise ValueError("rich menu ids must be unique")
        if not self.menus:
            return self
        enabled = [item for item in self.menus if item.enabled]
        primary_roles = {"customer", "staff", "union_staff"}
        roles = [item.audience_role for item in enabled if item.audience_role in primary_roles]
        if len(roles) != len(set(roles)):
            raise ValueError("only one enabled rich menu is allowed for each audience role")
        defaults = [item for item in enabled if item.set_as_default]
        if len(defaults) != 1:
            raise ValueError("exactly one enabled default rich menu is required")
        return self


__all__ = ["LineMenusConfig", "MenuAction", "MenuBounds", "RichMenuAppearance", "RichMenuButton", "RichMenuDefinition", "RichMenuSize"]
