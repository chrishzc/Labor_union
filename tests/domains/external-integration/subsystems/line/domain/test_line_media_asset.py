"""
File: test_line_media_asset.py
Description: 驗證 Rich Menu 圖片 metadata、刪除狀態與 canonical asset version。
"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domains.line.media_asset import RichMenuMediaAsset


def _asset(**changes) -> RichMenuMediaAsset:
    values = {
        "asset_id": 7,
        "menu_definition_id": "staff_menu",
        "original_filename": "staff-menu.png",
        "mime_type": "image/png",
        "file_size": 2048,
        "sha256": "a" * 64,
        "width": 2500,
        "height": 1686,
        "created_at": datetime(2026, 8, 26, 1, 2, tzinfo=timezone.utc),
        "deleted_at": None,
    }
    values.update(changes)
    return RichMenuMediaAsset(**values)


def test_active_asset_is_selectable_and_version_covers_canonical_metadata() -> None:
    asset = _asset()

    assert asset.selectable is True
    assert asset.business_reason is None
    assert len(asset.asset_version.value) == 64
    assert replace(asset, sha256="b" * 64).asset_version != asset.asset_version
    assert replace(asset, file_size=4096).asset_version != asset.asset_version
    assert replace(asset, height=843).asset_version != asset.asset_version


def test_deleted_asset_remains_queryable_but_is_not_selectable() -> None:
    asset = _asset(
        deleted_at=datetime(2026, 8, 26, 2, 2, tzinfo=timezone.utc),
    )

    assert asset.selectable is False
    assert asset.business_reason == "此背景圖已刪除，只保留歷史查詢，不能再選用。"
    assert asset.asset_version != _asset().asset_version


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sha256": "A" * 64}, "lowercase SHA-256"),
        ({"width": 1200}, "dimensions are unsupported"),
        ({"height": None}, "must be a positive integer"),
        ({"menu_definition_id": " staff_menu"}, "canonical non-empty text"),
        ({"created_at": datetime(2026, 8, 26)}, "timezone-aware"),
        (
            {
                "deleted_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            },
            "precedes created_at",
        ),
    ],
)
def test_invalid_digest_dimensions_owner_and_timestamps_fail_closed(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _asset(**changes)
