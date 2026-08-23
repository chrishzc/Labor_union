"""
File: test_line_rich_menu_publication_snapshot.py
Description: 驗證 Rich Menu 預覽使用 canonical revision 並產生零寫入的決定性收據。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision, LineRichMenuPublicationId
from domains.line.rich_menu import LineRichMenuPublicationSnapshot, LineRichMenuPublicationStatus
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line import rich_menu_publication_workflow
from subsystems.line.capabilities import LineCapability
from subsystems.line.ports import LineRichMenuPublicationPage
from subsystems.line.rich_menu_contracts import (
    LineRichMenuPublicationQuery,
    QueueLineRichMenuPublicationCommand,
)
from subsystems.line.rich_menu_definition import rich_menu_provider_definition


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


def test_publication_preview_receipt_is_deterministic_and_never_opens_database(
    monkeypatch,
) -> None:
    def reject_database_access():
        raise AssertionError("publication preview must not open a database connection")

    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "get_connection",
        reject_database_access,
    )
    candidate = {
        "menu_definition": {"id": "default_menu", "enabled": True},
        "provider_definition": {"size": {"width": 2500, "height": 843}},
    }

    first = rich_menu_publication_workflow.create_publication_preview(
        "default_menu",
        17,
        config_revision=7,
        candidate=candidate,
    )
    replay = rich_menu_publication_workflow.create_publication_preview(
        "default_menu",
        17,
        config_revision=7,
        candidate=candidate,
    )
    other_actor = rich_menu_publication_workflow.create_publication_preview(
        "default_menu",
        18,
        config_revision=7,
        candidate=candidate,
    )

    assert first == replay
    assert 0 < first["preview_id"] <= 9_223_372_036_854_775_807
    assert first["config_revision"] == "7"
    assert len(first["config_fingerprint"]) == 64
    assert other_actor["preview_id"] != first["preview_id"]


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


def test_stateless_preview_validation_recomputes_fresh_candidate(monkeypatch) -> None:
    candidate = {
        "menu_definition": _rich_menu_definition()["menus"][0],
        "provider_definition": json.loads(
            rich_menu_provider_definition(_rich_menu_definition()["menus"][0])
        ),
    }
    preview = rich_menu_publication_workflow.create_publication_preview(
        "default_menu", 17, config_revision=7, candidate=candidate
    )
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_rich_menu_definition()),
    )
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "open_line_unit_of_work",
        lambda: _UnitOfWork(snapshot),
    )
    validated = rich_menu_publication_workflow.validate_publication_preview(
        "default_menu", preview["preview_id"], 17
    )
    assert validated == preview


def test_apply_uses_one_uow_and_only_first_create_outbox(monkeypatch) -> None:
    definition = _rich_menu_definition()
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(definition),
    )
    candidate = {
        "menu_definition": definition["menus"][0],
        "provider_definition": json.loads(
            rich_menu_provider_definition(definition["menus"][0])
        ),
    }
    preview = rich_menu_publication_workflow.create_publication_preview(
        "default_menu", 17, config_revision=7, candidate=candidate
    )
    command = QueueLineRichMenuPublicationCommand(
        menu_definition_id="default_menu",
        configuration_revision=LineConfigurationRevision(7),
        actor=ActorContext("17", (LineCapability.MENU_PUBLISH.value,)),
        idempotency_key=IdempotencyKey("rich-menu-apply:17"),
        correlation_id=CorrelationId("rich-menu-apply-correlation"),
        preview_id=preview["preview_id"],
        preview_config_revision=preview["config_revision"],
        preview_config_fingerprint=preview["config_fingerprint"],
        previewed_by_admin_user_id=17,
    )
    unit_of_work = _ApplyUnitOfWork(snapshot)
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "open_line_unit_of_work",
        lambda: unit_of_work,
    )

    first = rich_menu_publication_workflow.queue_publication(
        command,
        reason="核准發布",
    )
    replay = rich_menu_publication_workflow.queue_publication(
        command,
        reason="核准發布",
    )

    assert first == replay
    assert unit_of_work.commit_count == 1
    assert len(unit_of_work.receipts.items) == 1
    assert len(unit_of_work.audit.items) == 1
    assert len(unit_of_work.outbox.items) == 1


def test_publication_page_delegates_count_limit_offset_to_repository(monkeypatch) -> None:
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_rich_menu_definition()),
    )
    unit_of_work = _ApplyUnitOfWork(snapshot)
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "open_line_unit_of_work",
        lambda: unit_of_work,
    )
    query = LineRichMenuPublicationQuery(page_size=25)

    page = rich_menu_publication_workflow.list_publication_page(
        query,
        offset=125,
        actor=ActorContext("17", (LineCapability.CONFIG_READ.value,)),
    )

    assert page.total == 243
    assert page.offset == 125
    assert page.page_size == 25
    assert unit_of_work.rich_menu_publications.page_calls == [(query, 125)]
    assert unit_of_work.commit_count == 0


class _ApplyReceipts:
    def __init__(self) -> None:
        self.items = []

    def get(self, key):
        return next((item for item in self.items if item.key == key), None)

    def append(self, item) -> None:
        self.items.append(item)


class _ApplyRepository:
    def __init__(self) -> None:
        self.item = LineRichMenuPublicationSnapshot(
            LineRichMenuPublicationId(41),
            "default_menu",
            LineConfigurationRevision(7),
            LineRichMenuPublicationStatus.QUEUED,
        )
        self.page_calls = []

    def queue(self, _command):
        return SimpleNamespace(publication=self.item)

    def get(self, _publication_id):
        return self.item

    def list_step_receipts(self, _publication_id):
        return ()

    def list_page(self, query, *, offset=0):
        self.page_calls.append((query, offset))
        return LineRichMenuPublicationPage(
            items=(self.item,),
            total=243,
            offset=offset,
            page_size=query.page_size,
        )


class _ApplyOutbox:
    def __init__(self) -> None:
        self.items = []

    def append(self, item):
        self.items.append(item)
        return len(self.items)


class _ApplyUnitOfWork(_UnitOfWork):
    def __init__(self, snapshot) -> None:
        super().__init__(snapshot)
        self.rich_menu_publications = _ApplyRepository()
        self.receipts = _ApplyReceipts()
        self.audit = _ApplyOutbox()
        self.outbox = _ApplyOutbox()
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


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
