from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODULE = PROJECT_ROOT / "subsystems" / "client_finance" / "subsidy_return_reconciliation.py"


def test_retired_subsidy_return_reconciliation_module_stays_removed() -> None:
    assert not LEGACY_MODULE.exists()


def test_required_client_finance_routes_remain_mounted() -> None:
    source = (PROJECT_ROOT / "api" / "main.py").read_text(encoding="utf-8")
    for route in ("client_refund_reversal", "finance_import", "government_subsidy"):
        assert f"app.include_router({route}.router)" in source


def test_required_client_finance_schema_contract_remains_declared() -> None:
    schema = (PROJECT_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    ledger_schema = (
        PROJECT_ROOT / "db" / "schema_parts" / "111_client_finance_ledger.sql"
    ).read_text(encoding="utf-8")
    advance_schema = (
        PROJECT_ROOT
        / "db"
        / "schema_parts"
        / "138_client_subsidy_advance_settlement.sql"
    ).read_text(encoding="utf-8")

    assert "subsidy_refund_receivable" in schema
    assert "subsidy_refund_refunded" in schema
    assert "CREATE TABLE IF NOT EXISTS client_ledger_entries" in ledger_schema
    assert "client_subsidy_advance_recoveries" in advance_schema
