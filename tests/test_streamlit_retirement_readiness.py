"""
File: test_streamlit_retirement_readiness.py
Description: 驗證 Phase6A rich receipt、registry、retention 與 fail-closed 契約。
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts.validate_streamlit_retirement_readiness import (
    INSTALLATION_STATUS,
    NOT_READY_STATUS,
    READY_CLEANUP_STATUS,
    READY_ENTRY_STATUS,
    installation_check,
    release_readiness,
)

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "validation" / "scenarios" / "react_admin_retirement_requirements.json"
NOW = "2026-08-21T12:00:00Z"
BASE = "f9240b9e3abbcf665b5c979e0973f675197d8494"


def _sha(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _receipt(fields: dict[str, object]) -> dict[str, object]:
    result = dict(fields)
    result["receipt_digest"] = _sha(result)
    return result


def _entry_receipts(entry_id: str, source: str, artifact: str) -> dict[str, dict[str, object]]:
    common = {"entry_id": entry_id, "base_ref": BASE, "source_digest": source, "artifact_digest": artifact, "status": "closed_success"}
    switch = _receipt({**common, "receipt_id": f"switch:{entry_id}", "occurred_at": "2026-08-21T01:00:00Z", "previous_receipt_digest": None, "manifest_revision": "phase5a-baseline-v3-system-status-identity", "previous_target": "streamlit", "current_target": "react", "changed_entry_ids": [entry_id], "cas_entry_count": 1, "audit_id": f"audit:{entry_id}", "audit_recorded": True})
    observation = _receipt({**common, "receipt_id": f"observation:{entry_id}", "occurred_at": "2026-08-21T03:00:00Z", "previous_receipt_digest": switch["receipt_digest"], "observation_started_at": "2026-08-21T02:00:00Z", "observation_ended_at": "2026-08-21T03:00:00Z", "observation_outcome": "closed_success", "command": "browser-smoke --entry", "http_status": 200, "response_contract": {"status": 200}, "browser_url": "http://127.0.0.1:5174/admin/", "browser_dom_identity": f"dom:{entry_id}", "network_evidence": [{"method": "GET", "status": 200}], "totp_auth_mode": "real-account-totp", "focused_tests": ["tests/entry_contract.py"]})
    rollback = _receipt({**common, "receipt_id": f"rollback:{entry_id}", "occurred_at": "2026-08-21T04:00:00Z", "previous_receipt_digest": observation["receipt_digest"], "switch_back_rehearsal_id": f"rehearsal:{entry_id}", "switch_back_manifest_revision": "phase5a-baseline-v3-system-status-identity", "switch_back_previous_target": "react", "switch_back_current_target": "streamlit", "switch_back_changed_entry_ids": [entry_id], "switch_back_cas_entry_count": 1, "switch_back_audit_id": f"rollback-audit:{entry_id}", "switch_back_audit_recorded": True, "command": "switch-back-rehearsal --entry", "http_status": 200, "response_contract": {"status": 200}, "focused_tests": ["tests/rollback_contract.py"]})
    forward = _receipt({**common, "receipt_id": f"forward:{entry_id}", "occurred_at": "2026-08-21T05:00:00Z", "previous_receipt_digest": rollback["receipt_digest"], "canonical_query": {"root_fact": entry_id}, "react_query": {"root_fact": entry_id, "version": 1}, "streamlit_query": {"root_fact": entry_id, "version": 1}, "react_requery": {"root_fact": entry_id, "version": 1}, "compatibility_proof": {"same_root_fact": True, "same_version": True, "same_receipt": True, "same_outbox": True, "same_anomaly": True, "same_audit": True, "proof_status": "closed_success"}, "focused_tests": ["tests/forward_data_contract.py"]})
    return {"switch": switch, "observation": observation, "rollback": rollback, "forward": forward}


def _entry(requirements: dict[str, object], index: int) -> dict[str, object]:
    entry_id = requirements["legacy_entries"][index]
    source = f"{index + 1:064x}"
    artifact = f"{index + 101:064x}"
    receipts = _entry_receipts(entry_id, source, artifact)
    return {
        "entry_id": entry_id,
        "source_path": f"ui/legacy_{index}.py",
        "source_digest": source,
        "artifact_digest": artifact,
        "base_ref": BASE,
        "git_state": "tracked",
        "static_callers": [f"ui/app.py::PAGE_REGISTRY[{index}]"],
        "dynamic_callers": [f"MasterLayout.tsx::route[{index}]"],
        "launcher_callers": ["scripts/launchers/start_local_development.bat"],
        "monitor_callers": ["scripts/run_service_monitor.py"],
        "migration_rehearsal_callers": ["scripts/migrate_preserved_database_additive_schema.py"],
        "dependency_owner": "Global Entry Point Governance",
        "test_disposition": {"status": "PASS", "focused_tests": ["tests/entry_contract.py"], "notes": "fresh receipt"},
        "replacement_identity": {"entry_id": requirements["react_entries"][index], "target": "react", "route": f"/admin/entry-{index}", "owner": "React Admin", "contract": "typed GET"},
        "current_inbound_links": ["document/current-ssot.md"],
        "archive_inbound_links": ["document/archive-restore.md"],
        "disposition": "migrate_then_remove",
        "release_identity": {"release_id": f"react-release:{index}", "manifest_revision": requirements["registry_revision"], "artifact_digest": artifact, "target": "react"},
        "deletion_authorization": {"status": "approved", "approved_by": "release-owner", "approved_at": "2026-08-21T11:00:00Z", "role": requirements["release_owner_role"], "entry_id": entry_id, "source_digest": source, "manifest_revision": requirements["registry_revision"]},
        "restore_procedure": {"command": "restore-entry --id", "source": f"backup/ui/legacy_{index}.py", "owner": "Global Entry Point Governance", "verified": True},
        "current_target": "react",
        "previous_target": "streamlit",
        "cas_entry_count": 1,
        "browser_verified": True,
        "totp_verified": True,
        "switch_receipt": receipts["switch"],
        "observation_receipt": receipts["observation"],
        "rollback_receipt": receipts["rollback"],
        "forward_data_receipt": receipts["forward"],
        "observation_outcome": "closed_success",
        "retention_history": [
            {"state": "pending", "at": "2026-08-21T06:00:00Z"},
            {"state": "active", "at": "2026-08-21T07:00:00Z"},
            {"state": "completed_not_expired", "at": "2026-08-21T08:00:00Z"},
            {"state": "expired_approved", "at": "2026-08-21T09:00:00Z"},
        ],
        "retention_end": "2026-08-21T10:00:00Z",
        "active_rollback_triggers": [{"trigger_id": f"trigger:{index}", "active": False}],
    }


def _release_component(requirements: dict[str, object], kind: str, artifact: str) -> dict[str, object]:
    return {
        "release_id": f"phase6b-{kind}-release",
        "package_id": f"phase6b-{kind}-package",
        "base_ref": BASE,
        "artifact_digest": artifact,
        "manifest_revision": requirements["registry_revision"],
        "api_compatibility": {"mode": "option-c", "manifest_identity": f"manifest:{kind}", "contract_status": "PASS"},
        "current_binding": {"entry_selector": f"admin-{kind}", "target": "react"},
        "previous_binding": {"entry_selector": f"streamlit-{kind}", "target": "streamlit"},
        "retention_identity": f"retention:{kind}",
        "retention_state": "completed_not_expired",
        "retention_end": "2026-09-01T00:00:00Z",
        "browser_rehearsal": {"command": f"browser-rehearsal --{kind}", "http_status": 200, "dom_identity": f"dom:{kind}", "network_evidence": [{"status": 200}], "totp_auth_mode": "real-account-totp"},
        "rollback_rehearsal": {"command": f"rollback-rehearsal --{kind}", "status": "closed_success", "previous_artifact_digest": "b" * 64, "current_artifact_digest": artifact},
        "closed_outcome": "closed_success",
        "approval": {"approved_by": "release-owner", "approved_at": "2026-08-21T11:00:00Z", "role": requirements["release_owner_role"]},
    }


def _inventory(requirements: dict[str, object], *, removal: bool = False) -> dict[str, object]:
    entries = [_entry(requirements, index) for index in range(10)]
    sources = [
        {"kind": "streamlit", "locator": "ui/app.py::PAGE_REGISTRY", "extraction_method": "AST registry", "digest": "1" * 64},
        {"kind": "react", "locator": "ui_react/src/MasterLayout.tsx::route registry", "extraction_method": "AST route map", "digest": "2" * 64},
        {"kind": "api", "locator": "api/main.py + api/routes/**/*.py", "extraction_method": "route inventory", "digest": "3" * 64},
        {"kind": "cli", "locator": "scripts/**/*.py + scripts/launchers/**", "extraction_method": "operator entry inventory", "digest": "4" * 64},
    ]
    source_receipts = [_receipt({"receipt_id": f"source:{entry['entry_id']}", "entry_id": entry["entry_id"], "source_path": entry["source_path"], "source_digest": entry["source_digest"], "base_ref": BASE, "status": "closed_success"}) for entry in entries]
    bindings = [{"entry_id": entry["entry_id"], "artifact_identity": entry["release_identity"]["release_id"], "artifact_digest": entry["artifact_digest"], "manifest_revision": requirements["registry_revision"], "current_target": "react", "previous_target": "streamlit", "status": "closed_success"} for entry in entries]
    result = {
        "schema_version": 1,
        "inventory_producer": "Independent Inventory Owner",
        "registry_revision": requirements["registry_revision"],
        "base_ref": BASE,
        "generated_at": "2026-08-21T11:30:00Z",
        "scope": "all Phase6A Streamlit source and runtime callers",
        "exclude_rules": "node_modules; generated caches; secrets",
        "reproduction_command": "python -m scripts.build_retirement_inventory",
        "count_kind": "files_and_matches",
        "files_count": 10,
        "matches_count": 10,
        "open_findings": [],
        "full_registry_sources": sources,
        "source_receipts": source_receipts,
        "artifact_bindings": bindings,
        "entries": entries,
        "remaining_runtime_owners": [] if removal else ["streamlit-runtime"],
        "historical_evidence_retained": True,
        "removal_receipts": [],
    }
    if removal:
        result["removal_receipts"] = [{
            "removal_receipt_id": f"remove:{entry['entry_id']}",
            "entry_id": entry["entry_id"],
            "source_digest": entry["source_digest"],
            "artifact_digest": entry["artifact_digest"],
            "base_ref": BASE,
            "release_identity": entry["release_identity"],
            "deletion_approval": entry["deletion_authorization"],
            "status": "closed_success",
            "historical_evidence_retained": True,
            "previous_receipt_digest": entry["forward_data_receipt"]["receipt_digest"],
        } for entry in entries]
        for removal_item in result["removal_receipts"]:
            removal_item["receipt_digest"] = _sha(removal_item)
        for entry in entries:
            entry["disposition"] = "remove"
    return result


def _release(requirements: dict[str, object]) -> dict[str, object]:
    result = {
        "schema_version": 1,
        "receipt_id": "release:phase6b:1",
        "role": requirements["release_owner_role"],
        "approved_by": "release-owner",
        "approved_at": NOW,
        "base_ref": BASE,
        "registry_revision": requirements["registry_revision"],
        "host_release_approved": True,
        "run_release_approved": True,
        "host_release": _release_component(requirements, "host", "9" * 64),
        "run_release": _release_component(requirements, "run", "a" * 64),
        "previous_receipt_digest": None,
    }
    result["receipt_digest"] = _sha(result)
    return result


def _write_inputs(tmp_path: Path, *, removal: bool = False) -> tuple[Path, Path, Path]:
    requirements = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    inventory_path = tmp_path / "inventory.json"
    release_path = tmp_path / "release.json"
    inventory_path.write_text(json.dumps(_inventory(requirements, removal=removal)), encoding="utf-8")
    release_path.write_text(json.dumps(_release(requirements)), encoding="utf-8")
    return REQUIREMENTS, inventory_path, release_path


def test_installation_check_is_not_release_ready() -> None:
    result = installation_check(REQUIREMENTS)
    assert result.exit_code == 0
    assert result.payload["validator_installation_status"] == INSTALLATION_STATUS
    assert result.payload["overall_status"] == NOT_READY_STATUS
    assert result.payload["legacy_entry_count"] == 10
    assert result.payload["react_entry_count"] == 15


def test_default_readiness_never_reports_installation_status(tmp_path: Path) -> None:
    result = release_readiness(REQUIREMENTS, None, None, NOW)
    assert result.exit_code != 0
    assert result.payload == {"overall_status": NOT_READY_STATUS, "codes": ["SOURCE_RETIREMENT_MANIFEST_INCOMPLETE"]}
    assert "validator_installation_status" not in result.payload
    assert release_readiness(REQUIREMENTS, None, None, None).payload["codes"] == ["BUSINESS_CLOCK_INVALID"]


def test_rich_evaluator_returns_entry_retirement_ready(tmp_path: Path) -> None:
    requirements, inventory, release = _write_inputs(tmp_path)
    result = release_readiness(requirements, inventory, release, NOW)
    assert result.exit_code == 0
    assert result.payload["overall_status"] == READY_ENTRY_STATUS


def test_rich_evaluator_requires_exact_ten_removals_for_cleanup(tmp_path: Path) -> None:
    requirements, inventory, release = _write_inputs(tmp_path, removal=True)
    result = release_readiness(requirements, inventory, release, NOW)
    assert result.exit_code == 0
    assert result.payload["overall_status"] == READY_CLEANUP_STATUS


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda item: item.__setitem__("current_target", "streamlit"), "PHASE5_ENTRY_TARGET_NOT_REACT"),
        (lambda item: item.__setitem__("cas_entry_count", 2), "PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE"),
        (lambda item: item.__setitem__("browser_verified", False), "RECEIPT_PROVENANCE_INVALID"),
        (lambda item: item.__setitem__("totp_verified", False), "RECEIPT_PROVENANCE_INVALID"),
        (lambda item: item.__setitem__("test_disposition", {"status": "PENDING", "focused_tests": ["x"], "notes": "waiting"}), "ENTRY_NOT_READY"),
        (lambda item: item.__setitem__("rollback_receipt", None), "BIDIRECTIONAL_ROLLBACK_NOT_PROVEN"),
        (lambda item: item.__setitem__("forward_data_receipt", None), "FORWARD_DATA_COMPATIBILITY_MISSING"),
        (lambda item: item.__setitem__("active_rollback_triggers", [{"trigger_id": "active", "active": True}]), "ROLLBACK_RETENTION_ACTIVE"),
        (lambda item: item.__setitem__("retention_history", item["retention_history"][::-1]), "ROLLBACK_RETENTION_ACTIVE"),
        (lambda item: item["switch_receipt"].__setitem__("changed_entry_ids", ["other"]), "PHASE5_ENTRY_SWITCH_MISSING"),
        (lambda item: item["observation_receipt"].update({"observation_started_at": "2026-08-21T04:00:00Z"}), "PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE"),
        (lambda item: item["compatibility_proof"].__setitem__("same_root_fact", False) if False else item["forward_data_receipt"]["compatibility_proof"].__setitem__("same_root_fact", False), "FORWARD_DATA_COMPATIBILITY_MISSING"),
    ],
)
def test_rich_negative_vectors(tmp_path: Path, mutation, code: str) -> None:
    requirements, inventory_path, release = _write_inputs(tmp_path)
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    mutation(payload["entries"][0])
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    result = release_readiness(requirements, inventory_path, release, NOW)
    assert result.exit_code != 0
    assert code in result.payload["codes"]


def test_release_role_and_base_ref_are_bound(tmp_path: Path) -> None:
    requirements, inventory_path, release = _write_inputs(tmp_path)
    release_payload = json.loads(release.read_text(encoding="utf-8"))
    release_payload["role"] = "wrong-role"
    release.write_text(json.dumps(release_payload), encoding="utf-8")
    assert "HUMAN_RELEASE_APPROVAL_MISSING" in release_readiness(requirements, inventory_path, release, NOW).payload["codes"]
    release_payload["role"] = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))["release_owner_role"]
    release_payload["base_ref"] = "0" * 40
    release_payload["receipt_digest"] = _sha({key: release_payload[key] for key in release_payload if key != "receipt_digest"})
    release.write_text(json.dumps(release_payload), encoding="utf-8")
    assert "RECEIPT_PROVENANCE_INVALID" in release_readiness(requirements, inventory_path, release, NOW).payload["codes"]


def test_independent_registry_and_path_inventory_are_required(tmp_path: Path) -> None:
    requirements, inventory_path, release = _write_inputs(tmp_path)
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    payload["inventory_producer"] = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))["requirements_producer"]
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    assert release_readiness(requirements, inventory_path, release, NOW).payload["codes"] == ["INDEPENDENT_MANIFEST_MISMATCH"]
    payload["inventory_producer"] = "Independent Inventory Owner"
    payload.pop("scope")
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    assert "SOURCE_RETIREMENT_MANIFEST_INCOMPLETE" in release_readiness(requirements, inventory_path, release, NOW).payload["codes"]


def test_artifact_and_removal_bindings_are_exact(tmp_path: Path) -> None:
    requirements, inventory_path, release = _write_inputs(tmp_path, removal=True)
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    payload["artifact_bindings"][0]["artifact_digest"] = "f" * 64
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    assert "REACT_ARTIFACT_CONTRACT_MISSING" in release_readiness(requirements, inventory_path, release, NOW).payload["codes"]
