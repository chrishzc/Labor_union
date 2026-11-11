"""
File: service_day_log.py
Description: 定義月嫂服務日日誌完成的不變量。[RETIRED] 2026-11-10 裁決：餐食與寶寶照片改維持於 LINE 群組相簿。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ServiceDayLogIntent:
    service_date: date
    baby_log_text: str = ""
    meal_photo_media_ids: tuple[str, ...] = ()


def require_service_day_log_completion(
    intent: ServiceDayLogIntent | None = None,
    *,
    requires_cooking: bool | None = None,
) -> None:
    """[RETIRED] 2026-11-10 裁決：餐食與寶寶照片改維持於 LINE 群組相簿，日誌完成不再強制要求餐食照片。"""
    return


__all__ = ["ServiceDayLogIntent", "require_service_day_log_completion"]
