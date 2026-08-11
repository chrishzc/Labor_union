"""Rich Menu preview receipts must lock the canonical DB configuration revision."""

from __future__ import annotations

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
