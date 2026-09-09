"""MySQL Knowledge, managed-log and append-only audit adapters for retention."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import pymysql

from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.mysql.line_repository_support import aware_utc, database_utc
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.runtime_governance.operational_retention import (
    RetentionCandidate,
    RetentionDeleteResult,
    RetentionEvidenceStore,
    RetentionIntent,
    RetentionReceipt,
    RetentionSourceSnapshot,
)


ConnectionFactory = Callable[[], object]
_TERMINAL_REQUESTS = ("answered", "unsupported", "failed")
_TERMINAL_JOBS = ("completed", "failed")
_KNOWLEDGE_TABLES = (
    "knowledge_answer_requests",
    "knowledge_jobs",
    "knowledge_indexes",
    "knowledge_answer_receipts",
    "knowledge_answer_sources",
)


class MySqlRetentionEvidenceStore(RetentionEvidenceStore):
    """Use immutable audit rows as cleanup intent, receipt and readback evidence."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def terminal_receipt(self, idempotency_key: str) -> RetentionReceipt | None:
        row = self._latest_row("operational_retention.terminal", idempotency_key)
        return _receipt_from_details(_details(row)) if row else None

    def pending_intent(self, idempotency_key: str) -> RetentionIntent | None:
        if self.terminal_receipt(idempotency_key) is not None:
            return None
        row = self._latest_row("operational_retention.intent", idempotency_key)
        return _intent_from_details(_details(row)) if row else None

    def append_intent(self, intent: RetentionIntent) -> None:
        self._append(
            action="operational_retention.intent",
            resource_id=intent.idempotency_key,
            actor_id=intent.actor_id,
            details=_intent_details(intent),
        )

    def append_terminal(self, receipt: RetentionReceipt, actor_id: str) -> None:
        self._append(
            action="operational_retention.terminal",
            resource_id=receipt.idempotency_key,
            actor_id=actor_id,
            details=_receipt_details(receipt),
        )

    def latest_by_source(self) -> dict[str, tuple[datetime, str]]:
        connection = self._connection_factory()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT details_json,created_at FROM admin_audit_logs "
                    "WHERE action='operational_retention.terminal' ORDER BY id DESC LIMIT 500"
                )
                rows = cursor.fetchall() or ()
        finally:
            connection.close()
        latest: dict[str, tuple[datetime, str]] = {}
        for row in rows:
            details = _details(row)
            source_id = str(details.get("source_id", ""))
            if not source_id or source_id in latest:
                continue
            latest[source_id] = (
                _aware_datetime(row["created_at"]),
                str(details.get("outcome", "unknown")),
            )
        return latest

    def _latest_row(self, action: str, idempotency_key: str):
        connection = self._connection_factory()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT details_json,created_at FROM admin_audit_logs "
                    "WHERE action=%s AND resource_type='operational_retention' "
                    "AND resource_id=%s ORDER BY id DESC LIMIT 1",
                    (action, idempotency_key),
                )
                return cursor.fetchone()
        finally:
            connection.close()

    def _append(self, *, action: str, resource_id: str, actor_id: str, details: dict) -> None:
        connection = self._connection_factory()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO admin_audit_logs "
                        "(admin_user_id,action,resource_type,resource_id,result_status,details_json) "
                        "VALUES (%s,%s,'operational_retention',%s,%s,%s)",
                        (
                            _admin_id(actor_id),
                            action,
                            resource_id,
                            202 if action.endswith(".intent") else 200,
                            json.dumps(details, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )
                unit_of_work.commit()
        finally:
            connection.close()


class MySqlKnowledgeRetentionSource:
    source_id = "knowledge-observations"

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        chroma_gateway: ChromaKnowledgeGateway,
        *,
        high_water_bytes: int | None,
        low_water_bytes: int | None,
    ) -> None:
        _validate_watermarks(high_water_bytes, low_water_bytes)
        self._connection_factory = connection_factory
        self._chroma = chroma_gateway
        self._high_water = high_water_bytes
        self._low_water = low_water_bytes

    def snapshot(self, now: datetime, retention_days: int) -> RetentionSourceSnapshot:
        cutoff = aware_utc(now) - timedelta(days=retention_days)
        connection = self._connection_factory()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                database_bytes = _knowledge_table_bytes(cursor)
                eligible_count, expired_count, oldest = _knowledge_counts(cursor, cutoff)
        finally:
            connection.close()
        try:
            vector_bytes = self._chroma.persistence_bytes()
        except Exception:
            vector_bytes = 0
        current_bytes = database_bytes + vector_bytes
        status = _capacity_status(current_bytes, self._high_water, self._low_water)
        estimate = int(current_bytes * expired_count / eligible_count) if eligible_count else 0
        return RetentionSourceSnapshot(
            self.source_id,
            "AI 客服技術觀測與舊索引",
            "database",
            "eligible",
            current_bytes,
            eligible_count,
            expired_count,
            oldest,
            estimate,
            self._high_water,
            self._low_water,
            status,
        )

    def candidates(
        self,
        *,
        cutoff_at_utc: datetime,
        limit: int,
    ) -> tuple[RetentionCandidate, ...]:
        connection = self._connection_factory()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                request_rows = _request_candidates(cursor, cutoff_at_utc, limit)
                remaining = max(0, limit - len(request_rows))
                job_rows = _job_candidates(cursor, cutoff_at_utc, remaining) if remaining else ()
                remaining = max(0, remaining - len(job_rows))
                index_rows = _index_candidates(cursor, cutoff_at_utc, remaining) if remaining else ()
        finally:
            connection.close()
        candidates = [
            _row_candidate("request", row, int(row.get("estimated_bytes") or 0))
            for row in request_rows
        ]
        candidates.extend(
            _row_candidate("job", row, int(row.get("estimated_bytes") or 0))
            for row in job_rows
        )
        for row in index_rows:
            version = int(row["id"])
            try:
                estimated = self._chroma.estimate_index_bytes(version)
            except Exception:
                estimated = int(row.get("estimated_bytes") or 0)
            candidates.append(_row_candidate("index", row, estimated))
        return tuple(sorted(candidates, key=lambda item: (item.occurred_at_utc, item.identity))[:limit])

    def delete(self, candidates: tuple[RetentionCandidate, ...]) -> RetentionDeleteResult:
        deleted = deleted_bytes = failed = 0
        error_code = None
        for candidate in candidates:
            try:
                removed = self._delete_one(candidate)
            except Exception:
                failed += 1
                error_code = "retention_source_delete_failed"
                continue
            if removed:
                deleted += 1
                deleted_bytes += candidate.estimated_bytes
            else:
                failed += 1
                error_code = "retention_source_reconciliation_required"
        return RetentionDeleteResult(deleted, deleted_bytes, failed, error_code)

    def rotate_oversized(self, now: datetime) -> int:
        return 0

    def _delete_one(self, candidate: RetentionCandidate) -> bool:
        kind, raw_id = candidate.identity.split(":", 1)
        connection = self._connection_factory()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    current = _locked_candidate(cursor, kind, int(raw_id))
                    if current is None:
                        unit_of_work.commit()
                        return True
                    current_candidate = _row_candidate(
                        kind,
                        current,
                        candidate.estimated_bytes,
                    )
                    if current_candidate.version != candidate.version:
                        unit_of_work.rollback()
                        return False
                    if kind == "index":
                        self._chroma.delete_index(int(raw_id))
                    if kind == "request":
                        cursor.execute(
                            "DELETE s FROM knowledge_answer_sources s "
                            "JOIN knowledge_answer_receipts r ON r.id=s.answer_receipt_id "
                            "WHERE r.answer_request_id=%s",
                            (raw_id,),
                        )
                        cursor.execute("DELETE FROM knowledge_answer_receipts WHERE answer_request_id=%s", (raw_id,))
                        cursor.execute("DELETE FROM knowledge_jobs WHERE answer_request_id=%s", (raw_id,))
                        cursor.execute("DELETE FROM knowledge_answer_requests WHERE id=%s", (raw_id,))
                    elif kind == "job":
                        cursor.execute(
                            "DELETE FROM knowledge_jobs WHERE id=%s AND answer_request_id IS NULL",
                            (raw_id,),
                        )
                    elif kind == "index":
                        cursor.execute("DELETE FROM knowledge_indexes WHERE index_version=%s", (raw_id,))
                    else:
                        raise ValueError("unsupported retention candidate")
                unit_of_work.commit()
                return True
        finally:
            connection.close()


