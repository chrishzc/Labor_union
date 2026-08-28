"""
File: matching_successor_persistence_adapter.py
Description: 在借用交易內建立 Matching successor package 與 package_proposed event。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping, Protocol

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingCriteriaResult,
    CriterionStatus,
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    MatchingSourceVersion,
    canonical_source_tuple,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


class MatchingSuccessorPersistenceError(RuntimeError):
    """Fresh Matching facts or immutable lineage cannot satisfy the contract."""


@dataclass(frozen=True, slots=True)
class MatchingSuccessorPersistenceRequest:
    case_no: str
    successor_package_identity: str
    successor_round_identity: str
    successor_matching_event_identity: str
    scenario: str
    candidate_count: int
    source_snapshot: Mapping[str, Any]
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    candidate_disposition: str | None = None


@dataclass(frozen=True, slots=True)
class MatchingSuccessorPersistenceResult:
    package_lineage_id: int
    matching_event_id: int
    package_identity: str
    round_identity: str
    event_identity: str
    package_version: int
    event_version: int
    candidate_count: int = 0


class MatchingSuccessorPersistencePort(Protocol):
    def persist_successor(
        self, request: MatchingSuccessorPersistenceRequest
    ) -> MatchingSuccessorPersistenceResult: ...


class MatchingSuccessorPersistenceAdapter:
    """Borrow one connection; this adapter never begins, commits, or rolls back."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def persist_successor(
        self, request: MatchingSuccessorPersistenceRequest
    ) -> MatchingSuccessorPersistenceResult:
        snapshot = _validated_snapshot(request.source_snapshot, request.case_no)
        source_versions = snapshot["source_versions"]
        snapshot_id = str(snapshot["snapshot_id"])
        existing_snapshot = self._one(
            "SELECT id,snapshot_id,case_no,criteria_version,criteria_snapshot,"
            "source_version_tuple,criteria_digest "
            "FROM matching_coordination_criteria_snapshots "
            "WHERE snapshot_id=%s FOR UPDATE",
            (snapshot_id,),
        )
        if existing_snapshot is None:
            raise MatchingSuccessorPersistenceError("matching source snapshot missing")
        _validate_stored_snapshot(existing_snapshot, snapshot, request.case_no)
        snapshot_id_value = int(existing_snapshot["id"])

        parent = self._one(
            "SELECT id,package_id,criteria_snapshot_id,package_version,package_state,"
            "package_snapshot,source_version_tuple,package_digest "
            "FROM matching_coordination_package_lineage "
            "WHERE case_no=%s ORDER BY package_version DESC LIMIT 1 FOR UPDATE",
            (request.case_no,),
        )
        if parent is None:
            raise MatchingSuccessorPersistenceError("matching parent package missing")
        _validate_parent(parent, snapshot, snapshot_id_value)
        source_event_identity = str(snapshot.get("source_event_identity", ""))
        if not source_event_identity:
            raise MatchingSuccessorPersistenceError("matching source event is required")
        source_event = self._one(
            "SELECT id,event_id,case_no,criteria_snapshot_id,package_lineage_id "
            "FROM matching_coordination_events WHERE event_id=%s FOR UPDATE",
            (source_event_identity,),
        )
        if source_event is None:
            raise MatchingSuccessorPersistenceError("matching source event missing")
        if (
            str(source_event["event_id"]) != source_event_identity
            or str(source_event["case_no"]) != request.case_no
            or int(source_event["criteria_snapshot_id"]) != snapshot_id_value
            or int(source_event["package_lineage_id"]) != int(parent["id"])
        ):
            raise MatchingSuccessorPersistenceError("matching source event binding drift")
        package_version = int(parent["package_version"]) + 1
        package = _successor_package(request, snapshot, package_version)
        package_snapshot = _package_storage_payload(package)
        package_digest = package.fingerprint.value
        package_id = self._insert(
            "INSERT INTO matching_coordination_package_lineage "
            "(package_id,case_no,criteria_snapshot_id,parent_package_id,package_version,"
            "lineage_kind,package_state,package_snapshot,source_version_tuple,"
            "package_digest,actor_ref) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                request.successor_package_identity,
                request.case_no,
                snapshot_id_value,
                int(parent["id"]),
                package_version,
                "rematch",
                package.state.value,
                _json(package_snapshot),
                _json(source_versions),
                package_digest,
                request.actor.actor_id,
            ),
        )
        event_payload = {
            "event_type": "package_proposed",
            "case_no": request.case_no,
            "package_id": request.successor_package_identity,
            "round_identity": request.successor_round_identity,
            "candidate_count": len(package.candidate_results),
            "candidate_disposition": request.candidate_disposition,
            "scenario": request.scenario,
            "package_snapshot": package_snapshot,
            "source_event_identity": source_event_identity,
        }
        event_digest = fingerprint_payload(event_payload).value
        event_id = self._insert(
            "INSERT INTO matching_coordination_events "
            "(event_id,case_no,criteria_snapshot_id,package_lineage_id,event_type,"
            "expected_version,resulting_version,event_payload,source_version_tuple,"
            "event_digest,actor_ref,idempotency_key,correlation_id,occurred_at_utc) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                request.successor_matching_event_identity,
                request.case_no,
                snapshot_id_value,
                package_id,
                "package_proposed",
                package_version - 1,
                package_version,
                _json(event_payload),
                _json(source_versions),
                event_digest,
                request.actor.actor_id,
                f"matching-successor:{request.idempotency_key.value}",
                request.correlation_id.value,
                _utc_now(),
            ),
        )
        return MatchingSuccessorPersistenceResult(
            package_lineage_id=package_id,
            matching_event_id=event_id,
            package_identity=request.successor_package_identity,
            round_identity=request.successor_round_identity,
            event_identity=request.successor_matching_event_identity,
            package_version=package_version,
            event_version=package_version,
            candidate_count=len(package.candidate_results),
        )

    def _one(self, sql: str, params: tuple[Any, ...]) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        if row is not None and not isinstance(row, Mapping):
            raise MatchingSuccessorPersistenceError("dict cursor is required")
        return row

    def _insert(self, sql: str, params: tuple[Any, ...]) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            value = cursor.lastrowid
        if value is None or int(value) <= 0:
            raise MatchingSuccessorPersistenceError("matching insert did not return numeric id")
        return int(value)


