"""Commute reads and metadata-only durable claims on the existing job ledger."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobLease
from subsystems.jobs.contracts import DurableJobFailureOutcome, DurableJobSuccessOutcome, parse_canonical_payload
from subsystems.scheduling.commute_query import BILLING_ZONE, COMMAND_TYPE, RECONCILIATION_TYPE, CommuteError, CommuteHistoryRecord, PreparedQuery


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class MySqlCommuteRepository:
    def __init__(self, connection):
        self.connection = connection
        self.jobs = BackgroundJobRepository(connection)

    def _one(self, sql, params):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def prepare(self, command, now):
        existing = self.jobs.read_canonical_command_by_identity(command.command_identity)
        if existing is not None:
            self.jobs.enqueue_canonical_command(command)  # Validate exact same-key equality.
            return PreparedQuery(None)
        facts = self._one("SELECT c.city AS client_city,c.address AS client_address,s.city AS staff_city,"
            "s.address AS staff_address FROM orders o JOIN clients c ON c.id=o.client_id "
            "JOIN staff s ON s.id=%s LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=s.id "
            "WHERE o.case_no=%s AND s.status='active' AND COALESCE(lifecycle.lifecycle_state,'active')='active'",
            (command.payload["staff_id"], command.payload["case_no"]))
        if facts is None:
            raise CommuteError("commute_subject_unavailable", "案件或在職月嫂不存在，請重新讀取清單。", 404)
        for field, label in (("staff_address", "月嫂名冊"), ("client_address", "本案客戶")):
            if not str(facts[field] or "").strip():
                raise CommuteError("commute_address_missing", f"{label}缺少地址，請先到名冊補齊。")
        job_id = self.jobs.enqueue_canonical_command(command)
        if job_id != command.job_id:
            return PreparedQuery(None)
        token = str(uuid.uuid4())
        # queued -> running occurs in the same transaction: no background worker
        # can claim this manually triggered request in between those two states.
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE background_jobs SET status='running',attempt_count=1,lease_token=%s,"
                "lease_owner='commute-http',lease_expires_at=DATE_ADD(%s, INTERVAL 60 SECOND),created_at=%s "
                "WHERE job_id=%s AND status='queued'", (token, now.replace(tzinfo=None), now.replace(tzinfo=None), job_id))
        def address(prefix):
            city, detail = (str(facts[f"{prefix}_{key}"] or "").strip() for key in ("city", "address"))
            return detail if not city or detail.startswith(city) else city + detail
        return PreparedQuery(DurableJobLease(job_id, token, command, 1), address("staff"), address("client"))

    def finish(self, lease, result):
        if result.status in ("ready", "no_route"):
            self.jobs.complete_canonical_claim(lease, DurableJobSuccessOutcome(f"commute:{result.status}"))
        else:
            self.jobs.fail_canonical_claim(lease, DurableJobFailureOutcome("unavailable",
                f"commute_{result.billing}", result.message, retryable=False))

    def usage(self, start, end):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT created_at,status,result_reference,error_payload FROM background_jobs "
                "WHERE command_type=%s AND created_at>=%s AND created_at<%s",
                (COMMAND_TYPE, start.replace(tzinfo=None), end.replace(tzinfo=None)))
            raw = cursor.fetchall()
        rows = []
        for row in raw:
            code = parse_canonical_payload(row["error_payload"])["error"]["code"] if row["error_payload"] else ""
            billing = "billable" if row["result_reference"] in ("commute:billable", "commute:ready", "commute:no_route") or code == "commute_billable" else "not_billable" if code == "commute_not_billable" else "unknown"
            rows.append(dict(at=_utc(row["created_at"]), billing=billing))
        row = self._one("SELECT command_payload,created_at FROM background_jobs WHERE command_type=%s "
            "AND status='succeeded' AND JSON_UNQUOTE(JSON_EXTRACT(command_payload,'$.month'))=%s "
            "ORDER BY JSON_UNQUOTE(JSON_EXTRACT(command_payload,'$.through')) DESC,created_at DESC LIMIT 1",
            (RECONCILIATION_TYPE, start.astimezone(BILLING_ZONE).strftime('%Y-%m')))
        reconciliation = None
        if row:
            payload = parse_canonical_payload(row["command_payload"])
            reconciliation = dict(count=payload["count"], through=datetime.fromisoformat(payload["through"]), at=_utc(row["created_at"]))
        return rows, reconciliation

    def history(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT j.job_id,j.created_at,j.status,j.result_reference,j.error_payload,"
                "JSON_UNQUOTE(JSON_EXTRACT(j.command_payload,'$.staff_id')) AS staff_id,s.name AS staff_name "
                "FROM background_jobs j LEFT JOIN staff s ON s.id="
                "CAST(JSON_UNQUOTE(JSON_EXTRACT(j.command_payload,'$.staff_id')) AS UNSIGNED) "
                "WHERE j.command_type=%s AND JSON_UNQUOTE(JSON_EXTRACT(j.command_payload,'$.case_no'))=%s "
                "ORDER BY j.created_at DESC,j.job_id DESC LIMIT 50", (COMMAND_TYPE, case_no))
            rows = cursor.fetchall()
        records = []
        for row in rows:
            code = parse_canonical_payload(row["error_payload"])["error"]["code"] if row["error_payload"] else ""
            status, message = "unknown", "結果待確認，請勿立即重複查詢。"
            if row["status"] == "succeeded":
                if row["result_reference"] == "commute:ready":
                    status, message = "succeeded", "已取得機車路線。"
                elif row["result_reference"] == "commute:no_route":
                    status, message = "failed", "找不到可用的機車路線。"
                else:
                    message = "舊紀錄未保存結果狀態，請勿僅因紀錄不明而重查。"
            elif row["status"] == "failed" and code in ("commute_billable", "commute_not_billable"):
                status, message = "failed", "未取得可顯示的機車路線；失敗仍可能計入用量。"
            records.append(CommuteHistoryRecord(row["job_id"], _utc(row["created_at"]),
                int(row["staff_id"]), row["staff_name"], status, message))
        return records

    def reconcile(self, command):
        job_id = self.jobs.enqueue_canonical_command(command)
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE background_jobs SET status='succeeded',receipt_payload=%s,"
                "result_reference='commute:billing-reconciliation',completed_at=UTC_TIMESTAMP(6),created_at=UTC_TIMESTAMP(6) "
                "WHERE job_id=%s AND status='queued'", ('{"kind":"success","schema_version":1,"result_reference":"commute:billing-reconciliation"}', job_id))
