"""
File: test_matching_coordination_repository.py
Description: 驗證 M3 MySQL adapter 的 borrowed transaction、FK 順序與 typed intents。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingPackage,
    MatchingPackageMode,
    RefusalRoutingGroup,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyCaregiverSelection,
    ApplyCustomerMatchingDecision,
    ApplyZeroCandidateAlternative,
    MatchingCriteriaRecontactIntentProjection,
    MatchingNotificationIntentProjection,
    MatchingNotificationRecipientRole,
    PreviewZeroCandidateAlternative,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
    MatchingCoordinationWorkflow,
)
from domains.scheduling.matching_coordination import build_criteria_snapshot


try:
    from infrastructure.mysql import matching_coordination_repository as _repository_module
    from infrastructure.mysql.matching_coordination_repository import (
        MySqlMatchingCoordinationRepository,
    )
except ImportError:  # The repository lane may land after this red-first test.
    _repository_module = None  # type: ignore[assignment]
    MySqlMatchingCoordinationRepository = None  # type: ignore[assignment,misc]


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection
        self.rowcount = 1
        self.lastrowid = 100 + len(connection.statements)
        self._row: object = None

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, sql: str, params=()) -> None:
        self.connection.statements.append((sql, params))
        if sql.lstrip().upper().startswith("SELECT"):
            self._row = self.connection.rows.pop(0) if self.connection.rows else None
        else:
            self._row = None

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._row if isinstance(self._row, list) else []


class _Connection:
    def __init__(self, rows=()) -> None:
        self.rows = list(rows)
        self.statements: list[tuple[str, object]] = []
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return _Cursor(self)


def _repo(connection: _Connection):
    if MySqlMatchingCoordinationRepository is None:
        pytest.fail("repository implementation is not present yet")
    return MySqlMatchingCoordinationRepository(
        connection,
        FixedBusinessClock(datetime(2026, 8, 22, tzinfo=timezone.utc)),
    )


def _sources(seed: str = "c") -> tuple[MatchingSourceVersion, ...]:
    return tuple(MatchingSourceVersion(kind, f"{kind}:1", 1, seed * 64) for kind in SOURCE_KINDS)


def _facts(*, no_candidate: bool = False) -> MatchingCoordinationFacts:
    sources = _sources()
    snapshot = build_criteria_snapshot(
        snapshot_id="snapshot-1",
        case_no="CASE-001",
        criteria_version=1,
        criteria={"service_days": 2},
        source_versions=sources,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    candidate = MatchingCandidateResult(
        "candidate-1",
        7,
        CandidateEligibility.INELIGIBLE if no_candidate else CandidateEligibility.ELIGIBLE,
        (),
        willingness="willing",
    )
    package = MatchingPackage(
        package_id="package-1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (date(2026, 9, 1), date(2026, 9, 2)), 1),),
        required_service_dates=(date(2026, 9, 1), date(2026, 9, 2)),
        candidate_results=(candidate,),
        criteria_snapshot_id=snapshot.snapshot_id,
        source_versions=sources,
    )
    return MatchingCoordinationFacts(
        snapshot=snapshot,
        package=package,
        candidates=(candidate,),
        source_versions=sources,
    )


def _command(facts: MatchingCoordinationFacts, key: str = "matching:case-001:1"):
    return ApplyCustomerMatchingDecision(
        case_no="CASE-001",
        actor=ActorContext("admin_user_id:1"),
        reason="matching review",
        correlation_id=CorrelationId("corr-matching-1"),
        idempotency_key=IdempotencyKey(key),
        expected_source_versions=facts.source_versions,
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )


def _accepted_receipt(facts: MatchingCoordinationFacts):
    command = _command(facts)
    receipt = MatchingCoordinationWorkflow().apply(
        command, facts, preview_fingerprint=facts.package.fingerprint
    )
    assert receipt.cross_domain_request is not None
    event_id = receipt.decision_event_id
    assert event_id is not None
    intents = tuple(
        MatchingNotificationIntentProjection(
            intent_id=f"{event_id}:line:{role.value}",
            recipient_role=role,
            recipient_subject_reference=(
                "customer:CASE-001" if role is MatchingNotificationRecipientRole.CUSTOMER else "staff:7"
            ),
            source_decision_event_id=event_id,
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            package_version=1,
            package_fingerprint=facts.package.fingerprint,
            candidate_id="candidate-1",
            idempotency_key=IdempotencyKey(f"matching:line:{role.value}:1"),
        )
        for role in (
            MatchingNotificationRecipientRole.CUSTOMER,
            MatchingNotificationRecipientRole.CAREGIVER,
        )
    )
    return command, replace(
        receipt,
        outbox_intent_ids=(
            receipt.cross_domain_request.request_id,
            *(item.intent_id for item in intents),
        ),
        notification_intents=intents,
    )


def _receipt_row(facts: MatchingCoordinationFacts, command, receipt):
    return {
        "receipt_id": receipt.receipt_id,
        "case_no": command.case_no,
        "event_id": 501,
        "criteria_snapshot_id": 601,
        "package_lineage_id": 701,
        "command_name": command.command_name.value,
        "idempotency_key": command.idempotency_key.value,
        "command_fingerprint": receipt.command_fingerprint.value,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "source_version_tuple": json.dumps([item.as_payload() for item in facts.source_versions]),
        "result_snapshot": json.dumps(_repository_module._receipt_payload(receipt)),
        "outcome_state": "applied",
        "actor_ref": command.actor.actor_id,
        "correlation_id": command.correlation_id.value,
        "applied_at_utc": datetime(2026, 8, 22, tzinfo=timezone.utc),
}


def _lineage_rows() -> list[object]:
    """Rows consumed by the repository's deterministic SELECT sequence."""

    return [None, None, None, {"id": 601}, None]


