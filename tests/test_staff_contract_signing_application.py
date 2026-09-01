"""
File: test_staff_contract_signing_application.py
Description: 驗證月嫂契約簽回、交易回滾與簽約前精確服務日承諾規則。
"""

from datetime import date, datetime
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.archive.contract_documents import (
    archive_contract_document,
    discard_uncommitted_contract_document,
)
import subsystems.contract_signing.staff_contract_application as staff_signing
from shared_kernel.identities import CorrelationId, IdempotencyKey


class _Connection:
    def __init__(self) -> None:
        self.began = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self) -> None:
        self.began = True

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_staff_signed_return_discards_new_archive_when_transaction_fails(tmp_path, monkeypatch):
    connection = _Connection()
    application = staff_signing.StaffContractSigningApplication(
        lambda: connection,
        archive_root=tmp_path,
        now=lambda: datetime(2030, 1, 1),
        archive_document=archive_contract_document,
        discard_document=discard_uncommitted_contract_document,
    )
    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: None)
    monkeypatch.setattr(staff_signing, "_staff_segment", lambda *_: {"plan_id": 3})
    monkeypatch.setattr(staff_signing, "_sent_staff_document", lambda *_: 4)
    monkeypatch.setattr(staff_signing, "_insert_signed_document", lambda *_: 5)
    monkeypatch.setattr(staff_signing, "_insert_signed_event", lambda *_: 6)
    monkeypatch.setattr(
        staff_signing,
        "_create_commitment_if_ready",
        lambda *_: (_ for _ in ()).throw(ValueError("stale_version")),
    )

    with pytest.raises(ValueError, match="stale_version"):
        application.record_signed_return(_command())

    assert connection.rolled_back is True
    assert connection.closed is True
    assert not (tmp_path / "CASE-1/staff/9/wp56-staff-signed-signed.xlsx").exists()


def test_staff_signed_return_rejects_same_key_with_different_signed_content(monkeypatch):
    application = staff_signing.StaffContractSigningApplication(
        lambda: _ReplayConnection(), archive_root=Path("unused"), now=lambda: datetime(2030, 1, 1)
    )
    monkeypatch.setattr(staff_signing, "archive_contract_document", lambda *_args, **_kwargs: pytest.fail("archive must not run on idempotency conflict"))

    with pytest.raises(ValueError, match="contract_signature_idempotency_conflict"):
        application.record_signed_return(_command())


def test_commitment_uses_weekly_two_rest_days_instead_of_calendar_interval():
    segment = {
        "id": 26,
        "staff_id": 537,
        "assigned_start_date": date(2026, 9, 10),
        "assigned_end_date": date(2026, 9, 16),
    }

    allocations = staff_signing._allocate_commitment_service_days(
        {"start_date": date(2026, 9, 10), "service_days": 5, "service_type": "週休2日"},
        [segment],
        set(),
    )

    assert [service_date for _segment, service_date in allocations] == [
        date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14),
        date(2026, 9, 15), date(2026, 9, 16),
    ]


def test_commitment_rejects_segments_that_do_not_cover_every_planned_service_day():
    segment = {
        "id": 26,
        "staff_id": 537,
        "assigned_start_date": date(2026, 9, 10),
        "assigned_end_date": date(2026, 9, 15),
    }

    with pytest.raises(ValueError, match="precontract_service_days_mismatch"):
        staff_signing._allocate_commitment_service_days(
            {"start_date": date(2026, 9, 10), "service_days": 5, "service_type": "週休2日"},
            [segment],
            set(),
        )


def test_manual_staff_attestation_accepts_a_plan_before_availability_lock_exists():
    staff_signing._require_manual_staff_snapshot_applicable({
        "status": "accepted", "is_active": None, "already_signed": 0,
    })


def test_manual_staff_attestation_requires_customer_acceptance_for_active_proposal():
    staff_signing._require_manual_staff_snapshot_applicable({
        "status": "proposed", "is_active": 1, "customer_decision": "accepted", "already_signed": 0,
    })
    with pytest.raises(ValueError, match="manual_contract_customer_acceptance_required"):
        staff_signing._require_manual_staff_snapshot_applicable({
            "status": "proposed", "is_active": 1, "customer_decision": "", "already_signed": 0,
        })