MySqlMatchingSuccessorPersistenceAdapter = MatchingSuccessorPersistenceAdapter


def _validated_snapshot(value: Mapping[str, Any], case_no: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) and all(
        hasattr(value, name) for name in ("snapshot_id", "criteria_version", "criteria", "source_versions", "fingerprint")
    ):
        value = {
            "snapshot_id": value.snapshot_id,
            "case_no": value.case_no,
            "criteria_version": value.criteria_version,
            "criteria": value.criteria,
            "source_versions": [
                {
                    "source_kind": item.source_kind,
                    "source_id": item.source_id,
                    "version": item.version,
                    "fingerprint": item.fingerprint,
                }
                for item in value.source_versions
            ],
            "criteria_digest": value.fingerprint.value,
        }
    if not isinstance(value, Mapping):
        raise MatchingSuccessorPersistenceError("matching source snapshot is required")
    required = (
        "snapshot_id", "criteria_version", "criteria", "source_versions",
        "criteria_digest", "parent_package", "source_event_identity",
    )
    if any(key not in value for key in required):
        raise MatchingSuccessorPersistenceError("matching source snapshot is incomplete")
    if "case_no" in value and str(value["case_no"]) != case_no:
        raise MatchingSuccessorPersistenceError("matching source case identity mismatch")
    if not isinstance(value["criteria"], Mapping) or not value["criteria"]:
        raise MatchingSuccessorPersistenceError("matching criteria source is incomplete")
    if not isinstance(value["source_versions"], (list, tuple)) or not value["source_versions"]:
        raise MatchingSuccessorPersistenceError("matching source versions are incomplete")
    try:
        versions = canonical_source_tuple(
            tuple(
                item if isinstance(item, MatchingSourceVersion) else MatchingSourceVersion(**dict(item))
                for item in value["source_versions"]
            )
        )
    except (TypeError, ValueError) as error:
        raise MatchingSuccessorPersistenceError("matching source versions are invalid") from error
    digest = str(value["criteria_digest"])
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise MatchingSuccessorPersistenceError("matching source digest is invalid")
    expected = fingerprint_payload({
        "case_no": case_no,
        "criteria": value["criteria"],
        "criteria_version": int(value["criteria_version"]),
        "source_versions": [item.as_payload() for item in versions],
    }).value
    if digest != expected:
        raise MatchingSuccessorPersistenceError("matching source criteria digest drift")
    normalized = dict(value)
    normalized["source_versions"] = _source_payload(versions)
    return normalized


