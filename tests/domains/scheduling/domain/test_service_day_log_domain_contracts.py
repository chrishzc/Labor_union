"""Direct regression contracts for Scheduling service-day-log invariants."""

from datetime import date

import pytest

from domains.scheduling.service_day_log import (
    ServiceDayLogIntent,
    require_service_day_log_completion,
)


def test_service_day_log_allows_non_cooking_day_and_cooking_day_with_photo() -> None:
    plain = ServiceDayLogIntent(
        service_date=date(2026, 8, 31),
        baby_log_text="feeding and sleep log",
    )
    require_service_day_log_completion(plain, requires_cooking=False)

    cooking = ServiceDayLogIntent(
        service_date=date(2026, 8, 31),
        baby_log_text="feeding, sleep, and meal log",
        meal_photo_media_ids=("media-001",),
    )
    require_service_day_log_completion(cooking, requires_cooking=True)


def test_cooking_day_requires_at_least_one_meal_photo() -> None:
    intent = ServiceDayLogIntent(
        service_date=date(2026, 8, 31),
        baby_log_text="daily log",
    )

    with pytest.raises(ValueError, match="meal photo is required"):
        require_service_day_log_completion(intent, requires_cooking=True)


def test_unresolved_cooking_requirement_cannot_complete_log() -> None:
    intent = ServiceDayLogIntent(
        service_date=date(2026, 8, 31),
        baby_log_text="daily log",
        meal_photo_media_ids=("media-001",),
    )

    with pytest.raises(ValueError, match="unresolved"):
        require_service_day_log_completion(intent, requires_cooking=None)


def test_baby_log_text_must_be_nonblank_and_bounded() -> None:
    for invalid in ("", "   "):
        with pytest.raises(ValueError, match="required"):
            ServiceDayLogIntent(date(2026, 8, 31), invalid)

    with pytest.raises(ValueError, match="too long"):
        ServiceDayLogIntent(date(2026, 8, 31), "x" * 5001)


def test_meal_photo_media_ids_must_be_unique_nonblank_and_bounded() -> None:
    with pytest.raises(ValueError, match="unique"):
        ServiceDayLogIntent(
            date(2026, 8, 31),
            "daily log",
            ("media-001", "media-001"),
        )

    for invalid in ("", "   ", "x" * 192):
        with pytest.raises(ValueError, match="invalid"):
            ServiceDayLogIntent(date(2026, 8, 31), "daily log", (invalid,))


def test_service_date_must_be_a_date_value() -> None:
    with pytest.raises(TypeError, match="must be a date"):
        ServiceDayLogIntent("2026-08-31", "daily log")
