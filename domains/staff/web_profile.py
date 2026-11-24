from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class WebProfileCategory(str, Enum):
    PHOTO = "photo"
    CERTIFICATE = "certificate"
    OTHER = "other"
    FEEDBACK = "feedback"

    @property
    def requires_expiry(self) -> bool:
        return self is WebProfileCategory.OTHER


@dataclass(frozen=True, slots=True)
class ReminderLead:
    months: int = 1
    days: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.months <= 120 or not 0 <= self.days <= 3650:
            raise ValueError("staff_web_invalid_reminder_lead")

    def starts_on(self, expiry: date) -> date:
        year, month_index = divmod(expiry.year * 12 + expiry.month - 1 - self.months, 12)
        month = month_index + 1
        shifted = date(year, month, min(expiry.day, monthrange(year, month)[1]))
        return shifted - timedelta(days=self.days)


@dataclass(frozen=True, slots=True)
class WebProfileTemplateItem:
    item_id: int | None
    version: int
    name: str
    category: WebProfileCategory
    display_order: int
    reminder_enabled: bool = False
    reminder_lead: ReminderLead = ReminderLead()

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > 100 or not 0 <= self.display_order <= 2147483647:
            raise ValueError("staff_web_invalid_template_item")
        object.__setattr__(self, "name", name)
        if not self.category.requires_expiry:
            object.__setattr__(self, "reminder_enabled", False)
            object.__setattr__(self, "reminder_lead", ReminderLead())

    def expiry_for_submission(self, expiry: date | None) -> date | None:
        if not self.category.requires_expiry:
            return None
        if expiry is None:
            raise ValueError("staff_web_expiry_required")
        return expiry

    def reminder_due(self, expiry: date | None, today: date) -> bool:
        return (
            self.category.requires_expiry and self.reminder_enabled
            and expiry is not None and today <= expiry
            and self.reminder_lead.starts_on(expiry) <= today
        )


@dataclass(frozen=True, slots=True)
class WebProfilePhoto:
    template_item_id: int
    original_file_id: str
    expiry_date: date | None = None
    entry_id: int | None = None
    entry_version: int | None = None
    template_version: int | None = None
    crop_file_id: str | None = None

    @property
    def published_file_id(self) -> str:
        return self.crop_file_id or self.original_file_id


@dataclass(frozen=True, slots=True)
class PublishedWebProfilePhoto:
    entry_id: int
    version: int
    staff_id: int
    item: WebProfileTemplateItem
    original_file_id: str
    crop_file_id: str | None
    expiry_date: date | None

    @property
    def file_id(self) -> str:
        return self.crop_file_id or self.original_file_id


@dataclass(frozen=True, slots=True)
class WebProfileEntryVersion:
    entry_id: int
    entry_version: int


@dataclass(frozen=True, slots=True)
class WebProfileFolderFile:
    entry_id: int
    entry_version: int
    filename: str
    expiry_date: date | None


@dataclass(frozen=True, slots=True)
class WebProfileFolder:
    template_item_id: int
    template_version: int
    name: str
    category: WebProfileCategory
    files: tuple[WebProfileFolderFile, ...]

    @property
    def count(self) -> int:
        return len(self.files)


class WebProfileConflict(ValueError):
    pass
