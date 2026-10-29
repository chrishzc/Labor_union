"""Closed template-management HTTP views; storage paths never cross this boundary."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field


class _View(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)


class TemplateFieldView(_View):
    key: str
    label: str
    requiredness: Literal['required', 'conditional', 'optional']
    applicability: str | None = None

    @computed_field
    @property
    def example(self) -> str:
        from domains.contract_signing.template_management import TemplateField
        from subsystems.contract_signing.template_management import sample_value
        return sample_value(TemplateField(self.key, self.label, self.requiredness, self.applicability))


class TemplateVersionView(_View):
    version_id: str
    template_key: str
    number: int
    filename: str
    worksheet_name: str
    template_sha256: str
    mapping_sha256: str
    created_by: str
    created_at: str | None


class TemplateCatalogView(_View):
    template_key: str
    catalog_version: int
    active_version_id: str
    versions: list[TemplateVersionView]
    fields: list[TemplateFieldView]


class CellStyleView(_View):
    font: str
    size: float
    bold: bool
    italic: bool
    color: str
    fill: str
    align: str
    vertical: str
    wrap: bool
    borders: dict[str, str]


class WorkbookCellView(_View):
    ref: str
    row: int
    col: int
    value: str
    style: CellStyleView


class MergeView(_View):
    start_row: int
    end_row: int
    start_col: int
    end_col: int


class WorkbookSheetView(_View):
    name: str
    rows: int
    columns: int
    column_widths: dict[str, float]
    row_heights: dict[str, float]
    merges: list[MergeView]
    cells: list[WorkbookCellView]
    formula_cells: list[str]
    images: list['WorkbookImageView']


class WorkbookImageView(_View):
    row: int
    col: int
    left: float
    top: float
    width: float
    height: float
    data_url: str


class WorkbookPreviewView(_View):
    filename: str
    worksheet_name: str
    worksheet_names: list[str]
    sheet: WorkbookSheetView
    missing_fields: list[str]
    assignments: dict[str, str]
    sample_values: dict[str, str]


class TemplateMutationView(_View):
    catalog: TemplateCatalogView
    version_id: str
    replayed: bool


class ActivateTemplateBody(_View):
    version_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=0)