class ManagedLogRetentionSource:
    source_id = "managed-logs"

    def __init__(
        self,
        roots: tuple[Path, ...],
        *,
        high_water_bytes: int | None,
        low_water_bytes: int | None,
        segment_max_bytes: int | None,
        max_files: int = 5000,
    ) -> None:
        _validate_watermarks(high_water_bytes, low_water_bytes)
        self._roots = tuple(_safe_root(root) for root in roots)
        self._high_water = high_water_bytes
        self._low_water = low_water_bytes
        self._segment_max = segment_max_bytes
        self._max_files = max_files

    def snapshot(self, now: datetime, retention_days: int) -> RetentionSourceSnapshot:
        files = self._scan()
        closed = [item for item in files if item[1]]
        cutoff = aware_utc(now) - timedelta(days=retention_days)
        expired = [item for item in closed if item[2] <= cutoff]
        current_bytes = sum(item[3] for item in files)
        classification = "eligible" if self._roots else "blocked-unclassified"
        return RetentionSourceSnapshot(
            self.source_id,
            "受管應用程式 Log",
            "files",
            classification,
            current_bytes,
            len(closed),
            len(expired),
            min((item[2] for item in closed), default=None),
            sum(item[3] for item in expired),
            self._high_water,
            self._low_water,
            _capacity_status(current_bytes, self._high_water, self._low_water),
            None if self._roots else "尚未設定 OPERATIONAL_RETENTION_LOG_ROOTS",
        )

    def candidates(
        self,
        *,
        cutoff_at_utc: datetime,
        limit: int,
    ) -> tuple[RetentionCandidate, ...]:
        candidates = []
        for path, closed, occurred_at, size, root in self._scan():
            if not closed or occurred_at > aware_utc(cutoff_at_utc):
                continue
            relative = path.relative_to(root).as_posix()
            identity = "file:" + hashlib.sha256(f"{root}|{relative}".encode("utf-8")).hexdigest()
            candidates.append(
                RetentionCandidate(identity, _file_version(relative, size, path.stat().st_mtime_ns), occurred_at, size)
            )
        return tuple(sorted(candidates, key=lambda item: (item.occurred_at_utc, item.identity))[:limit])

    def delete(self, candidates: tuple[RetentionCandidate, ...]) -> RetentionDeleteResult:
        current = {candidate.identity: (candidate, path) for candidate, path in self._candidate_paths()}
        deleted = deleted_bytes = failed = 0
        for candidate in candidates:
            match = current.get(candidate.identity)
            if match is None:
                deleted += 1
                deleted_bytes += candidate.estimated_bytes
                continue
            observed, path = match
            if observed.version != candidate.version:
                failed += 1
                continue
            try:
                path.unlink()
                deleted += 1
                deleted_bytes += candidate.estimated_bytes
            except OSError:
                failed += 1
        return RetentionDeleteResult(
            deleted,
            deleted_bytes,
            failed,
            "retention_file_reconciliation_required" if failed else None,
        )

    def rotate_oversized(self, now: datetime) -> int:
        if not self._segment_max:
            return 0
        rotated = 0
        stamp = aware_utc(now).strftime("%Y%m%dT%H%M%SZ")
        for path, closed, _, size, root in self._scan():
            if closed or size <= self._segment_max:
                continue
            target = path.with_name(f"{path.name}.{stamp}.{hashlib.sha256(path.name.encode()).hexdigest()[:8]}.closed")
            try:
                resolved_target = target.resolve(strict=False)
                resolved_target.relative_to(root)
                path.replace(target)
                rotated += 1
            except (OSError, ValueError):
                continue
        return rotated

    def _candidate_paths(self):
        for path, closed, occurred_at, size, root in self._scan():
            if not closed:
                continue
            relative = path.relative_to(root).as_posix()
            identity = "file:" + hashlib.sha256(f"{root}|{relative}".encode("utf-8")).hexdigest()
            yield (
                RetentionCandidate(identity, _file_version(relative, size, path.stat().st_mtime_ns), occurred_at, size),
                path,
            )

    def _scan(self):
        found = []
        for root in self._roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.rglob("*"):
                if len(found) >= self._max_files:
                    return tuple(found)
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(root)
                    kind = _log_kind(resolved.name)
                    if kind is None:
                        continue
                    stat = resolved.stat()
                    found.append(
                        (
                            resolved,
                            kind == "closed",
                            datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                            stat.st_size,
                            root,
                        )
                    )
                except (FileNotFoundError, OSError, ValueError):
                    continue
        return tuple(found)


