"""
File: validate_streamlit_retirement_readiness.py
Description: 唯讀驗證 Phase6A 安裝、receipt、observation 與 retention readiness。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import NoReturn

INSTALLATION_STATUS = "VALIDATOR_INSTALLED_NOT_READY"
NOT_READY_STATUS = "PHASE6_NOT_READY"
READY_ENTRY_STATUS = "PHASE6_READY_FOR_ENTRY_RETIREMENT"
READY_CLEANUP_STATUS = "PHASE6_READY_FOR_FINAL_DEPENDENCY_CLEANUP"
RELEASE_ROLE = "Global Deployment / Entry Point Governance"
_REQUIREMENTS_KEYS = {"schema_version", "requirements_producer", "release_owner_role", "registry_revision", "legacy_entries", "react_entries", "required_release_inputs", "allowed_overall_statuses", "allowed_retention_states", "allowed_observation_outcomes", "fail_closed_codes", "final_evaluator_schema"}
_BASELINE_LEGACY_COUNT = 10
_BASELINE_REACT_COUNT = 11
_OVERALL_STATUSES = {NOT_READY_STATUS, READY_ENTRY_STATUS, READY_CLEANUP_STATUS}
_RETENTION_STATES = {"pending", "active", "completed_not_expired", "expired_approved"}
_OBSERVATION_OUTCOMES = {"closed_success", "closed_failure", "outcome_unknown"}


@dataclass(frozen=True)
class ValidationResult:
    exit_code: int
    payload: dict[str, object]


class ContractError(ValueError):
    """代表輸入未符合 Phase6A checked-in closed contract。"""


def load_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError("INPUT_MISSING") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("INPUT_INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise ContractError("INPUT_NOT_OBJECT")
    return value


def validate_requirements(value: dict[str, object]) -> dict[str, object]:
    if set(value) != _REQUIREMENTS_KEYS or value["schema_version"] != 1:
        raise ContractError("REQUIREMENTS_SCHEMA_INVALID")
    producer = _required_text(value["requirements_producer"])
    revision = _required_text(value["registry_revision"])
    legacy = _unique_text_list(value["legacy_entries"])
    react = _unique_text_list(value["react_entries"])
    required_inputs = _unique_text_list(value["required_release_inputs"])
    overall_statuses = _unique_text_list(value["allowed_overall_statuses"])
    retention_states = _unique_text_list(value["allowed_retention_states"])
    observation_outcomes = _unique_text_list(value["allowed_observation_outcomes"])
    fail_codes = _unique_text_list(value["fail_closed_codes"])
    if len(legacy) != _BASELINE_LEGACY_COUNT or len(react) < _BASELINE_REACT_COUNT:
        raise ContractError("FULL_ENTRY_REGISTRY_DRIFT")
    if set(overall_statuses) != _OVERALL_STATUSES or set(retention_states) != _RETENTION_STATES or set(observation_outcomes) != _OBSERVATION_OUTCOMES or not _valid_schema_contract(value["final_evaluator_schema"]):
        raise ContractError("REQUIREMENTS_SCHEMA_INVALID")
    role = _required_text(value["release_owner_role"])
    if role != RELEASE_ROLE:
        raise ContractError("REQUIREMENTS_SCHEMA_INVALID")
    return {"schema_version": 1, "requirements_producer": producer, "release_owner_role": role, "registry_revision": revision, "legacy_entries": legacy, "react_entries": react, "required_release_inputs": required_inputs, "allowed_overall_statuses": overall_statuses, "allowed_retention_states": retention_states, "allowed_observation_outcomes": observation_outcomes, "fail_closed_codes": fail_codes, "final_evaluator_schema": value["final_evaluator_schema"]}


def installation_check(requirements_path: Path) -> ValidationResult:
    try:
        requirements = validate_requirements(load_json_object(requirements_path))
    except ContractError as exc:
        return _not_ready(str(exc), installation=False)
    return ValidationResult(0, {"validator_installation_status": INSTALLATION_STATUS, "overall_status": NOT_READY_STATUS, "registry_revision": requirements["registry_revision"], "legacy_entry_count": len(requirements["legacy_entries"]), "react_entry_count": len(requirements["react_entries"]), "codes": ["RELEASE_READINESS_NOT_EVALUATED"]})


def release_readiness(requirements_path: Path, inventory_path: Path | None, release_receipt_path: Path | None = None, business_now: str | None = None) -> ValidationResult:
    try:
        requirements = validate_requirements(load_json_object(requirements_path))
        now = _parse_instant(business_now, "BUSINESS_CLOCK_INVALID")
        inventory = _validate_inventory(load_json_object(_required_file(inventory_path)), requirements, now)
        release = _validate_release_receipt(load_json_object(_required_file(release_receipt_path)), requirements, now)
    except ContractError as exc:
        return _not_ready(str(exc))
    codes = _readiness_codes(requirements, inventory, release, now)
    if codes:
        return _not_ready(*codes)
    status = READY_CLEANUP_STATUS if inventory["removal_receipts"] else READY_ENTRY_STATUS
    return ValidationResult(0, {"overall_status": status, "registry_revision": requirements["registry_revision"], "entry_count": len(inventory["entries"]), "codes": []})


def _readiness_codes(requirements: dict[str, object], inventory: dict[str, object], release: dict[str, object], now: datetime) -> list[str]:
    codes: list[str] = []
    if release["base_ref"] != inventory["base_ref"]:
        codes.append("RECEIPT_PROVENANCE_INVALID")
    if not release["host_release_approved"] or not release["run_release_approved"]:
        codes.append("HUMAN_RELEASE_APPROVAL_MISSING")
    codes.extend(_release_component_codes(release["host_release"], "host", requirements, release, now))
    codes.extend(_release_component_codes(release["run_release"], "run", requirements, release, now))
    entries_by_id = {entry["entry_id"]: entry for entry in inventory["entries"]}
    if not _valid_registry_sources(inventory, requirements):
        codes.append("FULL_ENTRY_REGISTRY_DRIFT")
    if not _valid_source_receipts(inventory, entries_by_id):
        codes.append("RECEIPT_PROVENANCE_INVALID")
    if not _valid_artifact_bindings(inventory, entries_by_id, requirements):
        codes.append("REACT_ARTIFACT_CONTRACT_MISSING")
    if inventory["open_findings"]:
        codes.append("ENTRY_NOT_READY")
    for entry in inventory["entries"]:
        codes.extend(_entry_codes(entry, inventory, now))
    removals = inventory["removal_receipts"]
    if len(removals) not in {0, len(requirements["legacy_entries"])}:
        codes.append("ARCHIVE_GATE_INCOMPLETE")
    if removals and (inventory["remaining_runtime_owners"] or not inventory["historical_evidence_retained"]):
        codes.append("CURRENT_SSOT_SUCCESSOR_MISSING")
    if removals and any(item["status"] != "closed_success" or not item["historical_evidence_retained"] for item in removals):
        codes.append("ARCHIVE_GATE_INCOMPLETE")
    return sorted(set(codes))


def _entry_codes(entry: dict[str, object], inventory: dict[str, object], now: datetime) -> list[str]:
    codes: list[str] = []
    if entry["current_target"] != "react":
        codes.append("PHASE5_ENTRY_TARGET_NOT_REACT")
    if entry["previous_target"] != "streamlit" or entry["cas_entry_count"] != 1:
        codes.append("PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE")
    if not entry["browser_verified"] or not entry["totp_verified"]:
        codes.append("RECEIPT_PROVENANCE_INVALID")
    if any(trigger["active"] for trigger in entry["active_rollback_triggers"]):
        codes.append("ROLLBACK_RETENTION_ACTIVE")
    if not _valid_entry_contracts(entry, inventory, now):
        codes.append("ENTRY_NOT_READY")
    for field, code in (("rollback_receipt", "BIDIRECTIONAL_ROLLBACK_NOT_PROVEN"), ("forward_data_receipt", "FORWARD_DATA_COMPATIBILITY_MISSING")):
        if not _valid_evidence_receipt(entry[field], entry, inventory, now):
            codes.append(code)
    if not _valid_evidence_receipt(entry["switch_receipt"], entry, inventory, now):
        codes.append("PHASE5_ENTRY_SWITCH_MISSING")
    if not _valid_evidence_receipt(entry["observation_receipt"], entry, inventory, now) or entry["observation_outcome"] != "closed_success":
        codes.append("PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE")
    switch = entry.get("switch_receipt")
    if not isinstance(switch, dict) or switch.get("changed_entry_ids") != [entry["entry_id"]] or switch.get("cas_entry_count") != 1 or switch.get("previous_target") != "streamlit" or switch.get("current_target") != "react" or switch.get("audit_recorded") is not True:
        codes.append("PHASE5_ENTRY_SWITCH_MISSING")
    observation = entry.get("observation_receipt")
    if not _valid_observation_semantics(observation, entry, now):
        codes.append("PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE")
    rollback = entry.get("rollback_receipt")
    if not _valid_rollback_semantics(rollback, entry):
        codes.append("BIDIRECTIONAL_ROLLBACK_NOT_PROVEN")
    forward = entry.get("forward_data_receipt")
    if not _valid_forward_semantics(forward):
        codes.append("FORWARD_DATA_COMPATIBILITY_MISSING")
    if not _valid_receipt_chain(entry):
        codes.append("RECEIPT_PROVENANCE_INVALID")
    if not _valid_retention(entry["retention_history"], now, inventory["schema"]):
        codes.append("ROLLBACK_RETENTION_ACTIVE")
    return codes


def _validate_inventory(value: dict[str, object], requirements: dict[str, object], now: datetime) -> dict[str, object]:
    schema = requirements["final_evaluator_schema"]
    expected = set(schema["inventory_top_level"])
    if set(value) != expected:
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    producer = _required_text(value["inventory_producer"])
    if producer == requirements["requirements_producer"] or value["registry_revision"] != requirements["registry_revision"]:
        raise ContractError("INDEPENDENT_MANIFEST_MISMATCH")
    base_ref = _required_text(value["base_ref"])
    _parse_instant(value["generated_at"], "SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    entries = value["entries"]
    if not isinstance(entries, list) or {e.get("entry_id") for e in entries if isinstance(e, dict)} != set(requirements["legacy_entries"]):
        raise ContractError("FULL_ENTRY_REGISTRY_DRIFT")
    validated = [_validate_entry(e, base_ref, requirements) for e in entries]
    owners = value["remaining_runtime_owners"]
    if not isinstance(owners, list) or not all(isinstance(x, str) and x.strip() for x in owners):
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    if not isinstance(value["historical_evidence_retained"], bool) or not isinstance(value["removal_receipts"], list):
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    removals = value["removal_receipts"]
    if removals:
        if len(removals) != len(requirements["legacy_entries"]):
            raise ContractError("ARCHIVE_GATE_INCOMPLETE")
        for item in removals:
            if not isinstance(item, dict) or set(item) != set(schema["removal_required_fields"]) or item["base_ref"] != base_ref or not _digest(item["source_digest"]):
                raise ContractError("ARCHIVE_GATE_INCOMPLETE")
    if value["schema_version"] != 1 or value["count_kind"] != "files_and_matches" or not isinstance(value["files_count"], int) or value["files_count"] < len(validated) or not isinstance(value["matches_count"], int) or value["matches_count"] < len(validated):
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    for name in ("scope", "exclude_rules", "reproduction_command"):
        _required_text(value[name])
    if not isinstance(value["open_findings"], list) or not isinstance(value["full_registry_sources"], list) or not isinstance(value["source_receipts"], list) or not isinstance(value["artifact_bindings"], list):
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    return {**value, "base_ref": base_ref, "entries": validated, "react_entries": requirements["react_entries"], "remaining_runtime_owners": owners, "historical_evidence_retained": value["historical_evidence_retained"], "removal_receipts": removals, "schema": schema}


def _validate_entry(value: object, base_ref: str, requirements: dict[str, object]) -> dict[str, object]:
    schema = requirements["final_evaluator_schema"]
    fields = set(schema["entry_required_fields"])
    if not isinstance(value, dict) or set(value) != fields or value["entry_id"] not in requirements["legacy_entries"]:
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    if value["base_ref"] != base_ref or not _digest(value["source_digest"]) or not _digest(value["artifact_digest"]):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    if not isinstance(value["cas_entry_count"], int) or not isinstance(value["browser_verified"], bool) or not isinstance(value["totp_verified"], bool) or value["observation_outcome"] not in _OBSERVATION_OUTCOMES:
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    triggers = value["active_rollback_triggers"]
    if not isinstance(triggers, list) or any(not isinstance(item, dict) or set(item) != set(schema["rollback_trigger_fields"]) or not isinstance(item["trigger_id"], str) or not isinstance(item["active"], bool) for item in triggers):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    return value


def _valid_entry_contracts(entry: dict[str, object], inventory: dict[str, object], now: datetime) -> bool:
    schema = inventory["schema"]
    try:
        test_disposition = entry["test_disposition"]
        replacement = entry["replacement_identity"]
        release_identity = entry["release_identity"]
        deletion = entry["deletion_authorization"]
        restore = entry["restore_procedure"]
        if not _exact_object(test_disposition, schema["test_disposition_fields"]) or test_disposition["status"] != "PASS" or not _text_list(test_disposition["focused_tests"]):
            return False
        if not _exact_object(replacement, schema["replacement_identity_fields"]) or replacement["entry_id"] not in inventory.get("react_entries", []) or replacement["target"] != "react":
            return False
        if not _exact_object(release_identity, schema["release_identity_fields"]) or release_identity["manifest_revision"] != inventory["registry_revision"] or release_identity["artifact_digest"] != entry["artifact_digest"] or release_identity["target"] != "react":
            return False
        if not _exact_object(deletion, schema["deletion_authorization_fields"]) or deletion["status"] != "approved" or deletion["role"] != RELEASE_ROLE or deletion["entry_id"] != entry["entry_id"] or deletion["source_digest"] != entry["source_digest"] or deletion["manifest_revision"] != inventory["registry_revision"] or _parse_instant(deletion["approved_at"], "ENTRY_NOT_READY") > now:
            return False
        if not _exact_object(restore, schema["restore_procedure_fields"]) or restore["verified"] is not True:
            return False
        if not _text_list(entry["current_inbound_links"]) or not _text_list(entry["archive_inbound_links"]):
            return False
        if entry["disposition"] not in {"migrate_then_remove", "remove"}:
            return False
        if _parse_instant(entry["retention_end"], "ENTRY_NOT_READY") > now:
            return False
    except (ContractError, KeyError, TypeError):
        return False
    return True


def _valid_registry_sources(inventory: dict[str, object], requirements: dict[str, object]) -> bool:
    schema = requirements["final_evaluator_schema"]
    sources = inventory["full_registry_sources"]
    expected_kinds = {"streamlit", "react", "api", "cli"}
    return (
        isinstance(sources, list)
        and {item.get("kind") for item in sources if isinstance(item, dict)} == expected_kinds
        and all(_exact_object(item, schema["inventory_registry_source_fields"]) and _digest(item["digest"]) for item in sources)
    )


def _valid_source_receipts(inventory: dict[str, object], entries: dict[str, dict[str, object]]) -> bool:
    fields = inventory["schema"]["inventory_source_receipt_fields"]
    receipts = inventory["source_receipts"]
    if not isinstance(receipts, list) or len(receipts) != len(entries):
        return False
    seen: set[str] = set()
    for receipt in receipts:
        if not _exact_object(receipt, fields):
            return False
        entry = entries.get(receipt["entry_id"])
        if entry is None or receipt["entry_id"] in seen or receipt["source_path"] != entry["source_path"] or receipt["source_digest"] != entry["source_digest"] or receipt["base_ref"] != inventory["base_ref"] or receipt["status"] != "closed_success":
            return False
        if not _digest(receipt["receipt_digest"]) or receipt["receipt_digest"] != _sha({key: value for key, value in receipt.items() if key != "receipt_digest"}):
            return False
        seen.add(receipt["entry_id"])
    return seen == set(entries)


def _valid_artifact_bindings(inventory: dict[str, object], entries: dict[str, dict[str, object]], requirements: dict[str, object]) -> bool:
    fields = inventory["schema"]["artifact_binding_fields"]
    bindings = inventory["artifact_bindings"]
    if not isinstance(bindings, list) or len(bindings) != len(entries):
        return False
    seen: set[str] = set()
    for binding in bindings:
        if not _exact_object(binding, fields):
            return False
        entry = entries.get(binding["entry_id"])
        if entry is None or binding["entry_id"] in seen or binding["artifact_identity"] != entry["release_identity"]["release_id"] or binding["artifact_digest"] != entry["artifact_digest"] or binding["manifest_revision"] != requirements["registry_revision"] or binding["current_target"] != "react" or binding["previous_target"] != "streamlit" or binding["status"] != "closed_success":
            return False
        seen.add(binding["entry_id"])
    return seen == set(entries)


def _release_component_codes(component: object, kind: str, requirements: dict[str, object], release: dict[str, object], now: datetime) -> list[str]:
    schema = requirements["final_evaluator_schema"]
    if not _exact_object(component, schema["release_component_fields"]):
        return ["RUNTIME_SUCCESSOR_MISSING"]
    try:
        if component["base_ref"] != release["base_ref"] or component["manifest_revision"] != requirements["registry_revision"] or not _digest(component["artifact_digest"]):
            return ["RECEIPT_PROVENANCE_INVALID"]
        compatibility = component["api_compatibility"]
        if not _exact_object(compatibility, schema["api_compatibility_fields"]) or compatibility["mode"] != "option-c" or compatibility["contract_status"] != "PASS" or not _required_text(compatibility["manifest_identity"]):
            return ["REACT_ARTIFACT_CONTRACT_MISSING"]
        if not _valid_binding(component["current_binding"], schema, "react") or not _valid_binding(component["previous_binding"], schema, "streamlit"):
            return ["DEPLOYMENT_SSOT_CONFLICT"]
        if component["retention_state"] not in {"completed_not_expired", "expired_approved"} or not _required_text(component["retention_identity"]):
            return ["ROLLBACK_RETENTION_ACTIVE"]
        retention_end = _parse_instant(component["retention_end"], "ROLLBACK_RETENTION_ACTIVE")
        if component["retention_state"] == "completed_not_expired" and retention_end <= now:
            return ["ROLLBACK_RETENTION_ACTIVE"]
        browser = component["browser_rehearsal"]
        if not _exact_object(browser, schema["browser_evidence_fields"]) or browser["http_status"] != 200 or browser["totp_auth_mode"] != "real-account-totp":
            return ["RECEIPT_PROVENANCE_INVALID"]
        rollback = component["rollback_rehearsal"]
        if not _exact_object(rollback, schema["rollback_rehearsal_fields"]) or rollback["status"] != "closed_success" or rollback["current_artifact_digest"] != component["artifact_digest"] or not _digest(rollback["previous_artifact_digest"]):
            return ["BIDIRECTIONAL_ROLLBACK_NOT_PROVEN"]
        approval = component["approval"]
        if not _exact_object(approval, schema["release_approval_fields"]) or approval["role"] != RELEASE_ROLE or _parse_instant(approval["approved_at"], "HUMAN_RELEASE_APPROVAL_MISSING") > now:
            return ["HUMAN_RELEASE_APPROVAL_MISSING"]
        if component["closed_outcome"] != "closed_success" or kind not in component["release_id"]:
            return ["RUNTIME_SUCCESSOR_MISSING"]
    except (ContractError, KeyError, TypeError):
        return ["RUNTIME_SUCCESSOR_MISSING"]
    return []


def _valid_binding(value: object, schema: dict[str, object], target: str) -> bool:
    return _exact_object(value, schema["binding_fields"]) and value["target"] == target and isinstance(value["entry_selector"], str) and bool(value["entry_selector"].strip())


def _valid_observation_semantics(value: object, entry: dict[str, object], now: datetime) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        started = _parse_instant(value["observation_started_at"], "PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE")
        ended = _parse_instant(value["observation_ended_at"], "PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE")
        occurred = _parse_instant(value["occurred_at"], "PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE")
        return started <= ended <= occurred <= now and value["observation_outcome"] == entry["observation_outcome"] == "closed_success" and value["http_status"] == 200 and value["totp_auth_mode"] == "real-account-totp" and _text_list(value["focused_tests"])
    except (ContractError, KeyError, TypeError):
        return False


def _valid_rollback_semantics(value: object, entry: dict[str, object]) -> bool:
    return isinstance(value, dict) and value.get("switch_back_previous_target") == "react" and value.get("switch_back_current_target") == "streamlit" and value.get("switch_back_changed_entry_ids") == [entry["entry_id"]] and value.get("switch_back_cas_entry_count") == 1 and value.get("switch_back_audit_recorded") is True and value.get("http_status") == 200 and _text_list(value.get("focused_tests"))


def _valid_forward_semantics(value: object) -> bool:
    if not isinstance(value, dict) or not _text_list(value.get("focused_tests")):
        return False
    proof = value.get("compatibility_proof")
    expected = {"same_root_fact", "same_version", "same_receipt", "same_outbox", "same_anomaly", "same_audit"}
    return isinstance(proof, dict) and proof.get("proof_status") == "closed_success" and all(proof.get(key) is True for key in expected)


def _exact_object(value: object, fields: object) -> bool:
    return isinstance(value, dict) and isinstance(fields, list) and set(value) == set(fields)


def _text_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and bool(item.strip()) for item in value)


def _validate_release_receipt(value: dict[str, object], requirements: dict[str, object], now: datetime) -> dict[str, object]:
    expected = set(requirements["final_evaluator_schema"]["release_receipt_top_level"])
    if set(value) != expected or value["schema_version"] != 1 or value["role"] != RELEASE_ROLE or not isinstance(value["approved_by"], str) or not value["approved_by"].strip():
        raise ContractError("HUMAN_RELEASE_APPROVAL_MISSING")
    if _parse_instant(value["approved_at"], "HUMAN_RELEASE_APPROVAL_MISSING") > now:
        raise ContractError("HUMAN_RELEASE_APPROVAL_MISSING")
    if value["registry_revision"] != requirements["registry_revision"] or not isinstance(value["base_ref"], str) or not value["base_ref"].strip() or not isinstance(value["host_release_approved"], bool) or not isinstance(value["run_release_approved"], bool):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    if value["previous_receipt_digest"] is not None and not _digest(value["previous_receipt_digest"]):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    if not _digest(value["receipt_digest"]) or value["receipt_digest"] != _sha({key: item for key, item in value.items() if key != "receipt_digest"}):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    return value


def _validate_receipt_shape(value: object, entry: dict[str, object], base_ref: str, schema: dict[str, object]) -> datetime:
    receipt_id = value.get("receipt_id", "") if isinstance(value, dict) else ""
    if isinstance(receipt_id, str) and receipt_id.startswith("switch:"):
        fields = set(schema["switch_receipt_fields"])
    elif isinstance(receipt_id, str) and receipt_id.startswith("observation:"):
        fields = set(schema["observation_receipt_fields"])
    elif isinstance(receipt_id, str) and receipt_id.startswith("rollback:"):
        fields = set(schema["rollback_receipt_fields"])
    elif isinstance(receipt_id, str) and receipt_id.startswith("forward:"):
        fields = set(schema["forward_receipt_fields"])
    else:
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    if not isinstance(value, dict) or set(value) != fields or value["entry_id"] != entry["entry_id"] or value["base_ref"] != base_ref or value["status"] != "closed_success" or value["source_digest"] != entry["source_digest"] or value["artifact_digest"] != entry["artifact_digest"] or not _digest(value["source_digest"]) or not _digest(value["artifact_digest"]):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    occurred_at = _parse_instant(value["occurred_at"], "RECEIPT_PROVENANCE_INVALID")
    if value["previous_receipt_digest"] is not None and not _digest(value["previous_receipt_digest"]):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    if not _digest(value["receipt_digest"]):
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    expected = _sha({key: value[key] for key in fields if key != "receipt_digest"})
    if value["receipt_digest"] != expected:
        raise ContractError("RECEIPT_PROVENANCE_INVALID")
    return occurred_at


def _valid_evidence_receipt(value: object, entry: dict[str, object], inventory: dict[str, object], now: datetime) -> bool:
    try:
        if _validate_receipt_shape(value, entry, inventory["base_ref"], inventory["schema"]) > now:
            return False
    except ContractError:
        return False
    return True


def _valid_receipt_chain(entry: dict[str, object]) -> bool:
    previous: str | None = None
    for field in ("switch_receipt", "observation_receipt", "rollback_receipt", "forward_data_receipt"):
        receipt = entry[field]
        if not isinstance(receipt, dict) or receipt.get("previous_receipt_digest") != previous:
            return False
        previous = receipt.get("receipt_digest")
    return True


def _valid_retention(history: object, now: datetime, schema: dict[str, object], *, raise_error: bool = False) -> bool:
    try:
        if not isinstance(history, list) or len(history) != 4:
            raise ContractError("ROLLBACK_RETENTION_ACTIVE")
        states = [item["state"] for item in history if isinstance(item, dict) and set(item) == set(schema["retention_item_fields"])]
        if states != ["pending", "active", "completed_not_expired", "expired_approved"]:
            raise ContractError("ROLLBACK_RETENTION_ACTIVE")
        for item in history:
            _parse_instant(item["at"], "ROLLBACK_RETENTION_ACTIVE")
        if _parse_instant(history[-1]["at"], "ROLLBACK_RETENTION_ACTIVE") > now:
            raise ContractError("ROLLBACK_RETENTION_ACTIVE")
    except (ContractError, KeyError, TypeError):
        if raise_error:
            raise ContractError("ROLLBACK_RETENTION_ACTIVE")
        return False
    return True


def _required_file(path: Path | None) -> Path:
    if path is None or not path.is_file():
        raise ContractError("SOURCE_RETIREMENT_MANIFEST_INCOMPLETE")
    return path


def _parse_instant(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError(code)
    return parsed


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _valid_schema_contract(value: object) -> bool:
    required = {"inventory_top_level", "release_receipt_top_level", "entry_required_fields", "removal_required_fields", "switch_receipt_fields", "observation_receipt_fields", "rollback_receipt_fields", "forward_receipt_fields", "retention_item_fields", "rollback_trigger_fields", "inventory_registry_source_fields", "inventory_source_receipt_fields", "artifact_binding_fields", "release_component_fields", "release_approval_fields", "binding_fields", "api_compatibility_fields", "browser_evidence_fields", "rollback_rehearsal_fields", "release_identity_fields", "deletion_authorization_fields", "test_disposition_fields", "replacement_identity_fields", "restore_procedure_fields", "compatibility_proof_fields", "open_finding_fields"}
    return isinstance(value, dict) and set(value) == {"schema_version", *required} and value["schema_version"] == 1 and all(isinstance(value[key], list) and value[key] for key in required)


def _not_ready(*codes: str, installation: bool = False) -> ValidationResult:
    payload: dict[str, object] = {"overall_status": NOT_READY_STATUS, "codes": sorted(set(codes))}
    if installation:
        payload["validator_installation_status"] = INSTALLATION_STATUS
    return ValidationResult(2, payload)


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError("REQUIREMENTS_SCHEMA_INVALID")
    return value


def _unique_text_list(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ContractError("REQUIREMENTS_SCHEMA_INVALID")
    items = [_required_text(item) for item in value]
    if len(items) != len(set(items)):
        raise ContractError("REQUIREMENTS_SCHEMA_INVALID")
    return items


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Streamlit retirement readiness without writes.")
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--release-receipt", type=Path)
    parser.add_argument("--business-now")
    parser.add_argument("--installation-check", action="store_true")
    return parser.parse_args()


def _emit(result: ValidationResult) -> NoReturn:
    print(json.dumps(result.payload, ensure_ascii=False, sort_keys=True))
    raise SystemExit(result.exit_code)


def main() -> NoReturn:
    args = _parse_args()
    result = installation_check(args.requirements) if args.installation_check else release_readiness(args.requirements, args.inventory, args.release_receipt, args.business_now)
    _emit(result)


if __name__ == "__main__":
    main()
