"""
File: data_browser.py
Description: 定義 bounded 唯讀 Data Browser archive query 契約。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DataBrowserSourceId = Literal[
    "orders",
    "clients",
    "staff",
    "beclass_intake",
    "hcm_review",
    "bank_facts",
]
DataBrowserPresentation = Literal[
    "text",
    "date",
    "datetime",
    "integer",
    "decimal",
    "status",
]


class _StrictQueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DataBrowserCellView(_StrictQueryModel):
    field_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    value: str | int | bool | float | None
    presentation: DataBrowserPresentation


class DataBrowserRowView(_StrictQueryModel):
    source_id: DataBrowserSourceId
    row_identity: str = Field(min_length=1, max_length=191)
    display_title: str = Field(min_length=1, max_length=300)
    summary_cells: list[DataBrowserCellView]
    detail_cells: list[DataBrowserCellView]
    recorded_at: str | None
    source_actor_label: str | None
    version_identity: str = Field(pattern=r"^[0-9a-f]{64}$")


class DataBrowserPageView(_StrictQueryModel):
    source_id: DataBrowserSourceId
    items: list[DataBrowserRowView]
    next_cursor: str | None
