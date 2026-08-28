"""
File: matching_coordination_repository.py
Description: 在借用交易內保存 M3 不可變 lineage、replay receipt 與 owner intents。
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    CriterionStatus,
    DynamicWillingnessLineage,
    MatchingCandidateResult,
    MatchingCriteriaResult,
    MatchingCriteriaSnapshot,
    MatchingCrossDomainRequest,
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingRequestKind,
    RefusalRoutingGroup,
    MatchingSegment,
    MatchingSourceVersion,
    ZeroCandidateDecision,
    ZeroCandidateDecisionLineage,
    canonical_source_tuple,
)
from shared_kernel.clock import BusinessClock
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_application import (
    MatchingApplicationError,
)
from subsystems.scheduling.matching_coordination_contracts import (
    MatchingApplyReceipt,
    MatchingCommand,
    MatchingCommandName,
    MatchingCriteriaRecontactIntentProjection,
    MatchingNotificationIntentProjection,
    MatchingNotificationRecipientRole,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
)


class MatchingCoordinationPersistenceError(RuntimeError):
    """Persisted M3 bytes cannot satisfy the immutable contract."""


class MySqlMatchingCoordinationRepository:
    """Borrow one connection; this adapter never begins, commits, or rolls back."""

    def __init__(self, connection: Any, clock: BusinessClock) -> None:
        self._connection = connection
        self._clock = clock

    def claim_or_replay(
        self,
        idempotency_key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
        correlation_id: CorrelationId,
    ) -> MatchingApplyReceipt | None:
        row = self._one(
            "SELECT command_fingerprint,result_snapshot "
            "FROM matching_coordination_apply_receipts "
            "WHERE idempotency_key=%s FOR UPDATE",
            (idempotency_key.value,),
        )
        if row is None:
            return None
        if row["command_fingerprint"] != command_fingerprint.value:
            raise MatchingApplicationError(
                TypedError(
                    ErrorCategory.IDEMPOTENCY_MISMATCH,
                    "matching_idempotency_conflict",
                    "matching_idempotency_conflict",
                    correlation_id,
                )
            )
        return _receipt_from_payload(_json_object(row["result_snapshot"]))

    def lock_matching_root(self, case_no: str) -> None:
        # Both indexed reads participate in the caller-owned transaction.  An
        # absent row is intentionally not manufactured by this adapter.
        self._one(
            "SELECT id FROM matching_coordination_criteria_snapshots "
            "WHERE case_no=%s ORDER BY criteria_version DESC LIMIT 1 FOR UPDATE",
            (case_no,),
        )
        self._one(
            "SELECT id FROM matching_coordination_package_lineage "
            "WHERE case_no=%s ORDER BY package_version DESC LIMIT 1 FOR UPDATE",
            (case_no,),
        )

    def load_current_snapshot(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingCriteriaSnapshot:
        """Read the latest M3-owned criteria snapshot without inventing owner facts."""

        lock_clause = " FOR UPDATE" if for_update else ""
        row = self._one(
            "SELECT snapshot_id,case_no,criteria_version,criteria_snapshot,"
            "source_version_tuple,criteria_digest,occurred_at_utc "
            "FROM matching_coordination_criteria_snapshots WHERE case_no=%s "
            "ORDER BY criteria_version DESC LIMIT 1" + lock_clause,
            (case_no,),
        )
        if row is None:
            raise MatchingCoordinationPersistenceError("matching criteria snapshot missing")
        return _snapshot_from_row(row)

    def load_snapshot_history(
        self, case_no: str, *, for_update: bool = False
    ) -> tuple[MatchingCriteriaSnapshot, ...]:
        """Read the complete immutable snapshot lineage in canonical version order."""

        lock_clause = " FOR UPDATE" if for_update else ""
        rows = self._all(
            "SELECT snapshot_id,case_no,criteria_version,criteria_snapshot,"
            "source_version_tuple,criteria_digest,occurred_at_utc "
            "FROM matching_coordination_criteria_snapshots WHERE case_no=%s "
            "ORDER BY criteria_version ASC" + lock_clause,
            (case_no,),
        )
        if not rows:
            raise MatchingCoordinationPersistenceError("matching criteria history missing")
        snapshots = tuple(_snapshot_from_row(row) for row in rows)
        versions = tuple(item.criteria_version for item in snapshots)
        if versions != tuple(sorted(set(versions))):
            raise MatchingCoordinationPersistenceError(
                "matching criteria history is not canonical"
            )
        if any(item.case_no != case_no for item in snapshots):
            raise MatchingCoordinationPersistenceError(
                "matching criteria history identity is ambiguous"
            )
        return snapshots

    def load_current_package(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingPackage | None:
        """Read the latest immutable M3 package; absence is an explicit state."""

        lock_clause = " FOR UPDATE" if for_update else ""
        row = self._one(
            "SELECT package_snapshot,package_digest "
            "FROM matching_coordination_package_lineage "
            "WHERE case_no=%s ORDER BY package_version DESC LIMIT 1" + lock_clause,
            (case_no,),
        )
        if row is None:
            return None
        package = _package_from_payload(_json_object(row["package_snapshot"]))
        if str(row.get("package_digest", "")) != package.fingerprint.value:
            raise MatchingCoordinationPersistenceError("matching package digest drift")
        return package

    def load_willingness_history(
        self, case_no: str, *, for_update: bool = False
    ) -> tuple[DynamicWillingnessLineage, ...]:
        """Read only M3-owned immutable willingness events, never legacy text."""

        lock_clause = " FOR UPDATE" if for_update else ""
        rows = self._all(
            "SELECT event_id,event_payload FROM matching_coordination_events "
            "WHERE case_no=%s AND event_type='caregiver_willingness' "
            "ORDER BY id ASC" + lock_clause,
            (case_no,),
        )
        result: list[DynamicWillingnessLineage] = []
        for row in rows:
            receipt = _receipt_from_payload(_json_object(row["event_payload"]))
            lineage = receipt.willingness_lineage
            if lineage is None or lineage.event_id != str(row["event_id"]):
                raise MatchingCoordinationPersistenceError(
                    "matching willingness lineage is incomplete"
                )
            result.append(lineage)
        event_ids = tuple(item.event_id for item in result)
        if len(event_ids) != len(set(event_ids)):
            raise MatchingCoordinationPersistenceError(
                "matching willingness lineage is ambiguous"
            )
        return tuple(result)

    def append_lineage(
        self,
        command: MatchingCommand,
        facts: MatchingCoordinationFacts,
        receipt: MatchingApplyReceipt,
    ) -> None:
        snapshot_row_id = self._ensure_snapshot(command, facts)
        package_row_id = self._ensure_package(command, facts, receipt)
        self._ensure_event(
            command,
            facts,
            receipt,
            snapshot_row_id=snapshot_row_id,
            package_row_id=package_row_id,
        )

    def save_receipt(
        self,
        command: MatchingCommand,
        command_fingerprint: PreviewFingerprint,
        receipt: MatchingApplyReceipt,
    ) -> None:
        event_id = _event_identity(command, receipt)
        event = self._one(
            "SELECT id,criteria_snapshot_id,package_lineage_id "
            "FROM matching_coordination_events WHERE event_id=%s FOR UPDATE",
            (event_id,),
        )
        if event is None:
            raise MatchingCoordinationPersistenceError("matching event must precede receipt")
        payload = _receipt_payload(receipt)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO matching_coordination_apply_receipts "
                "(receipt_id,case_no,event_id,criteria_snapshot_id,package_lineage_id,"
                "command_name,idempotency_key,command_fingerprint,preview_fingerprint,"
                "source_version_tuple,result_snapshot,outcome_state,actor_ref,"
                "correlation_id,applied_at_utc) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    receipt.receipt_id,
                    command.case_no,
                    event["id"],
                    event["criteria_snapshot_id"],
                    event["package_lineage_id"],
                    receipt.command_name.value,
                    command.idempotency_key.value,
                    command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    _json_dump(_source_payload(receipt.source_versions)),
                    _json_dump(payload),
                    _outcome_state(receipt.result_state),
                    command.actor.actor_id,
                    command.correlation_id.value,
                    self._utc_now(),
                ),
            )

    def append_typed_intents(
        self, command: MatchingCommand, receipt: MatchingApplyReceipt
    ) -> None:
        if not receipt.outbox_intent_ids:
            return
        event = self._one(
            "SELECT id FROM matching_coordination_events WHERE event_id=%s",
            (_event_identity(command, receipt),),
        )
        stored_receipt = self._one(
            "SELECT id FROM matching_coordination_apply_receipts WHERE receipt_id=%s",
            (receipt.receipt_id,),
        )
        if event is None or stored_receipt is None:
            raise MatchingCoordinationPersistenceError(
                "matching event and receipt must precede owner intents"
            )
        intents = _intent_payloads(command, receipt)
        if tuple(item[0] for item in intents) != receipt.outbox_intent_ids:
            raise MatchingCoordinationPersistenceError(
                "typed owner intents do not match receipt identities"
            )
        with self._connection.cursor() as cursor:
            for reference_id, intent_type, target_owner, payload in intents:
                cursor.execute(
                    "INSERT INTO matching_coordination_outbox "
                    "(reference_id,event_id,receipt_id,case_no,intent_type,target_owner,"
                    "intent_payload,source_version_tuple,reference_digest,"
                    "idempotency_key,correlation_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        reference_id,
                        event["id"],
                        stored_receipt["id"],
                        command.case_no,
                        intent_type,
                        target_owner,
                        _json_dump(payload),
                        _json_dump(_source_payload(receipt.source_versions)),
                        fingerprint_payload(payload).value,
                        reference_id,
                        command.correlation_id.value,
                    ),
                )

    def _ensure_snapshot(
        self, command: MatchingCommand, facts: MatchingCoordinationFacts
    ) -> int:
        snapshot = facts.snapshot
        existing = self._one(
            "SELECT id,criteria_digest FROM matching_coordination_criteria_snapshots "
            "WHERE snapshot_id=%s FOR UPDATE",
            (snapshot.snapshot_id,),
        )
        if existing is not None:
            if existing["criteria_digest"] != snapshot.fingerprint.value:
                raise MatchingCoordinationPersistenceError("matching snapshot drift")
            return int(existing["id"])
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO matching_coordination_criteria_snapshots "
                "(snapshot_id,case_no,criteria_version,criteria_snapshot,"
                "source_version_tuple,criteria_digest,actor_ref,occurred_at_utc) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    snapshot.snapshot_id,
                    snapshot.case_no,
                    snapshot.criteria_version,
                    _json_dump(snapshot.criteria),
                    _json_dump(_source_payload(snapshot.source_versions)),
                    snapshot.fingerprint.value,
                    command.actor.actor_id,
                    _utc_naive(snapshot.created_at),
                ),
            )
            return int(cursor.lastrowid)

    def _ensure_package(
        self,
        command: MatchingCommand,
        facts: MatchingCoordinationFacts,
        receipt: MatchingApplyReceipt,
    ) -> int | None:
        package = receipt.resulting_package or facts.package
        if package is None:
            return None
        existing = self._one(
            "SELECT id,package_digest FROM matching_coordination_package_lineage "
            "WHERE package_id=%s FOR UPDATE",
            (package.package_id,),
        )
        if existing is not None:
            if existing["package_digest"] != package.fingerprint.value:
                raise MatchingCoordinationPersistenceError("matching package drift")
            return int(existing["id"])
        parent = self._one(
            "SELECT id,package_id,package_version FROM matching_coordination_package_lineage "
            "WHERE case_no=%s ORDER BY package_version DESC LIMIT 1 FOR UPDATE",
            (command.case_no,),
        )
        if receipt.resulting_package is not None:
            current = facts.package
            if (
                current is None
                or parent is None
                or str(parent["package_id"]) != current.package_id
                or int(parent["package_version"]) != current.version
            ):
                raise MatchingCoordinationPersistenceError(
                    "matching resulting package parent is stale"
                )
        snapshot = self._one(
            "SELECT id FROM matching_coordination_criteria_snapshots "
            "WHERE snapshot_id=%s",
            (package.criteria_snapshot_id,),
        )
        if snapshot is None:
            raise MatchingCoordinationPersistenceError("matching package snapshot missing")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO matching_coordination_package_lineage "
                "(package_id,case_no,criteria_snapshot_id,parent_package_id,"
                "package_version,lineage_kind,package_state,package_snapshot,"
                "source_version_tuple,package_digest,actor_ref) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    package.package_id,
                    command.case_no,
                    snapshot["id"],
                    parent["id"] if parent else None,
                    package.version,
                    "rematch" if parent else "initial",
                    package.state.value,
                    _json_dump(package),
                    _json_dump(_source_payload(package.source_versions)),
                    package.fingerprint.value,
                    command.actor.actor_id,
                ),
            )
            return int(cursor.lastrowid)

    def _ensure_event(
        self,
        command: MatchingCommand,
        facts: MatchingCoordinationFacts,
        receipt: MatchingApplyReceipt,
        *,
        snapshot_row_id: int,
        package_row_id: int | None,
    ) -> int:
        event_id = _event_identity(command, receipt)
        existing = self._one(
            "SELECT id,event_digest FROM matching_coordination_events "
            "WHERE event_id=%s FOR UPDATE",
            (event_id,),
        )
        payload = _receipt_payload(receipt)
        digest = fingerprint_payload(payload).value
        if existing is not None:
            if existing["event_digest"] != digest:
                raise MatchingCoordinationPersistenceError("matching event drift")
            return int(existing["id"])
        resulting_package = receipt.resulting_package or facts.package
        resulting_version = resulting_package.version if resulting_package else facts.snapshot.criteria_version
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO matching_coordination_events "
                "(event_id,case_no,criteria_snapshot_id,package_lineage_id,event_type,"
                "expected_version,resulting_version,event_payload,source_version_tuple,"
                "event_digest,actor_ref,idempotency_key,correlation_id,occurred_at_utc) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_id,
                    command.case_no,
                    snapshot_row_id,
                    package_row_id,
                    _event_type(command),
                    max(int(resulting_version) - 1, 0),
                    resulting_version,
                    _json_dump(payload),
                    _json_dump(_source_payload(receipt.source_versions)),
                    digest,
                    command.actor.actor_id,
                    command.idempotency_key.value,
                    command.correlation_id.value,
                    self._utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def _one(self, sql: str, params: tuple[Any, ...]) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        if row is not None and not isinstance(row, Mapping):
            raise MatchingCoordinationPersistenceError("dict cursor is required")
        return row

    def _all(self, sql: str, params: tuple[Any, ...]) -> tuple[Mapping[str, Any], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = tuple(cursor.fetchall() or ())
        if any(not isinstance(row, Mapping) for row in rows):
            raise MatchingCoordinationPersistenceError("dict cursor is required")
        return rows

    def _utc_now(self) -> datetime:
        return _utc_naive(self._clock.now())


def _event_identity(command: MatchingCommand, receipt: MatchingApplyReceipt) -> str:
    return receipt.decision_event_id or f"{command.idempotency_key.value}:event"


def _event_type(command: MatchingCommand) -> str:
    event_type_by_command = {
        "ApplyInitialCriteriaSnapshot": "criteria_snapshotted",
        "ApplyCriteriaDiffResend": "criteria_diff",
        "ApplyCaregiverSelection": "caregiver_willingness",
        "ApplyCustomerMatchingDecision": "customer_decision",
        "ApplyZeroCandidateAlternative": "customer_decision",
        "ApplyZeroCandidateConfirmation": "package_proposed",
        "ApplyRematch": "rematch_required",
        "ApplyLeaveImpactOnMatching": "rematch_required",
        "ApplyServiceDateChangeRematch": "rematch_required",
    }
    command_name = type(command).__name__
    try:
        return event_type_by_command[command_name]
    except KeyError as error:
        raise MatchingCoordinationPersistenceError(
            f"unsupported matching command event type: {command_name}"
        ) from error


def _outcome_state(result_state: str) -> str:
    if result_state == "rematch_required":
        return "rematch_required"
    if result_state in {"rejected", "disagree", "awaiting_matching"}:
        return "rejected_as_stale" if result_state == "rejected" else "applied"
    return "applied"


def _intent_payloads(
    command: MatchingCommand, receipt: MatchingApplyReceipt
) -> tuple[tuple[str, str, str, dict[str, Any]], ...]:
    by_identity: dict[str, tuple[str, str, dict[str, Any]]] = {}
    if receipt.cross_domain_request is not None:
        request = receipt.cross_domain_request
        intent_type = request.request_kind.value
        by_identity[request.request_id] = (
            intent_type,
            "assignment_workflow",
            _jsonable(request),
        )
    for intent in receipt.notification_intents:
        by_identity[intent.intent_id] = (
            "line_matching_interaction",
            "line_integration",
            _jsonable(intent),
        )
    for intent in receipt.criteria_recontact_intents:
        by_identity[intent.intent_id] = (
            "line_criteria_diff_resend",
            "line_integration",
            _jsonable(intent),
        )
    for reference_id in receipt.outbox_intent_ids:
        if reference_id in by_identity:
            continue
        if ":criteria-resend:" in reference_id:
            intent_type, owner = "line_criteria_diff_resend", "line_integration"
        elif reference_id.endswith(":orders"):
            intent_type, owner = "orders_terms_update_requested", "orders_workflow"
        elif reference_id.endswith(":assignment"):
            intent_type, owner = "rematch_requested", "assignment_workflow"
        else:
            raise MatchingCoordinationPersistenceError(
                f"unsupported matching intent identity: {reference_id}"
            )
        by_identity[reference_id] = (
            intent_type,
            owner,
            {
                "reference_id": reference_id,
                "case_no": command.case_no,
                "receipt_id": receipt.receipt_id,
                "result_state": receipt.result_state,
                "zero_candidate_decision": _jsonable(receipt.zero_candidate_decision),
                "resulting_package": _jsonable(receipt.resulting_package),
            },
        )
    return tuple(
        (identity, *by_identity[identity]) for identity in receipt.outbox_intent_ids
    )


def _receipt_payload(receipt: MatchingApplyReceipt) -> dict[str, Any]:
    return _jsonable(receipt)


def _source_payload(values: tuple[MatchingSourceVersion, ...]) -> list[dict[str, Any]]:
    return [
        {
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "version": item.version,
            "fingerprint": item.fingerprint,
        }
        for item in values
    ]


def _source_tuple_from_payload(value: Any) -> tuple[MatchingSourceVersion, ...]:
    decoded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    if not isinstance(decoded, list):
        raise MatchingCoordinationPersistenceError("matching source tuple is required")
    try:
        return canonical_source_tuple(
            tuple(MatchingSourceVersion(**_json_object(item)) for item in decoded)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MatchingCoordinationPersistenceError("matching source tuple is invalid") from error


def _snapshot_from_row(row: Mapping[str, Any]) -> MatchingCriteriaSnapshot:
    occurred_at = row["occurred_at_utc"]
    if not isinstance(occurred_at, datetime):
        raise MatchingCoordinationPersistenceError("matching snapshot time is invalid")
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    try:
        return MatchingCriteriaSnapshot(
            snapshot_id=str(row["snapshot_id"]),
            case_no=str(row["case_no"]),
            criteria_version=int(row["criteria_version"]),
            criteria=_json_object(row["criteria_snapshot"]),
            source_versions=_source_tuple_from_payload(row["source_version_tuple"]),
            fingerprint=PreviewFingerprint(str(row["criteria_digest"])),
            created_at=occurred_at,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MatchingCoordinationPersistenceError("matching snapshot is invalid") from error


def _package_from_payload(payload: Mapping[str, Any]) -> MatchingPackage:
    try:
        candidates = tuple(
            MatchingCandidateResult(
                candidate_id=str(item["candidate_id"]),
                staff_id=int(item["staff_id"]),
                eligibility=CandidateEligibility(item["eligibility"]),
                criteria_results=tuple(
                    MatchingCriteriaResult(
                        code=str(result["code"]),
                        status=CriterionStatus(result["status"]),
                        source_version=MatchingSourceVersion(
                            **_json_object(result["source_version"])
                        ),
                        detail=str(result.get("detail", "")),
                    )
                    for result in item.get("criteria_results", ())
                ),
                rejection_reasons=tuple(item.get("rejection_reasons", ())),
                coverage_evidence=tuple(
                    date.fromisoformat(value)
                    for value in item.get("coverage_evidence", ())
                ),
                willingness=str(item.get("willingness", "unconfirmed")),
                notification_lineage=tuple(item.get("notification_lineage", ())),
                staff_name=str(item.get("staff_name", "")),
            )
            for item in payload.get("candidate_results", ())
        )
        segments = tuple(
            MatchingSegment(
                staff_id=int(item["staff_id"]),
                service_dates=tuple(
                    date.fromisoformat(value) for value in item.get("service_dates", ())
                ),
                sequence=int(item["sequence"]),
            )
            for item in payload.get("segments", ())
        )
        return MatchingPackage(
            package_id=str(payload["package_id"]),
            version=int(payload["version"]),
            mode=MatchingPackageMode(payload["mode"]),
            segments=segments,
            required_service_dates=tuple(
                date.fromisoformat(value)
                for value in payload.get("required_service_dates", ())
            ),
            candidate_results=candidates,
            criteria_snapshot_id=str(payload["criteria_snapshot_id"]),
            source_versions=_source_tuple_from_payload(payload["source_versions"]),
            state=MatchingPackageState(payload.get("state", "proposed")),
            blockers=tuple(payload.get("blockers", ())),
            warnings=tuple(payload.get("warnings", ())),
            fingerprint=PreviewFingerprint(str(payload["fingerprint"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MatchingCoordinationPersistenceError("matching package is invalid") from error


def _receipt_from_payload(payload: Mapping[str, Any]) -> MatchingApplyReceipt:
    try:
        return _receipt_from_payload_unchecked(payload)
    except MatchingCoordinationPersistenceError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise MatchingCoordinationPersistenceError(
            "matching receipt payload is invalid"
        ) from error


def _receipt_from_payload_unchecked(
    payload: Mapping[str, Any],
) -> MatchingApplyReceipt:
    sources = canonical_source_tuple(
        tuple(MatchingSourceVersion(**item) for item in payload["source_versions"])
    )
    cross_payload = payload.get("cross_domain_request")
    cross_request = None
    if cross_payload:
        cross_request = MatchingCrossDomainRequest(
            **{
                **cross_payload,
                "request_kind": MatchingRequestKind(cross_payload["request_kind"]),
                "source_versions": canonical_source_tuple(
                    tuple(
                        MatchingSourceVersion(**item)
                        for item in cross_payload["source_versions"]
                    )
                ),
            }
        )
    zero_payload = payload.get("zero_candidate_decision")
    zero = None
    if zero_payload:
        zero = ZeroCandidateDecisionLineage(
            **{
                **zero_payload,
                "decision": ZeroCandidateDecision(zero_payload["decision"]),
                "source_versions": canonical_source_tuple(
                    tuple(
                        MatchingSourceVersion(**item)
                        for item in zero_payload["source_versions"]
                    )
                ),
            }
        )
    willingness_payload = payload.get("willingness_lineage")
    willingness = None
    if willingness_payload:
        willingness = DynamicWillingnessLineage(
            **{
                **willingness_payload,
                "source_versions": canonical_source_tuple(
                    tuple(
                        MatchingSourceVersion(**item)
                        for item in willingness_payload["source_versions"]
                    )
                ),
            }
        )
    notifications = tuple(
        MatchingNotificationIntentProjection(
            **{
                **item,
                "recipient_role": MatchingNotificationRecipientRole(
                    item["recipient_role"]
                ),
                "package_fingerprint": PreviewFingerprint(
                    item["package_fingerprint"]
                ),
                "idempotency_key": IdempotencyKey(item["idempotency_key"]),
            }
        )
        for item in payload.get("notification_intents", ())
    )
    recontact_intents = tuple(
        MatchingCriteriaRecontactIntentProjection(
            **{
                **item,
                "route_group": RefusalRoutingGroup(item["route_group"]),
                "diff_fingerprint": PreviewFingerprint(item["diff_fingerprint"]),
                "source_versions": canonical_source_tuple(
                    tuple(
                        MatchingSourceVersion(**source)
                        for source in item["source_versions"]
                    )
                ),
                "idempotency_key": IdempotencyKey(item["idempotency_key"]),
                "package_fingerprint": (
                    PreviewFingerprint(item["package_fingerprint"])
                    if item.get("package_fingerprint") is not None
                    else None
                ),
            }
        )
        for item in payload.get("criteria_recontact_intents", ())
    )
    return MatchingApplyReceipt(
        receipt_id=payload["receipt_id"],
        command_name=MatchingCommandName(payload["command_name"]),
        command_fingerprint=PreviewFingerprint(payload["command_fingerprint"]),
        preview_fingerprint=PreviewFingerprint(payload["preview_fingerprint"]),
        source_versions=sources,
        decision_event_id=payload.get("decision_event_id"),
        package_id=payload.get("package_id"),
        outbox_intent_ids=tuple(payload.get("outbox_intent_ids", ())),
        result_state=payload["result_state"],
        cross_domain_request=cross_request,
        zero_candidate_decision=zero,
        willingness_lineage=willingness,
        notification_intents=notifications,
        criteria_recontact_intents=recontact_intents,
        resulting_package=(
            _package_from_payload(payload["resulting_package"])
            if payload.get("resulting_package") is not None
            else None
        ),
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (PreviewFingerprint, IdempotencyKey, CorrelationId)):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"unsupported matching persistence value: {type(value).__name__}")


def _json_dump(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: Any) -> Mapping[str, Any]:
    decoded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    if not isinstance(decoded, Mapping):
        raise MatchingCoordinationPersistenceError("matching JSON object is required")
    return decoded


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("matching persistence time must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


__all__ = [
    "MatchingCoordinationPersistenceError",
    "MySqlMatchingCoordinationRepository",
]
