from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_finance_import_uses_anomalies_adapter_for_manual_review_resolution():
    finance_import_source = (
        ROOT / "infrastructure" / "mysql" / "finance_import_repository.py"
    ).read_text(encoding="utf-8")
    anomaly_adapter_source = (
        ROOT / "infrastructure" / "mysql" / "anomaly_registry_repository.py"
    ).read_text(encoding="utf-8")

    assert "append_finance_import_manual_review_resolution" in finance_import_source
    assert "INSERT INTO anomaly_workflow_events" not in finance_import_source
    assert "INSERT INTO anomaly_workflow_events" in anomaly_adapter_source
