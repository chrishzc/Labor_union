"""Regression guards for Client Finance legacy receipt-writer retirement."""

from pathlib import Path

from subsystems.finance_import import reconciliation_dispatch


class _Cursor:
    def __init__(self, row):
        self._row = row
        self.sql = []

    def execute(self, sql, _params=()):
        self.sql.append(sql)

    def fetchone(self):
        return self._row


def test_diagnostic_client_receipt_dispatch_never_posts_a_legacy_payment() -> None:
    cursor = _Cursor(
        {"id": 7, "classification_type": "client_receipt", "classification_reason": None}
    )

    result = reconciliation_dispatch.dispatch_finance_import_row(cursor, 7, 4)

    assert result == {
        "classification_type": "client_receipt",
        "result": "pending",
        "reason": "legacy_finance_import_diagnostic_dispatch_retired",
        "formal_references": {},
        "finance_alert_action": None,
    }
    assert all("client_payments" not in sql for sql in cursor.sql)
    assert all("client_payment_transactions" not in sql for sql in cursor.sql)


def test_retired_dispatch_sources_do_not_keep_legacy_payment_writers() -> None:
    project_root = Path(__file__).parents[1]
    source_path = project_root / "subsystems" / "finance_import" / "reconciliation_dispatch.py"

    source = source_path.read_text(encoding="utf-8")
    assert "client_payment_transactions" not in source
    assert "client_payments" not in source


def test_retired_finance_import_service_modules_do_not_remain_as_compatibility_paths() -> None:
    project_root = Path(__file__).parents[1]
    retired_paths = (
        "services/finance_cancellation_code.py",
        "services/finance_import_states.py",
        "services/finance_import_dispatch.py",
    )

    for relative_path in retired_paths:
        assert not (project_root / relative_path).exists()


def test_unused_client_payment_snapshot_writer_is_retired() -> None:
    project_root = Path(__file__).parents[1]

    assert not (project_root / "subsystems" / "client_finance" / "payment_snapshot.py").exists()
