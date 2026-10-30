"""
File: test_runtime_alert_target_application.py
Description: 驗證 runtime alert target 的 CAS、singleton、重播與原子交易契約。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.runtime_alert_target_application import (
    RuntimeAlertTargetApplication, _target_view,
    RuntimeAlertTargetError,
)
from subsystems.line.runtime_alert_target_contracts import (
    ResetLineAlertGroupCommand,
    SetLineAlertTargetEnabledCommand,
    command_fingerprint,
)


NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def _row(target_id=1, *, enabled=True, target_type="admin_user", updated=None):
    return {
        "id": target_id,
        "target_type": target_type,
        "display_name": "敏感對象不應外洩",
        "enabled": enabled,
        "minimum_status": "warning",
        "updated_at_utc": updated or NOW,
    }


class _Repo:
    def __init__(self, rows=()):
        self.rows = {row["id"]: dict(row) for row in rows}
        self.receipts = {}
        self.locked = False
        self.lock_calls = []
        self.release_calls = 0
        self.save_calls = 0
        self.update_calls = 0
        self.audits = []
        self.events = []
        self.next_receipt = None
        self.receipt_loads = 0

    def list_alert_targets(self):
        return tuple(self.rows.values())

    def list_admin_alert_candidates(self):
        return ()

    def load_admin_command_receipt(self, family, key, *, for_update=True):
        self.receipt_loads += 1
        if for_update and self.next_receipt is not None:
            return self.next_receipt
        return self.receipts.get((family, key))

    def save_alert_target_admin_audit(self, actor_id, action, receipt_id, details):
        self.audits.append((actor_id, action, receipt_id, details))

    def save_admin_command_receipt(self, family, key, fingerprint, actor, reason, result):
        self.save_calls += 1
        self.receipts[(family, key)] = {
            "request_fingerprint": fingerprint,
            "result_snapshot": result,
        }

    def acquire_alert_target_lock(self, timeout_seconds):
        self.lock_calls.append(timeout_seconds)
        self.locked = True
        return True

    def release_alert_target_lock(self):
        self.events.append("release")
        self.release_calls += 1
        self.locked = False
        return True

    def find_active_group_targets(self, *, for_update):
        return tuple(
            row for row in self.rows.values()
            if row["target_type"] == "group" and row["enabled"]
        )

    def get_alert_target(self, target_id, *, for_update):
        return self.rows.get(target_id)

    def find_group_target(self, group_id, *, for_update):
        return next((row for row in self.rows.values() if row.get("group_id") == group_id), None)

    def insert_group_target(self, group_id, display_name, actor_id):
        target_id = max(self.rows, default=0) + 1
        self.rows[target_id] = _row(target_id)
        self.rows[target_id]["group_id"] = group_id
        return target_id

    def update_alert_target_enabled(self, target_id, enabled):
        self.update_calls += 1
        self.rows[target_id]["enabled"] = enabled
        self.rows[target_id]["updated_at_utc"] = NOW


class _Audit:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


class _Uow:
    def __init__(self, repo):
        self.runtime_monitor = repo
        self.audit = _Audit()
        self.commits = 0
        self.rollbacks = 0
        self.hooks = []
        self.events = repo.events

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        if not self.commits:
            self.rollbacks += 1
            hooks, self.hooks = self.hooks, []
            for hook in hooks:
                hook()
        return False

    def commit(self):
        self.events.append("commit")
        self.commits += 1
        hooks, self.hooks = self.hooks, []
        for hook in hooks:
            hook()

    def add_after_completion(self, hook):
        self.hooks.append(hook)

    def rollback(self):
        self.rollbacks += 1


def _factory(repo, holder):
    def make():
        unit = _Uow(repo)
        holder.append(unit)
        return unit

    return make


def _actor():
    return ActorContext("admin:7", ())


def test_preferences_query_and_rejected_edit_do_not_commit():
    repo = _Repo((_row(),))
    repo.get_target_preferences = lambda target_id: {"system_health": False}
    units = []
    app = RuntimeAlertTargetApplication(_factory(repo, units), lambda: NOW)
    assert app.get_target_preferences(1) == {"system_health": False}
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.save_target_preferences(1, {"system_health": True})
    assert error.value.code == "line_admin_push_retired"
    assert all(unit.commits == 0 for unit in units)
    assert repo.update_calls == repo.save_calls == 0


def test_preferences_edit_preserves_missing_target_error():
    repo = _Repo()
    def missing(target_id):
        raise LookupError(target_id)
    repo.get_target_preferences = missing
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.save_target_preferences(1, {"system_health": True})
    assert error.value.code == "line_admin_push_retired"


def _disable_command(expected, reason, key, correlation, actor, fingerprint=None):
    return SetLineAlertTargetEnabledCommand(1, expected, False, reason, key, correlation, actor, fingerprint)


def _reset(repo, expected, key="reset-1"):
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    return app.set_enabled(
        _disable_command(
            expected,
            "群組輪替",
            IdempotencyKey(key),
            CorrelationId("corr-1"),
            _actor(),
        )
    )


def test_group_cannot_be_enabled_or_previewed_and_is_not_listed():
    repo = _Repo((_row(1, target_type="group"), _row(2, target_type="group", enabled=False)))
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    assert app.list_targets() == ()
    command = SetLineAlertTargetEnabledCommand(2, _target_view(repo.rows[2]).current_version, True,
        "舊入口", IdempotencyKey("enable-group"), CorrelationId("group"), _actor())
    repo.receipts[("line_alert_target", "enable-group")] = {"historical": "receipt"}
    for operation in (app.preview, app.set_enabled):
        with pytest.raises(RuntimeAlertTargetError) as error:
            operation(command)
        assert error.value.code == "line_admin_push_retired"
    assert repo.update_calls == repo.save_calls == 0


@pytest.mark.parametrize("existing", [False, True])
def test_retired_group_registration_and_reset_cannot_write_even_with_old_receipt(existing):
    repo = _Repo((_row(target_type="group"),) if existing else ())
    repo.receipts[("line_alert_target", "line-alert-registration:event-1")] = {"legacy": "receipt"}
    uow = _Uow(repo)
    app = RuntimeAlertTargetApplication(lambda: uow, lambda: NOW)
    command = ResetLineAlertGroupCommand("old-version", "舊入口", IdempotencyKey("reset-group"), CorrelationId("group"), _actor())
    for operation in (lambda: app.register_group(uow, "private-group", "admin:7", "event-1"),
                      lambda: app.reset(command), lambda: app.preview(command)):
        with pytest.raises(RuntimeAlertTargetError) as error:
            operation()
        assert error.value.code == "line_alert_group_retired"
        assert "private-group" not in error.value.message
    assert repo.update_calls == repo.save_calls == uow.commits == 0
    assert repo.lock_calls == []


def test_pymysql_naive_datetime_shape_is_explicitly_utc_at_boundary():
    repo = _Repo((_row(updated=NOW.replace(tzinfo=None)),))
    view = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW).list_targets()[0]
    assert view.updated_at.tzinfo == timezone.utc


def test_aware_non_utc_datetime_is_rejected_as_corrupt():
    repo = _Repo((_row(updated=NOW.astimezone(timezone(timedelta(hours=8)))),))
    with pytest.raises(RuntimeAlertTargetError) as error:
        RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW).list_targets()
    assert error.value.code == "line_alert_target_persistence_corrupt"


def test_corrupt_target_row_is_closed_typed_error():
    repo = _Repo((_row(),))
    del repo.rows[1]["minimum_status"]
    with pytest.raises(RuntimeAlertTargetError) as error:
        RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW).list_targets()
    assert error.value.code == "line_alert_target_persistence_corrupt"


@pytest.mark.parametrize("operation", ["add", "enable", "disable", "preview", "preferences"])
@pytest.mark.parametrize("stored_receipt", [None, "{broken", {"historical":"receipt"}])
def test_retired_personal_target_writers_reject_before_opening_any_uow(operation, stored_receipt):
    from types import SimpleNamespace
    def forbidden():
        pytest.fail("retired writer opened a read/write transaction")
    app = RuntimeAlertTargetApplication(forbidden, lambda: NOW)
    command = SimpleNamespace(enabled=operation == "enable", existing_receipt=stored_receipt)
    call = {"add": lambda: app.add_admin_target(command), "enable": lambda: app.set_enabled(command),
            "disable": lambda: app.set_enabled(command), "preview": lambda: app.preview(command),
            "preferences": lambda: app.save_target_preferences(1, {"system_health":True})}[operation]
    with pytest.raises(RuntimeAlertTargetError) as error:
        call()
    assert error.value.code == "line_admin_push_retired"
