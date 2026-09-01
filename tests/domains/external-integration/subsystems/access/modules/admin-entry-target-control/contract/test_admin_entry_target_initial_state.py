"""
File: test_admin_entry_target_initial_state.py
Description: 驗證 entry target 初始 state 的凍結 identity、registry 與 digest 契約。
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from subsystems.access.admin_entry_target_control import (
    AdminEntryTargetControl,
    ArtifactBinding,
    ArtifactHealth,
    FROZEN_ENTRY_TARGETS,
    EntryTargetError,
    SwitchCommand,
    ANOMALIES_INITIAL_REACT_ARTIFACT,
    calculate_state_digest,
    digest_value,
    make_initial_state,
    state_from_mapping,
    state_to_mapping,
)


class HealthyArtifact:
    def query(self):
        return ArtifactHealth(True, "react-v1", "a" * 64, "api-v1")


ROOT = Path(__file__).resolve().parents[8]
LEGACY_REGISTRY_DIGEST = "31de811259c9e737c5c136e85a4190fbeaa2278d67d83c396f2b55a62548a1ce"


def test_initial_state_matches_frozen_phase5a_mapping() -> None:
    payload = json.loads((ROOT / "config/admin_entry_targets.initial.json").read_text(encoding="utf-8"))
    state = state_from_mapping(payload)

    assert state == make_initial_state()
    assert {item.entry_id for item in state.entries} == set(FROZEN_ENTRY_TARGETS)
    assert state.entry("ui-react:#anomalies").current_target == "react"
    assert state.entry("ui-react:#anomalies").required_react_artifact == ANOMALIES_INITIAL_REACT_ARTIFACT
    assert all(
        item.current_target == ("react" if item.entry_id == "ui-react:#anomalies" else "streamlit")
        for item in state.entries
    )
    assert len(state.receipts) == 1
    assert state.receipts[0].entry_id == "ui-react:#anomalies"
    assert state.receipts[0].resulting_target == "react"
    assert state.entry("ui-react:#system-status").replacement_group == "reports-system"
    assert state.entry("ui-react:#system-status").streamlit_target == "/?entry=system-status"
    assert state.entry("ui-react:#system-status").react_target == "/admin/#system-status"
    assert not {
        "ui-react:#line-ai-events",
        "ui-react:#line-liff-studio",
        "ui-react:#line-security",
    } & {item.entry_id for item in state.entries}


def test_schema_is_closed_and_pins_registry_revision() -> None:
    schema = json.loads((ROOT / "config/admin_entry_targets.schema.json").read_text(encoding="utf-8"))

    assert schema["additionalProperties"] is False
    assert schema["properties"]["entries"]["minItems"] == 12
    assert schema["properties"]["entries"]["maxItems"] == 12
    assert schema["$defs"]["entry"]["additionalProperties"] is False
    assert schema["$defs"]["receipt"]["additionalProperties"] is False


def test_legacy_eleven_entry_registry_fails_closed() -> None:
    initial = make_initial_state()
    legacy = replace(
        initial,
        registry_revision="phase5a-mapped-entries-v1",
        registry_digest=LEGACY_REGISTRY_DIGEST,
        entries=tuple(item for item in initial.entries if item.entry_id != "ui-react:#system-status"),
        state_digest="",
    )
    legacy = replace(legacy, state_digest=calculate_state_digest(legacy))

    with pytest.raises(EntryTargetError, match="entry_target_registry_stale"):
        state_from_mapping(state_to_mapping(legacy))


def test_recomputed_digest_cannot_hide_revision_or_registry_drift() -> None:
    initial = make_initial_state()
    bad_revision = replace(initial, revision=3, state_digest="")
    bad_revision = replace(bad_revision, state_digest=calculate_state_digest(bad_revision))
    with pytest.raises(EntryTargetError, match="entry_target_receipt_chain_corrupt"):
        state_from_mapping(json.loads(json.dumps(state_to_mapping(bad_revision))))

    bad_registry = replace(initial, registry_revision="phase5a-mapped-entries-v2", state_digest="")
    bad_registry = replace(bad_registry, state_digest=calculate_state_digest(bad_registry))
    with pytest.raises(EntryTargetError, match="entry_target_registry_stale"):
        state_from_mapping(json.loads(json.dumps(state_to_mapping(bad_registry))))


def test_recomputed_digests_cannot_hide_malformed_receipt_identity() -> None:
    class MemoryStore:
        def __init__(self):
            self.state = make_initial_state()

        def read(self):
            return self.state

        def mutate(self, operation):
            self.state, result = operation(self.state)
            return result

    store = MemoryStore()
    AdminEntryTargetControl(store, HealthyArtifact()).apply(
        SwitchCommand(
            "ui-react:#orders", 2, 1, "streamlit", "react",
            ArtifactBinding("react-v1", "a" * 64, "api-v1"),
            "activate_react", "initial-state-switch", "admin:1", "correlation-1",
        )
    )
    payload = state_to_mapping(store.state)
    receipt = payload["receipts"][0]
    receipt["actor_id"] = "invalid actor identity"
    receipt["receipt_digest"] = digest_value({key: value for key, value in receipt.items() if key != "receipt_digest"})
    payload["state_digest"] = digest_value({key: value for key, value in payload.items() if key != "state_digest"})

    with pytest.raises(EntryTargetError, match="entry_target_receipt_chain_corrupt"):
        state_from_mapping(payload)


def test_recomputed_digests_cannot_hide_receipt_entry_artifact_mismatch() -> None:
    class MemoryStore:
        def __init__(self):
            self.state = make_initial_state()

        def read(self):
            return self.state

        def mutate(self, operation):
            self.state, result = operation(self.state)
            return result

    store = MemoryStore()
    AdminEntryTargetControl(store, HealthyArtifact()).apply(
        SwitchCommand(
            "ui-react:#orders", 2, 1, "streamlit", "react",
            ArtifactBinding("react-v1", "a" * 64, "api-v1"),
            "activate_react", "artifact-mismatch-switch", "admin:1", "correlation-1",
        )
    )
    payload = state_to_mapping(store.state)
    receipt = payload["receipts"][0]
    receipt["artifact_version"] = "react-v2"
    receipt["artifact_digest"] = "b" * 64
    receipt["api_compatibility_revision"] = "api-v2"
    receipt["receipt_digest"] = digest_value({key: value for key, value in receipt.items() if key != "receipt_digest"})
    payload["state_digest"] = digest_value({key: value for key, value in payload.items() if key != "state_digest"})

    with pytest.raises(EntryTargetError, match="entry_target_receipt_chain_corrupt"):
        state_from_mapping(payload)
