"""
File: staff_matching_preferences.py
Description: 定義 Staff matching preference Query、Preview、Apply 與 receipt 嚴格契約。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class IntegerRangePreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["integer_range"]
    minimum: int = Field(gt=0)
    maximum: int = Field(gt=0)

    def canonical_value(self) -> dict[str, object]:
        return {"maximum": self.maximum, "minimum": self.minimum}


class IntegerSetPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["integer_set"]
    values: list[int] = Field(min_length=1)

    def canonical_value(self) -> dict[str, object]:
        return {"values": self.values}


PreferenceValueInput = Annotated[
    IntegerRangePreferenceInput | IntegerSetPreferenceInput,
    Field(discriminator="kind"),
]


class StaffPreferenceDefinitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)
    value_kind: Literal["integer_range", "integer_set"]
    is_filterable: bool
    order_fact_key: str | None = Field(default=None, min_length=1, max_length=64)
    comparison_operator: Literal["range_with_tolerance", "contains_integer"] | None = None
    active: bool = True


class StaffPreferenceDefinitionView(StaffPreferenceDefinitionInput):
    preference_key: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=0)


class DefinitionPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: StaffPreferenceDefinitionView | None
    after: StaffPreferenceDefinitionView
    version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class DefinitionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: StaffPreferenceDefinitionInput


class DefinitionApplyRequest(DefinitionPreviewRequest):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffPreferenceValueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference_key: str = Field(min_length=1, max_length=64)
    value: PreferenceValueInput


class StaffPreferenceValueView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference_key: str
    value: PreferenceValueInput


class StaffPreferenceProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[StaffPreferenceValueInput]


class StaffPreferenceProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    version: int = Field(ge=0)
    values: list[StaffPreferenceValueView]


class ProfilePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    before: list[StaffPreferenceValueView]
    after: list[StaffPreferenceValueView]
    version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProfileApplyRequest(StaffPreferenceProfileInput):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffPreferenceDefinitionApplyReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference_key: str = Field(min_length=1, max_length=64)
    version: int = Field(gt=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)


class StaffPreferenceProfileApplyReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    version: int = Field(gt=0)
    values: list[StaffPreferenceValueView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
