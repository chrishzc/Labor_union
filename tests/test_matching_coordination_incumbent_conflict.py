"""
File: test_matching_coordination_incumbent_conflict.py
Description: 驗證 M3 assignment conversion 的 durable submit、canonical query 與 mismatch fail closed。
"""

import pytest

from domains.scheduling.matching_coordination import (
    SOURCE_KINDS,
    MatchingCrossDomainRequest,
    MatchingRequestKind,
    MatchingSourceVersion,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_assignment_conversion import (
    AssignmentConversionResultState,
    AssignmentConversionSubmitCommand,
    AssignmentConversionSubmissionReceipt,
    CanonicalAssignmentConversionReceipt,
    MatchingAssignmentConversion,
    MatchingAssignmentConversionError,
)


class _RequestPort:
    def __init__(self, receipt: AssignmentConversionSubmissionReceipt) -> None:
        self.receipt = receipt
        self.calls: list[AssignmentConversionSubmitCommand] = []

    def submit(self, command: AssignmentConversionSubmitCommand) -> AssignmentConversionSubmissionReceipt:
        self.calls.append(command)
        return self.receipt


class _QueryPort:
    def __init__(self, receipt: CanonicalAssignmentConversionReceipt | None = None) -> None:
        self.receipt = receipt
        self.calls: list[tuple[str, object]] = []

    def get_canonical_receipt(self, request_id: str) -> CanonicalAssignmentConversionReceipt | None:
        self.calls.append(("get_canonical_receipt", request_id))
        return self.receipt

    def __getattr__(self, name: str):
        def unexpected(*args: object):
            self.calls.append((name, args))
            raise AssertionError("conversion submit must not query or write assignment roots")

        return unexpected


def _request(kind: MatchingRequestKind, candidate_id: str | None) -> MatchingCrossDomainRequest:
    source_versions = tuple(MatchingSourceVersion(item, f"{item}:1", 1, "a" * 64) for item in SOURCE_KINDS)
    return MatchingCrossDomainRequest(
        request_id=f"request-{kind.value}-{candidate_id or 'none'}",
        request_kind=kind,
        case_no="CASE-001",
        package_id="package-001",
        package_version=2,
        criteria_snapshot_id="criteria-001",
        candidate_id=candidate_id,
        source_versions=source_versions,
        lineage_event_id="matching-decision-001",
        reason="customer accepted willing candidate",
    )


def test_assignment_conversion_submit_returns_pending_receipt_without_query_or_root_write() -> None:
    request = _request(MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED, "candidate-001")
    command = AssignmentConversionSubmitCommand(
        request,
        IdempotencyKey("assignment-conversion-submit-001"),
        CorrelationId("assignment-conversion-correlation-001"),
    )
    expected = AssignmentConversionSubmissionReceipt(
        request.request_id,
        "assignment-conversion:pending:001",
        command.fingerprint,
        False,
    )
    request_port = _RequestPort(expected)
    query_port = _QueryPort()

    result = MatchingAssignmentConversion(request_port, query_port).submit(command)

    assert result is expected
    assert request_port.calls == [command]
    assert query_port.calls == []


def test_rematch_or_missing_candidate_fails_closed_without_submit() -> None:
    invalid_requests = (
        _request(MatchingRequestKind.REMATCH_REQUESTED, "candidate-001"),
        _request(MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED, None),
    )
    for index, request in enumerate(invalid_requests, start=1):
        receipt = AssignmentConversionSubmissionReceipt(
            request.request_id,
            f"assignment-conversion:pending:{index}",
            PreviewFingerprint("b" * 64),
            False,
        )
        request_port = _RequestPort(receipt)
        query_port = _QueryPort()
        command = AssignmentConversionSubmitCommand(
            request,
            IdempotencyKey(f"assignment-conversion-invalid-{index}"),
            CorrelationId(f"assignment-conversion-invalid-correlation-{index}"),
        )

        with pytest.raises(MatchingAssignmentConversionError) as raised:
            MatchingAssignmentConversion(request_port, query_port).submit(command)

        assert raised.value.error.code == "matching_assignment_conversion_mismatch"
        assert request_port.calls == []
        assert query_port.calls == []


def test_query_returns_exact_converted_canonical_receipt_without_submit() -> None:
    request = _request(MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED, "candidate-001")
    receipt = CanonicalAssignmentConversionReceipt(
        request_id=request.request_id,
        result_state=AssignmentConversionResultState.CONVERTED,
        package_id=request.package_id,
        package_version=request.package_version,
        criteria_snapshot_id=request.criteria_snapshot_id,
        candidate_id=request.candidate_id,
        source_versions=request.source_versions,
        assignment_reference="assignment:canonical-001",
        receipt_fingerprint=PreviewFingerprint("c" * 64),
    )
    request_port = _RequestPort(
        AssignmentConversionSubmissionReceipt(
            request.request_id,
            "assignment-conversion:pending:query",
            PreviewFingerprint("d" * 64),
            False,
        )
    )
    query_port = _QueryPort(receipt)

    result = MatchingAssignmentConversion(request_port, query_port).query(
        request,
        CorrelationId("assignment-conversion-query-correlation-001"),
    )

    assert result is receipt
    assert result.result_state is AssignmentConversionResultState.CONVERTED
    assert result.request_id == request.request_id
    assert result.package_id == request.package_id
    assert result.package_version == request.package_version
    assert result.criteria_snapshot_id == request.criteria_snapshot_id
    assert result.candidate_id == request.candidate_id
    assert result.source_versions == request.source_versions
    assert result.assignment_reference
    assert isinstance(result.receipt_fingerprint, PreviewFingerprint)
    assert request_port.calls == []
    assert query_port.calls == [("get_canonical_receipt", request.request_id)]


@pytest.mark.parametrize("mode", ("pending", "mismatch"))
def test_query_pending_or_mismatched_receipt_fails_without_submit(mode: str) -> None:
    request = _request(MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED, "candidate-001")
    receipt = None
    if mode == "mismatch":
        receipt = CanonicalAssignmentConversionReceipt(
            request_id=request.request_id,
            result_state=AssignmentConversionResultState.CONVERTED,
            package_id="different-package",
            package_version=request.package_version,
            criteria_snapshot_id=request.criteria_snapshot_id,
            candidate_id=request.candidate_id,
            source_versions=request.source_versions,
            assignment_reference="assignment:canonical-mismatch",
            receipt_fingerprint=PreviewFingerprint("e" * 64),
        )
    request_port = _RequestPort(
        AssignmentConversionSubmissionReceipt(
            request.request_id,
            "assignment-conversion:pending:query-error",
            PreviewFingerprint("f" * 64),
            False,
        )
    )
    query_port = _QueryPort(receipt)

    with pytest.raises(MatchingAssignmentConversionError) as raised:
        MatchingAssignmentConversion(request_port, query_port).query(
            request,
            CorrelationId(f"assignment-conversion-query-correlation-{mode}"),
        )

    assert raised.value.error.code == (
        "matching_assignment_conversion_pending"
        if mode == "pending"
        else "matching_assignment_conversion_mismatch"
    )
    assert request_port.calls == []
    assert query_port.calls == [("get_canonical_receipt", request.request_id)]