def _knowledge_table_bytes(cursor) -> int:
    placeholders = ",".join(["%s"] * len(_KNOWLEDGE_TABLES))
    cursor.execute(
        f"SELECT COALESCE(SUM(data_length+index_length),0) AS total_bytes "
        f"FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ({placeholders})",
        _KNOWLEDGE_TABLES,
    )
    row = cursor.fetchone() or {}
    return int(row.get("total_bytes") or 0)


def _knowledge_counts(cursor, cutoff: datetime):
    cursor.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM knowledge_answer_requests WHERE request_status IN ('answered','unsupported','failed')) + "
        "(SELECT COUNT(*) FROM knowledge_jobs WHERE answer_request_id IS NULL AND processing_status IN ('completed','failed')) + "
        "(SELECT COUNT(*) FROM knowledge_indexes i WHERE i.index_status IN ('failed','stale') OR "
        "(i.index_status='ready' AND i.index_version < COALESCE((SELECT MAX(r.index_version) FROM knowledge_indexes r WHERE r.index_status='ready'),i.index_version))) AS eligible_count, "
        "(SELECT COUNT(*) FROM knowledge_answer_requests WHERE request_status IN ('answered','unsupported','failed') AND COALESCE(completed_at_utc,created_at_utc)<=%s) + "
        "(SELECT COUNT(*) FROM knowledge_jobs WHERE answer_request_id IS NULL AND processing_status IN ('completed','failed') AND COALESCE(completed_at_utc,created_at_utc)<=%s) + "
        "(SELECT COUNT(*) FROM knowledge_indexes i WHERE (i.index_status IN ('failed','stale') OR "
        "(i.index_status='ready' AND i.index_version < COALESCE((SELECT MAX(r.index_version) FROM knowledge_indexes r WHERE r.index_status='ready'),i.index_version))) "
        "AND COALESCE(i.built_at_utc,i.created_at_utc)<=%s) AS expired_count, "
        "LEAST("
        "COALESCE((SELECT MIN(COALESCE(completed_at_utc,created_at_utc)) FROM knowledge_answer_requests WHERE request_status IN ('answered','unsupported','failed')),'9999-12-31'),"
        "COALESCE((SELECT MIN(COALESCE(completed_at_utc,created_at_utc)) FROM knowledge_jobs WHERE answer_request_id IS NULL AND processing_status IN ('completed','failed')),'9999-12-31'),"
        "COALESCE((SELECT MIN(COALESCE(i.built_at_utc,i.created_at_utc)) FROM knowledge_indexes i WHERE i.index_status IN ('failed','stale') OR (i.index_status='ready' AND i.index_version < COALESCE((SELECT MAX(r.index_version) FROM knowledge_indexes r WHERE r.index_status='ready'),i.index_version))),'9999-12-31')) AS oldest",
        (database_utc(cutoff), database_utc(cutoff), database_utc(cutoff)),
    )
    row = cursor.fetchone() or {}
    oldest_raw = row.get("oldest")
    oldest = None if oldest_raw is None or str(oldest_raw).startswith("9999-") else _aware_datetime(oldest_raw)
    return int(row.get("eligible_count") or 0), int(row.get("expired_count") or 0), oldest


