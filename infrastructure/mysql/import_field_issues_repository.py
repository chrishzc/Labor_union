"""Read current warnings from accepted source receipts and owner facts."""
from __future__ import annotations

import json

from domains.case_import.import_field_issues import current_beclass_field_issues
from domains.case_import.refund_account import REFUND_FIELDS
from infrastructure.mysql.hcm_resubmission_repository import MySqlHcmResubmissionRepository


# Only a successful source receipt may associate a review with a case. A failed
# re-import with the same query number cannot attach to an older accepted root.
_ACCEPTED_BECLASS = (
    " FROM admin_command_receipts receipt "
    "JOIN beclass_records source ON source.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.root_id')) AS UNSIGNED) "
    "JOIN beclass_import_review_rows review ON review.review_identity="
    "JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.review_identity')) "
    "WHERE receipt.command_family='client_beclass_row_intake' "
    "AND JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.outcome'))='created' "
    "AND review.source_kind='client' AND source.bound_case_no IS NOT NULL "
)


class MySqlImportFieldIssuesRepository:
    def __init__(self, connection):
        self._connection = connection
        self._hcm = MySqlHcmResubmissionRepository(connection)

    def candidate_case_nos(self, *, offset: int, limit: int, case_no: str | None):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT cases.case_no FROM ("
                "SELECT b.case_no FROM case_import_hcm_review_rows r "
                "JOIN case_import_hcm_review_case_bindings b ON b.review_row_id=r.id "
                "WHERE NOT EXISTS (SELECT 1 FROM case_import_hcm_review_rows newer "
                "JOIN case_import_hcm_review_case_bindings nb ON nb.review_row_id=newer.id "
                "WHERE nb.case_no=b.case_no AND newer.id>r.id) "
                "UNION SELECT source.bound_case_no AS case_no" + _ACCEPTED_BECLASS +
                ") cases WHERE (%s IS NULL OR cases.case_no=%s) ORDER BY cases.case_no LIMIT %s OFFSET %s",
                (case_no, case_no, limit, offset),
            )
            return tuple(str(row["case_no"]) for row in cursor.fetchall())

    def query_case(self, case_no: str):
        issues = list(self._hcm.query_current_field_issues(case_no))
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT source.id,source.email,source.city,source.refund_bank_code,source.refund_account_no,review.issue_codes"
                + _ACCEPTED_BECLASS + "AND source.bound_case_no=%s ORDER BY source.id,receipt.id", (case_no,),
            )
            warnings = tuple(cursor.fetchall())
            if not warnings:
                return tuple(issues)
            cursor.execute(
                "SELECT c.email,c.city,o.requires_cooking "
                "FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s",
                (case_no,),
            )
            profile = cursor.fetchone()
            if profile is None:
                raise RuntimeError("import_field_issues_client_root_missing")
            cursor.execute(
                "SELECT id FROM beclass_records WHERE bound_case_no=%s ORDER BY id LIMIT 2", (case_no,),
            )
            if len(tuple(cursor.fetchall())) != 1:
                raise RuntimeError("import_field_issues_beclass_binding_ambiguous")
            cursor.execute(
                "SELECT aggregate_version,effective_values_json FROM beclass_record_correction_states WHERE beclass_record_id=%s",
                (warnings[0]["id"],),
            )
            state = cursor.fetchone()
            cursor.execute(
                "SELECT result_snapshot FROM admin_command_receipts WHERE command_family=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.beclass_record_id'))=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.case_no'))=%s "
                "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.resulting_version')) AS UNSIGNED) BETWEEN 1 AND %s",
                ("client_beclass_correction/v1", str(warnings[0]["id"]), case_no,
                 int((state or {}).get("aggregate_version") or 0)),
            )
            receipts = tuple(cursor.fetchall())
        corrections = _json((state or {}).get("effective_values_json"), {})
        corrected_fields = _corrected_refund_fields(
            receipts, record_id=warnings[0]["id"], case_no=case_no,
            version=int((state or {}).get("aggregate_version") or 0),
        )
        for warning in warnings:
            values = {field: warning.get(field) for field in ("refund_bank_code", "refund_account_no")}
            values.update({field: corrections[field] for field in corrected_fields if field in corrections})
            values["requires_cooking"] = profile.get("requires_cooking")
            issues.extend(current_beclass_field_issues(tuple(_json(warning["issue_codes"], [])), values, profile, cleared_fields=corrected_fields & frozenset(corrections)))
        return tuple({(issue.source, issue.owner, issue.field, issue.code): issue for issue in issues}.values())


def _corrected_refund_fields(receipts, *, record_id, case_no: str, version: int) -> frozenset[str]:
    fields = set()
    for receipt in receipts:
        result = _json(receipt["result_snapshot"], {})
        resulting_version = result.get("resulting_version")
        if (result.get("beclass_record_id") != record_id or result.get("case_no") != case_no
                or type(resulting_version) is not int or not 1 <= resulting_version <= version):
            continue
        changed_fields = result.get("changed_fields")
        if isinstance(changed_fields, list):
            fields.update(field for field in changed_fields if isinstance(field, str) and field in REFUND_FIELDS)
    return frozenset(fields)


def _json(value, default):
    return default if value is None else json.loads(value) if isinstance(value, str) else value
