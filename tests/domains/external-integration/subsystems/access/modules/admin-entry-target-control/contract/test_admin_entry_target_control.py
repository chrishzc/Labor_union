"""
File: test_admin_entry_target_control.py
Description: 驗證 entry target Preview、單筆 CAS、artifact gate、重播、衝突與 rollback。
"""

from datetime import datetime, timezone

import pytest

from subsystems.access.admin_entry_target_control import (
    AdminEntryTargetControl,
    ArtifactBinding,
    ArtifactHealth,
    EntryTargetError,
    SwitchCommand,
    make_initial_state,
)


ARTIFACT = ArtifactBinding("react-v1", "a" * 64, "api-v1")
INITIAL_STATE = make_initial_state()


class MemoryStore:
    def __init__(self):
        self.state = make_initial_state()
        self.writes = 0

    def read(self):
        return self.state

    def mutate(self, operation):
        next_state, result = operation(self.state)
        if next_state != self.state:
            self.state = next_state
            self.writes += 1
        return result


class HealthyArtifact:
    def query(self):
        return ArtifactHealth(True, ARTIFACT.version, ARTIFACT.digest, ARTIFACT.api_compatibility_revision)


def command(**updates):
    values = {
        "entry_id": "ui-react:#orders",
        "expected_state_revision": INITIAL_STATE.revision,
        "expected_entry_revision": 1,
        "expected_current_target": "streamlit",
        "desired_target": "react",
        "required_react_artifact": ARTIFACT,
        "reason_code": "activate_react",
        "idempotency_key": "switch-orders-1",
        "actor_id": "admin:1",
        "correlation_id": "correlation-1",
    }
    values.update(updates)
    return SwitchCommand(**values)


def control(store, health=None):
    return AdminEntryTargetControl(
        store,
        health,
        clock=lambda: datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
    )


def test_preview_is_zero_write_and_apply_changes_only_one_entry() -> None:
    store = MemoryStore()
    workflow = control(store, HealthyArtifact())
    before = {item.entry_id: item for item in store.state.entries}

    preview = workflow.preview(command())
    receipt = workflow.apply(command())

    assert preview.desired_target == "react"
    assert store.writes == 1
    assert receipt.resulting_state_revision == INITIAL_STATE.revision + 1
    assert receipt.previous_receipt_digest == INITIAL_STATE.receipts[-1].receipt_digest
    after = {item.entry_id: item for item in store.state.entries}
    assert after["ui-react:#orders"].current_target == "react"
    assert after["ui-react:#orders"].entry_revision == 2
    assert all(after[key] == value for key, value in before.items() if key != "ui-react:#orders")


def test_replay_precedes_stale_checks_and_mismatch_conflicts() -> None:
    store = MemoryStore()
    workflow = control(store, HealthyArtifact())
    first = workflow.apply(command())

    replay = workflow.apply(command())
    assert replay.receipt_digest == first.receipt_digest
    assert replay.replayed is True
    assert store.writes == 1

    with pytest.raises(EntryTargetError, match="idempotency_key_conflict"):
        workflow.apply(command(entry_id="ui-react:#finance"))


def test_default_artifact_health_and_stale_or_noop_are_fail_closed() -> None:
    store = MemoryStore()
    with pytest.raises(EntryTargetError, match="react_artifact_unavailable"):
        control(store).apply(command())
    with pytest.raises(EntryTargetError, match="entry_target_stale"):
        control(store, HealthyArtifact()).apply(command(expected_state_revision=9))
    with pytest.raises(EntryTargetError, match="entry_target_noop"):
        control(store).apply(
            command(
                desired_target="streamlit",
                required_react_artifact=None,
                reason_code="rollback",
            )
        )
    assert store.writes == 0


def test_entry_revision_current_target_and_artifact_identity_are_independent_cas_gates() -> None:
    store = MemoryStore()
    workflow = control(store, HealthyArtifact())

    with pytest.raises(EntryTargetError, match="entry_target_stale"):
        workflow.apply(command(expected_entry_revision=9))
    with pytest.raises(EntryTargetError, match="entry_target_stale"):
        workflow.apply(command(expected_current_target="react"))

    class DifferentArtifact:
        def query(self):
            return ArtifactHealth(True, "react-v2", "b" * 64, "api-v1")

    with pytest.raises(EntryTargetError, match="react_artifact_stale"):
        control(store, DifferentArtifact()).apply(command())
    assert store.writes == 0


def test_rollback_uses_same_cas_and_appends_receipt_chain() -> None:
    store = MemoryStore()
    workflow = control(store, HealthyArtifact())
    activated = workflow.apply(command())
    rolled_back = workflow.apply(
        command(
            expected_state_revision=activated.resulting_state_revision,
            expected_entry_revision=2,
            expected_current_target="react",
            desired_target="streamlit",
            required_react_artifact=None,
            reason_code="rollback",
            idempotency_key="rollback-orders-1",
        )
    )

    assert rolled_back.previous_receipt_digest == activated.receipt_digest
    assert store.state.entry("ui-react:#orders").current_target == "streamlit"
    assert store.state.revision == INITIAL_STATE.revision + 2


def test_system_status_and_reports_share_group_but_keep_independent_cas_and_rollback() -> None:
    store = MemoryStore()
    workflow = control(store, HealthyArtifact())
    reports_before = store.state.entry("ui-react:#reports")

    activated = workflow.apply(
        command(
            entry_id="ui-react:#system-status",
            idempotency_key="switch-system-status-1",
        )
    )

    system_status = store.state.entry("ui-react:#system-status")
    assert system_status.replacement_group == reports_before.replacement_group == "reports-system"
    assert system_status.current_target == "react"
    assert store.state.entry("ui-react:#reports") == reports_before

    workflow.apply(
        command(
            entry_id="ui-react:#system-status",
            expected_state_revision=activated.resulting_state_revision,
            expected_entry_revision=activated.resulting_entry_revision,
            expected_current_target="react",
            desired_target="streamlit",
            required_react_artifact=None,
            reason_code="rollback",
            idempotency_key="rollback-system-status-1",
        )
    )

    assert store.state.entry("ui-react:#system-status").current_target == "streamlit"
    assert store.state.entry("ui-react:#reports") == reports_before
