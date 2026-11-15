"""
File: test_line_rich_menu_backup.py
Description: 驗證 LINE 圖文選單 ID 之原子備份、容災讀取與 Worker 雙寫整合。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contextlib import nullcontext
from types import SimpleNamespace

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import LineRichMenuPublicationId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.line.outbox_contracts import LineOutboxWorkItem, RICH_MENU_BINDING_INTENT
from subsystems.line.ports import LineRichMenuProviderPort
from subsystems.line.rich_menu_backup import (
    read_rich_menu_id_backup,
    write_rich_menu_id_backup,
)
from subsystems.line.rich_menu_binding import LineRichMenuBindingWorker
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
    LineRichMenuPublicationWorkItem,
)
from subsystems.line.rich_menu_worker import LineRichMenuWorker

NOW = datetime(2026, 8, 20, 4, tzinfo=timezone.utc)


def test_write_and_read_rich_menu_id_backup(tmp_path: Path):
    backup_file = tmp_path / "rich_menu_ids.json"

    # 1. 寫入 staff 選單
    write_rich_menu_id_backup("staff", "richmenu-staff-111", path=backup_file)
    assert read_rich_menu_id_backup("staff_menu", path=backup_file) == "richmenu-staff-111"
    assert read_rich_menu_id_backup("staff", path=backup_file) == "richmenu-staff-111"

    # 2. 寫入 visitor / default 選單，保留既有 staff
    write_rich_menu_id_backup("visitor", "richmenu-default-000", path=backup_file)
    assert read_rich_menu_id_backup("default_menu", path=backup_file) == "richmenu-default-000"
    assert read_rich_menu_id_backup("staff_menu", path=backup_file) == "richmenu-staff-111"

    # 3. customer_menu 未設置時回退到 default_menu
    assert read_rich_menu_id_backup("customer_menu", path=backup_file) == "richmenu-default-000"

    # 4. 寫入自訂 customer 選單後不再回退
    write_rich_menu_id_backup("customer", "richmenu-cust-222", path=backup_file)
    assert read_rich_menu_id_backup("customer_menu", path=backup_file) == "richmenu-cust-222"

    # 5. 重複寫入相同 ID 時無副作用
    write_rich_menu_id_backup("customer", "richmenu-cust-222", path=backup_file)
    data = json.loads(backup_file.read_text(encoding="utf-8"))
    assert data["customer_rich_menu_id"] == "richmenu-cust-222"


def test_read_backup_returns_none_on_missing_or_corrupt_file(tmp_path: Path):
    missing_file = tmp_path / "non_existent.json"
    assert read_rich_menu_id_backup("staff_menu", path=missing_file) is None

    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("invalid json content", encoding="utf-8")
    assert read_rich_menu_id_backup("staff_menu", path=corrupt_file) is None


class _FakePublicationRepo:
    def __init__(self, item):
        self.item = item
        self.recorded = []

    def claim(self, _query):
        return (self.item,) if self.item else ()

    def list_step_receipts(self, _publication_id):
        return ()

    def list_step_attempt_events(self, _publication_id):
        return ()

    def append_step_receipt(self, receipt):
        return receipt

    def append_step_attempt_event(self, event):
        return event

    def published_provider_menu_id(self, _definition_id, *, before_publication_id=None):
        return None

    def record(self, command):
        self.recorded.append(command)
        return self.item.publication


class _FakeUow:
    def __init__(self, repo):
        self.rich_menu_publications = repo
        self.identities = type("Identities", (), {"list_bound_by_subject_type": lambda self, _: ()})()
        self.outbox = type("Outbox", (), {"append": lambda self, _: None, "lock_menu_user": lambda self, _: None})()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        pass


class _FakeProvider:
    def create(self, request):
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id="richmenu-created-999",
        )

    def upload(self, request, menu_id):
        return LineRichMenuProviderOutcome(LineRichMenuProviderOutcomeType.SUCCESS, provider_menu_id=menu_id)

    def upsert_alias(self, request, menu_id):
        return LineRichMenuProviderOutcome(LineRichMenuProviderOutcomeType.SUCCESS, provider_menu_id=menu_id)

    def switch_default(self, request, menu_id):
        return LineRichMenuProviderOutcome(LineRichMenuProviderOutcomeType.SUCCESS, provider_menu_id=menu_id)


def test_rich_menu_worker_persists_backup_on_successful_publish():
    recorded_backups = {}

    def mock_backup_writer(role: str, menu_id: str):
        recorded_backups[role] = menu_id

    definition_json = canonical_line_payload_json({
        "id": "staff_menu",
        "name": "月嫂選單",
        "audience_role": "staff",
        "chat_bar_text": "月嫂專區",
    })
    snapshot = LineRichMenuPublicationSnapshot(
        LineRichMenuPublicationId(10),
        "staff_menu",
        1,
        LineRichMenuPublicationStatus.QUEUED,
    )
    work_item = LineRichMenuPublicationWorkItem(
        snapshot,
        definition_json,
        "rich-menu/test.png",
        0,
        3,
        "worker-1",
        NOW + timedelta(minutes=5),
        CorrelationId("test-corr"),
    )
    repo = _FakePublicationRepo(work_item)
    worker = LineRichMenuWorker(
        unit_of_work_factory=lambda: _FakeUow(repo),
        provider=_FakeProvider(),
        image_materializer=lambda def_json, ref: "resolved-ref",
        worker_identity="test-worker",
        now=lambda: NOW,
        ids_backup_writer=mock_backup_writer,
    )
    processed = worker.run_once()
    assert processed == 1
    assert recorded_backups.get("staff") == "richmenu-created-999"


class _RecordingOutbox:
    def menu_provider_lock(self, line_user_id):
        return nullcontext(True)

    def __init__(self, claimed=(), *, latest=7, lease_valid=True, reset_pending=False) -> None:
        self.appended = []
        self.claimed = tuple(claimed)
        self.completed = []
        self.latest = latest
        self.lease_valid = lease_valid
        self.reset_pending = reset_pending

    def append(self, intent) -> None:
        self.appended.append(intent)

    def claim(self, query):
        assert query.intent_type == RICH_MENU_BINDING_INTENT
        result, self.claimed = self.claimed, ()
        return result

    def complete(self, command) -> None:
        self.completed.append(command)

    def lock_menu_user(self, line_user_id):
        pass

    def lock_menu_lease(self, item, now):
        return self.lease_valid and now < item.lease_expires_at

    def latest_menu_intent_id(self, line_user_id):
        return self.latest

    def menu_reset_pending(self, line_user_id):
        return self.reset_pending


class _BindingUow:
    def __init__(self, outbox, provider_menu_id=None):
        self.outbox = outbox
        self.rich_menu_publications = type("Pub", (), {
            "published_provider_menu_id": lambda self, *a, **k: provider_menu_id
        })()
        self.identities = type("Id", (), {
            "list_bound_by_subject_type": lambda self, _: (),
            "list_by_user": lambda self, uid, **kw: (
                LineIdentityBindingSnapshot(
                    LineUserId("U-staff"),
                    LineIdentityBindingStatus.BOUND,
                    ExpectedVersion(1),
                    LineBindingSubjectType.STAFF,
                    "ST-001",
                ),
            ),
        })()
        self.audit = SimpleNamespace(append=lambda _: None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        pass


class _RecordingBindingProvider:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def link_to_user(self, provider_menu_id, line_user_id):
        self.calls.append((provider_menu_id, line_user_id))
        return self.outcome

    def get_user_rich_menu(self, line_user_id):
        return self.outcome


def _test_binding_work_item(provider_menu_id=None):
    payload = {"line_user_id": "U-staff", "menu_definition_id": "staff_menu"}
    if provider_menu_id is not None:
        payload["provider_menu_id"] = provider_menu_id
    return LineOutboxWorkItem(
        7,
        "line_identity",
        "U-staff",
        RICH_MENU_BINDING_INTENT,
        json.dumps(payload),
        1,
        5,
        "worker-1",
        NOW + timedelta(seconds=90),
        NOW + timedelta(minutes=10),
        True,
    )


def test_binding_worker_fallbacks_to_backup_when_db_has_no_published_menu(tmp_path: Path, monkeypatch):
    # 建立備份檔
    backup_file = tmp_path / "rich_menu_ids.json"
    backup_file.write_text(json.dumps({
        "staff_rich_menu_id": "richmenu-staff-backup-888"
    }), encoding="utf-8")

    from subsystems.line import rich_menu_backup
    monkeypatch.setattr(rich_menu_backup, "DEFAULT_IDS_BACKUP_PATH", backup_file)

    item = _test_binding_work_item(provider_menu_id=None)
    outbox = _RecordingOutbox((item,))
    provider = _RecordingBindingProvider(
        LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id="richmenu-staff-backup-888",
        )
    )

    uow = _BindingUow(outbox, provider_menu_id=None)
    worker = LineRichMenuBindingWorker(
        lambda: uow,
        provider,
        "worker-1",
        lambda: NOW,
    )
    assert worker.run_once() == 1
    # 成功從備份中讀取並連結至使用者！
    assert provider.calls == [("richmenu-staff-backup-888", LineUserId("U-staff"))]
    assert outbox.completed[0].succeeded is True
