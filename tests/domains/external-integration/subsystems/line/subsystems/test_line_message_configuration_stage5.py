"""
File: test_line_message_configuration_stage5.py
Description: 驗證 LINE 範本、排程與版本化設定的契約。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision, LineUserId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.follow_schedule_application import enqueue_follow_schedule
from subsystems.line.message_configuration import (
    LineMessageConfigurationError,
    follow_schedule_steps,
    render_message_template,
)

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)
FOLLOWED_AT = datetime(2026, 8, 8, 2, 30, tzinfo=timezone.utc)


class FakeUow:
    def __init__(self, **repositories) -> None:
        self.__dict__.update(repositories)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class ConfigurationRepository:
    def __init__(self, snapshots) -> None:
        self.snapshots = dict(snapshots)
        self.applied = []

    def get(self, kind):
        return self.snapshots.get(
            kind,
            LineConfigurationSnapshot(kind, LineConfigurationRevision(0), "{}"),
        )

    def apply(self, command):
        self.applied.append(command)
        snapshot = LineConfigurationSnapshot(
            command.candidate.kind,
            command.candidate.resulting_revision,
            command.candidate.definition_json,
        )
        return SimpleNamespace(outcome="created", snapshot=snapshot)


class RecordingRepository:
    def __init__(self) -> None:
        self.items = []

    def enqueue(self, item):
        self.items.append(item)
        return item

    def append(self, item):
        self.items.append(item)


def _definition(name: str):
    return json.loads((ROOT / "config" / f"{name}.json").read_text("utf-8"))


def _snapshot(kind, name):
    return LineConfigurationSnapshot(
        kind,
        LineConfigurationRevision(1),
        canonical_line_payload_json(_definition(name)),
    )


def test_retired_follow_schedule_does_not_expand_delivery_steps() -> None:
    templates = _definition("message_templates")
    schedules = _definition("message_schedules")

    steps = follow_schedule_steps(schedules, templates, FOLLOWED_AT)

    assert steps == ()


def test_template_render_requires_declared_required_variables() -> None:
    templates = _definition("message_templates")

    with pytest.raises(LineMessageConfigurationError, match="missing"):
        render_message_template(templates, "client_rebind_approved", {})

    rendered = render_message_template(
        templates,
        "client_rebind_approved",
        {"client_name": "測試客戶"},
    )
    assert "測試客戶" in rendered.payload_json
    registration = render_message_template(templates, "register_success")
    assert json.loads(registration.payload_json)["text"] == "申請已送出，待工會核准。"

    welcome = render_message_template(templates, "customer_onboarding_welcome", {"url": "https://example.test/register"})
    assert "本帳號採自助服務，一般留言不會有專員回覆" in json.loads(welcome.payload_json)["text"]


def test_retired_follow_schedule_enqueues_no_delivery_tasks() -> None:
    configurations = ConfigurationRepository(
        {
            LineConfigurationKind.MESSAGE_TEMPLATES: _snapshot(
                LineConfigurationKind.MESSAGE_TEMPLATES,
                "message_templates",
            ),
            LineConfigurationKind.MESSAGE_SCHEDULES: _snapshot(
                LineConfigurationKind.MESSAGE_SCHEDULES,
                "message_schedules",
            ),
        }
    )
    deliveries = RecordingRepository()
    uow = FakeUow(configurations=configurations, delivery_tasks=deliveries)
    inbox = SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value="event-follow-1"),
            occurred_at=FOLLOWED_AT,
        )
    )

    count = enqueue_follow_schedule(inbox, uow, LineUserId("U-stage5"))

    assert count == 0
    assert deliveries.items == []


def test_configuration_apply_requires_capability_and_commits_revision() -> None:
    repository = ConfigurationRepository({})
    audit = RecordingRepository()
    uow = FakeUow(configurations=repository, audit=audit)
    application = LineConfigurationApplication(lambda: uow)
    definition = _definition("message_templates")

    result = application.apply(
        kind=LineConfigurationKind.MESSAGE_TEMPLATES,
        expected_revision=LineConfigurationRevision(0),
        definition=definition,
        actor=ActorContext("admin:1", ("line.config.manage",)),
        reason="匯入現有範本",
        idempotency_key=IdempotencyKey("stage5-config:templates:1"),
        correlation_id=CorrelationId("stage5-config:templates:1"),
    )

    assert result.snapshot.revision == LineConfigurationRevision(1)
    assert uow.committed is True
    assert audit.items[0].action == "line.configuration.apply"


def test_exact_empty_rich_menu_configuration_is_repaired_once() -> None:
    repository = ConfigurationRepository({
        LineConfigurationKind.RICH_MENUS: LineConfigurationSnapshot(
            LineConfigurationKind.RICH_MENUS, LineConfigurationRevision(4), "{}",
        )
    })
    audit = RecordingRepository()
    uow = FakeUow(configurations=repository, audit=audit)
    application = LineConfigurationApplication(lambda: uow)

    result = application.repair_empty_rich_menu_configuration(
        _definition("line_menu"), ActorContext("system:repair", ("line.config.manage",)),
        correlation_id=CorrelationId("repair-empty-rich-menu"),
    )

    assert result.snapshot.revision == LineConfigurationRevision(5)
    assert audit.items[0].action == "line.configuration.repair_empty_rich_menus"
    assert uow.committed is True


def test_nonempty_rich_menu_configuration_is_never_repaired_by_bootstrap() -> None:
    repository = ConfigurationRepository({
        LineConfigurationKind.RICH_MENUS: _snapshot(
            LineConfigurationKind.RICH_MENUS, "line_menu"
        )
    })
    uow = FakeUow(configurations=repository, audit=RecordingRepository())

    result = LineConfigurationApplication(lambda: uow).repair_empty_rich_menu_configuration(
        _definition("line_menu"), ActorContext("system:repair", ("line.config.manage",)),
        correlation_id=CorrelationId("repair-nonempty-rich-menu"),
    )

    assert result is None
    assert repository.applied == []


def test_management_models_read_current_templates_without_renaming_formal_ids():
    from api.schemas.line_config import MessageTemplatesConfig, LineMenusConfig
    root = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
    templates = json.loads((root / 'config/message_templates.json').read_text(encoding='utf-8'))
    parsed = MessageTemplatesConfig.model_validate(templates)
    assert [item.id for item in parsed.templates] == [item['id'] for item in templates['templates']]
    LineMenusConfig.model_validate_json((root / 'config/line_menu.json').read_text(encoding='utf-8'))


class _SyncConfigurationRepository(ConfigurationRepository):
    def __init__(self, snapshots) -> None:
        super().__init__(snapshots)
        self.by_key = {}

    def get_by_idempotency_key(self, kind, key):
        snapshot = self.by_key.get(key.value)
        if snapshot is None or snapshot.kind is not kind:
            return None
        return snapshot

    def apply(self, command):
        result = super().apply(command)
        self.snapshots[command.candidate.kind] = result.snapshot
        self.by_key[command.idempotency_key.value] = result.snapshot
        return result


class _PublicationListRepository:
    def __init__(self, publications=()) -> None:
        self.publications = tuple(publications)

    def list_for_configuration_revision(self, _revision):
        return self.publications


def test_sync_rich_menu_from_definition_updates_stale_revision_once_and_preserves_ui_edits() -> None:
    from domains.line.rich_menu import LineRichMenuPublicationStatus
    from domains.line.rich_menu_draft import normalize_rich_menu_draft, project_saved_staff_menu

    current_file = _definition("line_menu")
    stale_definition = json.loads(json.dumps(current_file))
    for menu in stale_definition["menus"]:
        if menu["id"] == "customer_menu":
            menu["buttons"] = [
                {
                    "id": "old_profile",
                    "label": "修改登記資料",
                    "text_color": "#FFFFFF",
                    "background_color": "#2563EB",
                    "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
                    "action": {"type": "uri", "uri": "?target=profile_update", "uri_source": "liff"},
                    "border_radius": 54,
                },
                {
                    "id": "old_order",
                    "label": "修改訂單資訊",
                    "text_color": "#FFFFFF",
                    "background_color": "#0D9488",
                    "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
                    "action": {"type": "uri", "uri": "?target=order_update", "uri_source": "liff"},
                    "border_radius": 54,
                },
                {
                    "id": "old_faq",
                    "label": "常見問答",
                    "text_color": "#FFFFFF",
                    "background_color": "#3B82F6",
                    "bounds": {"x": 0, "y": 843, "width": 2500, "height": 843},
                    "action": {"type": "message", "text": "常見問答"},
                    "border_radius": 54,
                },
            ]
    repository = _SyncConfigurationRepository({
        LineConfigurationKind.RICH_MENUS: LineConfigurationSnapshot(
            LineConfigurationKind.RICH_MENUS,
            LineConfigurationRevision(9),
            canonical_line_payload_json(stale_definition),
        )
    })
    audit = RecordingRepository()
    publications = _PublicationListRepository((
        SimpleNamespace(status=LineRichMenuPublicationStatus.PUBLISHED),
    ))
    uow = FakeUow(configurations=repository, audit=audit, rich_menu_publications=publications)
    application = LineConfigurationApplication(lambda: uow)
    actor = ActorContext("system:sync", ("line.config.manage",))

    synced = application.sync_rich_menu_from_definition(
        current_file,
        actor,
        reason="啟動同步新版選單",
        correlation_id=CorrelationId("sync-test-1"),
    )

    assert synced is not None
    assert synced.snapshot.revision == LineConfigurationRevision(10)
    assert audit.items[0].action == "line.rich_menu.repo_sync"
    synced_menus = json.loads(synced.snapshot.definition_json)["menus"]
    customer = next(m for m in synced_menus if m["id"] == "customer_menu")
    assert [b["label"] for b in customer["buttons"]] == ["案件資訊", "常見問題"]

    # Subsequent UI edit must not be overwritten when the repo file digest is unchanged.
    ui_edited = normalize_rich_menu_draft(project_saved_staff_menu(current_file))
    for menu in ui_edited["menus"]:
        if menu["id"] == "customer_menu":
            menu["chat_bar_text"] = "客戶即時區"
    repository.snapshots[LineConfigurationKind.RICH_MENUS] = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(11),
        canonical_line_payload_json(ui_edited),
    )

    repeated = application.sync_rich_menu_from_definition(
        current_file,
        actor,
        reason="啟動同步新版選單",
        correlation_id=CorrelationId("sync-test-2"),
    )
    assert repeated is None
    assert repository.get(LineConfigurationKind.RICH_MENUS).revision == LineConfigurationRevision(11)


def test_sync_rich_menu_from_definition_noops_when_matching_or_publishing() -> None:
    from domains.line.rich_menu import LineRichMenuPublicationStatus
    from domains.line.rich_menu_draft import normalize_rich_menu_draft, project_saved_staff_menu

    current_file = _definition("line_menu")
    normalized = normalize_rich_menu_draft(project_saved_staff_menu(current_file))
    matching_repo = _SyncConfigurationRepository({
        LineConfigurationKind.RICH_MENUS: LineConfigurationSnapshot(
            LineConfigurationKind.RICH_MENUS,
            LineConfigurationRevision(14),
            canonical_line_payload_json(normalized),
        )
    })
    matching_uow = FakeUow(
        configurations=matching_repo,
        audit=RecordingRepository(),
        rich_menu_publications=_PublicationListRepository(),
    )
    actor = ActorContext("system:sync", ("line.config.manage",))
    assert (
        LineConfigurationApplication(lambda: matching_uow).sync_rich_menu_from_definition(
            current_file,
            actor,
            reason="已相符不新增版本",
            correlation_id=CorrelationId("sync-noop-match"),
        )
        is None
    )
    assert matching_repo.applied == []

    stale_definition = json.loads(json.dumps(current_file))
    stale_definition["menus"][1]["chat_bar_text"] = "舊選單列"
    publishing_repo = _SyncConfigurationRepository({
        LineConfigurationKind.RICH_MENUS: LineConfigurationSnapshot(
            LineConfigurationKind.RICH_MENUS,
            LineConfigurationRevision(9),
            canonical_line_payload_json(stale_definition),
        )
    })
    publishing_uow = FakeUow(
        configurations=publishing_repo,
        audit=RecordingRepository(),
        rich_menu_publications=_PublicationListRepository((
            SimpleNamespace(status=LineRichMenuPublicationStatus.PUBLISHING),
        )),
    )
    assert (
        LineConfigurationApplication(lambda: publishing_uow).sync_rich_menu_from_definition(
            current_file,
            actor,
            reason="發布中跳過同步",
            correlation_id=CorrelationId("sync-noop-publishing"),
        )
        is None
    )
    assert publishing_repo.applied == []
