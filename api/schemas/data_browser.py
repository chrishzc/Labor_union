"""
File: data_browser.py
Description: 定義 legacy Data Browser 與六來源 canonical query 契約。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


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


class DataBrowserTableResponse(BaseModel):
    rows: List[Dict[str, Any]]
    columns: List[str]
    primary_key: str = "id"
    editable_columns: List[str]
    valid_options: Dict[str, List[str]] = Field(default_factory=dict)
    read_only: bool = False


class DataBrowserPatchRequest(BaseModel):
    updates: Dict[str, Any] = Field(..., description="要微調更新的欄位與值")


class DataBrowserSourceCorrectionPreviewRequest(DataBrowserPatchRequest):
    pass


class DataBrowserSourceCorrectionApplyRequest(DataBrowserPatchRequest):
    preview_fingerprint: str = Field(min_length=1)
    reason: str = Field(min_length=1)


DataBrowserCorrectionValue = JsonValue | date | datetime | Decimal


class DataBrowserFieldChangeView(_StrictQueryModel):
    before: DataBrowserCorrectionValue
    after: DataBrowserCorrectionValue


class DataBrowserSourceCorrectionPreviewView(_StrictQueryModel):
    table: Literal["clients", "beclass_records", "staff"]
    row_id: int = Field(gt=0)
    changes: dict[str, DataBrowserFieldChangeView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class DataBrowserSourceCorrectionReceiptView(_StrictQueryModel):
    table: Literal["clients", "beclass_records", "staff"]
    row_id: int = Field(gt=0)
    changed_fields: list[str]