def test_claim_none_locks_receipt_key_without_commit() -> None:
    connection = _Connection([None])
    repository = _repo(connection)
    key = IdempotencyKey("matching:claim:none")
    fingerprint = fingerprint_payload({"command": "none"})

    assert repository.claim_or_replay(key, fingerprint, CorrelationId("corr-1")) is None
    sql = connection.statements[0][0].upper()
    assert "MATCHING_COORDINATION_APPLY_RECEIPTS" in sql
    assert "FOR UPDATE" in sql
    assert connection.commit_count == 0


def test_zero_candidate_agree_projects_only_orders_owner_intent() -> None:
    facts = _facts(no_candidate=True)
    alternative = MatchingCoordinationWorkflow().preview(
        PreviewZeroCandidateAlternative(
            case_no="CASE-001",
            actor=ActorContext("admin_user_id:1"),
            reason="no candidate preview",
            correlation_id=CorrelationId("corr-zero-preview-agree"),
            idempotency_key=IdempotencyKey("preview:matching:zero:agree"),
            expected_source_versions=facts.source_versions,
            criteria_snapshot_id="snapshot-1",
            policy_id="policy-v1",
            policy_version=1,
            relaxed_criteria=("service_days",),
        ),
        facts,
    )
    command = ApplyZeroCandidateAlternative(
        case_no="CASE-001",
        actor=ActorContext("admin_user_id:1"),
        reason="accept explicit compromise",
        correlation_id=CorrelationId("corr-zero-agree"),
        idempotency_key=IdempotencyKey("matching:zero:agree"),
        expected_source_versions=facts.source_versions,
        criteria_snapshot_id="snapshot-1",
        alternative_id=alternative.alternative_id,
        policy_id="policy-v1",
        policy_version=1,
        relaxed_criteria=("service_days",),
        preview_fingerprint=alternative.preview_fingerprint,
        decision="agree",
    )
    receipt = MatchingCoordinationWorkflow().apply(
        command,
        facts,
        preview_fingerprint=alternative.preview_fingerprint,
    )

    replay = _repository_module._receipt_from_payload(
        _repository_module._receipt_payload(receipt)
    )
    payloads = _repository_module._intent_payloads(command, replay)

    assert replay.outbox_intent_ids == ("matching:zero:agree:zero-candidate:orders",)
    assert len(payloads) == 1
    assert payloads[0][0:3] == (
        "matching:zero:agree:zero-candidate:orders",
        "orders_terms_update_requested",
        "orders_workflow",
    )


