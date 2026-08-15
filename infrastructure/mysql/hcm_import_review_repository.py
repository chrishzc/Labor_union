"""
File: hcm_import_review_repository.py
Description: 在同一 MySQL transaction 保存 HCM review root 與 anomaly outbox。
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json

from domains.case_import.hcm_import_review import HcmImportReviewRoot, opened_anomaly_snapshot
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class HcmImportReviewMySqlUnitOfWork(MySqlUnitOfWork):
    pass


class MySqlHcmImportReviewRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def find_fingerprint(self, source_event_identity: str, *, for_update: bool) -> str | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT source_fingerprint FROM case_import_hcm_review_rows "
                "WHERE source_event_identity=%s" + suffix,
                (source_event_identity,),
            )
            row = cursor.fetchone()
        return None if row is None else str(row["source_fingerprint"])

    def append_root_and_outbox(
        self,
        root: HcmImportReviewRoot,
        *,
        canonical_case_no: str | None,
    ) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO case_import_hcm_review_rows "
                "(review_identity,source_event_identity,source_content_digest,source_sheet_identity,"
                "source_row,masked_case_identity,source_fingerprint,issue_codes,evidence_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    root.review_identity,
                    root.source_event_identity,
                    root.source_content_digest,
                    root.source_sheet_identity,
                    root.source_row,
                    root.masked_case_identity,
                    root.source_fingerprint.value,
                    _canonical_json(root.issue_codes),
                    _canonical_json(root.evidence_snapshot),
                ),
            )
            review_row_id = int(cursor.lastrowid or 0)
            if review_row_id <= 0:
                raise RuntimeError("case_import_hcm_review_insert_failed")
            self._append_case_binding(cursor, root, review_row_id, canonical_case_no)
            cursor.execute(
                "INSERT INTO case_import_hcm_review_outbox "
                "(review_row_id,intent_key,bounded_snapshot) VALUES (%s,%s,%s)",
                (
                    review_row_id,
                    f"hcm-review-opened:{root.source_fingerprint.value}",
                    _canonical_json(opened_anomaly_snapshot(root)),
                ),
            )

    @staticmethod
    def _append_case_binding(cursor, root, review_row_id: int, canonical_case_no: str | None) -> None:
        if canonical_case_no is None:
            return
        cursor.execute(
            "SELECT id FROM case_import_events WHERE case_no=%s FOR UPDATE",
            (canonical_case_no,),
        )
        import_event = cursor.fetchone()
        if import_event is None:
            return
        identity = hashlib.sha256(
            f"hcm-review-case-binding:{root.review_identity}:{canonical_case_no}".encode("utf-8")
        ).hexdigest()
        cursor.execute(
            "INSERT INTO case_import_hcm_review_case_bindings "
            "(binding_identity,review_row_id,case_no,root_import_event_id) VALUES (%s,%s,%s,%s)",
            (identity, review_row_id, canonical_case_no, int(import_event["id"])),
        )


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


__all__ = ["HcmImportReviewMySqlUnitOfWork", "MySqlHcmImportReviewRepository"]
