from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domains.line.delivery import LineMessageKind
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.contract_signing.line_delivery import (
    ContractLineBinding,
    ContractLineRecipientError,
    build_contract_delivery_request,
    require_contract_line_recipient,
)


def _bound_staff_binding() -> ContractLineBinding:
    return ContractLineBinding("Ustaff", "bound", "staff", "42")


def test_contract_delivery_uses_the_exact_bound_subject():
    recipient = require_contract_line_recipient(
        _bound_staff_binding(),
        subject_type="staff",
        subject_reference="42",
    )

    request = build_contract_delivery_request(
        recipient,
        case_no="116000001",
        document_version_id=8,
        download_url="https://contracts.example.test/download/token",
        audience_label="月嫂合約",
        scheduled_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        idempotency_key=IdempotencyKey("contract-send-staff-1"),
        correlation_id=CorrelationId("contract-send-staff-1"),
    )

    assert request.recipient.identity.value == "Ustaff"
    assert request.message_kind is LineMessageKind.TEXT
    assert '"text"' in request.payload_json
    assert request.source_aggregate_identity == "116000001:8"


@pytest.mark.parametrize(
    ("binding", "subject_type", "subject_reference", "error"),
    [
        (ContractLineBinding(None, None, None, None), "staff", "42", "unbound"),
        (_bound_staff_binding(), "customer", "1", "subject_mismatch"),
    ],
)
def test_contract_delivery_rejects_unbound_or_wrong_subject(
    binding,
    subject_type,
    subject_reference,
    error,
):
    with pytest.raises(ValueError, match=error):
        require_contract_line_recipient(
            binding,
            subject_type=subject_type,
            subject_reference=subject_reference,
        )


def test_contract_delivery_refuses_non_https_document_locations():
    recipient = require_contract_line_recipient(
        _bound_staff_binding(),
        subject_type="staff",
        subject_reference="42",
    )

    with pytest.raises(ValueError, match="HTTPS"):
        build_contract_delivery_request(
            recipient,
            case_no="116000001",
            document_version_id=8,
            download_url="file:///contract.xlsx",
            audience_label="月嫂合約",
            scheduled_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            idempotency_key=IdempotencyKey("contract-send-staff-1"),
            correlation_id=CorrelationId("contract-send-staff-1"),
        )
