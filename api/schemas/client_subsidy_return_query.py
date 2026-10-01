"""Transport views for the read-only customer subsidy-return case list."""

from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class ClientSubsidyReturnRowView(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_no: str
    client_name: str
    order_status: str
    amount_ntd: int | None = Field(ge=0)
    due_date: date | None
    is_estimate: bool


class ClientSubsidyReturnPageView(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rows: list[ClientSubsidyReturnRowView]
    next_cursor: str | None