def _successor_package(
    request: MatchingSuccessorPersistenceRequest,
    snapshot: Mapping[str, Any],
    version: int,
) -> MatchingPackage:
    """Build only the canonical package understood by Matching readers.

    A successor never reconstructs candidate/segment facts from a count or a
    root id.  Those facts must be carried by the fresh source package.  The
    one intentional empty representation is ``candidate_pool_open``.
    """
    raw = snapshot.get("reuse_package")
    source_versions = _canonical_versions(snapshot.get("source_versions", ()))
    if raw is None:
        if request.candidate_count:
            raise MatchingSuccessorPersistenceError(
                "fresh matching package facts are required for non-empty successor"
            )
        return MatchingPackage(
            package_id=request.successor_package_identity,
            version=version,
            mode=MatchingPackageMode.SINGLE,
            segments=(),
            required_service_dates=tuple(_dates(snapshot.get("required_service_dates", ()))),
            candidate_results=(),
            criteria_snapshot_id=str(snapshot["snapshot_id"]),
            source_versions=source_versions,
            state=MatchingPackageState.CANDIDATE_POOL_OPEN,
        )
    if isinstance(raw, MatchingPackage):
        package = raw
    elif isinstance(raw, Mapping):
        package = _package_from_payload(raw)
    else:
        raise MatchingSuccessorPersistenceError("fresh matching package facts are invalid")
    if package.criteria_snapshot_id != str(snapshot["snapshot_id"]):
        raise MatchingSuccessorPersistenceError("matching package criteria binding drift")
    if source_versions and package.source_versions != source_versions:
        raise MatchingSuccessorPersistenceError("matching package source tuple drift")
    if request.candidate_count != len(package.candidate_results):
        raise MatchingSuccessorPersistenceError("matching candidate count does not match fresh package")
    return MatchingPackage(
        package_id=request.successor_package_identity,
        version=version,
        mode=package.mode,
        segments=package.segments,
        required_service_dates=package.required_service_dates,
        candidate_results=package.candidate_results,
        criteria_snapshot_id=package.criteria_snapshot_id,
        source_versions=package.source_versions,
        state=package.state,
        blockers=package.blockers,
        warnings=package.warnings,
    )


def _canonical_versions(value: Any) -> tuple[MatchingSourceVersion, ...]:
    try:
        return canonical_source_tuple(tuple(
            item if isinstance(item, MatchingSourceVersion) else MatchingSourceVersion(**dict(item))
            for item in value
        ))
    except (TypeError, ValueError) as error:
        raise MatchingSuccessorPersistenceError("matching source versions are invalid") from error


def _dates(values: Any) -> tuple[Any, ...]:
    from datetime import date
    try:
        return tuple(item if isinstance(item, date) else date.fromisoformat(str(item)) for item in values)
    except (TypeError, ValueError) as error:
        raise MatchingSuccessorPersistenceError("matching service dates are invalid") from error


