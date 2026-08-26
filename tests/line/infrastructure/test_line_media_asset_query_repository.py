"""
File: test_line_media_asset_query_repository.py
Description: 驗證 Rich Menu 圖片查詢固定 owner、分頁且不公開儲存欄位。
"""

from datetime import datetime

import pytest

from infrastructure.mysql.line_media_asset_query_repository import (
    MySqlLineRichMenuMediaAssetQueryRepository,
)
from subsystems.line.media_asset_contracts import (
    RichMenuMediaAssetDetailQuery,
    RichMenuMediaAssetListQuery,
)


class _Cursor:
    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters):
        self.executed.append((sql, tuple(parameters)))

    def fetchone(self):
        return self._results.pop(0)

    def fetchall(self):
        return self._results.pop(0)


class _Connection:
    def __init__(self, results: list[object]) -> None:
        self.cursor_instance = _Cursor(results)

    def cursor(self):
        return self.cursor_instance


def _row(**changes) -> dict[str, object]:
    row = {
        "id": 9,
        "category": "rich_menu",
        "owner_type": "line_menu",
        "owner_id": "staff_menu",
        "original_filename": "staff.png",
        "mime_type": "image/png",
        "file_size": 1234,
        "sha256": "a" * 64,
        "width": 2500,
        "height": 1686,
        "created_at": datetime(2026, 8, 26, 1, 2),
        "deleted_at": None,
    }
    row.update(changes)
    return row


def test_list_is_numbered_owner_scoped_and_metadata_only() -> None:
    connection = _Connection([{"total": 26}, [_row()]])
    repository = MySqlLineRichMenuMediaAssetQueryRepository(connection)

    result = repository.list(RichMenuMediaAssetListQuery("staff_menu", 2, 25))

    assert (result.page, result.page_size, result.total, result.total_pages) == (
        2,
        25,
        26,
        2,
    )
    assert result.items[0].menu_definition_id == "staff_menu"
    count_call, list_call = connection.cursor_instance.executed
    assert count_call[1] == ("rich_menu", "line_menu", "staff_menu")
    assert list_call[1] == ("rich_menu", "line_menu", "staff_menu", 25, 25)
    assert "storage_provider" not in list_call[0]
    assert "storage_key" not in list_call[0]
    assert "created_by_admin_user_id" not in list_call[0]


def test_detail_is_owner_scoped_and_deleted_asset_is_visible() -> None:
    connection = _Connection(
        [_row(deleted_at=datetime(2026, 8, 26, 2, 2))]
    )
    repository = MySqlLineRichMenuMediaAssetQueryRepository(connection)

    item = repository.get(RichMenuMediaAssetDetailQuery("staff_menu", 9))

    assert item is not None
    assert item.selectable is False
    assert connection.cursor_instance.executed[0][1] == (
        9,
        "rich_menu",
        "line_menu",
        "staff_menu",
    )


def test_detail_lock_uses_exact_owner_predicate_and_for_update() -> None:
    connection = _Connection([_row()])
    repository = MySqlLineRichMenuMediaAssetQueryRepository(connection)

    item = repository.get_for_update(
        RichMenuMediaAssetDetailQuery("staff_menu", 9)
    )

    assert item is not None
    sql, parameters = connection.cursor_instance.executed[0]
    assert sql.endswith(" FOR UPDATE")
    assert parameters == (9, "rich_menu", "line_menu", "staff_menu")


@pytest.mark.parametrize(
    "changes",
    [
        {"category": "other"},
        {"owner_type": "rich_menu"},
        {"owner_id": "default_menu"},
        {"sha256": "invalid"},
        {"width": 1200},
    ],
)
def test_persisted_owner_digest_and_dimensions_drift_fail_closed(
    changes: dict[str, object],
) -> None:
    repository = MySqlLineRichMenuMediaAssetQueryRepository(
        _Connection([_row(**changes)])
    )

    with pytest.raises(ValueError):
        repository.get(RichMenuMediaAssetDetailQuery("staff_menu", 9))
