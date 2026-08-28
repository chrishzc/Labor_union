"""
File: matching_coordination.py
Description: 提供 M3 typed Query／Preview／Apply API，不寫 owner 根事實或呼叫 provider。
"""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.matching_coordination import (
    MatchingCoordinationComposition,
    get_matching_coordination_composition,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.matching_coordination import (
    ApplyInitialCriteriaRequest,
    ApplyLeaveImpactRequest,
    ApplyCriteriaDiffRequest,
    ApplyCaregiverSelectionRequest,
    ApplyCustomerDecisionRequest,
    ApplyZeroCandidateRequest,
    ApplyZeroCandidateConfirmationRequest,
    CriteriaDiffTransportView,
    MatchingApplyReceiptResponse,
    MatchingCoordinationQueryRequest,
    MatchingCoordinationQueryResponse,
    MatchingCriteriaSnapshotView,
    MatchingPackageTransportView,
    PreviewInitialCriteriaRequest,
    PreviewLeaveImpactRequest,
    LeaveImpactPreviewResponse,
    PreviewCriteriaDiffRequest,
    PreviewMatchingPackageRequest,
    PreviewRematchRequest,
    ApplyRematchRequest,
    ApplyServiceDateRematchRequest,
    PreviewServiceDateRematchRequest,
    ServiceDateRematchPreviewResponse,
    ServiceDateShiftAvailabilityConfirmationTransportView,
    ServiceDateShiftReassignmentReferenceTransportView,
    PreviewZeroCandidateRequest,
    PreviewZeroCandidateConfirmationRequest,
    ZeroCandidateAlternativeTransportView,
)
from domains.scheduling.matching_coordination import (
    MatchingSegment,
    MatchingSourceVersion,
    canonical_source_tuple,
)
from infrastructure.mysql.matching_coordination_facts_adapter import (
    MatchingCoordinationFactsAdapterError,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.matching_coordination_application import (
    MatchingApplicationError,
)
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyInitialCriteriaSnapshot,
    ApplyLeaveImpactOnMatching,
    ApplyCriteriaDiffResend,
    ApplyCaregiverSelection,
    ApplyCustomerMatchingDecision,
    ApplyZeroCandidateAlternative,
    ApplyZeroCandidateConfirmation,
    PreviewCriteriaDiffResend,
    PreviewLeaveImpactOnMatching,
    PreviewMatchingPackage,
    PreviewRematch,
    PreviewServiceDateChangeRematch,
    ApplyRematch,
    ApplyServiceDateChangeRematch,
    PreviewZeroCandidateAlternative,
    PreviewZeroCandidateConfirmation,
    PreviewInitialCriteriaSnapshot,
    QueryMatchingCoordination,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationWorkflowError,
    ServiceDateShiftAvailabilityConfirmation,
)
from subsystems.scheduling.matching_leave_integration import (
    MatchingLeaveImpactRequest,
    MatchingLeaveIntegrationError,
)


router = APIRouter(
    prefix="/api/v1/matching-coordination",
    tags=["Scheduling Matching Coordination"],
)


@router.post(
    "/{case_no}/query",
    response_model=BaseResponse[MatchingCoordinationQueryResponse],
)
def query_matching_coordination(
    body: MatchingCoordinationQueryRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = QueryMatchingCoordination(
        case_no=case_no,
        actor=_actor(principal),
        correlation_id=correlation,
        expected_source_versions=(
            None
            if body.expected_source_versions is None
            else _source_tuple(body.expected_source_versions)
        ),
    )
    try:
        result = composition.application.query(command)
        return BaseResponse(
            data=MatchingCoordinationQueryResponse.model_validate(result)
        )
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/initial-criteria",
    response_model=BaseResponse[MatchingCriteriaSnapshotView],
)
def preview_initial_criteria(
    body: PreviewInitialCriteriaRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewInitialCriteriaSnapshot(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:" + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=(
            None
            if body.expected_source_versions is None
            else _source_tuple(body.expected_source_versions)
        ),
    )
    try:
        result = composition.application.preview(command)
        return BaseResponse(data=MatchingCriteriaSnapshotView.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/package",
    response_model=BaseResponse[MatchingPackageTransportView],
)
def preview_matching_package(
    body: PreviewMatchingPackageRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewMatchingPackage(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        required_service_dates=body.required_service_dates,
        segments=tuple(
            MatchingSegment(item.staff_id, item.service_dates, item.sequence)
            for item in body.segments
        ),
    )
    try:
        result = composition.application.preview(command)
        return BaseResponse(data=MatchingPackageTransportView.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/criteria-diff",
    response_model=BaseResponse[CriteriaDiffTransportView],
)
def preview_criteria_diff(
    body: PreviewCriteriaDiffRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewCriteriaDiffResend(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        before_snapshot_id=body.before_snapshot_id,
        after_snapshot_id=body.after_snapshot_id,
    )
    try:
        result = composition.application.preview(command)
        return BaseResponse(data=CriteriaDiffTransportView.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/zero-candidate",
    response_model=BaseResponse[ZeroCandidateAlternativeTransportView],
)
def preview_zero_candidate_alternative(
    body: PreviewZeroCandidateRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewZeroCandidateAlternative(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        policy_id=body.policy_id,
        policy_version=body.policy_version,
        relaxed_criteria=body.relaxed_criteria,
    )
    try:
        result = composition.application.preview(command)
        return BaseResponse(
            data=ZeroCandidateAlternativeTransportView.model_validate(result)
        )
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/confirm-zero-candidate",
    response_model=BaseResponse[MatchingPackageTransportView],
)
def preview_zero_candidate_confirmation(
    body: PreviewZeroCandidateConfirmationRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewZeroCandidateConfirmation(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
        package_version=body.package_version,
        evidence=body.evidence,
    )
    try:
        result = composition.application.preview(command)
        return BaseResponse(data=MatchingPackageTransportView.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/rematch",
    response_model=BaseResponse[MatchingPackageTransportView],
)
def preview_rematch(
    body: PreviewRematchRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewRematch(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
    )
    try:
        result = composition.application.preview(command)
        return BaseResponse(data=MatchingPackageTransportView.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/leave-impact",
    response_model=BaseResponse[LeaveImpactPreviewResponse],
)
def preview_leave_impact(
    body: PreviewLeaveImpactRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    expected_sources = _source_tuple(body.expected_source_versions)
    command = PreviewLeaveImpactOnMatching(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {
                    "case_no": case_no,
                    "receipt_key": body.receipt_key,
                    "correlation_id": correlation.value,
                }
            ).value
        ),
        expected_source_versions=expected_sources,
        package_id=body.package_id,
        leave_reference=body.receipt_key,
    )
    request = MatchingLeaveImpactRequest(
        receipt_key=body.receipt_key,
        case_no=case_no,
        package_id=body.package_id,
        criteria_snapshot_id=body.criteria_snapshot_id,
        expected_leave_version=body.expected_leave_version,
        original_staff_id=body.original_staff_id,
        expected_source_versions=expected_sources,
        correlation_id=correlation,
    )
    try:
        result = composition.application.preview_leave_impact(command, request)
        return BaseResponse(data=LeaveImpactPreviewResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/preview/service-date-rematch",
    response_model=BaseResponse[ServiceDateRematchPreviewResponse],
)
def preview_service_date_rematch(
    body: PreviewServiceDateRematchRequest,
    case_no: str = Path(min_length=1, max_length=50),
    correlation_header: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header or uuid4().hex)
    command = PreviewServiceDateChangeRematch(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(
            "preview:"
            + fingerprint_payload(
                {"case_no": case_no, "correlation_id": correlation.value}
            ).value
        ),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        assignment_id=body.assignment_id,
        original_staff_id=body.original_staff_id,
        original_service_dates=body.original_service_dates,
        shifted_service_dates=body.shifted_service_dates,
        package_id=body.package_id,
    )
    try:
        result = composition.application.preview_service_date_rematch(command)
        if isinstance(result, ServiceDateShiftAvailabilityConfirmation):
            response = ServiceDateRematchPreviewResponse(
                outcome_kind="availability_confirmation",
                availability_confirmation=(
                    ServiceDateShiftAvailabilityConfirmationTransportView.model_validate(
                        result
                    )
                ),
            )
        else:
            response = ServiceDateRematchPreviewResponse(
                outcome_kind="reassignment_reference",
                reassignment_reference=(
                    ServiceDateShiftReassignmentReferenceTransportView.model_validate(
                        result
                    )
                ),
            )
        return BaseResponse(data=response)
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/leave-impact",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_leave_impact(
    body: ApplyLeaveImpactRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyLeaveImpactOnMatching(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        package_id=body.package_id,
        leave_reference=body.leave_reference,
        criteria_snapshot_id=body.criteria_snapshot_id,
        expected_leave_version=body.expected_leave_version,
        original_staff_id=body.original_staff_id,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/service-date-rematch",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_service_date_rematch(
    body: ApplyServiceDateRematchRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyServiceDateChangeRematch(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
        assignment_id=body.assignment_id,
        original_staff_id=body.original_staff_id,
        original_service_dates=body.original_service_dates,
        shifted_service_dates=body.shifted_service_dates,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/rematch",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_rematch(
    body: ApplyRematchRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyRematch(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/initial-criteria",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_initial_criteria(
    body: ApplyInitialCriteriaRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyInitialCriteriaSnapshot(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/criteria-diff",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_criteria_diff(
    body: ApplyCriteriaDiffRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyCriteriaDiffResend(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        before_snapshot_id=body.before_snapshot_id,
        after_snapshot_id=body.after_snapshot_id,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
        recipient_ids=body.recipient_ids,
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/caregiver-selection",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_caregiver_selection(
    body: ApplyCaregiverSelectionRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyCaregiverSelection(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
        package_version=body.package_version,
        candidate_id=body.candidate_id,
        willingness=body.willingness,
        reason_code=body.reason_code,
        affected_criteria=body.affected_criteria,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/customer-decision",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_customer_decision(
    body: ApplyCustomerDecisionRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyCustomerMatchingDecision(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
        package_version=body.package_version,
        candidate_id=body.candidate_id,
        decision=body.decision,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/zero-candidate",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_zero_candidate_alternative(
    body: ApplyZeroCandidateRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyZeroCandidateAlternative(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        alternative_id=body.alternative_id,
        policy_id=body.policy_id,
        policy_version=body.policy_version,
        relaxed_criteria=body.relaxed_criteria,
        decision=body.decision,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


@router.post(
    "/{case_no}/apply/confirm-zero-candidate",
    response_model=BaseResponse[MatchingApplyReceiptResponse],
)
def apply_zero_candidate_confirmation(
    body: ApplyZeroCandidateConfirmationRequest,
    idempotency_header: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
    ],
    correlation_header: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
    ],
    case_no: Annotated[str, Path(min_length=1, max_length=50)],
    principal: AdminPrincipal = Depends(require_system_admin),
    composition: MatchingCoordinationComposition = Depends(
        get_matching_coordination_composition
    ),
):
    correlation = CorrelationId(correlation_header)
    command = ApplyZeroCandidateConfirmation(
        case_no=case_no,
        actor=_actor(principal),
        reason=body.reason,
        correlation_id=correlation,
        idempotency_key=IdempotencyKey(idempotency_header),
        expected_source_versions=_source_tuple(body.expected_source_versions),
        criteria_snapshot_id=body.criteria_snapshot_id,
        package_id=body.package_id,
        package_version=body.package_version,
        evidence=body.evidence,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
    )
    try:
        result = composition.application.apply(command)
        return BaseResponse(data=MatchingApplyReceiptResponse.model_validate(result))
    except Exception as error:
        _raise_matching_error(error, correlation)


def _source_tuple(view):
    return canonical_source_tuple(
        tuple(
            MatchingSourceVersion(
                item.source_kind,
                item.source_id,
                item.version,
                item.fingerprint,
            )
            for item in view.items
        )
    )


def _actor(principal: AdminPrincipal) -> ActorContext:
    return ActorContext(str(principal.username or "").strip())


def _raise_matching_error(error: Exception, correlation: CorrelationId) -> None:
    if isinstance(
        error,
        (
            MatchingApplicationError,
            MatchingCoordinationWorkflowError,
            MatchingLeaveIntegrationError,
        ),
    ):
        typed = error.error
        raise typed_http_error(
            409,
            typed.category.value,
            typed.code,
            typed.message,
            correlation.value,
            retryable=typed.retryable,
        ) from error
    if isinstance(error, MatchingCoordinationFactsAdapterError):
        raise typed_http_error(
            409,
            "domain_blocked",
            "matching_criteria_source_stale",
            str(error),
            correlation.value,
        ) from error
    if isinstance(error, (TypeError, ValueError)):
        raise typed_http_error(
            422,
            "validation",
            "matching_criteria_invalid",
            "matching criteria request is invalid",
            correlation.value,
        ) from error
    raise error


__all__ = ["router"]