def test_current_snapshot_round_trips_typed_bytes_and_optional_lock() -> None:
    facts = _facts()
    snapshot = facts.snapshot
    connection = _Connection(
        [
            {
                "snapshot_id": snapshot.snapshot_id,
                "case_no": snapshot.case_no,
                "criteria_version": snapshot.criteria_version,
                "criteria_snapshot": json.dumps(dict(snapshot.criteria)),
                "source_version_tuple": json.dumps(
                    _repository_module._source_payload(snapshot.source_versions)
                ),
                "criteria_digest": snapshot.fingerprint.value,
                "occurred_at_utc": datetime(2026, 8, 21),
            }
        ]
    )

    loaded = _repo(connection).load_current_snapshot("CASE-001", for_update=True)

    assert loaded == snapshot
    assert "FOR UPDATE" in connection.statements[0][0].upper()
    assert connection.commit_count == 0


def test_snapshot_history_round_trips_in_ascending_version_order() -> None:
    snapshot = _facts().snapshot
    rows = [
        {
            "snapshot_id": snapshot.snapshot_id,
            "case_no": snapshot.case_no,
            "criteria_version": snapshot.criteria_version,
            "criteria_snapshot": json.dumps(dict(snapshot.criteria)),
            "source_version_tuple": json.dumps(
                _repository_module._source_payload(snapshot.source_versions)
            ),
            "criteria_digest": snapshot.fingerprint.value,
            "occurred_at_utc": datetime(2026, 8, 21),
        }
    ]
    connection = _Connection([rows])

    loaded = _repo(connection).load_snapshot_history("CASE-001")

    assert loaded == (snapshot,)
    assert "ORDER BY CRITERIA_VERSION ASC" in connection.statements[0][0].upper()
    assert "FOR UPDATE" not in connection.statements[0][0].upper()
    assert connection.commit_count == 0


def test_snapshot_history_rejects_missing_lineage() -> None:
    connection = _Connection([[]])

    with pytest.raises(
        _repository_module.MatchingCoordinationPersistenceError,
        match="history missing",
    ):
        _repo(connection).load_snapshot_history("CASE-001")


def test_willingness_history_reads_only_typed_m3_event_payload() -> None:
    facts = _facts()
    assert facts.package is not None
    facts = replace(
        facts,
        candidates=(replace(facts.candidates[0], willingness="pending"),),
    )
    command = ApplyCaregiverSelection(
        case_no="CASE-001",
        actor=ActorContext("admin_user_id:1"),
        reason="record caregiver confirmation",
        correlation_id=CorrelationId("corr-willingness-1"),
        idempotency_key=IdempotencyKey("matching:willingness:1"),
        expected_source_versions=facts.source_versions,
        criteria_snapshot_id=facts.snapshot.snapshot_id,
        package_id=facts.package.package_id,
        package_version=facts.package.version,
        candidate_id="candidate-1",
        willingness="willing",
        reason_code=None,
        affected_criteria=(),
        preview_fingerprint=facts.package.fingerprint,
    )
    receipt = MatchingCoordinationWorkflow().apply(
        command,
        facts,
        preview_fingerprint=facts.package.fingerprint,
    )
    assert receipt.willingness_lineage is not None
    connection = _Connection(
        [[{
            "event_id": receipt.willingness_lineage.event_id,
            "event_payload": json.dumps(_repository_module._receipt_payload(receipt)),
        }]]
    )

    history = _repo(connection).load_willingness_history("CASE-001")

    assert history == (receipt.willingness_lineage,)
    assert "CAREGIVER_WILLINGNESS" in connection.statements[0][0].upper()
    assert connection.commit_count == 0


