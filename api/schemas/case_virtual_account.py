"""Bounded schemas for Client Finance single-case account editing."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CaseVirtualAccountApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    virtual_account: str = Field(min_length=1, max_length=14)
    expected_mapping_ids: tuple[Annotated[int, Field(gt=0, strict=True)], ...]


class CaseVirtualAccountView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    imported_virtual_accounts: tuple[str, ...]
    built_in_virtual_account: str | None
    mapping_ids: tuple[int, ...]


class CaseVirtualAccountReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    before: tuple[str, ...]
    virtual_account: str