def _package_from_payload(value: Mapping[str, Any]) -> MatchingPackage:
    try:
        candidates = tuple(
            MatchingCandidateResult(
                candidate_id=str(item["candidate_id"]), staff_id=int(item["staff_id"]),
                eligibility=CandidateEligibility(item["eligibility"]),
                criteria_results=tuple(
                    MatchingCriteriaResult(
                        code=str(result["code"]), status=CriterionStatus(result["status"]),
                        source_version=MatchingSourceVersion(**dict(result["source_version"])),
                        detail=str(result.get("detail", "")),
                    ) for result in item.get("criteria_results", ())
                ),
                rejection_reasons=tuple(item.get("rejection_reasons", ())),
                coverage_evidence=_dates(item.get("coverage_evidence", ())),
                willingness=str(item.get("willingness", "unconfirmed")),
                notification_lineage=tuple(item.get("notification_lineage", ())),
                staff_name=str(item.get("staff_name", "")),
            ) for item in value.get("candidate_results", ())
        )
        return MatchingPackage(
            package_id=str(value["package_id"]), version=int(value["version"]),
            mode=MatchingPackageMode(value["mode"]),
            segments=tuple(MatchingSegment(int(item["staff_id"]), _dates(item.get("service_dates", ())), int(item["sequence"])) for item in value.get("segments", ())),
            required_service_dates=_dates(value.get("required_service_dates", ())),
            candidate_results=candidates,
            criteria_snapshot_id=str(value["criteria_snapshot_id"]),
            source_versions=_canonical_versions(value["source_versions"]),
            state=MatchingPackageState(value.get("state", "proposed")),
            blockers=tuple(value.get("blockers", ())), warnings=tuple(value.get("warnings", ())),
            fingerprint=PreviewFingerprint(str(value["fingerprint"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MatchingSuccessorPersistenceError("fresh matching package facts are invalid") from error


def _validate_stored_snapshot(
    row: Mapping[str, Any], snapshot: Mapping[str, Any], case_no: str
) -> None:
    stored_criteria = _json_value(row.get("criteria_snapshot"))
    stored_versions = _canonical_versions(_json_value(row.get("source_version_tuple")))
    expected_versions = _canonical_versions(snapshot["source_versions"])
    if (
        str(row.get("snapshot_id")) != str(snapshot["snapshot_id"])
        or str(row.get("case_no")) != case_no
        or int(row.get("criteria_version", -1)) != int(snapshot["criteria_version"])
        or stored_criteria != dict(snapshot["criteria"])
        or stored_versions != expected_versions
        or str(row.get("criteria_digest")) != str(snapshot["criteria_digest"])
    ):
        raise MatchingSuccessorPersistenceError("matching source snapshot drift")


def _validate_parent(
    row: Mapping[str, Any], snapshot: Mapping[str, Any], snapshot_id: int
) -> None:
    stored_payload = _json_value(row.get("package_snapshot"))
    if not isinstance(stored_payload, Mapping):
        raise MatchingSuccessorPersistenceError("matching parent package snapshot is invalid")
    stored_package = _package_from_payload(stored_payload)
    fresh_value = snapshot.get("parent_package")
    if isinstance(fresh_value, MatchingPackage):
        fresh_package = fresh_value
    elif isinstance(fresh_value, Mapping):
        fresh_package = _package_from_payload(fresh_value)
    else:
        raise MatchingSuccessorPersistenceError("fresh matching parent package is invalid")
    stored_sources = _canonical_versions(_json_value(row.get("source_version_tuple")))
    if (
        int(row.get("criteria_snapshot_id", 0)) != snapshot_id
        or stored_package != fresh_package
        or str(row.get("package_id")) != fresh_package.package_id
        or int(row.get("package_version", -1)) != fresh_package.version
        or str(row.get("package_state")) != fresh_package.state.value
        or stored_sources != fresh_package.source_versions
        or str(row.get("package_digest")) != fresh_package.fingerprint.value
    ):
        raise MatchingSuccessorPersistenceError("matching parent package binding drift")


def _package_storage_payload(package: MatchingPackage) -> dict[str, Any]:
    return {
        "blockers": list(package.blockers),
        "candidate_results": [
            {
                "candidate_id": item.candidate_id,
                "coverage_evidence": [day.isoformat() for day in item.coverage_evidence],
                "criteria_results": [
                    {
                        "code": result.code,
                        "detail": result.detail,
                        "source_version": _source_mapping(result.source_version),
                        "status": result.status.value,
                    }
                    for result in item.criteria_results
                ],
                "eligibility": item.eligibility.value,
                "notification_lineage": list(item.notification_lineage),
                "rejection_reasons": list(item.rejection_reasons),
                "staff_id": item.staff_id,
                "staff_name": item.staff_name,
                "willingness": item.willingness,
            }
            for item in package.candidate_results
        ],
        "criteria_snapshot_id": package.criteria_snapshot_id,
        "fingerprint": package.fingerprint.value,
        "mode": package.mode.value,
        "package_id": package.package_id,
        "required_service_dates": [day.isoformat() for day in package.required_service_dates],
        "segments": [
            {
                "sequence": item.sequence,
                "service_dates": [day.isoformat() for day in item.service_dates],
                "staff_id": item.staff_id,
            }
            for item in package.segments
        ],
        "source_versions": _source_payload(package.source_versions),
        "state": package.state.value,
        "version": package.version,
        "warnings": list(package.warnings),
    }


def _source_payload(values: tuple[MatchingSourceVersion, ...]) -> list[dict[str, Any]]:
    return [_source_mapping(item) for item in values]


def _source_mapping(value: MatchingSourceVersion) -> dict[str, Any]:
    return {
        "source_kind": value.source_kind,
        "source_id": value.source_id,
        "version": value.version,
        "fingerprint": value.fingerprint,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (TypeError, ValueError) as error:
            raise MatchingSuccessorPersistenceError("matching stored JSON is invalid") from error
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


__all__ = [
    "MatchingSuccessorPersistenceAdapter",
    "MatchingSuccessorPersistenceError",
    "MatchingSuccessorPersistencePort",
    "MatchingSuccessorPersistenceRequest",
    "MatchingSuccessorPersistenceResult",
    "MySqlMatchingSuccessorPersistenceAdapter",
]