def test_willingness_history_rejects_malformed_receipt_as_typed_error() -> None:
    connection = _Connection(
        [
            [
                {
                    "event_id": "event-malformed",
                    "event_payload": json.dumps({"receipt_id": "receipt-malformed"}),
                }
            ]
        ]
    )

    with pytest.raises(
        _repository_module.MatchingCoordinationPersistenceError,
        match="receipt payload is invalid",
    ):
        _repo(connection).load_willingness_history("CASE-001")
    assert connection.commit_count == 0


def test_current_package_round_trips_typed_bytes_without_commit() -> None:
    package = _facts().package
    assert package is not None
    connection = _Connection(
        [
            {
                "package_snapshot": _repository_module._json_dump(package),
                "package_digest": package.fingerprint.value,
            }
        ]
    )

    loaded = _repo(connection).load_current_package("CASE-001")

    assert loaded == package
    assert "FOR UPDATE" not in connection.statements[0][0].upper()
    assert connection.commit_count == 0


def test_current_package_rejects_digest_drift_without_commit() -> None:
    package = _facts().package
    assert package is not None
    connection = _Connection(
        [
            {
                "package_snapshot": _repository_module._json_dump(package),
                "package_digest": "f" * 64,
            }
        ]
    )

    with pytest.raises(
        _repository_module.MatchingCoordinationPersistenceError,
        match="package digest drift",
    ):
        _repo(connection).load_current_package("CASE-001")
    assert connection.commit_count == 0


def test_current_package_absence_is_explicit_none() -> None:
    connection = _Connection([None])

    assert _repo(connection).load_current_package("CASE-001") is None
    assert connection.commit_count == 0


def test_claim_exact_replay_returns_typed_receipt() -> None:
    facts = _facts()
    command, receipt = _accepted_receipt(facts)
    connection = _Connection([_receipt_row(facts, command, receipt)])
    repository = _repo(connection)

    replay = repository.claim_or_replay(
        command.idempotency_key,
        receipt.command_fingerprint,
        command.correlation_id,
    )

    assert replay is not None
    assert replay.receipt_id == receipt.receipt_id
    assert connection.commit_count == 0


def test_criteria_recontact_intent_round_trips_exact_receipt_and_outbox_payload() -> None:
    facts = _facts()
    command, receipt = _accepted_receipt(facts)
    intent = MatchingCriteriaRecontactIntentProjection(
        intent_id="matching:case-001:resend:criteria-resend:candidate-1",
        recipient_subject_reference="staff:7",
        candidate_id="candidate-1",
        staff_id=7,
        route_group=RefusalRoutingGroup.GROUP1_ORIGINAL_WILLING_RECONFIRM,
        action="reconfirm",
        reason_code="willingness_unconfirmed",
        before_snapshot_id="snapshot-before",
        after_snapshot_id="snapshot-1",
        diff_fingerprint=fingerprint_payload({"diff": "region"}),
        source_versions=facts.source_versions,
        idempotency_key=command.idempotency_key,
        package_id=facts.package.package_id,
        package_version=facts.package.version,
        package_fingerprint=facts.package.fingerprint,
    )
    receipt = replace(
        receipt,
        cross_domain_request=None,
        notification_intents=(),
        outbox_intent_ids=(intent.intent_id,),
        criteria_recontact_intents=(intent,),
    )

    replay = _repository_module._receipt_from_payload(
        _repository_module._receipt_payload(receipt)
    )
    assert replay == receipt
    payloads = _repository_module._intent_payloads(command, receipt)
    assert len(payloads) == 1
    assert payloads[0][0:3] == (
        intent.intent_id,
        "line_criteria_diff_resend",
        "line_integration",
    )
    assert payloads[0][3]["route_group"] == intent.route_group.value
    assert payloads[0][3]["before_snapshot_id"] == "snapshot-before"
    assert payloads[0][3]["after_snapshot_id"] == "snapshot-1"
    assert payloads[0][3]["diff_fingerprint"] == intent.diff_fingerprint.value


