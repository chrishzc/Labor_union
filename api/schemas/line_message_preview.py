"""Closed display-only LINE preview contracts; provider actions cannot cross this boundary."""

from typing import Annotated, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, ConfigDict, Field, model_serializer


class PreviewDescriptorView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    template_id: str | None
    name: str
    format: Literal["text", "flex"]
    requires_case: bool
    requires_staff: bool
    builtin: bool
    allows_draft: bool


class PreviewOptionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str


class PreviewOptionPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[PreviewOptionView]
    next_cursor: str | None


class RenderPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=191)
    content: str | None = Field(default=None, max_length=30000)
    data_source: Literal["record", "sample"] = "record"
    case_no: str | None = Field(default=None, min_length=1, max_length=191)
    staff_id: int | None = Field(default=None, gt=0)


PreviewColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")]
PreviewPixels = Annotated[int, Field(strict=True, ge=0, le=1000)]


class PreviewAppearanceView(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    background_color: PreviewColor
    color: PreviewColor
    border_color: PreviewColor
    border_width: PreviewPixels
    corner_radius: PreviewPixels
    padding_top: PreviewPixels
    padding_right: PreviewPixels
    padding_bottom: PreviewPixels
    padding_left: PreviewPixels
    gap: PreviewPixels
    margin: PreviewPixels
    width: PreviewPixels
    height: PreviewPixels
    flex: Annotated[int, Field(strict=True, ge=0, le=100)]
    align: Literal["start", "center", "end"]
    justify_content: Literal["start", "center", "end", "space-between", "space-around", "space-evenly"]
    align_items: Literal["start", "center", "end", "stretch"]
    button_style: Literal["primary", "secondary", "link"]
    bubble_size: Literal["nano", "micro", "deca", "hecto", "kilo", "mega", "giga"]
    wrap: Annotated[bool, Field(strict=True)]


class PreviewNodeView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text", "box", "button", "separator", "image"]
    text: str
    bold: bool
    size: str
    layout: Literal["horizontal", "vertical"]
    primary: bool
    action_description: str
    children: list["PreviewNodeView"]
    image_data: str = ''
    appearance: PreviewAppearanceView | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        if self.appearance is None:
            data.pop("appearance", None)
        return data


class RenderPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "needs_subject", "unavailable"]
    note: str
    format: Literal["text", "flex"]
    text: str
    bubbles: list[PreviewNodeView]
    facts: list[PreviewOptionView]
