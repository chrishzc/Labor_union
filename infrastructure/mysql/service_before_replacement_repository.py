"""
File: service_before_replacement_repository.py
Description: 保存服務前換人 1012 lineage、root disposition、receipt 與內部 outbox。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import json
import re
from typing import Any, Callable, Iterator, Mapping

from domains.scheduling.service_before_replacement import (
    ReplacementResumeStep,
    ReplacementRootKind,
    ReplacementScenario,
    ReplacementRootIdentity,
    ServiceBeforeReplacementFacts,
    ServiceBeforeReplacementCandidate,
)
from infrastructure.mysql.matching_successor_persistence_adapter import (
    MatchingSuccessorPersistenceAdapter,
    MatchingSuccessorPersistenceError,
    MatchingSuccessorPersistenceRequest,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from subsystems.scheduling.service_before_replacement_workflow import (
    ReplacementOwnerReadback,
    ReplacementPersistenceBundle,
    ReplacementReceipt,
    StoredReplacementReceipt,
)


class ServiceBeforeReplacementPersistenceError(RuntimeError):
    """Stored replacement bytes cannot satisfy the owner contract."""


class MySqlServiceBeforeReplacementRepository:
    """Borrow one connection; this repository never commits or rolls back."""

    def __init__(
        self,
        connection: Any,
        matching_adapter: MatchingSuccessorPersistenceAdapter | None = None,
        *,
        facts_loader: Callable[[object, bool], ServiceBeforeReplacementFacts | None] | None = None,
        matching_source_loader: Callable[[str, bool], Mapping[str, Any] | None] | None = None,
    ) -> None:
        self._connection = connection
        self._matching_adapter = matching_adapter
        self._facts_loader = facts_loader
        self._matching_source_loader = matching_source_loader

    def load_facts(self, case_no: str, *, for_update: bool) -> ServiceBeforeReplacementFacts | None:
        if self._facts_loader is None:
            return None
        return self._facts_loader(case_no, for_update=for_update)

    def load_facts_for_request(self, request: object, *, for_update: bool) -> ServiceBeforeReplacementFacts | None:
        if self._facts_loader is None:
            return None
        return self._facts_loader(request, for_update=for_update)

    def find_receipt(self, key: IdempotencyKey, case_no: str, *, for_update: bool) -> StoredReplacementReceipt | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT receipt.command_fingerprint,receipt.receipt_identity,"
                "receipt.replacement_event_id,"
                "receipt.idempotency_key,receipt.preview_fingerprint,"
                "receipt.retained_root_set_digest,receipt.retained_root_count,"
                "receipt.superseded_root_set_digest,receipt.superseded_root_count,"
                "receipt.created_root_set_digest,receipt.created_root_count,"
                "receipt.resulting_aggregate_version,receipt.resulting_generation_version,"
                "receipt.resulting_event_version,receipt.outbox_identity,"
                "event.case_no,event.prior_generation_identity,event.prior_event_identity,"
                "event.replacement_generation_identity,event.replacement_event_identity,"
                "successor.successor_round_identity,successor.matching_package_lineage_id,"
                "successor.matching_event_id,event.scenario "
                "FROM scheduling_service_before_replacement_receipts receipt "
                "JOIN scheduling_service_before_replacement_events event "
                "ON event.id=receipt.replacement_event_id "
                "JOIN scheduling_service_before_replacement_successors successor "
                "ON successor.id=receipt.successor_binding_id "
                "WHERE receipt.idempotency_key=%s AND receipt.case_no=%s" + suffix,
                (key.value, case_no),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        try:
            receipt = ReplacementReceipt(
                case_no=str(row["case_no"]),
                receipt_identity=str(row["receipt_identity"]),
                idempotency_key=IdempotencyKey(str(row["idempotency_key"])),
                command_fingerprint=PreviewFingerprint(str(row["command_fingerprint"])),
                preview_fingerprint=PreviewFingerprint(str(row["preview_fingerprint"])),
                replacement_generation_identity=str(row["replacement_generation_identity"]),
                replacement_event_identity=str(row["replacement_event_identity"]),
                successor_round_identity=str(row["successor_round_identity"]),
                resulting_generation_version=int(row["resulting_generation_version"]),
                resulting_event_version=int(row["resulting_event_version"]),
                resulting_aggregate_version=int(row["resulting_aggregate_version"]),
                outbox_identity=str(row["outbox_identity"]),
                retained_root_ids=(),
                superseded_root_ids=(),
                created_root_ids=(),
                retained_root_set_digest=str(row["retained_root_set_digest"]),
                retained_root_count=int(row["retained_root_count"]),
                superseded_root_set_digest=str(row["superseded_root_set_digest"]),
                superseded_root_count=int(row["superseded_root_count"]),
                created_root_set_digest=str(row["created_root_set_digest"]),
                created_root_count=int(row["created_root_count"]),
                matching_package_lineage_id=int(row["matching_package_lineage_id"]),
                matching_event_id=int(row["matching_event_id"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ServiceBeforeReplacementPersistenceError("replacement receipt is invalid") from error
        roots = self._read_root_sets(int(row.get("replacement_event_id", 0)), case_no)
        receipt = _replace_receipt_roots(receipt, roots)
        return StoredReplacementReceipt(receipt.command_fingerprint, receipt)

    def persist_replacement(self, bundle: ReplacementPersistenceBundle) -> ReplacementReceipt:
        command = bundle.command
        candidate = bundle.candidate
        proof = candidate.actual_service_proof
        if proof is None or proof.service_dates:
            raise ServiceBeforeReplacementPersistenceError("actual service proof is not zero")
        # Resolve the owner source and adapter before touching Scheduling
        # generations.  Any incomplete Matching handoff therefore fails
        # closed without creating a partial replacement lineage.
        source = self._matching_source(command, for_update=True)
        owner_proof = candidate.matching_zero_candidate_proof
        if owner_proof is not None:
            source_package = source.get("parent_package")
            if (
                source_package is None
                or str(getattr(source_package, "package_id", ""))
                != owner_proof.package_identity
                or int(getattr(source_package, "version", -1))
                != owner_proof.package_version
                or str(getattr(getattr(source_package, "fingerprint", None), "value", ""))
                != owner_proof.package_fingerprint.value
                or str(source.get("snapshot_id"))
                != owner_proof.criteria_snapshot_identity
                or str(source.get("source_event_identity"))
                != owner_proof.event_identity
                or int(source.get("source_event_version", -1))
                != owner_proof.event_version
                or str(source.get("source_event_fingerprint"))
                != owner_proof.event_fingerprint.value
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "matching zero candidate owner proof is stale"
                )
        if candidate.candidate_pool_reuse_proof is None:
            source = dict(source)
            source.pop("reuse_package", None)
        adapter = self._matching_adapter
        if adapter is None:
            raise ServiceBeforeReplacementPersistenceError("matching source adapter is required")
        prior_generation_id, replacement_generation_id = self.create_replacement_generation(
            case_no=command.case_no,
            expected_generation_version=command.expected_generation_version.value,
            resulting_generation_version=candidate.resulting_generation_version,
            expected_aggregate_version=command.expected_aggregate_version.value,
            resulting_aggregate_version=candidate.resulting_aggregate_version,
            actor_id=command.actor.actor_id,
            reason=command.reason,
        )
        prior_event_id = self._prior_replacement_event_id(
            candidate.prior_event_identity,
            command.case_no,
            expected_generation_id=prior_generation_id,
        )
        event_id = self._insert_event(
            command,
            candidate,
            proof,
            prior_event_id,
            prior_generation_id,
            replacement_generation_id,
        )
        if candidate.scenario is ReplacementScenario.R03:
            self._cancel_r03_waiting_lock(
                command=command,
                candidate=candidate,
                replacement_event_id=event_id,
                replacement_generation_id=replacement_generation_id,
            )
        self._insert_roots(event_id, command.case_no, candidate)
        persisted_roots = self._read_root_sets(event_id, command.case_no)
        # A bundle may contain a preview convenience value, but Apply must
        # always use the Matching facts obtained above through this locked UoW.
        try:
            successor = adapter.persist_successor(
                MatchingSuccessorPersistenceRequest(
                    case_no=command.case_no,
                    successor_package_identity=(
                        candidate.matching_zero_candidate_proof.package_identity
                        if candidate.matching_zero_candidate_proof is not None
                        else f"successor-package:{candidate.successor_round_identity}"
                    ),
                    successor_round_identity=candidate.successor_round_identity or "",
                    successor_matching_event_identity=(
                        candidate.matching_zero_candidate_proof.event_identity
                        if candidate.matching_zero_candidate_proof is not None
                        else f"successor-matching-event:{candidate.successor_round_identity}"
                    ),
                    scenario=candidate.scenario.value,
                    candidate_count=0 if candidate.candidate_pool_reuse_proof is None else 1,
                    source_snapshot=source,
                    actor=command.actor,
                    idempotency_key=command.idempotency_key,
                    correlation_id=command.correlation_id,
                    candidate_disposition=(
                        "blocked_no_candidate"
                        if candidate.matching_zero_candidate_proof is not None
                        else None
                        if candidate.successor_round_fact is None
                        else candidate.successor_round_fact.zero_candidate_disposition
                    ),
                    reuse_existing_successor=(
                        candidate.matching_zero_candidate_proof is not None
                    ),
                    existing_package_lineage_id=(
                        int(source["matching_package_lineage_id"])
                        if owner_proof is not None
                        else None
                    ),
                    existing_matching_event_id=(
                        int(source["matching_event_id"])
                        if owner_proof is not None
                        else None
                    ),
                    existing_package_fingerprint=(
                        owner_proof.package_fingerprint.value
                        if owner_proof is not None
                        else None
                    ),
                    existing_event_fingerprint=(
                        owner_proof.event_fingerprint.value
                        if owner_proof is not None
                        else None
                    ),
                )
            )
        except MatchingSuccessorPersistenceError as error:
            raise ServiceBeforeReplacementPersistenceError(str(error)) from error
        successor_id = self._insert_successor(event_id, command, candidate, replacement_generation_id, successor)
        persisted_receipt = replace(
            bundle.receipt,
            matching_package_lineage_id=successor.package_lineage_id,
            matching_event_id=successor.matching_event_id,
        )
        self._insert_receipt(event_id, successor_id, command, candidate, persisted_receipt, persisted_roots)
        self._insert_outbox(event_id, command, persisted_receipt)
        return persisted_receipt

    def load_owner_readback(self, case_no: str, *, for_update: bool) -> ReplacementOwnerReadback | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT event.id,event.case_no,event.replacement_generation_identity,"
                "event.replacement_event_identity,event.replacement_generation_id,event.scenario,"
                "event.resulting_generation_version,"
                "event.resulting_event_version,event.resulting_aggregate_version,"
                "successor.id AS successor_id,successor.matching_package_lineage_id,"
                "successor.matching_event_id,successor.successor_round_identity,"
                "successor.resume_step,successor.candidate_count,"
                "successor.zero_candidate_disposition,"
                "receipt.outbox_identity,receipt.command_fingerprint,"
                "receipt.retained_root_set_digest,receipt.retained_root_count,"
                "receipt.superseded_root_set_digest,receipt.superseded_root_count,"
                "receipt.created_root_set_digest,receipt.created_root_count "
                "FROM scheduling_service_before_replacement_events event "
                "JOIN scheduling_service_before_replacement_successors successor "
                "ON successor.replacement_event_id=event.id "
                "JOIN scheduling_service_before_replacement_receipts receipt "
                "ON receipt.replacement_event_id=event.id "
                "JOIN scheduling_service_before_replacement_outbox outbox "
                "ON outbox.replacement_event_id=event.id AND outbox.receipt_id=receipt.id "
                "AND outbox.outbox_identity=receipt.outbox_identity "
                "WHERE event.case_no=%s ORDER BY event.id DESC LIMIT 1" + suffix,
                (case_no,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            event_id = int(row["id"])
        roots = self._read_root_sets(event_id, case_no, for_update=for_update)
        digests = tuple(root_set_digest(values) for values in roots)
        counts = tuple(len(values) for values in roots)
        persisted_digests = tuple(
            str(row[key]) for key in (
                "retained_root_set_digest", "superseded_root_set_digest", "created_root_set_digest"
            )
        )
        persisted_counts = tuple(
            int(row[key]) for key in (
                "retained_root_count", "superseded_root_count", "created_root_count")
        )
        if digests != persisted_digests or counts != persisted_counts:
            raise ServiceBeforeReplacementPersistenceError("replacement root digest readback drift")
        if str(row.get("scenario") or "") == ReplacementScenario.R03.value:
            self._require_r03_waiting_lock_readback(
                row,
                superseded_root_ids=roots[1],
                for_update=for_update,
            )
        return ReplacementOwnerReadback(
            str(row["case_no"]),
            str(row["replacement_generation_identity"]),
            str(row["replacement_event_identity"]),
            str(row["successor_round_identity"]),
            int(row["resulting_generation_version"]),
            int(row["resulting_event_version"]),
            int(row["resulting_aggregate_version"]),
            roots[0], roots[1], roots[2],
            ReplacementResumeStep(str(row["resume_step"])),
            int(row["candidate_count"]),
            (
                None
                if row.get("zero_candidate_disposition") is None
                else str(row["zero_candidate_disposition"])
            ),
            True, digests, counts,
            str(row["outbox_identity"]), int(row["matching_package_lineage_id"]),
            int(row["matching_event_id"]),
        )

    def require_matching_source(self, source: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if source is None:
            raise ServiceBeforeReplacementPersistenceError("matching source is required")
        return source

    def create_replacement_generation(
        self,
        *,
        case_no: str,
        expected_generation_version: int,
        resulting_generation_version: int | None,
        expected_aggregate_version: int,
        resulting_aggregate_version: int | None,
        actor_id: str,
        reason: str,
    ) -> tuple[int, int]:
        """Create and activate the empty successor generation in this UoW."""
        if resulting_generation_version is None or resulting_aggregate_version is None:
            raise ServiceBeforeReplacementPersistenceError("replacement generation transition is incomplete")
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT aggregate_version,generation_counter,effective_generation_id "
                "FROM scheduling_aggregates WHERE case_no=%s FOR UPDATE",
                (case_no,),
            )
            aggregate = cursor.fetchone()
            if aggregate is None:
                raise ServiceBeforeReplacementPersistenceError("scheduling aggregate is missing")
            if int(aggregate["aggregate_version"]) != expected_aggregate_version or int(aggregate["generation_counter"]) != expected_generation_version:
                raise ServiceBeforeReplacementPersistenceError("scheduling generation transition is stale")
            prior_generation_id = aggregate.get("effective_generation_id")
            if prior_generation_id is None:
                raise ServiceBeforeReplacementPersistenceError(
                    "prior effective generation is required"
                )
            cursor.execute(
                "INSERT INTO scheduling_generations "
                "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) "
                "VALUES (%s,%s,%s,'preparing',NULL,%s,%s)",
                (case_no, resulting_generation_version, resulting_aggregate_version, actor_id, reason),
            )
            replacement_generation_id = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE scheduling_generations SET status='cancelled',effective_marker=NULL,"
                "cancelled_at=CURRENT_TIMESTAMP WHERE id=%s AND status='effective' AND effective_marker=1",
                (int(prior_generation_id),),
            )
            if int(cursor.rowcount) != 1:
                raise ServiceBeforeReplacementPersistenceError("prior scheduling generation is not effective")
            cursor.execute(
                "UPDATE scheduling_generations SET status='effective',effective_marker=1 "
                "WHERE id=%s AND status='preparing'",
                (replacement_generation_id,),
            )
            if int(cursor.rowcount) != 1:
                raise ServiceBeforeReplacementPersistenceError("replacement scheduling generation activation failed")
            cursor.execute(
                "UPDATE scheduling_aggregates SET aggregate_version=%s,generation_counter=%s,effective_generation_id=%s "
                "WHERE case_no=%s AND aggregate_version=%s AND generation_counter=%s "
                "AND effective_generation_id <=> %s",
                (resulting_aggregate_version, resulting_generation_version, replacement_generation_id,
                 case_no, expected_aggregate_version, expected_generation_version, prior_generation_id),
            )
            if int(cursor.rowcount) != 1:
                raise ServiceBeforeReplacementPersistenceError("scheduling aggregate transition conflicted")
        return int(prior_generation_id), replacement_generation_id

    def _cancel_r03_waiting_lock(
        self,
        *,
        command: Any,
        candidate: ServiceBeforeReplacementCandidate,
        replacement_event_id: int,
        replacement_generation_id: int,
    ) -> None:
        waiting_roots = tuple(
            root
            for root in candidate.superseded_roots
            if root.kind is ReplacementRootKind.WAITING_LOCK
        )
        if len(waiting_roots) != 1:
            raise ServiceBeforeReplacementPersistenceError(
                "replacement waiting lock root is not exact"
            )
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT lock_header.id,lock_header.plan_id,lock_header.status,"
                "lock_header.is_active,plan.case_no "
                "FROM caregiver_availability_locks lock_header "
                "JOIN caregiver_matching_plans plan ON plan.id=lock_header.plan_id "
                "WHERE plan.case_no=%s AND plan.status='accepted' AND plan.is_active=1 "
                "AND lock_header.status='active' "
                "AND lock_header.is_active=1 ORDER BY lock_header.id FOR UPDATE",
                (command.case_no,),
            )
            locks = tuple(cursor.fetchall() or ())
            if len(locks) != 1:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock is not exact"
                )
            lock_id = int(locks[0]["id"])
            cursor.execute(
                "SELECT id,lock_id,segment_id,staff_id,lock_date,active_marker,"
                "released_by,released_at FROM caregiver_availability_lock_days "
                "WHERE lock_id=%s ORDER BY lock_date,segment_id,id FOR UPDATE",
                (lock_id,),
            )
            active_days = tuple(cursor.fetchall() or ())
            if not active_days or any(
                day.get("active_marker") != 1
                or day.get("released_by") is not None
                or day.get("released_at") is not None
                for day in active_days
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock days are missing"
                )
            cursor.execute(
                "SELECT id,lock_id,event_type,event_key,payload "
                "FROM caregiver_availability_lock_events WHERE lock_id=%s "
                "ORDER BY id FOR UPDATE",
                (lock_id,),
            )
            lock_events = tuple(cursor.fetchall() or ())
            if (
                len(lock_events) != 1
                or lock_events[0].get("event_type") != "lock_acquired"
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock event history is not exact"
                )
            from infrastructure.mysql.service_before_replacement_loader import _root
            root_lock = {
                key: locks[0][key]
                for key in ("id", "plan_id", "status", "is_active")
            }
            root_days = tuple(
                {
                    key: day[key]
                    for key in (
                        "id", "lock_id", "segment_id", "staff_id",
                        "lock_date", "active_marker",
                    )
                }
                for day in active_days
            )
            persisted_root = _root(
                ReplacementRootKind.WAITING_LOCK,
                command.case_no,
                "scheduling.waiting-lock",
                (root_lock, *root_days, *lock_events),
            )
            if persisted_root != waiting_roots[0]:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock root drift"
                )
            prior_active_days = [
                {
                    "lock_day_id": int(day["id"]),
                    "segment_id": int(day["segment_id"]),
                    "staff_id": int(day["staff_id"]),
                    "lock_date": day["lock_date"].isoformat(),
                }
                for day in active_days
            ]
            cursor.execute(
                "UPDATE caregiver_availability_lock_days "
                "SET active_marker=NULL,released_by=%s,released_at=CURRENT_TIMESTAMP "
                "WHERE lock_id=%s AND active_marker=1",
                (command.actor.actor_id, lock_id),
            )
            if int(cursor.rowcount) != len(active_days):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock day transition conflicted"
                )
            cursor.execute(
                "UPDATE caregiver_availability_locks "
                "SET status='cancelled',is_active=NULL,released_by=%s,"
                "released_at=CURRENT_TIMESTAMP "
                "WHERE id=%s AND status='active' AND is_active=1",
                (command.actor.actor_id, lock_id),
            )
            if int(cursor.rowcount) != 1:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock transition conflicted"
                )
            cursor.execute(
                "INSERT INTO caregiver_availability_lock_events "
                "(lock_id,event_type,event_key,actor,reason,payload) "
                "VALUES (%s,'lock_cancelled',%s,%s,%s,%s)",
                (
                    lock_id,
                    f"rpre-lock:{sha256((candidate.replacement_event_identity or '').encode('utf-8')).hexdigest()}",
                    command.actor.actor_id,
                    command.reason,
                    _json({
                        "cause": "service_before_replacement",
                        "case_no": command.case_no,
                        "command_fingerprint": bundle_fingerprint(command),
                        "lock_id": lock_id,
                        "plan_id": int(locks[0]["plan_id"]),
                        "prior_active_days": prior_active_days,
                        "replacement_event_id": replacement_event_id,
                        "replacement_event_identity": candidate.replacement_event_identity,
                        "replacement_generation_identity": candidate.replacement_generation_identity,
                        "replacement_generation_id": replacement_generation_id,
                        "superseded_root_identity": waiting_roots[0].root_id,
                        "scenario": candidate.scenario.value,
                        "successor_round_identity": candidate.successor_round_identity,
                    }),
                ),
            )
            if int(cursor.rowcount) != 1:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock event insert failed"
                )

    def _require_r03_waiting_lock_readback(
        self,
        replacement_row: Mapping[str, Any],
        *,
        superseded_root_ids: tuple[str, ...],
        for_update: bool,
    ) -> None:
        suffix = " FOR UPDATE" if for_update else ""
        fingerprint = str(replacement_row["command_fingerprint"])
        event_key = "rpre-lock:" + sha256(
            str(replacement_row["replacement_event_identity"]).encode("utf-8")
        ).hexdigest()
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT lock_header.id,lock_header.plan_id,lock_header.status,lock_header.is_active,"
                "lock_header.released_by,lock_header.released_at,lock_event.actor,"
                "lock_event.event_type,lock_event.event_key,lock_event.payload "
                "FROM caregiver_availability_locks lock_header "
                "JOIN caregiver_matching_plans plan ON plan.id=lock_header.plan_id "
                "JOIN caregiver_availability_lock_events lock_event "
                "ON lock_event.lock_id=lock_header.id "
                "WHERE plan.case_no=%s AND lock_event.event_key=%s" + suffix,
                (replacement_row["case_no"], event_key),
            )
            locks = tuple(cursor.fetchall() or ())
            if len(locks) != 1:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock readback is not exact"
                )
            lock = locks[0]
            if (
                str(lock["status"]) != "cancelled"
                or lock.get("is_active") is not None
                or not str(lock.get("released_by") or "").strip()
                or lock.get("released_at") is None
                or lock.get("event_type") != "lock_cancelled"
                or lock.get("event_key") != event_key
                or lock.get("actor") != lock.get("released_by")
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock header readback is incomplete"
                )
            payload = lock["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            expected_payload = {
                "case_no": str(replacement_row["case_no"]),
                "cause": "service_before_replacement",
                "command_fingerprint": fingerprint,
                "lock_id": int(lock["id"]),
                "plan_id": int(lock["plan_id"]),
                "replacement_event_id": int(replacement_row["id"]),
                "replacement_event_identity": str(replacement_row["replacement_event_identity"]),
                "replacement_generation_id": int(replacement_row["replacement_generation_id"]),
                "replacement_generation_identity": str(replacement_row["replacement_generation_identity"]),
                "scenario": ReplacementScenario.R03.value,
                "successor_round_identity": str(replacement_row["successor_round_identity"]),
            }
            if not isinstance(payload, dict) or any(
                payload.get(key) != value for key, value in expected_payload.items()
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock event readback drift"
                )
            waiting_roots = tuple(
                identity
                for identity in superseded_root_ids
                if identity.startswith("scheduling.waiting-lock:")
            )
            if waiting_roots != (payload.get("superseded_root_identity"),):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock root readback drift"
                )
            cursor.execute(
                "SELECT id,segment_id,staff_id,lock_date,active_marker,released_by,released_at "
                "FROM caregiver_availability_lock_days WHERE lock_id=%s "
                "ORDER BY lock_date,segment_id,id" + suffix,
                (int(lock["id"]),),
            )
            days = tuple(cursor.fetchall() or ())
            if not days or any(
                day.get("active_marker") is not None
                or day.get("released_by") != lock.get("actor")
                or day.get("released_at") is None
                for day in days
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock day readback is incomplete"
                )
            persisted_days = [
                {
                    "lock_day_id": int(day["id"]),
                    "segment_id": int(day["segment_id"]),
                    "staff_id": int(day["staff_id"]),
                    "lock_date": day["lock_date"].isoformat(),
                }
                for day in days
            ]
            if payload.get("prior_active_days") != persisted_days:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement waiting lock day identity readback drift"
                )

    def _matching_source(self, request: object, *, for_update: bool) -> Mapping[str, Any]:
        return self.require_matching_source(
            None
            if self._matching_source_loader is None
            else self._matching_source_loader(request, for_update=for_update)
        )

    def _generation_ids(self, case_no: str, prior_version: int, result_version: int | None) -> tuple[int, int]:
        if result_version is None:
            raise ServiceBeforeReplacementPersistenceError("replacement generation version is required")
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,generation_number FROM scheduling_generations "
                "WHERE case_no=%s AND generation_number IN (%s,%s) "
                "ORDER BY generation_number FOR UPDATE",
                (case_no, prior_version, result_version),
            )
            rows = tuple(cursor.fetchall() or ())
        by_version = {int(row["generation_number"]): int(row["id"]) for row in rows}
        if prior_version not in by_version or result_version not in by_version:
            raise ServiceBeforeReplacementPersistenceError("replacement scheduling generations are incomplete")
        return by_version[prior_version], by_version[result_version]

    def _prior_replacement_event_id(
        self, identity: str, case_no: str, *, expected_generation_id: int | None = None
    ) -> int | None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,replacement_generation_id FROM scheduling_service_before_replacement_events "
                "WHERE replacement_event_identity=%s AND case_no=%s FOR UPDATE",
                (identity, case_no),
            )
            row = cursor.fetchone()
        if row is not None:
            try:
                if (
                    expected_generation_id is not None
                    and int(row["replacement_generation_id"]) != expected_generation_id
                ):
                    raise ServiceBeforeReplacementPersistenceError(
                        "replacement prior event generation binding drift"
                    )
                return int(row["id"])
            except (KeyError, TypeError, ValueError) as error:
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement prior event identity is malformed"
                ) from error
        match = re.fullmatch(r"scheduling-rebuild-event:(.+):(\d+)", str(identity))
        if match is None or match.group(1) != case_no:
            raise ServiceBeforeReplacementPersistenceError(
                "replacement prior event identity is unavailable"
            )
        rebuild_id = int(match.group(2))
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,case_no,new_generation_id,previous_generation_id,"
                "expected_scheduling_version,resulting_scheduling_version "
                "FROM scheduling_rebuild_events WHERE id=%s AND case_no=%s FOR UPDATE",
                (rebuild_id, case_no),
            )
            rebuild = cursor.fetchone()
        if rebuild is None:
            raise ServiceBeforeReplacementPersistenceError(
                "replacement rebuild predecessor is unavailable"
            )
        try:
            if (
                int(rebuild["id"]) != rebuild_id
                or rebuild["case_no"] != case_no
                or expected_generation_id is not None
                and int(rebuild["new_generation_id"]) != expected_generation_id
                or int(rebuild["resulting_scheduling_version"])
                != int(rebuild["expected_scheduling_version"]) + 1
            ):
                raise ServiceBeforeReplacementPersistenceError(
                    "replacement rebuild predecessor binding drift"
                )
        except (KeyError, TypeError, ValueError) as error:
            raise ServiceBeforeReplacementPersistenceError(
                "replacement rebuild predecessor is malformed"
            ) from error
        return None

    def _insert_event(self, command, candidate, proof, prior_event_id, prior_generation_id, replacement_generation_id):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO scheduling_service_before_replacement_events "
                "(replacement_event_identity,prior_replacement_event_id,case_no,scenario,"
                "prior_generation_id,replacement_generation_id,prior_generation_identity,"
                "replacement_generation_identity,prior_event_identity,expected_aggregate_version,"
                "resulting_aggregate_version,expected_generation_version,resulting_generation_version,"
                "expected_event_version,resulting_event_version,zero_service_proof_identity,"
                "zero_service_proof_owner,zero_service_proof_contract_version,"
                "zero_service_source_projection_identity,zero_service_source_projection_version,"
                "zero_service_proof_version,zero_service_proof_fingerprint,official_service_day_count,"
                "replacement_reason,reason_evidence_digest,command_fingerprint,preview_fingerprint,"
                "actor_id,capability_atom,idempotency_key,correlation_id) VALUES ("
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    candidate.replacement_event_identity, prior_event_id, command.case_no, candidate.scenario.value,
                    prior_generation_id, replacement_generation_id, candidate.prior_generation_identity,
                    candidate.replacement_generation_identity, candidate.prior_event_identity,
                    candidate.expected_aggregate_version, candidate.resulting_aggregate_version,
                    candidate.expected_generation_version, candidate.resulting_generation_version,
                    candidate.expected_event_version, candidate.resulting_event_version,
                    proof.source_identity, "scheduling_official_service_projection", 1,
                    proof.source_identity, proof.source_version, proof.source_version, proof.fingerprint.value,
                    len(proof.service_dates), command.reason, _evidence_digest(command.evidence),
                    bundle_fingerprint(command), candidate.fingerprint.value, command.actor.actor_id,
                    command.actor.permission_scope[0] if command.actor.permission_scope else "scheduling.replace",
                    command.idempotency_key.value, command.correlation_id.value,
                ),
            )
            return int(cursor.lastrowid)

    def _insert_roots(self, event_id: int, case_no: str, candidate: ServiceBeforeReplacementCandidate) -> None:
        for disposition, roots in (
            ("retained", candidate.retained_roots),
            ("superseded", candidate.superseded_roots),
            ("created", candidate.created_roots),
        ):
            for ordinal, root in enumerate(sorted(roots, key=lambda item: item.root_id), 1):
                owner = "matching" if root.kind.value in _MATCHING_ROOT_KINDS else "scheduling"
                descriptor = f"service-before-replacement.{owner}.{root.kind.value}"
                fingerprint = _descriptor_fingerprint(owner, root.kind.value, descriptor)
                with _cursor(self._connection) as cursor:
                    cursor.execute(
                        "INSERT INTO scheduling_service_before_replacement_roots "
                        "(replacement_event_id,case_no,root_identity,owner_domain,root_kind,"
                        "disposition,canonical_ordinal,owner_descriptor_identity,"
                        "owner_descriptor_version,owner_descriptor_fingerprint) VALUES "
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (event_id, case_no, root.root_id, owner, root.kind.value, disposition,
                         ordinal, descriptor, 1, fingerprint),
                    )

    def _insert_successor(self, event_id, command, candidate, generation_id, successor):
        proof = candidate.candidate_pool_reuse_proof
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO scheduling_service_before_replacement_successors "
                "(replacement_event_id,case_no,replacement_generation_id,matching_package_lineage_id,"
                "matching_event_id,successor_package_identity,successor_round_identity,"
                "successor_matching_event_identity,scenario,expected_generation_version,"
                "expected_event_version,candidate_count,zero_candidate_disposition,reuse_proof_variant,"
                "reuse_pool_identity,reuse_round_identity,reuse_coverage_version,reuse_availability_version,"
                "reuse_willingness_version,reuse_candidate_identity,reuse_accepted_candidate,"
                "reuse_proof_fingerprint,resume_step) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_id, command.case_no, generation_id, successor.package_lineage_id,
                    successor.matching_event_id, successor.package_identity, successor.round_identity,
                    successor.event_identity, candidate.scenario.value, candidate.expected_generation_version,
                    candidate.expected_event_version, successor.candidate_count,
                    "blocked_no_candidate" if candidate.scenario.value == "R-07" else None,
                    "candidate_pool_reused" if proof is not None else "not_reused",
                    None if proof is None else proof.pool_identity,
                    None if proof is None else proof.round_identity,
                    None if proof is None else proof.coverage_version,
                    None if proof is None else proof.availability_version,
                    None if proof is None else proof.willingness_version,
                    None if proof is None else proof.candidate_identity,
                    None if proof is None else int(proof.accepted_candidate),
                    None if proof is None else proof.fingerprint.value,
                    candidate.resume_step.value,
                ),
            )
            return int(cursor.lastrowid)

    def _insert_receipt(self, event_id, successor_id, command, candidate, receipt, root_sets):
        retained, superseded, created = root_sets
        if (receipt.retained_root_set_digest and receipt.retained_root_set_digest != root_set_digest(retained)):
            raise ServiceBeforeReplacementPersistenceError("retained root digest drift")
        if (receipt.superseded_root_set_digest and receipt.superseded_root_set_digest != root_set_digest(superseded)):
            raise ServiceBeforeReplacementPersistenceError("superseded root digest drift")
        if (receipt.created_root_set_digest and receipt.created_root_set_digest != root_set_digest(created)):
            raise ServiceBeforeReplacementPersistenceError("created root digest drift")
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO scheduling_service_before_replacement_receipts "
                "(receipt_identity,replacement_event_id,successor_binding_id,case_no,idempotency_key,"
                "root_set_digest_contract,command_fingerprint,preview_fingerprint,"
                "retained_root_set_digest,retained_root_count,superseded_root_set_digest,"
                "superseded_root_count,created_root_set_digest,created_root_count,resulting_aggregate_version,"
                "resulting_generation_version,resulting_event_version,outbox_identity,result_state) "
                "VALUES (%s,%s,%s,%s,%s,'sha256_newline_v1',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'applied')",
                (
                    receipt.receipt_identity, event_id, successor_id, command.case_no,
                    command.idempotency_key.value, receipt.command_fingerprint.value,
                    receipt.preview_fingerprint.value, root_set_digest(retained), len(retained),
                    root_set_digest(superseded), len(superseded), root_set_digest(created),
                    len(created), receipt.resulting_aggregate_version,
                    receipt.resulting_generation_version, receipt.resulting_event_version,
                    receipt.outbox_identity,
                ),
            )

    def _insert_outbox(self, event_id, command, receipt):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO scheduling_service_before_replacement_outbox "
                "(replacement_event_id,receipt_id,case_no,outbox_identity,intent_type,target_owner,bounded_payload) "
                "SELECT event.id,receipt.id,%s,%s,'successor_projection_readback_requested',"
                "'orders_anomalies_projection',%s FROM scheduling_service_before_replacement_events event "
                "JOIN scheduling_service_before_replacement_receipts receipt ON receipt.replacement_event_id=event.id "
                "WHERE event.id=%s AND receipt.receipt_identity=%s",
                (command.case_no, receipt.outbox_identity, _json({"case_no": command.case_no, "receipt_identity": receipt.receipt_identity}), event_id, receipt.receipt_identity),
            )
            if int(cursor.rowcount) != 1:
                raise ServiceBeforeReplacementPersistenceError("replacement outbox binding missing")

    def _last_event_id(self, cursor, case_no: str) -> int:
        cursor.execute(
            "SELECT id FROM scheduling_service_before_replacement_events WHERE case_no=%s ORDER BY id DESC LIMIT 1",
            (case_no,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ServiceBeforeReplacementPersistenceError("replacement event readback missing")
        return int(row["id"])

    def _read_root_sets(self, event_id: int, case_no: str, *, for_update: bool = False):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT root_identity,disposition,canonical_ordinal,owner_domain,root_kind,"
                "owner_descriptor_identity,owner_descriptor_version,owner_descriptor_fingerprint "
                "FROM scheduling_service_before_replacement_roots "
                "WHERE replacement_event_id=%s AND case_no=%s ORDER BY disposition,canonical_ordinal" + suffix,
                (event_id, case_no),
            )
            rows = tuple(cursor.fetchall() or ())
        grouped = {"retained": [], "superseded": [], "created": []}
        for row in rows:
            owner = str(row["owner_domain"])
            kind = str(row["root_kind"])
            descriptor = f"service-before-replacement.{owner}.{kind}"
            if str(row["owner_descriptor_identity"]) != descriptor or int(row["owner_descriptor_version"]) != 1:
                raise ServiceBeforeReplacementPersistenceError("replacement root descriptor drift")
            if str(row["owner_descriptor_fingerprint"]) != _descriptor_fingerprint(owner, kind, descriptor):
                raise ServiceBeforeReplacementPersistenceError("replacement root descriptor fingerprint drift")
            grouped[str(row["disposition"])].append(str(row["root_identity"]))
        for disposition, values in grouped.items():
            ordinals = [int(row["canonical_ordinal"]) for row in rows if str(row["disposition"]) == disposition]
            if ordinals != list(range(1, len(values) + 1)):
                raise ServiceBeforeReplacementPersistenceError("replacement root ordinals are not canonical")
        return tuple(tuple(grouped[name]) for name in ("retained", "superseded", "created"))


_MATCHING_ROOT_KINDS = frozenset({
    "candidate_binding", "willingness", "matching_plan", "matching_segment", "matching_reply",
    "recipient_confirmation", "successor_round",
})


def root_set_digest(values: tuple[str, ...] | list[str]) -> str:
    return sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def _descriptor_fingerprint(owner: str, kind: str, identity: str) -> str:
    return PreviewFingerprint(
        fingerprint_payload({"owner": owner, "kind": kind, "identity_path": identity, "version": 1}).value
    ).value


def _evidence_digest(values: tuple[str, ...]) -> str:
    return root_set_digest(values)


def bundle_fingerprint(command) -> str:
    from subsystems.scheduling.service_before_replacement_workflow import replacement_command_fingerprint
    return replacement_command_fingerprint(command).value


def _replace_receipt_roots(receipt, roots):
    return replace(
        receipt,
        retained_root_ids=roots[0],
        superseded_root_ids=roots[1],
        created_root_ids=roots[2],
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


@contextmanager
def _cursor(connection: Any) -> Iterator[Any]:
    with connection.cursor() as cursor:
        yield cursor


__all__ = ["MySqlServiceBeforeReplacementRepository", "ServiceBeforeReplacementPersistenceError", "root_set_digest"]
