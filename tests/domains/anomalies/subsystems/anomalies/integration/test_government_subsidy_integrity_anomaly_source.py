"""
File: test_government_subsidy_integrity_anomaly_source.py
Description: 驗證 GOVSUB-003 只在 current revision 完整無 blocker 時解除。
"""

from subsystems.anomalies.government_subsidy_integrity_anomaly_source import (
    GovernmentSubsidyIntegrityRootFact,
    build_integrity_alert_requests,
)


def test_current_revision_with_integrity_blocker_stays_active() -> None:
    requests = build_integrity_alert_requests(
        _root_fact(("outstanding_projection_mismatch",))
    )

    assert len(requests) == 1
    assert requests[0].desired.active is True
    assert requests[0].display_snapshot["integrity_blockers"] == (
        "outstanding_projection_mismatch",
    )


def test_current_revision_resolves_only_when_all_integrity_blockers_are_clear() -> None:
    request = build_integrity_alert_requests(_root_fact(()))[0]

    assert request.desired.active is False
    assert request.display_snapshot["integrity_blockers"] == ()


def test_prior_revision_is_replaced_but_current_blocked_revision_remains_active() -> None:
    requests = build_integrity_alert_requests(
        _root_fact(
            ("transaction_allocation_total_mismatch",),
            previous_revisions=(1,),
        )
    )

    assert [
        (request.display_snapshot["integrity_revision"], request.desired.active)
        for request in requests
    ] == [(1, False), (2, True)]


def _root_fact(blockers, *, previous_revisions=()):
    return GovernmentSubsidyIntegrityRootFact(
        batch_id=7,
        integrity_revision=2,
        integrity_blockers=blockers,
        previous_integrity_revisions=previous_revisions,
        source_version=9,
        source_event_identity="government-integrity:test",
    )
