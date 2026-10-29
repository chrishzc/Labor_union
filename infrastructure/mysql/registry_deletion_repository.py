"""Root-only unsigned case deletion; all effects share the caller's transaction."""
from __future__ import annotations

import json
import os
from typing import Any

from infrastructure.mysql.nas_mutations import call_mutation
from infrastructure.mysql.registry_case_deletion import CASE_TASK_SCOPE, bind_case_statement, case_deletion_statements
from subsystems.registry_deletion import RegistryDeletionConflict, RegistryDeletionNotFound, RegistryDeletionPreview, RegistryKind

_FAMILY = "registry_delete/v1"


class MySqlRegistryDeletionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._client_id: int | None = None
        self._delete_client = False
        self._command_key: str | None = None

    def load(self, kind: RegistryKind, identity: str, *, for_update: bool) -> RegistryDeletionPreview:
        if kind != "case":
            raise RegistryDeletionNotFound("registry_deletion_not_found")
        lock = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT case_no,client_id,lifecycle_version FROM orders WHERE case_no=%s" + lock, (identity,))
            row = cursor.fetchone()
            if row is None:
                raise RegistryDeletionNotFound("registry_deletion_not_found")
            cursor.execute("SELECT id,client_profile_version FROM clients WHERE id=%s" + lock, (row["client_id"],))
            client = cursor.fetchone()
            if client is None:
                raise RegistryDeletionConflict("registry_deletion_invalid_client_binding")
            self._client_id = int(client["id"])
            blockers = set()
            for table, event in (("contract_signing_events", "signed_received"), ("order_contract_flow_events", "contract_completed")):
                cursor.execute(f"SELECT 1 FROM `{table}` WHERE case_no=%s AND event_type=%s LIMIT 1" + lock, (identity, event))
                if cursor.fetchone() is not None:
                    blockers.add("已有月嫂或客戶簽回，禁止刪除")
            cursor.execute("SELECT case_no FROM orders WHERE client_id=%s AND case_no<>%s" + lock, (self._client_id, identity))
            self._delete_client = not cursor.fetchall()
        return RegistryDeletionPreview("case", identity, int(row["lifecycle_version"]), int(client["client_profile_version"]), tuple(sorted(blockers)))

    def claim(self, key: str, digest: str, kind: RegistryKind, identity: str, correlation: str) -> None:
        aggregate = f"{kind}:{identity}"
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)",
                (key, _FAMILY, aggregate, digest, correlation),
            )
            if cursor.rowcount == 1:
                self._command_key = key
                return
            cursor.execute("SELECT command_family,aggregate_identity,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE", (key,))
            row = cursor.fetchone()
            if row is None or (row["command_family"], row["aggregate_identity"], row["command_fingerprint"]) != (_FAMILY, aggregate, digest):
                raise RegistryDeletionConflict("registry_deletion_idempotency_mismatch")
            self._command_key = key

    def receipt(self, key: str) -> dict[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s FOR UPDATE", (_FAMILY, key))
            row = cursor.fetchone()
        if row is None:
            return None
        result = row["result_snapshot"]
        return {"digest": row["request_fingerprint"], "result": result if isinstance(result, dict) else json.loads(result)}

    def delete(self, target: RegistryDeletionPreview) -> None:
        if self._command_key is None:
            raise RegistryDeletionConflict("registry_deletion_context_required")
        with self._connection.cursor() as cursor:
            if os.getenv("DEPLOYMENT_PROFILE") == "nas":
                call_mutation(cursor, "lu_nas_delete_unsigned_case_v2", target.identity, target.version, self._client_id, target.client_version, self._command_key)
                return
            sql, parameters = bind_case_statement("SELECT t.id FROM line_delivery_tasks t WHERE " + CASE_TASK_SCOPE + " FOR UPDATE", target.identity, self._client_id, self._delete_client)
            cursor.execute(sql, parameters)
            task_ids = json.dumps([row["id"] for row in cursor.fetchall()])
            cursor.execute("SET @registry_delete_key=%s,@registry_delete_case=%s,@registry_delete_client=%s,@registry_delete_client_owned=%s,@registry_delete_tasks=%s", (self._command_key,target.identity,self._client_id,self._delete_client,task_ids))
            try:
                for _, statement in case_deletion_statements():
                    sql, parameters = bind_case_statement(statement, target.identity, self._client_id, self._delete_client, task_ids)
                    cursor.execute(sql, parameters)
            finally:
                cursor.execute("SET @registry_delete_key=NULL,@registry_delete_case=NULL,@registry_delete_client=NULL,@registry_delete_client_owned=NULL,@registry_delete_tasks=NULL")

    def save_receipt(self, key: str, digest: str, target: RegistryDeletionPreview, actor: str) -> None:
        result = {"kind": target.kind, "identity": target.identity, "deleted": True,
                  "before": {"exists": True, "version": target.version, "client_version": target.client_version},
                  "after": {"exists": False}}
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts (command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (_FAMILY, key, digest, digest, actor, "root confirmed permanent registry deletion", json.dumps(result, ensure_ascii=False, sort_keys=True)),
            )