def _request_candidates(cursor, cutoff: datetime, limit: int):
    cursor.execute(
        "SELECT q.id,COALESCE(q.completed_at_utc,q.created_at_utc) AS occurred_at_utc,q.request_status AS state,"
        "COALESCE(OCTET_LENGTH(q.question),0)+COALESCE(MAX(OCTET_LENGTH(r.answer_text)),0)+"
        "COALESCE(SUM(OCTET_LENGTH(s.safe_excerpt)+OCTET_LENGTH(s.source_identity)),0)+"
        "COALESCE(SUM(OCTET_LENGTH(j.question)+OCTET_LENGTH(j.last_error_code)),0) AS estimated_bytes,"
        "COALESCE(MAX(r.id),0) AS receipt_version,COALESCE(MAX(s.id),0) AS source_version,COALESCE(MAX(j.id),0) AS job_version "
        "FROM knowledge_answer_requests q "
        "LEFT JOIN knowledge_answer_receipts r ON r.answer_request_id=q.id "
        "LEFT JOIN knowledge_answer_sources s ON s.answer_receipt_id=r.id "
        "LEFT JOIN knowledge_jobs j ON j.answer_request_id=q.id "
        "WHERE q.request_status IN ('answered','unsupported','failed') "
        "AND COALESCE(q.completed_at_utc,q.created_at_utc)<=%s "
        "GROUP BY q.id,q.completed_at_utc,q.created_at_utc,q.request_status "
        "ORDER BY occurred_at_utc,q.id LIMIT %s",
        (database_utc(cutoff), limit),
    )
    return tuple(cursor.fetchall() or ())


