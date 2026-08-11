"""Rich Menu preview receipts must lock the canonical DB configuration revision."""

from __future__ import annotations

import json

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from subsystems.line import rich_menu_publication_workflow


class _ConfigurationRepository:
    def __init__(self, snapshot: LineConfigurationSnapshot) -> None:
        self._snapshot = snapshot

    def get(self, kind: LineConfigurationKind) -> LineConfigurationSnapshot:
        assert kind is LineConfigurationKind.RICH_MENUS
        return self._snapshot


class _UnitOfWork:
    def __init__(self, snapshot: LineConfigurationSnapshot) -> None:
        self.configurations = _ConfigurationRepository(snapshot)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _LegacyImportCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        self.executions.append((query, parameters))

    def fetchone(self):
        return None


class _LegacyImportConnection:
    def __init__(self) -> None:
        self.cursor_instance = _LegacyImportCursor()
        self.committed = False

    def begin(self) -> None:
        pass

    def cursor(self, *_):
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_current_menu_snapshot_uses_canonical_database_revision(monkeypatch) -> None:
    definition = _rich_menu_definition()
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(definition),
    )
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "open_line_unit_of_work",
        lambda: _UnitOfWork(snapshot),
    )

    menu, revision, fingerprint = rich_menu_publication_workflow._current_menu_snapshot(
        "default_menu"
    )

    assert menu.id == "default_menu"
    assert revision == "7"
    assert len(fingerprint) == 64


def test_legacy_import_uses_canonical_database_configuration(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_rich_menu_definition()),
    )
    legacy_ids_path = tmp_path / "rich_menu_ids.json"
    legacy_ids_path.write_text(
        json.dumps({"default_rich_menu_id": "rich-menu-123"}),
        encoding="utf-8",
    )
    connection = _LegacyImportConnection()
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "open_line_unit_of_work",
        lambda: _UnitOfWork(snapshot),
    )
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "LEGACY_IDS_PATH",
        legacy_ids_path,
    )
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "get_connection",
        lambda: connection,
    )

    imported = rich_menu_publication_workflow.import_legacy_rich_menu_ids()

    insert_parameters = connection.cursor_instance.executions[-1][1]
    assert imported == 1
    assert insert_parameters[0:3] == ("default_menu", "customer", "7")
    assert insert_parameters[4] == "rich-menu-123"
    assert connection.committed is True


def _rich_menu_definition() -> dict[str, object]:
    return {
        "version": 2,
        "menus": [
            {
                "id": "default_menu",
                "name": "一般用戶選單",
                "audience_role": "customer",
                "enabled": True,
                "selected": True,
                "set_as_default": True,
                "chat_bar_text": "用戶選單",
                "size": {"width": 2500, "height": 843},
                "appearance": {"image_mode": "generated"},
                "buttons": [
                    {
                        "id": "orders",
                        "label": "訂單查詢",
                        "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843},
                        "action": {"type": "message", "text": "訂單查詢"},
                    }
                ],
            }
        ],
    }
