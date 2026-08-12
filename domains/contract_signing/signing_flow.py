"""Derive contract-signing state without treating it as an order lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StaffContractSigningStatus(StrEnum):
    MATCHING_READY = "matching_ready"
    DOCUMENT_DRAFT = "staff_contract_draft"
    SENT = "staff_contract_sent"
    SIGNED_RECEIVED = "staff_signed_received"


class CaseContractSigningStatus(StrEnum):
    STAFF_SIGNING_IN_PROGRESS = "staff_signing_in_progress"
    COMMITMENT_READY = "commitment_ready"
    CLIENT_DOCUMENT_DRAFT = "client_contract_draft"
    CLIENT_CONTRACT_SENT = "client_contract_sent"
    CLIENT_SIGNED_RECEIVED = "client_signed_received"
    CONTRACT_COMPLETED = "contract_completed"


class ContractSigningBlocker(StrEnum):
    STAFF_COMMITMENT_INCOMPLETE = "staff_commitment_incomplete"
    LINE_RECIPIENT_UNBOUND = "line_recipient_unbound"
    CLIENT_CONTRACT_NOT_COMPLETED = "client_contract_not_completed"
    DEPOSIT_UNSETTLED = "deposit_unsettled"
    COMMITMENT_NOT_READY = "commitment_not_ready"


@dataclass(frozen=True, slots=True)
class StaffContractSigningFacts:
    document_generated: bool
    contract_sent: bool
    signed_return_received: bool

    def __post_init__(self) -> None:
        _require_monotonic_staff_facts(self)


@dataclass(frozen=True, slots=True)
class CaseContractSigningFacts:
    staff_segments: tuple[StaffContractSigningFacts, ...]
    commitment_created: bool
    client_document_generated: bool
    client_contract_sent: bool
    client_signed_return_received: bool
    contract_completed: bool

    def __post_init__(self) -> None:
        _require_case_facts(self)


@dataclass(frozen=True, slots=True)
class ExecutionConversionFacts:
    commitment_ready: bool
    client_contract_completed: bool
    deposit_settled: bool


def staff_contract_status(
    facts: StaffContractSigningFacts,
) -> StaffContractSigningStatus:
    if facts.signed_return_received:
        return StaffContractSigningStatus.SIGNED_RECEIVED
    if facts.contract_sent:
        return StaffContractSigningStatus.SENT
    if facts.document_generated:
        return StaffContractSigningStatus.DOCUMENT_DRAFT
    return StaffContractSigningStatus.MATCHING_READY


def case_contract_status(
    facts: CaseContractSigningFacts,
) -> CaseContractSigningStatus:
    if facts.contract_completed:
        return CaseContractSigningStatus.CONTRACT_COMPLETED
    if facts.client_signed_return_received:
        return CaseContractSigningStatus.CLIENT_SIGNED_RECEIVED
    if facts.client_contract_sent:
        return CaseContractSigningStatus.CLIENT_CONTRACT_SENT
    if facts.client_document_generated:
        return CaseContractSigningStatus.CLIENT_DOCUMENT_DRAFT
    if facts.commitment_created:
        return CaseContractSigningStatus.COMMITMENT_READY
    return CaseContractSigningStatus.STAFF_SIGNING_IN_PROGRESS


def client_contract_delivery_blockers(
    facts: CaseContractSigningFacts,
    *,
    client_line_identity_bound: bool,
) -> tuple[ContractSigningBlocker, ...]:
    blockers = list(_commitment_delivery_blockers(facts))
    if not client_line_identity_bound:
        blockers.append(ContractSigningBlocker.LINE_RECIPIENT_UNBOUND)
    return tuple(blockers)


def staff_contract_delivery_blockers(
    facts: StaffContractSigningFacts,
    *,
    staff_line_identity_bound: bool,
) -> tuple[ContractSigningBlocker, ...]:
    blockers: list[ContractSigningBlocker] = []
    if not facts.document_generated:
        blockers.append(ContractSigningBlocker.STAFF_COMMITMENT_INCOMPLETE)
    if not staff_line_identity_bound:
        blockers.append(ContractSigningBlocker.LINE_RECIPIENT_UNBOUND)
    return tuple(blockers)


def execution_conversion_blockers(
    facts: ExecutionConversionFacts,
) -> tuple[ContractSigningBlocker, ...]:
    blockers: list[ContractSigningBlocker] = []
    if not facts.commitment_ready:
        blockers.append(ContractSigningBlocker.COMMITMENT_NOT_READY)
    if not facts.client_contract_completed:
        blockers.append(ContractSigningBlocker.CLIENT_CONTRACT_NOT_COMPLETED)
    if not facts.deposit_settled:
        blockers.append(ContractSigningBlocker.DEPOSIT_UNSETTLED)
    return tuple(blockers)


def _all_staff_signed(
    staff_segments: tuple[StaffContractSigningFacts, ...],
) -> bool:
    return all(segment.signed_return_received for segment in staff_segments)


def _commitment_delivery_blockers(
    facts: CaseContractSigningFacts,
) -> tuple[ContractSigningBlocker, ...]:
    if _all_staff_signed(facts.staff_segments) and facts.commitment_created:
        return ()
    return (ContractSigningBlocker.STAFF_COMMITMENT_INCOMPLETE,)


def _require_monotonic_staff_facts(
    facts: StaffContractSigningFacts,
) -> None:
    values = (
        facts.document_generated,
        facts.contract_sent,
        facts.signed_return_received,
    )
    if any(not isinstance(value, bool) for value in values):
        raise TypeError("staff contract facts must be boolean")
    if facts.contract_sent and not facts.document_generated:
        raise ValueError("staff contract cannot be sent before document generation")
    if facts.signed_return_received and not facts.contract_sent:
        raise ValueError("staff signature requires a sent contract")


def _require_case_facts(facts: CaseContractSigningFacts) -> None:
    if not facts.staff_segments:
        raise ValueError("contract signing requires at least one staff segment")
    values = (
        facts.commitment_created,
        facts.client_document_generated,
        facts.client_contract_sent,
        facts.client_signed_return_received,
        facts.contract_completed,
    )
    if any(not isinstance(value, bool) for value in values):
        raise TypeError("case contract facts must be boolean")
    if facts.commitment_created and not _all_staff_signed(facts.staff_segments):
        raise ValueError("commitment requires every staff signature")
    if facts.client_document_generated and not facts.commitment_created:
        raise ValueError("client document requires a staff commitment")
    if facts.client_contract_sent and not facts.client_document_generated:
        raise ValueError("client contract cannot be sent before document generation")
    if facts.client_signed_return_received and not facts.client_contract_sent:
        raise ValueError("client signature requires a sent contract")
    if facts.contract_completed and not facts.client_signed_return_received:
        raise ValueError("contract completion requires a client signature")