def _job_candidates(cursor, cutoff: datetime, limit: int):
    cursor.execute(
        "SELECT id,COALESCE(completed_at_utc,created_at_utc) AS occurred_at_utc,processing_status AS state,"
        "COALESCE(OCTET_LENGTH(question),0)+COALESCE(OCTET_LENGTH(last_error_code),0) AS estimated_bytes,"
        "attempt_count AS job_version,0 AS receipt_version,0 AS source_version "
        "FROM knowledge_jobs WHERE answer_request_id IS NULL AND processing_status IN ('completed','failed') "
        "AND COALESCE(completed_at_utc,created_at_utc)<=%s ORDER BY occurred_at_utc,id LIMIT %s",
        (database_utc(cutoff), limit),
    )
    return tuple(cursor.fetchall() or ())


def _index_candidates(cursor, cutoff: datetime, limit: int):
    cursor.execute(
        "SELECT i.index_version AS id,COALESCE(i.built_at_utc,i.created_at_utc) AS occurred_at_utc,"
        "i.index_status AS state,COALESCE(OCTET_LENGTH(i.content_set_digest),0) AS estimated_bytes,"
        "0 AS receipt_version,0 AS source_version,0 AS job_version "
        "FROM knowledge_indexes i WHERE (i.index_status IN ('failed','stale') OR "
        "(i.index_status='ready' AND i.index_version < COALESCE((SELECT MAX(r.index_version) FROM knowledge_indexes r WHERE r.index_status='ready'),i.index_version))) "
        "AND COALESCE(i.built_at_utc,i.created_at_utc)<=%s ORDER BY occurred_at_utc,i.index_version LIMIT %s",
        (database_utc(cutoff), limit),
    )
    return tuple(cursor.fetchall() or ())


