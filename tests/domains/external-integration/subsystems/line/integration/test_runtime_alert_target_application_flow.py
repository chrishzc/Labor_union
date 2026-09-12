"""Application flow regression for disabling and replacing the active LINE alert group."""

from datetime import datetime, timezone

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication
from subsystems.line.runtime_alert_target_contracts import SetLineAlertTargetEnabledCommand


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class _Repository:
    def __init__(self) -> None:
        self.rows = {
            7: {
                "id": 7,
                "group_id": "group-a",
                "target_type": "group",
                "display_name": "測試 LINE 群組",
                "enabled": True,
                "minimum_status": "critical",
                "updated_at_utc": NOW,
            }
        }
        self.receipts = {}
        self.update_calls = 0
        self.audits = []
        self.locked = False

    def list_alert_targets(self):
        return tuple(self.rows.values())

    def list_admin_alert_candidates(self):
        return ()

    def load_admin_command_receipt(self, family, key, *, for_update=True):
        return self.receipts.get((family, key))

    def save_admin_command_receipt(self, family, key, fingerprint, actor, reason, result):
        self.receipts[(family, key)] = {
            "request_fingerprint": fingerprint,
            "result_snapshot": result,
        }

    def save_alert_target_admin_audit(self, actor_id, action, resource_id, details):
        self.audits.append((actor_id, action, resource_id, details))

    def acquire_alert_target_lock(self, _timeout_seconds):
        self.locked = True
        return True

    def release_alert_target_lock(self):
        self.locked = False
        return True

    def get_alert_target(self, target_id, *, for_update):
        return self.rows.get(target_id)

    def find_active_group_targets(self, *, for_update):
        return tuple(row for row in self.rows.values() if row["target_type"] == "group" and row["enabled"])

    def find_group_target(self, group_id, *, for_update):
        return next((row for row in self.rows.values() if row.get("group_id") == group_id), None)

    def update_alert_target_enabled(self, target_id, enabled):
        self.update_calls += 1
        self.rows[target_id]["enabled"] = enabled
        self.rows[target_id]["updated_at_utc"] = NOW

    def insert_group_target(self, group_id, display_name, actor_id):
        target_id = max(self.rows) + 1
        self.rows[target_id] = {
            "id": target_id,
            "group_id": group_id,
            "target_type": "group",
            "display_name": display_name,
            "enabled": True,
            "minimum_status": "critical",
            "updated_at_utc": NOW,
        }
        return target_id


class _UnitOfWork:
    def __init__(self, repository) -> None:
        self.runtime_monitor = repository
        self.commits = 0
        self.hooks = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.commits += 1
        hooks, self.hooks = self.hooks, []
        for hook in hooks:
            hook()

    def add_after_completion(self, hook):
        self.hooks.append(hook)


def test_disable_preview_apply_readback_then_new_group_registration_preserves_singleton():
    repository = _Repository()
    units = []
    app = RuntimeAlertTargetApplication(lambda: units.append(_UnitOfWork(repository)) or units[-1], lambda: NOW)
    current = app.list_targets()[0].current_version
    actor = ActorContext("admin:7", ())
    preview_command = SetLineAlertTargetEnabledCommand(
        7, current, False, "解除目前群組", IdempotencyKey("disable-group-a"),
        CorrelationId("corr-disable-group-a"), actor,
    )

    preview = app.preview(preview_command)

    assert preview.operation == "disable"
    assert preview.previous_state == "active"
    assert preview.resulting_state == "disabled"
    assert repository.update_calls == 0
    assert app.list_targets()[0].state == "active"

    receipt = app.set_enabled(SetLineAlertTargetEnabledCommand(
        7, current, False, "解除目前群組", IdempotencyKey("disable-group-a"),
        CorrelationId("corr-disable-group-a"), actor, preview.preview_fingerprint,
    ))

    assert receipt.operation == "disable"
    assert receipt.previous_state == "active"
    assert receipt.resulting_state == "disabled"
    assert repository.update_calls == 1
    assert repository.audits
    assert app.list_targets()[0].state == "disabled"

    registration_unit = _UnitOfWork(repository)
    assert app.register_group(registration_unit, "group-b", "admin:7", "event-group-b") is True
    registration_unit.commit()

    targets = app.list_targets()
    assert [target.state for target in targets if target.target_kind == "group"] == ["disabled", "active"]
    assert sum(target.target_kind == "group" and target.state == "active" for target in targets) == 1
