from __future__ import annotations

import pytest

from domains.contract_signing.signing_flow import (
    CaseContractSigningFacts,
    CaseContractSigningStatus,
    ContractSigningBlocker,
    ExecutionConversionFacts,
    StaffContractSigningFacts,
    StaffContractSigningStatus,
    case_contract_status,
    client_contract_delivery_blockers,
    execution_conversion_blockers,
    staff_contract_delivery_blockers,
    staff_contract_status,
)


def _staff_signed() -> StaffContractSigningFacts:
    return StaffContractSigningFacts(True, True, True)


def test_staff_contract_requires_template_document_before_send():
    facts = StaffContractSigningFacts(True, False, False)

    assert staff_contract_status(facts) is StaffContractSigningStatus.DOCUMENT_DRAFT
    with pytest.raises(ValueError, match="before document generation"):
        StaffContractSigningFacts(False, True, False)


def test_client_contract_requires_every_staff_signature_and_commitment():
    unsigned = StaffContractSigningFacts(True, True, False)
    facts = CaseContractSigningFacts((unsigned,), False, False, False, False, False)

    assert client_contract_delivery_blockers(
        facts,
        client_line_identity_bound=True,
    ) == (
        ContractSigningBlocker.STAFF_COMMITMENT_INCOMPLETE,
    )
    with pytest.raises(ValueError, match="every staff signature"):
        CaseContractSigningFacts((_staff_signed(), unsigned), True, False, False, False, False)


def test_contract_delivery_requires_a_bound_line_identity():
    draft = StaffContractSigningFacts(True, False, False)
    case = CaseContractSigningFacts((_staff_signed(),), True, True, False, False, False)

    assert staff_contract_delivery_blockers(
        draft,
        staff_line_identity_bound=False,
    ) == (ContractSigningBlocker.LINE_RECIPIENT_UNBOUND,)
    assert client_contract_delivery_blockers(
        case,
        client_line_identity_bound=False,
    ) == (ContractSigningBlocker.LINE_RECIPIENT_UNBOUND,)


def test_contract_signing_status_is_independent_from_deposit_and_execution_gate():
    signing = CaseContractSigningFacts(
        (_staff_signed(),), True, True, True, False, False
    )
    conversion = ExecutionConversionFacts(True, False, True)

    assert case_contract_status(signing) is CaseContractSigningStatus.CLIENT_CONTRACT_SENT
    assert execution_conversion_blockers(conversion) == (
        ContractSigningBlocker.CLIENT_CONTRACT_NOT_COMPLETED,
    )


def test_execution_requires_commitment_contract_and_deposit():
    blockers = execution_conversion_blockers(ExecutionConversionFacts(False, False, False))

    assert blockers == (
        ContractSigningBlocker.COMMITMENT_NOT_READY,
        ContractSigningBlocker.CLIENT_CONTRACT_NOT_COMPLETED,
        ContractSigningBlocker.DEPOSIT_UNSETTLED,
    )


def test_completed_contract_requires_signed_return():
    with pytest.raises(ValueError, match="requires a client signature"):
        CaseContractSigningFacts((_staff_signed(),), True, True, True, False, True)


def test_exact_conversion_stays_blocked_until_all_roots_are_effective():
    blockers = execution_conversion_blockers(
        ExecutionConversionFacts(True, True, False)
    )

    assert blockers == (ContractSigningBlocker.DEPOSIT_UNSETTLED,)