def _locked_candidate(cursor, kind: str, item_id: int):
    if kind == "request":
        rows = _request_candidates_for_id(cursor, item_id)
    elif kind == "job":
        cursor.execute(
            "SELECT id,COALESCE(completed_at_utc,created_at_utc) AS occurred_at_utc,processing_status AS state,"
            "attempt_count AS job_version,0 AS receipt_version,0 AS source_version FROM knowledge_jobs "
            "WHERE id=%s AND answer_request_id IS NULL AND processing_status IN ('completed','failed') FOR UPDATE",
            (item_id,),
        )
        rows = cursor.fetchall() or ()
    elif kind == "index":
        cursor.execute(
            "SELECT i.index_version AS id,COALESCE(i.built_at_utc,i.created_at_utc) AS occurred_at_utc,"
            "i.index_status AS state,0 AS job_version,0 AS receipt_version,0 AS source_version "
            "FROM knowledge_indexes i WHERE i.index_version=%s AND (i.index_status IN ('failed','stale') OR "
            "(i.index_status='ready' AND i.index_version < COALESCE((SELECT MAX(r.index_version) FROM knowledge_indexes r WHERE r.index_status='ready'),i.index_version))) FOR UPDATE",
            (item_id,),
        )
        rows = cursor.fetchall() or ()
    else:
        return None
    return rows[0] if rows else None


def _request_candidates_for_id(cursor, item_id: int):
    cursor.execute(
        "SELECT q.id,COALESCE(q.completed_at_utc,q.created_at_utc) AS occurred_at_utc,q.request_status AS state,"
        "COALESCE(MAX(r.id),0) AS receipt_version,COALESCE(MAX(s.id),0) AS source_version,COALESCE(MAX(j.id),0) AS job_version "
        "FROM knowledge_answer_requests q LEFT JOIN knowledge_answer_receipts r ON r.answer_request_id=q.id "
        "LEFT JOIN knowledge_answer_sources s ON s.answer_receipt_id=r.id LEFT JOIN knowledge_jobs j ON j.answer_request_id=q.id "
        "WHERE q.id=%s AND q.request_status IN ('answered','unsupported','failed') "
        "GROUP BY q.id,q.completed_at_utc,q.created_at_utc,q.request_status FOR UPDATE",
        (item_id,),
    )
    return cursor.fetchall() or ()


def _row_candidate(kind: str, row: dict, estimated_bytes: int) -> RetentionCandidate:
    occurred = _aware_datetime(row["occurred_at_utc"])
    version_payload = "|".join(
        str(row.get(key, ""))
        for key in ("id", "state", "occurred_at_utc", "receipt_version", "source_version", "job_version")
    )
    return RetentionCandidate(
        f"{kind}:{int(row['id'])}",
        hashlib.sha256(version_payload.encode("utf-8")).hexdigest(),
        occurred,
        max(0, estimated_bytes),
    )


def _capacity_status(current: int, high: int | None, low: int | None):
    if high is None or low is None:
        return "unconfigured"
    return "high" if current > high else "normal"


