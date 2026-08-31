"""Read-only MySQL composition for Finance Import ``IMPORT-006`` facts.

The adapter locks the Finance Import batch contract before loading the bounded
membership aggregates.  It never writes an anomaly projection and never
derives source-correction lineage from weak fields.  Source-correction
lineage is read from its immutable owner table and its successor is re-read
through the same owner facts before it can be terminal.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pymysql.err import IntegrityError

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from domains.finance_import.anomaly_remediation import (
    FinanceImportIntegrityCounts,
    FinanceImportIntegrityOwnerFact,
    FinanceImportIntegrityRepairPath,
    FinanceImportSourceCorrectionApplyRequest,
    FinanceImportSourceCorrectionLineage,
    build_finance_import_integrity_owner_fact,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.finance_import.current_anomaly_facts import (
    FINANCE_IMPORT_ANOMALY_OWNER_DOMAIN,
    FINANCE_IMPORT_ANOMALY_OWNER_ROOT_TYPE,
    IMPORT_006_SUBJECT_TYPE,
)


class FinanceImportSourceCorrectionConflict(ValueError):
    """Raised when one original batch/version is linked to another successor."""


class MySqlFinanceImportCurrentIssueAdapter:
    """Compose Finance Import root facts from one fresh, locked batch snapshot."""

    def __init__(
        self,
        connection: Any,
        source_correction_reader: Callable[[str, int], FinanceImportSourceCorrectionLineage | None] | None = None,
    ) -> None:
        self._connection = connection
        self._source_correction_reader = source_correction_reader or self.read_source_correction_lineage

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        _validate_scope(scope)
        facts = tuple(self._read_fact(subject, for_update=True) for subject in scope.subject_ids)
        token = fingerprint_payload(
            {
                "scope": tuple(scope.subject_ids),
                "facts": tuple(_fact_payload(fact) for fact in facts),
            }
        ).value
        return OwnerSnapshot(
            scope,
            token,
            max((fact.batch_version for fact in facts), default=0),
            facts,
            all(fact.authoritative_complete for fact in facts),
        )

    def read_integrity(
        self, batch_identity: str, *, for_update: bool = False
    ) -> FinanceImportIntegrityOwnerFact:
        _validate_batch_identity(batch_identity)
        return self._read_fact(batch_identity, for_update=for_update)

    def append_source_correction_lineage(
        self,
        request: FinanceImportSourceCorrectionApplyRequest,
        lineage: FinanceImportSourceCorrectionLineage | None = None,
    ) -> str:
        """Append an owner-verified original-to-successor relation.

        ``lineage`` remains an ignored compatibility input for older callers;
        all successor flags are recomputed from fresh owner facts here.
        """

        if not isinstance(request, FinanceImportSourceCorrectionApplyRequest):
            raise TypeError("Finance Import source correction Apply request is required")
        if lineage is not None and not isinstance(lineage, FinanceImportSourceCorrectionLineage):
            raise TypeError("Finance Import source correction lineage is invalid")
        if lineage is not None and (
            lineage.original_batch_identity != request.original_batch_identity
            or lineage.original_batch_version != request.expected_original_batch_version
            or lineage.corrected_successor_batch_identity != request.corrected_successor_batch_identity
            or lineage.corrected_successor_version != request.corrected_successor_batch_version
        ):
            raise ValueError("Finance Import source correction lineage does not match Apply request")

        existing = self._load_lineage_row(
            request.original_batch_identity,
            request.expected_original_batch_version,
        )
        if existing is not None:
            if _lineage_row_matches_request(existing, request):
                return f"finance-import-source-correction:{int(existing['id'])}"
            raise FinanceImportSourceCorrectionConflict(
                "finance_import_source_correction_lineage_conflict"
            )

        original = self.read_integrity(request.original_batch_identity, for_update=True)
        if original.batch_version != request.expected_original_batch_version:
            raise ValueError("finance_import_source_correction_original_stale")
        if not original.predicate_active:
            raise ValueError("finance_import_source_correction_original_not_active")
        successor = self.read_integrity(
            request.corrected_successor_batch_identity,
            for_update=True,
        )
        if successor.batch_version != request.corrected_successor_batch_version:
            raise ValueError("finance_import_source_correction_successor_version_mismatch")
        if not successor.authoritative_complete:
            raise ValueError("finance_import_source_correction_successor_not_completed")
        if successor.predicate_active:
            raise ValueError("finance_import_source_correction_successor_incomplete")

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _SOURCE_CORRECTION_LINEAGE_INSERT_SQL,
                    (
                        original.batch_id,
                        request.original_batch_identity,
                        request.expected_original_batch_version,
                        successor.batch_id,
                        request.corrected_successor_batch_identity,
                        request.corrected_successor_batch_version,
                        request.actor,
                        request.reason,
                        request.evidence_reference,
                    ),
                )
                lineage_id = getattr(cursor, "lastrowid", None)
        except IntegrityError as error:
            if not error.args or int(error.args[0]) != 1062:
                raise
            existing = self._load_lineage_row(
                request.original_batch_identity,
                request.expected_original_batch_version,
            )
            if existing is not None and _lineage_row_matches_request(existing, request):
                return f"finance-import-source-correction:{int(existing['id'])}"
            raise FinanceImportSourceCorrectionConflict(
                "finance_import_source_correction_lineage_conflict"
            ) from error
        if lineage_id is None:
            raise RuntimeError("finance_import_source_correction_lineage_insert_failed")
        return f"finance-import-source-correction:{int(lineage_id)}"

    def read_source_correction_lineage(
        self,
        original_batch_identity: str,
        original_batch_version: int,
    ) -> FinanceImportSourceCorrectionLineage | None:
        """Read persisted identity fields and verify successor facts freshly."""

        _validate_batch_identity(original_batch_identity)
        if isinstance(original_batch_version, bool) or not isinstance(original_batch_version, int):
            raise ValueError("original batch version is invalid")
        row = self._load_lineage_row(original_batch_identity, original_batch_version)
        if row is None:
            return None
        successor_identity = str(row["corrected_successor_batch_identity"])
        successor_version = _nonnegative_int(
            row["corrected_successor_version"],
            "corrected successor batch version",
        )
        if (
            int(row["original_batch_id"]) != _batch_database_id(original_batch_identity)
            or int(row["corrected_successor_batch_id"]) != _batch_database_id(successor_identity)
        ):
            raise ValueError("finance_import_source_correction_lineage_identity_mismatch")
        try:
            successor = self._read_fact(
                successor_identity,
                for_update=True,
                resolve_source_correction=False,
            )
        except ValueError as error:
            if str(error) != "finance_import_batch_not_found":
                raise
            return FinanceImportSourceCorrectionLineage(
                original_batch_identity,
                original_batch_version,
                successor_identity,
                successor_version,
                successor_unique=False,
                successor_completed=False,
                successor_fresh_verified=False,
                successor_covers_all_current_problems=False,
                accepted_in_owner_uow=True,
            )
        if successor.batch_version != successor_version:
            return FinanceImportSourceCorrectionLineage(
                original_batch_identity,
                original_batch_version,
                successor_identity,
                successor_version,
                successor_unique=True,
                successor_completed=False,
                successor_fresh_verified=True,
                successor_covers_all_current_problems=False,
                accepted_in_owner_uow=True,
            )
        return FinanceImportSourceCorrectionLineage(
            original_batch_identity,
            original_batch_version,
            successor_identity,
            successor_version,
            successor_unique=True,
            successor_completed=successor.authoritative_complete,
            successor_fresh_verified=bool(successor.owner_snapshot_token),
            successor_covers_all_current_problems=not successor.predicate_active,
            accepted_in_owner_uow=True,
        )

    def _load_lineage_row(self, original_batch_identity: str, original_batch_version: int):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _SOURCE_CORRECTION_LINEAGE_SELECT_SQL,
                (original_batch_identity, original_batch_version),
            )
            row = cursor.fetchone()
        if row is not None and not isinstance(row, Mapping):
            raise TypeError("Finance Import source correction lineage row is invalid")
        return row

    def _read_fact(
        self,
        subject_identity: str,
        *,
        for_update: bool,
        resolve_source_correction: bool = True,
    ) -> FinanceImportIntegrityOwnerFact:
        batch_identity = _validate_batch_identity(subject_identity)
        locking = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            # Lock the canonical owner contract before reading any membership
            # or reprocess aggregate.  This keeps batch_version and all
            # derived counts in one owner snapshot.
            cursor.execute(_BATCH_CONTRACT_SQL + locking, (batch_identity,))
            contract = cursor.fetchone()
            if contract is None:
                raise ValueError("finance_import_batch_not_found")
            if not isinstance(contract, Mapping):
                raise TypeError("Finance Import owner contract row is invalid")
            cursor.execute(
                _INTEGRITY_COUNTS_SQL,
                (contract["batch_id"], contract["batch_id"]),
            )
            counts = cursor.fetchone()
        if counts is None:
            raise ValueError("finance_import_batch_not_found")
        if not isinstance(counts, Mapping):
            raise TypeError("Finance Import owner aggregate row is invalid")
        row = {**contract, **counts}

        batch_version = _nonnegative_int(row.get("batch_version"), "batch version")
        row_count = _nonnegative_int(row.get("row_count"), "batch row count")
        counts = FinanceImportIntegrityCounts(
            row_count,
            _nonnegative_int(row.get("occurrence_count"), "occurrence count"),
            _nonnegative_int(row.get("distinct_canonical_count"), "distinct canonical count"),
            _nonnegative_int(row.get("non_pending_inconsistent_count"), "non-pending inconsistent count"),
            _nonnegative_int(row.get("partial_batch_count"), "partial batch count"),
        )
        status = str(row.get("status") or "")
        authoritative_complete = status == "completed" and bool(row.get("complete_readback", 1))
        source_correction = None
        if resolve_source_correction and self._source_correction_reader is not None:
            source_correction = self._source_correction_reader(batch_identity, batch_version)
            if source_correction is not None and not isinstance(
                source_correction, FinanceImportSourceCorrectionLineage
            ):
                raise TypeError("Finance Import source correction lineage is invalid")
        repair_path = (
            FinanceImportIntegrityRepairPath.SOURCE_CORRECTION
            if source_correction is not None
            else FinanceImportIntegrityRepairPath.DERIVED_REBUILD
        )
        token = fingerprint_payload(_canonical_row(row)).value
        return build_finance_import_integrity_owner_fact(
            batch_identity,
            batch_version,
            token,
            counts,
            authoritative_complete=authoritative_complete,
            canonical_roots_valid=counts.integrity_inconsistent_count == 0,
            projection_consistent=True,
            repair_path=repair_path,
            source_correction=source_correction,
        )


def _validate_scope(scope: RecheckScope) -> None:
    if (
        scope.owner_domain != FINANCE_IMPORT_ANOMALY_OWNER_DOMAIN
        or scope.owner_root_type != FINANCE_IMPORT_ANOMALY_OWNER_ROOT_TYPE
        or scope.subject_type != IMPORT_006_SUBJECT_TYPE
    ):
        raise ValueError("finance_import anomaly owner scope is invalid")
    for subject in scope.subject_ids:
        _validate_batch_identity(subject)


def _validate_batch_identity(value: str) -> str:
    prefix = "finance-import-batch:"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("finance_import batch identity is invalid")
    raw = value.removeprefix(prefix)
    if not raw.isdecimal() or int(raw) <= 0:
        raise ValueError("finance_import batch identity is invalid")
    return value


def _batch_database_id(value: str) -> int:
    return int(_validate_batch_identity(value).removeprefix("finance-import-batch:"))


def _nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field_name} is invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} is invalid") from error
    if parsed < 0:
        raise ValueError(f"{field_name} is invalid")
    return parsed


def _canonical_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): row[key] for key in sorted(row)}


def _fact_payload(fact: FinanceImportIntegrityOwnerFact) -> dict[str, Any]:
    return {
        "batch_identity": fact.batch_identity,
        "batch_version": fact.batch_version,
        "owner_snapshot_token": fact.owner_snapshot_token,
        "authoritative_complete": fact.authoritative_complete,
        "integrity_inconsistent_count": fact.integrity_inconsistent_count,
        "canonical_roots_valid": fact.canonical_roots_valid,
        "projection_consistent": fact.projection_consistent,
        "repair_path": fact.repair_path.value,
        "predicate_active": fact.predicate_active,
    }


_BATCH_CONTRACT_SQL = """
SELECT contract.batch_id, contract.batch_identity, contract.batch_version,
       batch.row_count, batch.status
