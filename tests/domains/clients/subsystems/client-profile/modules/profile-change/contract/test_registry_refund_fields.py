"""Refund corrections share the existing owner; presentation and audits never expose full accounts."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routes.client_registry import _field_capabilities
from api.schemas.client_registry import ClientProfileChangeSet, BeClassChangeSet
from domains.case_import.beclass_correction import normalize_beclass_changes, BeClassCorrectionError
from domains.case_import.refund_account import effective_refund_account, mask_refund_values
from infrastructure.mysql.beclass_refund_account import load_effective_refund_account
from infrastructure.mysql.client_receipt_reconciliation_repository import _insert_refund_recipient_snapshot


def test_refund_normalization_preserves_leading_zero_and_readonly_allowlists():
    values = normalize_beclass_changes({"refund_bank_code": "０００-１２３４", "refund_account_no": "０００１２３４５６７８９"})
    assert values == {"refund_bank_code": "0001234", "refund_account_no": "000123456789"}
    for field in ("identity_status", "admin_notes"):
        with pytest.raises(ValidationError): ClientProfileChangeSet.model_validate({field: "unauthorized"})
    with pytest.raises(ValidationError): BeClassChangeSet.model_validate({"birth_date": "2000-01-01"})
    for field in ("identity_status", "birth_date"):
        with pytest.raises(BeClassCorrectionError): normalize_beclass_changes({field: "unauthorized"})
    capabilities = _field_capabilities({"identity_status": "原住民", "admin_notes": "合成", "name": "合成"}, "client_profile", True)
    assert not capabilities["identity_status"]["editable"] and not capabilities["admin_notes"]["editable"]
    assert capabilities["name"]["editable"]


class Cursor:
    def __init__(self, sources, *, existing=False):
        self.sources = sources
        self.existing = existing
        self.operations = []
        self.rowcount = 1
    def execute(self, sql, args): self.operations.append((sql, args))
    def fetchone(self): return {"refund_obligation_identity": "existing"} if self.existing else None
    def fetchall(self): return self.sources


def test_same_effective_account_is_used_by_financial_snapshot_and_safe_view():
    source = {"refund_bank_code": "0000000", "refund_account_no": "000011112222",
              "effective_values_json": {"refund_account_no": "000033334444"}}
    cursor = Cursor([source])
    account = load_effective_refund_account(cursor, "SYNTHETIC-1")
    assert account.account_no == "000033334444"
    assert _insert_refund_recipient_snapshot(cursor, "synthetic-refund", "SYNTHETIC-1", "client_refund")
    assert cursor.operations[-1][1][3] == account.account_no
    masked = mask_refund_values({"refund_account_no": account.account_no})
    assert masked["refund_account_no"] == "****4444"
    assert account.account_no not in str(masked)


def test_ambiguous_or_missing_account_is_not_payable_and_existing_snapshot_is_immutable():
    for sources in ([], [{"refund_bank_code": "0000000"}], [{}, {}]):
        cursor = Cursor(sources)
        assert not _insert_refund_recipient_snapshot(cursor, "synthetic-refund", "SYNTHETIC-1", "client_refund", require_complete=False)
        assert all(not sql.startswith("INSERT") for sql, _ in cursor.operations)
    cursor = Cursor([], existing=True)
    assert not _insert_refund_recipient_snapshot(cursor, "existing", "SYNTHETIC-1", "client_refund")
    assert len(cursor.operations) == 1
