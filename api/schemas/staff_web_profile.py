from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from domains.staff.web_profile import (
    ReminderLead,
    WebProfileCategory,
    WebProfilePhoto,
    WebProfileTemplateItem,
)


class WebProfilePhotoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_item_id: int = Field(gt=0)
    template_version: int = Field(gt=0)
    original_file_id: str = Field(pattern=r"^cf_[a-f0-9]{32}$")
    expiry_date: date | None = None
    entry_id: int | None = Field(default=None, gt=0)
    entry_version: int | None = Field(default=None, gt=0)


class TemplateItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    category: WebProfileCategory
    display_order: int = Field(ge=0, le=2147483647)
    reminder_enabled: bool = False
    reminder_months: int = Field(default=1, ge=0, le=120)
    reminder_days: int = Field(default=0, ge=0, le=3650)
    version: int = Field(default=0, ge=0)

    def to_item(self, item_id: int | None = None) -> WebProfileTemplateItem:
        if (item_id is None) != (self.version == 0):
            raise ValueError("staff_web_invalid_template_version")
        return WebProfileTemplateItem(
            item_id, self.version, self.name, self.category, self.display_order,
            self.reminder_enabled, ReminderLead(self.reminder_months, self.reminder_days),
        )


class CropInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(gt=0)
    crop_id: UUID
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(gt=0)
    bottom: int = Field(gt=0)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


class CustomerWebProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interaction_token: str = Field(min_length=1, max_length=191)
    line_id_token: str = Field(min_length=1, max_length=4096)


class PublishedWebProfileImageView(BaseModel):
    item_name: str
    image_entry: int = Field(gt=0)
    image_version: int = Field(gt=0)


class PublishedWebProfileGroupView(BaseModel):
    category: WebProfileCategory
    images: list[PublishedWebProfileImageView]


class PublishedWebProfilePreviewView(BaseModel):
    name: str
    groups: list[PublishedWebProfileGroupView]


class EntryVersionView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    entry_id: int = Field(gt=0)
    entry_version: int = Field(gt=0)


class FolderFileView(EntryVersionView):
    filename: str
    expiry_date: date | None


class FolderView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    template_item_id: int = Field(gt=0)
    template_version: int = Field(gt=0)
    name: str
    category: WebProfileCategory
    count: int = Field(ge=0)
    files: tuple[FolderFileView, ...]


class FoldersView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: tuple[FolderView, ...]


class UploadedPhotoView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(pattern=r"^cf_[a-f0-9]{32}$")
    filename: str


class PublishPhotoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(pattern=r"^cf_[a-f0-9]{32}$")
    expiry_date: date | None


class PublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    template_item_id: int = Field(gt=0)
    template_version: int = Field(gt=0)
    files: list[PublishPhotoInput] = Field(min_length=1, max_length=50)
    expected_current: EntryVersionView | None

    def to_photos(self) -> tuple[WebProfilePhoto, ...]:
        expected = self.expected_current
        if expected is not None and len(self.files) != 1:
            raise ValueError("staff_web_other_single_photo")
        return tuple(WebProfilePhoto(
            self.template_item_id,
            file.file_id,
            file.expiry_date,
            expected.entry_id if expected else None,
            expected.entry_version if expected else None,
            self.template_version,
        ) for file in self.files)


class PublicationsView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: tuple[EntryVersionView, ...]


class RemovedFileView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: int = Field(gt=0)
