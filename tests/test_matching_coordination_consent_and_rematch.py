"""File: test_matching_coordination_consent_and_rematch.py
Description: 驗證 criteria resend 的 typed consent、fresh fingerprint 與收件者邊界。
"""

from datetime import datetime, timezone

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingSourceVersion,
    RefusalHistoryEntry,
    SOURCE_KINDS,
    build_criteria_snapshot,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyCriteriaDiffResend,
    PreviewCriteriaDiffResend,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
    MatchingCoordinationWorkflow,
    MatchingCoordinationWorkflowError,
)


def _sources() -> tuple[MatchingSourceVersion, ...]:
    return tuple(
        MatchingSourceVersion(kind, f"{kind}:1", 1, "a" * 64)
        for kind in SOURCE_KINDS
    )


def _facts() -> MatchingCoordinationFacts:
    sources = _sources()
    before = build_criteria_snapshot(
        snapshot_id="snapshot-before",
        case_no="CASE-001",
        criteria_version=1,
        criteria={"region": "east"},
        source_versions=sources,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    after = build_criteria_snapshot(
        snapshot_id="snapshot-after",
        case_no="CASE-001",
        criteria_version=2,
        criteria={"region": "west"},
        source_versions=sources,
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    candidate = MatchingCandidateResult(
        "candidate-g2",
        7,
        CandidateEligibility.ELIGIBLE,
        (),
        willingness="unwilling",
    )
    refusal = RefusalHistoryEntry(
        "refusal-g2",
        "candidate-g2",
        before.snapshot_id,
        "region_mismatch",
        ("region",),
        pain_resolved=True,
    )
    return MatchingCoordinationFacts(
        snapshot=after,
        package=None,
        candidates=(candidate,),
        source_versions=sources,
        criteria_snapshots=(before,),
        refusal_history=(refusal,),
        willingness_lineage=(),
    )


def _common() -> dict[str, object]:
    return {
        "case_no": "CASE-001",
        "actor": ActorContext("admin_user_id:1"),
        "reason": "criteria recontact",
        "correlation_id": CorrelationId("corr-criteria-resend-1"),
        "idempotency_key": IdempotencyKey("matching:case-001:resend"),
        "expected_source_versions": _sources(),
    }


def test_criteria_resend_uses_preview_fingerprint_and_deterministic_outbox() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    preview = workflow.preview(
        PreviewCriteriaDiffResend(
            **_common(),
            before_snapshot_id="snapshot-before",
            after_snapshot_id="snapshot-after",
        ),
        facts,
    )

    result = workflow.apply(
        ApplyCriteriaDiffResend(
            **_common(),
            before_snapshot_id="snapshot-before",
            after_snapshot_id="snapshot-after",
            preview_fingerprint=preview.diff_fingerprint,
            recipient_ids=("candidate-g2",),
        ),
        facts,
        preview_fingerprint=preview.diff_fingerprint,
    )

    assert result.result_state == "intent_queued"
    assert result.outbox_intent_ids == (
        "matching:case-001:resend:criteria-resend:candidate-g2",
    )
    assert result.cross_domain_request is None
    assert len(result.criteria_recontact_intents) == 1
    intent = result.criteria_recontact_intents[0]
    assert intent.intent_id == result.outbox_intent_ids[0]
    assert intent.recipient_subject_reference == "staff:7"
    assert intent.candidate_id == "candidate-g2"
    assert intent.route_group.value == "group2_pain_resolved_reprobe"
    assert intent.action == "reprobe"
    assert intent.reason_code == "region_mismatch"
    assert intent.before_snapshot_id == "snapshot-before"
    assert intent.after_snapshot_id == "snapshot-after"
    assert intent.diff_fingerprint == preview.diff_fingerprint
    assert intent.source_versions == facts.source_versions
    assert intent.package_id is None


def test_criteria_resend_rejects_same_stale_fingerprint_in_request_and_argument() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    stale = PreviewFingerprint("b" * 64)

    with pytest.raises(MatchingCoordinationWorkflowError) as captured:
        workflow.apply(
            ApplyCriteriaDiffResend(
                **_common(),
                before_snapshot_id="snapshot-before",
                after_snapshot_id="snapshot-after",
                preview_fingerprint=stale,
                recipient_ids=("candidate-g2",),
            ),
            facts,
            preview_fingerprint=stale,
        )

    assert captured.value.error.code == "matching_recontact_source_stale"


@pytest.mark.parametrize(
    "recipient_ids",
    (("candidate-unknown",), ("candidate-g2", "candidate-g2")),
)
def test_criteria_resend_rejects_unknown_or_non_unique_recipients(recipient_ids) -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    preview_fingerprint = MatchingCoordinationWorkflow().preview(
        PreviewCriteriaDiffResend(
            **_common(),
            before_snapshot_id="snapshot-before",
            after_snapshot_id="snapshot-after",
        ),
        facts,
    ).diff_fingerprint

    with pytest.raises(MatchingCoordinationWorkflowError) as captured:
        workflow.apply(
            ApplyCriteriaDiffResend(
                **_common(),
                before_snapshot_id="snapshot-before",
                after_snapshot_id="snapshot-after",
                preview_fingerprint=preview_fingerprint,
                recipient_ids=recipient_ids,
            ),
            facts,
            preview_fingerprint=preview_fingerprint,
        )

    assert captured.value.error.code == "matching_recontact_source_stale"
