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
    RuntimeAlertTargetApplication,
    RuntimeAlertTargetError,
)
from subsystems.line.runtime_alert_target_contracts import (
    ResetLineAlertGroupCommand,
    SetLineAlertTargetEnabledCommand,
    command_fingerprint,
)


NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def _row(target_id=1, *, enabled=True, target_type="group", updated=None):
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


def _reset(repo, expected, key="reset-1"):
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    return app.reset(
        ResetLineAlertGroupCommand(
            expected,
            "群組輪替",
            IdempotencyKey(key),
            CorrelationId("corr-1"),
            _actor(),
        )
    )


def test_reset_requires_fresh_version_and_commits_receipt_and_audit():
    repo = _Repo((_row(),))
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    current = app.list_targets()[0].current_version

    result = app.reset(
        ResetLineAlertGroupCommand(
            current,
            "群組輪替",
            IdempotencyKey("reset-1"),
            CorrelationId("corr-1"),
            _actor(),
        )
    )

    assert result.resulting_state == "disabled"
    assert repo.rows[1]["enabled"] is False
    assert repo.save_calls == 1
    assert repo.release_calls == 1


def test_reset_preview_is_zero_write_and_apply_requires_matching_fingerprint():
    repo = _Repo((_row(),))
    holder = []
    app = RuntimeAlertTargetApplication(_factory(repo, holder), lambda: NOW)
    current = app.list_targets()[0].current_version
    command = ResetLineAlertGroupCommand(
        current,
        "群組輪替",
        IdempotencyKey("reset-preview-1"),
        CorrelationId("corr-preview-1"),
        _actor(),
    )

    preview = app.preview(command)

    assert preview.operation == "group_reset"
    assert preview.previous_state == "active"
    assert preview.resulting_state == "disabled"
    assert preview.current_version == current
    assert preview.apply_ready is True
    assert repo.update_calls == 0
    assert repo.save_calls == 0
    assert repo.audits == []
    assert repo.lock_calls == []

    with pytest.raises(RuntimeAlertTargetError) as mismatch:
        app.reset(ResetLineAlertGroupCommand(
            current,
            "群組輪替",
            IdempotencyKey("reset-preview-1"),
            CorrelationId("corr-preview-1"),
            _actor(),
            PreviewFingerprint("0" * 64),
        ))
    assert mismatch.value.code == "line_alert_target_preview_conflict"
    assert repo.update_calls == 0

    receipt = app.reset(ResetLineAlertGroupCommand(
        current,
        "群組輪替",
        IdempotencyKey("reset-preview-1"),
        CorrelationId("corr-preview-1"),
        _actor(),
        preview.preview_fingerprint,
    ))
    assert receipt.resulting_state == "disabled"
    assert repo.update_calls == 1


def test_stale_reset_is_zero_write_and_typed_conflict():
    repo = _Repo((_row(),))
    with pytest.raises(RuntimeAlertTargetError) as error:
        _reset(repo, "stale-token")
    assert error.value.code == "line_alert_target_version_conflict"
    assert repo.update_calls == 0


def test_same_key_replay_returns_receipt_without_second_write():
    repo = _Repo((_row(),))
    holder = []
    app = RuntimeAlertTargetApplication(_factory(repo, holder), lambda: NOW)
    current = app.list_targets()[0].current_version
    command = ResetLineAlertGroupCommand(
        current,
        "群組輪替",
        IdempotencyKey("reset-1"),
        CorrelationId("corr-1"),
        _actor(),
    )
    first = app.reset(command)
    second = app.reset(command)
    assert first.receipt_id == second.receipt_id
    assert second.replayed is True
    assert repo.update_calls == 1
    assert repo.save_calls == 1


def test_same_key_different_payload_is_rejected():
    repo = _Repo((_row(),))
    holder = []
    app = RuntimeAlertTargetApplication(_factory(repo, holder), lambda: NOW)
    current = app.list_targets()[0].current_version
    app.reset(ResetLineAlertGroupCommand(
        current, "第一次", IdempotencyKey("reset-1"), CorrelationId("corr-1"), _actor()
    ))
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.reset(ResetLineAlertGroupCommand(
            current, "不同原因", IdempotencyKey("reset-1"), CorrelationId("corr-1"), _actor()
        ))
    assert error.value.code == "line_alert_target_idempotency_mismatch"


def test_enable_competing_group_fails_closed_without_disabling_other():
    repo = _Repo((_row(1), _row(2, enabled=False)))
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    current = app.list_targets()[1].current_version
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.set_enabled(SetLineAlertTargetEnabledCommand(
            2, current, True, "啟用備援", IdempotencyKey("enable-2"),
            CorrelationId("corr-2"), _actor()
        ))
    assert error.value.code == "line_alert_group_already_active"
    assert repo.rows[1]["enabled"] is True
    assert repo.rows[2]["enabled"] is False
    assert repo.update_calls == 0


def test_lock_failure_is_unavailable_and_does_not_write():
    repo = _Repo((_row(),))
    repo.acquire_alert_target_lock = lambda _timeout: False
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    current = app.list_targets()[0].current_version
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.reset(ResetLineAlertGroupCommand(
            current, "鎖定測試", IdempotencyKey("reset-lock"),
            CorrelationId("corr-lock"), _actor()
        ))
    assert error.value.code == "line_alert_target_serialization_unavailable"
    assert repo.update_calls == 0


