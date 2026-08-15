"""
File: service_day_log.py
Description: 定義月嫂服務日日誌完成的不變量，含下廚時必須附餐食照片的規則。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ServiceDayLogIntent:
    service_date: date
    baby_log_text: str
    meal_photo_media_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.service_date, date):
            raise TypeError("service day must be a date")
        if not isinstance(self.baby_log_text, str) or not self.baby_log_text.strip():
            raise ValueError("baby log text is required")
        if len(self.baby_log_text) > 5000:
            raise ValueError("baby log text is too long")
        if len(set(self.meal_photo_media_ids)) != len(self.meal_photo_media_ids):
            raise ValueError("meal photo media IDs must be unique")
        for media_id in self.meal_photo_media_ids:
            if not isinstance(media_id, str) or not media_id.strip() or len(media_id) > 191:
                raise ValueError("meal photo media ID is invalid")


def require_service_day_log_completion(
    intent: ServiceDayLogIntent,
    *,
    requires_cooking: bool | None,
) -> None:
    if requires_cooking is True and not intent.meal_photo_media_ids:
        raise ValueError("meal photo is required when cooking is required")
    if requires_cooking is None:
        raise ValueError("cooking requirement is unresolved")


__all__ = ["ServiceDayLogIntent", "require_service_day_log_completion"]
