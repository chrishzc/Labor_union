"""
File: external_signing.py
Description: 定義外部簽約完成回報的 closed state、順序、版本與最終 PDF 門禁。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import re

from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
    require_sha256_hex,
)


_SESSION_ID = re.compile(r"^ces_[0-9a-f]{32}$")


def derive_external_signing_session_id(
    case_no: str,
    matching_plan_id: int,
    document_set_fingerprint: str,
) -> str:
    require_canonical_text(case_no, "case number", 50)
    require_positive_integer(matching_plan_id, "matching plan ID")
    require_sha256_hex(document_set_fingerprint, "document set fingerprint")
    source = f"{case_no}\n{matching_plan_id}\n{document_set_fingerprint}"
    return f"ces_{hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]}"


class ExternalSigningState(StrEnum):
    STAFF_REPORTING = "staff_reporting"
    STAFF_REPORTS_COMPLETE = "staff_reports_complete"
    CLIENT_REPORTED_FINAL_PDF_PENDING = "client_reported_final_pdf_pending"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"


class ExternalSigningErrorCode(StrEnum):
    STATUS_VERSION_STALE = "external_signing_status_version_stale"
    SESSION_SUPERSEDED = "external_signing_session_superseded"
    SESSION_COMPLETED = "external_signing_session_completed"
    STAFF_TARGET_NOT_FOUND = "external_staff_report_target_not_found"
    STAFF_DOCUMENT_VERSION_STALE = "external_staff_report_document_stale"
    STAFF_REPORT_ALREADY_RECORDED = "external_staff_report_already_recorded"
    STAFF_REPORTS_INCOMPLETE = "external_staff_reports_incomplete"
    CLIENT_REPORT_ALREADY_RECORDED = "external_client_report_already_recorded"
    CLIENT_REPORT_OUT_OF_ORDER = "external_client_report_out_of_order"
    CLIENT_DOCUMENT_VERSION_STALE = "external_client_report_document_stale"
    COMMITMENT_STALE = "external_client_report_commitment_stale"
    COMMITMENT_MISSING = "external_signing_commitment_missing"
    FINAL_PDF_NOT_PENDING = "final_signed_contract_not_pending"
    FINAL_PDF_ALREADY_APPLIED = "final_signed_contract_already_applied"


_CONFLICT_CODES = frozenset(
    {
        ExternalSigningErrorCode.STATUS_VERSION_STALE,
        ExternalSigningErrorCode.STAFF_DOCUMENT_VERSION_STALE,
        ExternalSigningErrorCode.CLIENT_DOCUMENT_VERSION_STALE,
        ExternalSigningErrorCode.COMMITMENT_STALE,
    }
)


class ExternalSigningRuleError(ValueError):
    def __init__(
        self,
        code: ExternalSigningErrorCode,
        *,
        current_version: int | None = None,
    ) -> None:
        self.code = code
        self.category = "conflict" if code in _CONFLICT_CODES else "domain_blocked"
        self.retryable = False
        self.current_version = current_version
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class StaffSigningReportTarget:
    matching_segment_id: int
    staff_subject_reference: str
    document_version_id: int

    def __post_init__(self) -> None:
        require_positive_integer(self.matching_segment_id, "matching segment ID")
        require_canonical_text(
            self.staff_subject_reference,
            "staff subject reference",
            191,
        )
        require_positive_integer(self.document_version_id, "staff document version ID")


@dataclass(frozen=True, slots=True)
class ExternalSigningSessionFacts:
    session_id: str
    case_no: str
    matching_plan_id: int
    document_set_fingerprint: str
    staff_targets: tuple[StaffSigningReportTarget, ...]
    reported_staff_segment_ids: tuple[int, ...]
    client_subject_reference: str
    client_document_version_id: int
    commitment_id: int | None
    client_reported: bool
    state: ExternalSigningState
    status_version: int

    def __post_init__(self) -> None:
        _validate_session_identity(self)
        _validate_staff_targets(self)
        _validate_session_state(self)

    @property
    def required_staff_segment_ids(self) -> tuple[int, ...]:
        return tuple(target.matching_segment_id for target in self.staff_targets)

    @property
    def all_staff_reported(self) -> bool:
        return self.reported_staff_segment_ids == self.required_staff_segment_ids

    def staff_target(self, matching_segment_id: int) -> StaffSigningReportTarget | None:
        return next(
            (
                target
                for target in self.staff_targets
                if target.matching_segment_id == matching_segment_id
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class ExternalSigningTransition:
    after_state: ExternalSigningState
    resulting_status_version: int
    reported_staff_segment_ids: tuple[int, ...]
    client_reported: bool
    requires_commitment: bool = False
    create_client_reminder_intent: bool = False
    create_final_pdf_recovery_task: bool = False
    contract_completed: bool = False


def reduce_staff_completion_report(
    facts: ExternalSigningSessionFacts,
    *,
    matching_segment_id: int,
    expected_document_version_id: int,
    expected_status_version: int,
) -> ExternalSigningTransition:
    _require_mutable_session(facts)
    _require_current_version(facts, expected_status_version)
    if facts.state is not ExternalSigningState.STAFF_REPORTING:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.STAFF_REPORT_ALREADY_RECORDED,
            current_version=facts.status_version,
        )
    target = facts.staff_target(matching_segment_id)
    if target is None:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.STAFF_TARGET_NOT_FOUND,
            current_version=facts.status_version,
        )
    if target.document_version_id != expected_document_version_id:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.STAFF_DOCUMENT_VERSION_STALE,
            current_version=facts.status_version,
        )
    if matching_segment_id in facts.reported_staff_segment_ids:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.STAFF_REPORT_ALREADY_RECORDED,
            current_version=facts.status_version,
        )

    reported = tuple(sorted((*facts.reported_staff_segment_ids, matching_segment_id)))
    all_reported = reported == facts.required_staff_segment_ids
    return ExternalSigningTransition(
        after_state=(
            ExternalSigningState.STAFF_REPORTS_COMPLETE
            if all_reported
            else ExternalSigningState.STAFF_REPORTING
        ),
        resulting_status_version=facts.status_version + 1,
        reported_staff_segment_ids=reported,
        client_reported=False,
        requires_commitment=all_reported,
        create_client_reminder_intent=all_reported,
    )


def reduce_client_completion_report(
    facts: ExternalSigningSessionFacts,
    *,
    expected_document_version_id: int,
    expected_commitment_id: int,
    expected_status_version: int,
) -> ExternalSigningTransition:
    _require_mutable_session(facts)
    _require_current_version(facts, expected_status_version)
    if facts.client_reported:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.CLIENT_REPORT_ALREADY_RECORDED,
            current_version=facts.status_version,
        )
    if (
        facts.state is not ExternalSigningState.STAFF_REPORTS_COMPLETE
        or not facts.all_staff_reported
    ):
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.CLIENT_REPORT_OUT_OF_ORDER,
            current_version=facts.status_version,
        )
    if facts.commitment_id is None:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.COMMITMENT_MISSING,
            current_version=facts.status_version,
        )
    if facts.commitment_id != expected_commitment_id:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.COMMITMENT_STALE,
            current_version=facts.status_version,
        )
    if facts.client_document_version_id != expected_document_version_id:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.CLIENT_DOCUMENT_VERSION_STALE,
            current_version=facts.status_version,
        )
    return ExternalSigningTransition(
        after_state=ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING,
        resulting_status_version=facts.status_version + 1,
        reported_staff_segment_ids=facts.reported_staff_segment_ids,
        client_reported=True,
        create_final_pdf_recovery_task=True,
        contract_completed=False,
    )


def final_signed_contract_blockers(
    facts: ExternalSigningSessionFacts,
) -> tuple[ExternalSigningErrorCode, ...]:
    if facts.state is ExternalSigningState.SUPERSEDED:
        return (ExternalSigningErrorCode.SESSION_SUPERSEDED,)
    if facts.state is ExternalSigningState.COMPLETED:
        return (ExternalSigningErrorCode.FINAL_PDF_ALREADY_APPLIED,)
    blockers: list[ExternalSigningErrorCode] = []
    if not facts.all_staff_reported:
        blockers.append(ExternalSigningErrorCode.STAFF_REPORTS_INCOMPLETE)
    if not facts.client_reported:
        blockers.append(ExternalSigningErrorCode.CLIENT_REPORT_OUT_OF_ORDER)
    if facts.commitment_id is None:
        blockers.append(ExternalSigningErrorCode.COMMITMENT_MISSING)
    if facts.state is not ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING:
        blockers.append(ExternalSigningErrorCode.FINAL_PDF_NOT_PENDING)
    return tuple(blockers)


def _require_mutable_session(facts: ExternalSigningSessionFacts) -> None:
    if facts.state is ExternalSigningState.SUPERSEDED:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.SESSION_SUPERSEDED,
            current_version=facts.status_version,
        )
    if facts.state is ExternalSigningState.COMPLETED:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.SESSION_COMPLETED,
            current_version=facts.status_version,
        )


def _require_current_version(
    facts: ExternalSigningSessionFacts,
    expected_status_version: int,
) -> None:
    require_nonnegative_integer(expected_status_version, "expected status version")
    if expected_status_version != facts.status_version:
        raise ExternalSigningRuleError(
            ExternalSigningErrorCode.STATUS_VERSION_STALE,
            current_version=facts.status_version,
        )


def _validate_session_identity(facts: ExternalSigningSessionFacts) -> None:
    require_canonical_text(facts.session_id, "external signing session ID", 64)
    if _SESSION_ID.fullmatch(facts.session_id) is None:
        raise ValueError("external signing session ID is invalid")
    require_canonical_text(facts.case_no, "case number", 50)
    require_positive_integer(facts.matching_plan_id, "matching plan ID")
    require_sha256_hex(facts.document_set_fingerprint, "document set fingerprint")
    require_canonical_text(
        facts.client_subject_reference,
        "client subject reference",
        191,
    )
    require_positive_integer(
        facts.client_document_version_id,
        "client document version ID",
    )
    if facts.commitment_id is not None:
        require_positive_integer(facts.commitment_id, "commitment ID")
    if not isinstance(facts.client_reported, bool):
        raise TypeError("client reported flag must be boolean")
    if not isinstance(facts.state, ExternalSigningState):
        raise TypeError("external signing state is invalid")
    require_nonnegative_integer(facts.status_version, "external signing status version")


def _validate_staff_targets(facts: ExternalSigningSessionFacts) -> None:
    if not isinstance(facts.staff_targets, tuple) or not facts.staff_targets:
        raise ValueError("external signing requires staff report targets")
    if any(not isinstance(target, StaffSigningReportTarget) for target in facts.staff_targets):
        raise TypeError("staff report targets must be typed")
    required = tuple(target.matching_segment_id for target in facts.staff_targets)
    if required != tuple(sorted(set(required))):
        raise ValueError("staff report targets must be sorted and unique")
    reported = facts.reported_staff_segment_ids
    if (
        not isinstance(reported, tuple)
        or reported != tuple(sorted(set(reported)))
        or not set(reported).issubset(required)
    ):
        raise ValueError("reported staff segments must be a sorted target subset")


def _validate_session_state(facts: ExternalSigningSessionFacts) -> None:
    if facts.state is ExternalSigningState.SUPERSEDED:
        return
    all_reported = facts.all_staff_reported
    if facts.state is ExternalSigningState.STAFF_REPORTING:
        if all_reported or facts.client_reported:
            raise ValueError("staff-reporting state facts are inconsistent")
        return
    if not all_reported or facts.commitment_id is None:
        raise ValueError("post-staff-report state requires all reports and commitment")
    if facts.state is ExternalSigningState.STAFF_REPORTS_COMPLETE:
        if facts.client_reported:
            raise ValueError("staff-reports-complete state cannot contain client report")
        return
    if not facts.client_reported:
        raise ValueError("final-PDF state requires client report")


__all__ = [
    "ExternalSigningErrorCode",
    "ExternalSigningRuleError",
    "ExternalSigningSessionFacts",
    "ExternalSigningState",
    "ExternalSigningTransition",
    "StaffSigningReportTarget",
    "derive_external_signing_session_id",
    "final_signed_contract_blockers",
    "reduce_client_completion_report",
    "reduce_staff_completion_report",
]