def test_claim_same_key_different_fingerprint_is_typed_conflict() -> None:
    facts = _facts()
    command, receipt = _accepted_receipt(facts)
    connection = _Connection([_receipt_row(facts, command, receipt)])
    repository = _repo(connection)

    with pytest.raises(Exception) as captured:
        repository.claim_or_replay(
            command.idempotency_key,
            fingerprint_payload({"command": "different"}),
            command.correlation_id,
        )

    assert getattr(captured.value, "error").code == "matching_idempotency_conflict"
    assert connection.commit_count == 0


def test_lock_matching_root_uses_m3_for_update_and_never_commits() -> None:
    connection = _Connection()
    repository = _repo(connection)

    repository.lock_matching_root("CASE-001")

    sql = connection.statements[0][0].upper()
    assert "FOR UPDATE" in sql
    assert "MATCHING_COORDINATION_" in sql
    assert not any(root in sql for root in ("ORDERS", "ASSIGNMENT", "LEAVE", "PAYROLL"))
    assert connection.commit_count == 0


def test_accepted_lineage_receipt_then_three_immutable_intents_without_commit() -> None:
    facts = _facts()
    command, receipt = _accepted_receipt(facts)
    connection = _Connection(
        _lineage_rows()
        + [{"id": 701, "criteria_snapshot_id": 601, "package_lineage_id": 801}]
        + [{"id": 701}, {"id": 901}]
    )
    repository = _repo(connection)

    repository.append_lineage(command, facts, receipt)
    repository.save_receipt(command, receipt.command_fingerprint, receipt)
    repository.append_typed_intents(command, receipt)

    sqls = [statement.upper() for statement, _ in connection.statements]
    receipt_index = next(index for index, sql in enumerate(sqls) if "APPLY_RECEIPTS" in sql and "INSERT" in sql)
    intent_indices = [index for index, sql in enumerate(sqls) if "OUTBOX" in sql and "INSERT" in sql]
    assert intent_indices and receipt_index < min(intent_indices)
    assert len(intent_indices) == 3
    assert connection.commit_count == 0
    assert not any("LINE" in sql and "HTTP" in sql for sql in sqls)


def test_zero_candidate_disagree_writes_no_intents() -> None:
    facts = _facts(no_candidate=True)
    alternative = MatchingCoordinationWorkflow().preview(
        PreviewZeroCandidateAlternative(
            case_no="CASE-001",
            actor=ActorContext("admin_user_id:1"),
            reason="no candidate preview",
            correlation_id=CorrelationId("corr-zero-preview-1"),
            idempotency_key=IdempotencyKey("preview:matching:zero:1"),
            expected_source_versions=facts.source_versions,
            criteria_snapshot_id="snapshot-1",
            policy_id="policy-v1",
            policy_version=1,
            relaxed_criteria=("service_days",),
        ),
        facts,
    )
    command = ApplyZeroCandidateAlternative(
        case_no="CASE-001",
        actor=ActorContext("admin_user_id:1"),
        reason="no candidate review",
        correlation_id=CorrelationId("corr-zero-1"),
        idempotency_key=IdempotencyKey("matching:zero:1"),
        expected_source_versions=facts.source_versions,
        criteria_snapshot_id="snapshot-1",
        alternative_id=alternative.alternative_id,
        policy_id="policy-v1",
        policy_version=1,
        relaxed_criteria=("service_days",),
        preview_fingerprint=alternative.preview_fingerprint,
        decision="disagree",
    )
    receipt = MatchingCoordinationWorkflow().apply(
        command, facts, preview_fingerprint=alternative.preview_fingerprint
    )
    connection = _Connection(
        _lineage_rows()
        + [{"id": 701, "criteria_snapshot_id": 601, "package_lineage_id": 801}]
    )
    repository = _repo(connection)

    repository.append_lineage(command, facts, receipt)
    repository.save_receipt(command, receipt.command_fingerprint, receipt)
    repository.append_typed_intents(command, receipt)

    assert not any("OUTBOX" in statement.upper() for statement, _ in connection.statements)
    assert connection.commit_count == 0