def test_manual_staff_attestation_uses_injected_finance_adapters(tmp_path, monkeypatch):
    class _ConnectionWithCursor(_Connection):
        @contextmanager
        def cursor(self):
            yield object()

    connection = _ConnectionWithCursor()
    finance_calls = []

    def order_selector(_cursor, case_no, *, lock):
        finance_calls.append(("order_selector", case_no, lock))
        return {"case_no": case_no}

    def facts_loader(_cursor, order, *, lock):
        finance_calls.append(("facts_loader", order, lock))
        return {"case_no": order["case_no"]}

    def terms_writer(_cursor, _command):
        finance_calls.append(("terms_writer",))

    application = staff_signing.StaffContractSigningApplication(
        lambda: connection,
        archive_root=tmp_path,
        now=lambda: datetime(2030, 1, 1),
        archive_document=lambda *_args, **_kwargs: SimpleNamespace(storage_key="archive-key"),
        discard_document=lambda **_kwargs: None,
        order_selector=order_selector,
        finance_facts_loader=facts_loader,
        finance_terms_writer=terms_writer,
    )
    command = staff_signing.ManualStaffContractAttestationCommand(
        "CASE-1", 9, b"signed-content", "signed.xlsx", "application/octet-stream",
        "phone", "customer-confirmed", "manual-preview", "staff-1",
        IdempotencyKey("manual-key"), CorrelationId("manual-key"),
    )

    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: None)
    monkeypatch.setattr(
        staff_signing,
        "_manual_staff_snapshot",
        lambda *_args, **_kwargs: {"status": "accepted", "is_active": None, "already_signed": 0},
    )
    monkeypatch.setattr(staff_signing, "_manual_preview_fingerprint", lambda *_args: "manual-preview")
    monkeypatch.setattr(staff_signing, "_staff_segment", lambda *_args: {"id": 9, "plan_id": 3})
    monkeypatch.setattr(
        staff_signing,
        "load_approved_template",
        lambda *_args: SimpleNamespace(template_filename="template.xlsx", template_key="contract_staff_service"),
    )
    monkeypatch.setattr(staff_signing, "approved_template_mapping_path", lambda *_args: Path("mapping.json"))
    monkeypatch.setattr(staff_signing, "_staff_template_facts", lambda *_args: {})
    monkeypatch.setattr(staff_signing, "render_contract_template", lambda **_kwargs: b"template-content")
    monkeypatch.setattr(staff_signing, "_insert_generated_document", lambda *_args: 41)
    monkeypatch.setattr(staff_signing, "_insert_signed_document", lambda *_args: 42)
    monkeypatch.setattr(staff_signing, "_insert_signed_event", lambda *_args: 43)
    monkeypatch.setattr(staff_signing, "_create_commitment_if_ready", lambda *_args: 44)
    monkeypatch.setattr(staff_signing, "_append_command_outcome", lambda *_args: None)
    monkeypatch.setattr(
        staff_signing,
        "build_precontract_deposit_candidate",
        lambda *_args: SimpleNamespace(mutates=True),
    )
    monkeypatch.setattr(staff_signing, "precontract_deposit_terms_impact", lambda *_args: "impact")

    receipt = application.record_manual_attestation(command)

    assert receipt.commitment_id == 44
    assert finance_calls == [
        ("order_selector", "CASE-1", True),
        ("facts_loader", {"case_no": "CASE-1"}, True),
        ("terms_writer",),
    ]
    assert connection.committed is True

class _ReplayConnection:
    @contextmanager
    def cursor(self):
        yield _ReplayCursor()

    def close(self) -> None:
        pass


class _ReplayCursor:
    def execute(self, _statement, _parameters=()) -> None:
        pass

    def fetchone(self):
        return {
            "document_version_id": 7,
            "id": 8,
            "line_delivery_task_id": None,
            "sha256": "different-content-digest",
        }


def _command() -> staff_signing.RecordStaffSignedReturnCommand:
    return staff_signing.RecordStaffSignedReturnCommand(
        "CASE-1", 9, b"signed-content", "signed.xlsx", "application/octet-stream",
        "wp56-test", IdempotencyKey("wp56-staff-signed"), CorrelationId("wp56-staff-signed"), 4,
    )