FROM finance_import_batch_contracts contract
JOIN finance_import_batches batch ON batch.id=contract.batch_id
WHERE contract.batch_identity=%s
"""

_INTEGRITY_COUNTS_SQL = """
SELECT
       COUNT(occurrence.id) AS occurrence_count,
       COUNT(DISTINCT occurrence.finance_import_row_id) AS distinct_canonical_count,
       COALESCE(SUM(CASE WHEN bank_fact.classification_type='non_business_review'
                              AND bank_fact.reconciliation_status<>'pending'
                         THEN 1 ELSE 0 END), 0) AS non_pending_inconsistent_count,
       COALESCE((
           SELECT CASE WHEN run.dispatch_count <> run.reconciled_count + run.pending_count
                       THEN 1 ELSE 0 END
           FROM finance_import_reprocess_runs run
           WHERE run.batch_id=%s AND run.status='completed'
           ORDER BY run.completed_at DESC, run.id DESC LIMIT 1
       ), 0) AS partial_batch_count
FROM finance_import_occurrences occurrence
LEFT JOIN finance_import_rows bank_fact ON bank_fact.id=occurrence.finance_import_row_id
WHERE occurrence.batch_id=%s
"""

_SOURCE_CORRECTION_LINEAGE_SELECT_SQL = """
SELECT id, original_batch_identity, original_batch_version,
       original_batch_id,
       corrected_successor_batch_id,
       corrected_successor_batch_identity, corrected_successor_version,
       actor, reason, evidence_reference
FROM finance_import_source_correction_lineages
WHERE original_batch_identity=%s AND original_batch_version=%s
FOR UPDATE
"""

_SOURCE_CORRECTION_LINEAGE_INSERT_SQL = """
INSERT INTO finance_import_source_correction_lineages(
    original_batch_id, original_batch_identity, original_batch_version,
    corrected_successor_batch_id, corrected_successor_batch_identity,
    corrected_successor_version,
    actor, reason, evidence_reference
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""


def _lineage_row_matches_request(row: Mapping[str, Any], request: FinanceImportSourceCorrectionApplyRequest) -> bool:
    return (
        str(row["original_batch_identity"]) == request.original_batch_identity
        and int(row["original_batch_version"]) == request.expected_original_batch_version
        and str(row["corrected_successor_batch_identity"]) == request.corrected_successor_batch_identity
        and int(row["corrected_successor_version"]) == request.corrected_successor_batch_version
        and str(row["actor"]) == request.actor
        and str(row["reason"]) == request.reason
        and str(row["evidence_reference"]) == request.evidence_reference
    )


__all__ = [
    "FinanceImportSourceCorrectionConflict",
    "MySqlFinanceImportCurrentIssueAdapter",
]
