"""Compare registered validation dataset expectations with read-only observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from infrastructure.mysql.order_contract_completion_repository import (
    MySqlOrderContractCompletionRepository,
)
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.contract_completion_workflow import ContractCompletionWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_CONTRACT = "labor-union-validation-dataset/v1"
FOUNDATION_DATASET_ID = "lu-test-dataset-v1-foundation"
_DATASET_PATHS = {
    FOUNDATION_DATASET_ID: PROJECT_ROOT / "validation" / "datasets" / "dataset_v1_foundation.json",
}


class ValidationDatasetInspectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationDatasetCheck:
    check_id: str
    expected: object
    observed: object
    passed: bool


@dataclass(frozen=True, slots=True)
class ValidationDatasetInspection:
    dataset_id: str
    scenario_id: str
    case_no: str
    verdict: str
    domain_blockers: tuple[str, ...]
    checks: tuple[ValidationDatasetCheck, ...]

    def payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "scenario_id": self.scenario_id,
            "case_no": self.case_no,
            "verdict": self.verdict,
            "domain_blockers": list(self.domain_blockers),
            "checks": [asdict(check) for check in self.checks],
        }


def registered_dataset_ids() -> tuple[str, ...]:
    return tuple(sorted(_DATASET_PATHS))


def inspect_dataset(connection, dataset_id: str = FOUNDATION_DATASET_ID) -> ValidationDatasetInspection:
    dataset = _load_dataset(dataset_id)
    root = _required_object(dataset, "root_case")
    expected = _required_object(dataset, "expected_after_apply")
    case_no = _required_text(root, "case_no")
    checks = _read_checks(connection, root, expected, case_no)
    checks += _anomaly_checks(connection, _required_object(expected, "anomaly_scenario"), case_no)
    checks += _finance_manual_review_checks(
        connection,
        _required_object(expected, "finance_manual_review"),
    )
    checks += _beclass_review_repair_checks(
        connection,
        _required_object(expected, "beclass_review_repair"),
    )
    checks += _beclass_review_open_checks(
        connection,
        _required_object(expected, "beclass_review_open"),
    )
    completion = _contract_completion_query(connection, case_no)
    blockers = tuple(blocker.value for blocker in completion.domain_blockers)
    checks += (_check("contract_completion_blockers", expected["contract_completion_blockers"], list(blockers)),)
    completed = bool(expected.get("contract_completion_completed", False))
    if "contract_completion_completed" in expected:
        checks += (_check("contract_completion_completed", completed, completion.facts.contract_completed),)
    verdict = _verdict(checks, blockers, completed)
    return ValidationDatasetInspection(dataset_id, f"{dataset_id}:foundation", case_no, verdict, blockers, checks)


def _load_dataset(dataset_id: str) -> dict[str, object]:
    path = _DATASET_PATHS.get(dataset_id)
    if path is None:
        raise ValidationDatasetInspectionError("validation_dataset_not_registered")
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("contract") != DATASET_CONTRACT:
        raise ValidationDatasetInspectionError("validation_dataset_contract_invalid")
    return dataset


def _read_checks(connection, root, expected, case_no: str) -> tuple[ValidationDatasetCheck, ...]:
    with connection.cursor() as cursor:
        return (
            _client_check(cursor, root, case_no),
            _order_check(cursor, expected, case_no),
            *_aggregate_checks(cursor, expected, case_no),
            *_case_count_checks(cursor, expected, case_no),
            *_claim_checks(cursor, expected, case_no),
        )


def _client_check(cursor, root, case_no: str) -> ValidationDatasetCheck:
    attributes = _required_object(root, "client_attributes")
    expected = {key: attributes[key] for key in ("case_no", "name", "identity_status", "service_time")}
    cursor.execute("SELECT case_no,name,identity_status,service_time FROM clients WHERE case_no=%s", (case_no,))
    return _check("client_root", expected, cursor.fetchone())


def _order_check(cursor, expected, case_no: str) -> ValidationDatasetCheck:
    cursor.execute("SELECT status,lifecycle_version,service_days,service_hours_per_day FROM orders WHERE case_no=%s", (case_no,))
    return _check("order_projection", _required_object(expected, "order"), cursor.fetchone())


def _aggregate_checks(cursor, expected, case_no: str) -> tuple[ValidationDatasetCheck, ...]:
    versions = _required_object(expected, "aggregate_versions")
    sources = {
        "client_finance": ("client_finance_accounts", "aggregate_version"),
        "payroll": ("payroll_case_accounts", "aggregate_version"),
        "scheduling": ("scheduling_aggregates", "aggregate_version"),
        "scheduling_generation": ("scheduling_aggregates", "generation_counter"),
    }
    return tuple(_aggregate_check(cursor, key, table, field, versions[key], case_no) for key, (table, field) in sources.items())


def _aggregate_check(cursor, key, table, field, expected, case_no: str) -> ValidationDatasetCheck:
    cursor.execute(f"SELECT `{field}` AS value FROM `{table}` WHERE case_no=%s", (case_no,))
    row = cursor.fetchone()
    observed = None if row is None else int(row["value"])
    return _check(f"aggregate.{key}", expected, observed)


def _case_count_checks(cursor, expected, case_no: str) -> tuple[ValidationDatasetCheck, ...]:
    counts = _required_object(expected, "case_row_counts")
    return tuple(_case_count_check(cursor, table, count, case_no) for table, count in counts.items())


def _case_count_check(cursor, table, expected, case_no: str) -> ValidationDatasetCheck:
    cursor.execute(f"SELECT COUNT(*) AS count FROM `{table}` WHERE case_no=%s", (case_no,))
    return _check(f"row_count.{table}", expected, int(cursor.fetchone()["count"]))


def _claim_checks(cursor, expected, case_no: str) -> tuple[ValidationDatasetCheck, ...]:
    counts = _required_object(expected, "case_command_claim_counts")
    return tuple(_claim_check(cursor, family, count, case_no) for family, count in counts.items())


def _claim_check(cursor, family, expected, case_no: str) -> ValidationDatasetCheck:
    cursor.execute("SELECT COUNT(*) AS count FROM application_command_claims WHERE command_family=%s AND aggregate_identity=%s", (family, case_no))
    return _check(f"command_claim.{family}", expected, int(cursor.fetchone()["count"]))


def _anomaly_checks(connection, expected, case_no: str) -> tuple[ValidationDatasetCheck, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT fingerprint,workflow_status,predicate_active FROM anomaly_current_alerts "
            "WHERE definition_code=%s AND source_identity=%s",
            (expected["definition_code"], f"case:{case_no}"),
        )
        alert = cursor.fetchone()
        observed = None if alert is None else {
            "workflow_status": str(alert["workflow_status"]),
            "predicate_active": int(alert["predicate_active"]),
        }
        alert_expected = {
            "workflow_status": expected["workflow_status"],
            "predicate_active": expected["predicate_active"],
        }
        if alert is None:
            return (_check("anomaly.current", alert_expected, None),)
        cursor.execute(
            "SELECT action FROM anomaly_workflow_events WHERE alert_fingerprint=%s ORDER BY id",
            (alert["fingerprint"],),
        )
        actions = [str(row["action"]) for row in cursor.fetchall()]
    return (
        _check("anomaly.current", alert_expected, observed),
        _check("anomaly.timeline", expected["timeline_actions"], actions),
    )


def _finance_manual_review_checks(connection, expected) -> tuple[ValidationDatasetCheck, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT CONCAT('finance-import-row:',event.finance_import_row_id) AS row_identity,"
            "event.classification_type,event.disposition FROM finance_import_batch_contracts contract "
            "JOIN finance_import_ingestion_receipts receipt ON receipt.batch_id=contract.batch_id "
            "JOIN finance_import_classification_events event ON event.batch_id=contract.batch_id "
            "WHERE receipt.idempotency_key=%s",
            (expected["ingestion_idempotency_key"],),
        )
        row = cursor.fetchone()
        alert = None
        if row is not None:
            cursor.execute(
                "SELECT workflow_status,predicate_active FROM anomaly_current_alerts "
                "WHERE definition_code=%s AND source_identity=%s",
                ("finance_import_manual_review", row["row_identity"]),
            )
            alert = cursor.fetchone()
    review_expected = {
        key: expected[key] for key in ("classification_type", "disposition")
    }
    observed_review = None if row is None else {
        key: row[key] for key in review_expected
    }
    alert_expected = {
        key: expected[key] for key in ("workflow_status", "predicate_active")
    }
    return (
        _check("finance.manual_review_row", review_expected, observed_review),
        _check("finance.manual_review_alert", alert_expected, alert),
    )


def _beclass_review_repair_checks(connection, expected) -> tuple[ValidationDatasetCheck, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT root.review_identity,event.resulting_version FROM beclass_import_review_rows root "
            "JOIN beclass_import_review_events event ON event.review_row_id=root.id "
            "WHERE JSON_UNQUOTE(JSON_EXTRACT(root.source_payload,'$.query_no'))=%s",
            (expected["query_no"],),
        )
        review = cursor.fetchone()
        review_observed = None if review is None else {
            "review_version": int(review["resulting_version"]),
        }
        if review is None:
            return (_check("beclass.review_repair", expected, None),)
        cursor.execute(
            "SELECT workflow_status,predicate_active FROM anomaly_current_alerts "
            "WHERE definition_code='IMPORT-001' AND source_identity=%s",
            (review["review_identity"],),
        )
        alert = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS count FROM beclass_records WHERE query_no=%s", (expected["query_no"],))
        record_count = int(cursor.fetchone()["count"])
    observed = {
        **review_observed,
        "workflow_status": None if alert is None else str(alert["workflow_status"]),
        "predicate_active": None if alert is None else int(alert["predicate_active"]),
        "beclass_record_count": record_count,
    }
    expected_values = {
        key: expected[key]
        for key in ("review_version", "workflow_status", "predicate_active", "beclass_record_count")
    }
    return (_check("beclass.review_repair", expected_values, observed),)


def _beclass_review_open_checks(connection, expected) -> tuple[ValidationDatasetCheck, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT root.review_identity,COUNT(event.id) AS event_count FROM beclass_import_review_rows root "
            "LEFT JOIN beclass_import_review_events event ON event.review_row_id=root.id "
            "WHERE JSON_UNQUOTE(JSON_EXTRACT(root.source_payload,'$.query_no'))=%s "
            "GROUP BY root.review_identity",
            (expected["query_no"],),
        )
        review = cursor.fetchone()
        if review is None:
            return (_check("beclass.review_open", expected, None),)
        cursor.execute(
            "SELECT workflow_status,predicate_active FROM anomaly_current_alerts "
            "WHERE definition_code='IMPORT-001' AND source_identity=%s",
            (review["review_identity"],),
        )
        alert = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS count FROM beclass_records WHERE query_no=%s", (expected["query_no"],))
        record_count = int(cursor.fetchone()["count"])
    observed = {
        "review_version": int(review["event_count"]),
        "workflow_status": None if alert is None else str(alert["workflow_status"]),
        "predicate_active": None if alert is None else int(alert["predicate_active"]),
        "beclass_record_count": record_count,
    }
    expected_values = {
        key: expected[key]
        for key in ("review_version", "workflow_status", "predicate_active", "beclass_record_count")
    }
    return (_check("beclass.review_open", expected_values, observed),)


def _contract_completion_query(connection, case_no: str):
    workflow = ContractCompletionWorkflow(MySqlOrderContractCompletionRepository(connection), _query_only_unit_of_work, SystemBusinessClock())
    return workflow.query(case_no)


def _query_only_unit_of_work():
    raise RuntimeError("validation inspection query must not open a unit of work")


def _check(check_id: str, expected: object, observed: object) -> ValidationDatasetCheck:
    return ValidationDatasetCheck(check_id, expected, observed, expected == observed)


def _verdict(checks: tuple[ValidationDatasetCheck, ...], blockers: tuple[str, ...], completed: bool) -> str:
    if not all(check.passed for check in checks):
        return "mismatch"
    if completed:
        return "pass"
    return "blocked_as_expected" if blockers else "pass"


def _required_object(source: dict[str, object], key: str) -> dict[str, object]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValidationDatasetInspectionError(f"validation_dataset_{key}_invalid")
    return value


def _required_text(source: dict[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationDatasetInspectionError(f"validation_dataset_{key}_invalid")
    return value
