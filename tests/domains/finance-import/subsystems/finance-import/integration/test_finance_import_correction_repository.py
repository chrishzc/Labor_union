"""Focused correction facts and legacy-alert compatibility contracts."""

from types import SimpleNamespace

from domains.finance_import.correction import FinanceImportCorrectionSelection
from domains.finance_import.planning import FinanceClassificationType
from infrastructure.mysql.anomaly_registry_repository import (
    append_finance_import_manual_review_resolution,
)
from infrastructure.mysql.finance_import_repository import _load_correction_facts
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext
from subsystems.finance_import.correction_workflow import (
    FinanceImportCorrectionPreview,
    _build_receipt,
)


class _Cursor:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.executions = []
        self._current = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))
        self._current = next(self._responses)

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current


class _Connection:
    def __init__(self, responses):
        self.cursor_instance = _Cursor(responses)

    def cursor(self):
        return self.cursor_instance


def _selection():
    return FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_RECEIPT,
        ("client-obligation:1",),
        "owner review confirmed",
        ("bank-statement:line-1",),
    )


def test_correction_facts_use_latest_owner_review_without_anomaly_projection():
    connection = _Connection(
        (
            {
                "batch_id": 1,
                "batch_identity": "finance-import-batch:1",
                "batch_version": 3,
                "canonical_fact_version": 2,
                "classification_version": 7,
                "disposition": "manual_review",
                "credit": 12000,
                "debit": 0,
            },
            ({"obligation_identity": "client-obligation:1", "remaining_amount_ntd": 12000},),
            (),
            (),
        )
    )

    facts = _load_correction_facts(
        connection.cursor_instance,
        _selection(),
        for_update=True,
    )

    assert facts.active_manual_review is True
    assert facts.alert_version == 7
    assert len(connection.cursor_instance.executions) == 4
    assert all(
        "anomaly_current_alerts" not in statement
        for statement, _parameters in connection.cursor_instance.executions
    )


def test_legacy_alert_resolution_is_a_noop_when_no_projection_exists():
    connection = _Connection((None,))
    candidate = SimpleNamespace(
        row_identity="finance-import-row:1",
        fingerprint=PreviewFingerprint("a" * 64),
        reason="owner review confirmed",
    )

    assert (
        append_finance_import_manual_review_resolution(
            connection,
            candidate,
            ActorContext("test-operator"),
        )
        == 0
    )
    assert len(connection.cursor_instance.executions) == 1


def test_correction_receipt_reports_zero_legacy_alert_events():
    candidate = SimpleNamespace(
        row_identity="finance-import-row:1",
        batch_identity="finance-import-batch:1",
        allocations=(SimpleNamespace(),),
    )
    preview = FinanceImportCorrectionPreview(
        candidate,
        3,
        2,
        7,
        PreviewFingerprint("b" * 64),
    )

    receipt = _build_receipt(preview, 1, 0)

    assert receipt.alert_resolved_event_count == 0
