"""Compose LIFF meal-photo upload outside the HTTP route."""

from api.dependencies.line_worker_operation import _media_storage_root
from infrastructure.line.media_adapters import FileSystemLineMediaObjectStore
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.liff_media_upload import LiffMealPhotoUploadApplication


def get_liff_meal_photo_upload_application() -> LiffMealPhotoUploadApplication:
    return LiffMealPhotoUploadApplication(
        open_line_unit_of_work,
        FileSystemLineMediaObjectStore(_media_storage_root()),
    )