def _aware_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return aware_utc(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _validate_watermarks(high: int | None, low: int | None) -> None:
    if high is None and low is None:
        return
    if high is None or low is None or low <= 0 or high <= low:
        raise ValueError("retention watermarks must satisfy 0 < low < high")


def _safe_root(root: Path) -> Path:
    resolved = root.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ValueError("managed log root cannot be a filesystem root")
    return resolved


def _log_kind(name: str) -> str | None:
    lowered = name.lower()
    if lowered.endswith((".log", ".out", ".err")):
        return "active"
    if any(marker in lowered for marker in (".log.", ".out.", ".err.")) or lowered.endswith(".closed"):
        return "closed"
    return None


def _file_version(relative: str, size: int, mtime_ns: int) -> str:
    return hashlib.sha256(f"{relative}|{size}|{mtime_ns}".encode("utf-8")).hexdigest()


def _admin_id(actor_id: str) -> int | None:
    if not actor_id.startswith("admin:"):
        return None
    try:
        return int(actor_id.split(":", 1)[1])
    except ValueError:
        return None


def _details(row) -> dict:
    raw = row.get("details_json") if row else None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _candidate_details(candidate: RetentionCandidate) -> dict:
    return {
        "identity": candidate.identity,
        "version": candidate.version,
        "occurred_at_utc": candidate.occurred_at_utc.isoformat(),
        "estimated_bytes": candidate.estimated_bytes,
    }


def _candidate_from_details(value: dict) -> RetentionCandidate:
    return RetentionCandidate(
        str(value["identity"]),
        str(value["version"]),
        datetime.fromisoformat(str(value["occurred_at_utc"]).replace("Z", "+00:00")),
        int(value["estimated_bytes"]),
    )


def _intent_details(intent: RetentionIntent) -> dict:
    return {
        "idempotency_key": intent.idempotency_key,
        "source_id": intent.source_id,
        "mode": intent.mode,
        "reason": intent.reason,
        "policy_revision": intent.policy_revision,
        "previewed_at_utc": intent.previewed_at_utc.isoformat(),
        "cutoff_at_utc": intent.cutoff_at_utc.isoformat(),
        "batch_size": intent.batch_size,
        "preview_fingerprint": intent.preview_fingerprint,
        "candidates": [_candidate_details(item) for item in intent.candidates],
        "actor_id": intent.actor_id,
        "correlation_id": intent.correlation_id,
        "started_at_utc": intent.started_at_utc.isoformat(),
    }


def _intent_from_details(value: dict) -> RetentionIntent:
    return RetentionIntent(
        str(value["idempotency_key"]),
        str(value["source_id"]),
        str(value["mode"]),
        str(value["reason"]),
        str(value["policy_revision"]),
        datetime.fromisoformat(str(value["previewed_at_utc"]).replace("Z", "+00:00")),
        datetime.fromisoformat(str(value["cutoff_at_utc"]).replace("Z", "+00:00")),
        int(value["batch_size"]),
        str(value["preview_fingerprint"]),
        tuple(_candidate_from_details(item) for item in value.get("candidates", ())),
        str(value["actor_id"]),
        str(value["correlation_id"]),
        datetime.fromisoformat(str(value["started_at_utc"]).replace("Z", "+00:00")),
    )


def _receipt_details(receipt: RetentionReceipt) -> dict:
    return {
        "idempotency_key": receipt.idempotency_key,
        "source_id": receipt.source_id,
        "mode": receipt.mode,
        "policy_revision": receipt.policy_revision,
        "preview_fingerprint": receipt.preview_fingerprint,
        "outcome": receipt.outcome,
        "candidate_count": receipt.candidate_count,
        "deleted_count": receipt.deleted_count,
        "failed_count": receipt.failed_count,
        "deleted_logical_bytes": receipt.deleted_logical_bytes,
        "started_at_utc": receipt.started_at_utc.isoformat(),
        "finished_at_utc": receipt.finished_at_utc.isoformat(),
        "correlation_id": receipt.correlation_id,
        "error_code": receipt.error_code,
    }


def _receipt_from_details(value: dict) -> RetentionReceipt:
    return RetentionReceipt(
        str(value["idempotency_key"]),
        str(value["source_id"]),
        str(value["mode"]),
        str(value["policy_revision"]),
        str(value["preview_fingerprint"]),
        str(value["outcome"]),
        int(value["candidate_count"]),
        int(value["deleted_count"]),
        int(value["failed_count"]),
        int(value["deleted_logical_bytes"]),
        datetime.fromisoformat(str(value["started_at_utc"]).replace("Z", "+00:00")),
        datetime.fromisoformat(str(value["finished_at_utc"]).replace("Z", "+00:00")),
        str(value["correlation_id"]),
        value.get("error_code"),
    )


__all__ = [
    "ManagedLogRetentionSource",
    "MySqlKnowledgeRetentionSource",
    "MySqlRetentionEvidenceStore",
]
