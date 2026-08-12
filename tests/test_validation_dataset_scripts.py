from pathlib import Path
import os

import pytest

from scripts.seed_validation_dataset import (
    DEFAULT_MANIFEST,
    _require_matching_root_case,
    build_intent,
    load_dataset,
    require_dataset_database,
)
from scripts.seed_ui_validation_dataset import _configure_runtime_database
from scripts.seed_validation_finance_manual_review import _INGESTION_KEY


def test_foundation_dataset_builds_a_canonical_case_import_intent():
    dataset = load_dataset(DEFAULT_MANIFEST)

    intent = build_intent(dataset)

    assert intent.case_no == "DSV1-CASE-0001"
    assert intent.order.service_days == 5
    assert intent.bootstrap.client_payment_terms.client_hourly_rate.amount == 400


@pytest.mark.parametrize("database", ["union_db", "lu_test_validation_v1", "lu_test_dataset_BAD"])
def test_dataset_seed_rejects_non_dataset_database_names(database):
    with pytest.raises(ValueError, match="lu_test_dataset"):
        require_dataset_database(database)


def test_dataset_manifest_is_strict_utf8_json_contract():
    dataset = load_dataset(Path(DEFAULT_MANIFEST))

    assert dataset["contract"] == "labor-union-validation-dataset/v1"
    assert "orders.status" in dataset["expected_after_apply"]["non_seeded_outputs"]
    assert dataset["expected_after_apply"]["contract_completion_completed"] is False
    assert dataset["expected_after_apply"]["contract_completion_blockers"] == [
        "contract_identity_missing",
        "official_service_dates_incomplete",
    ]
    assert dataset["expected_after_apply"]["anomaly_scenario"]["timeline_actions"] == [
        "claim", "resolve", "reopen", "auto_resolve", "reopen"
    ]
    assert dataset["expected_after_apply"]["beclass_review_repair"]["workflow_status"] == "resolved"
    assert dataset["expected_after_apply"]["beclass_review_open"]["workflow_status"] == "open"


def test_complete_dataset_seed_configures_only_the_requested_database() -> None:
    arguments = type(
        "Arguments",
        (),
        {"host": "127.0.0.1", "port": 3306, "user": "tester", "password": "secret", "database": "lu_test_dataset_v1"},
    )()

    previous = os.environ.get("DB_DATABASE")
    try:
        _configure_runtime_database(arguments)
        assert os.environ["DB_DATABASE"] == "lu_test_dataset_v1"
    finally:
        if previous is None:
            os.environ.pop("DB_DATABASE", None)
        else:
            os.environ["DB_DATABASE"] = previous


def test_integrated_dataset_replay_requires_the_same_root_case() -> None:
    dataset = load_dataset(DEFAULT_MANIFEST)

    _require_matching_root_case(
        {
            "case_no": "DSV1-CASE-0001",
            "client_id": 1,
            "name": "測試資料基礎案例客戶",
            "phone": "0900000001",
        },
        dataset,
    )

    with pytest.raises(RuntimeError, match="differs from manifest"):
        _require_matching_root_case(
            {
                "case_no": "DSV1-CASE-0001",
                "client_id": 1,
                "name": "其他客戶",
                "phone": "0900000001",
            },
            dataset,
        )


def test_finance_manual_review_uses_a_stable_scenario_command_identity() -> None:
    assert _INGESTION_KEY == "validation-dataset-v1-finance-manual-review"