def test_post_commit_release_failure_is_typed_unknown_without_rollback_mask():
    repo = _Repo((_row(),))
    holder = []
    app = RuntimeAlertTargetApplication(_factory(repo, holder), lambda: NOW)
    current = app.list_targets()[0].current_version
    repo.release_alert_target_lock = lambda: False
    command = ResetLineAlertGroupCommand(
        current, "群組輪替", IdempotencyKey("release-unknown"), CorrelationId("corr-release"), _actor()
    )
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.reset(command)
    assert error.value.code == "line_alert_target_commit_outcome_unknown"
    assert holder[-1].commits == 1
    assert holder[-1].rollbacks == 0


def test_atomic_admin_audit_failure_prevents_commit():
    repo = _Repo((_row(),))
    holder = []
    app = RuntimeAlertTargetApplication(_factory(repo, holder), lambda: NOW)
    current = app.list_targets()[0].current_version
    repo.save_alert_target_admin_audit = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit"))
    command = ResetLineAlertGroupCommand(
        current, "群組輪替", IdempotencyKey("audit-failure"), CorrelationId("corr-audit"), _actor()
    )
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.reset(command)
    assert error.value.code == "line_alert_target_persistence_unavailable"
    assert holder[-1].commits == 0
    assert holder[-1].rollbacks == 1


def test_registration_commits_before_after_completion_release():
    repo = _Repo(())
    uow = _Uow(repo)
    app = RuntimeAlertTargetApplication(lambda: uow, lambda: NOW)
    assert app.register_group(uow, "group-1", "admin:7", "event-1") is True
    assert repo.locked is True
    assert repo.events == []
    uow.commit()
    assert repo.events == ["commit", "release"]
    assert repo.audits[0][1] == "line.alert_target.register"
    assert repo.audits[0][2] == 1


def test_registration_same_key_replay_does_not_repeat_mutation():
    repo = _Repo(())
    uow = _Uow(repo)
    app = RuntimeAlertTargetApplication(lambda: uow, lambda: NOW)
    assert app.register_group(uow, "group-1", "admin:7", "event-1") is True
    row_count = len(repo.rows)
    assert app.register_group(uow, "group-1", "admin:7", "event-1") is True
    assert len(repo.rows) == row_count


def test_registration_post_lock_race_replays_existing_receipt():
    source = _Repo(())
    source_uow = _Uow(source)
    app = RuntimeAlertTargetApplication(lambda: source_uow, lambda: NOW)
    app.register_group(source_uow, "group-1", "admin:7", "event-1")
    stored = next(iter(source.receipts.values()))
    repo = _Repo(())
    repo.next_receipt = stored
    uow = _Uow(repo)
    app = RuntimeAlertTargetApplication(lambda: uow, lambda: NOW)
    assert app.register_group(uow, "group-1", "admin:7", "event-1") is True
    assert repo.rows == {}


def test_registration_audit_failure_rolls_back_then_releases():
    repo = _Repo(())
    repo.save_alert_target_admin_audit = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit"))
    uow = _Uow(repo)
    app = RuntimeAlertTargetApplication(lambda: uow, lambda: NOW)
    with pytest.raises(RuntimeError, match="audit"):
        app.register_group(uow, "group-1", "admin:7", "event-1")
    uow.__exit__(RuntimeError, RuntimeError("audit"), None)
    assert uow.rollbacks == 1
    assert repo.events == ["release"]


def test_registration_same_key_different_group_is_typed_mismatch_without_identity_leak():
    repo = _Repo(())
    uow = _Uow(repo)
    app = RuntimeAlertTargetApplication(lambda: uow, lambda: NOW)
    app.register_group(uow, "private-group-a", "admin:7", "event-1")
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.register_group(uow, "private-group-b", "admin:7", "event-1")
    assert error.value.code == "line_alert_target_idempotency_mismatch"
    assert "private-group" not in error.value.message


def test_pymysql_naive_datetime_shape_is_explicitly_utc_at_boundary():
    repo = _Repo((_row(updated=NOW.replace(tzinfo=None)),))
    view = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW).list_targets()[0]
    assert view.updated_at.tzinfo == timezone.utc


def test_aware_non_utc_datetime_is_rejected_as_corrupt():
    repo = _Repo((_row(updated=NOW.astimezone(timezone(timedelta(hours=8)))),))
    with pytest.raises(RuntimeAlertTargetError) as error:
        RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW).list_targets()
    assert error.value.code == "line_alert_target_persistence_corrupt"


@pytest.mark.parametrize("snapshot", ["{broken", {}, {"receipt_id": "only-one-field"}])
def test_corrupt_receipt_is_closed_typed_error(snapshot):
    repo = _Repo((_row(),))
    app = RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW)
    current = app.list_targets()[0].current_version
    command = ResetLineAlertGroupCommand(
        current, "群組輪替", IdempotencyKey("reset-1"), CorrelationId("corr-1"), _actor()
    )
    repo.receipts[("line_alert_target", "reset-1")] = {
        "request_fingerprint": command_fingerprint(command).value,
        "result_snapshot": snapshot,
    }
    with pytest.raises(RuntimeAlertTargetError) as error:
        app.reset(command)
    assert error.value.code == "line_alert_target_persistence_corrupt"


def test_corrupt_target_row_is_closed_typed_error():
    repo = _Repo((_row(),))
    del repo.rows[1]["minimum_status"]
    with pytest.raises(RuntimeAlertTargetError) as error:
        RuntimeAlertTargetApplication(_factory(repo, []), lambda: NOW).list_targets()
    assert error.value.code == "line_alert_target_persistence_corrupt"
