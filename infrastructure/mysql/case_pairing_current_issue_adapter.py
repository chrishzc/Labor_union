"""Read-only exact Case Import pairing current-fact composition."""

from __future__ import annotations

from collections.abc import Mapping
import json

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.pairing_current_facts import (
    CASE_PAIRING_ANOMALY_OWNER_DOMAIN,
    CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE,
    BeClassCounterpartCurrentFact,
    CasePairingCurrentIssueCode,
    HcmCounterpartCurrentFact,
)


class MySqlCasePairingCurrentIssueAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        _validate_scope(scope)
        code = CasePairingCurrentIssueCode(scope.subject_type)
        facts = tuple(self._read(code, subject_id) for subject_id in scope.subject_ids)
        token = fingerprint_payload({"code": code.value, "facts": tuple(_payload(fact) for fact in facts)}).value
        return OwnerSnapshot(scope, token, max((fact.owner_version for fact in facts), default=0), facts, all(fact.authoritative_complete for fact in facts))

    def _read(self, code, subject_id):
        if code is CasePairingCurrentIssueCode.HCM_COUNTERPART_MISSING:
            return self._read_hcm(subject_id)
        entity_kind, separator, review_item_id = subject_id.partition(":")
        if not separator or not entity_kind or not review_item_id:
            raise ValueError("Case pairing import subject is invalid")
        return self._read_beclass(entity_kind, review_item_id)

    def _read_hcm(self, case_no: str):
        row = self._one(_HCM_PAIR_SQL, (case_no, case_no))
        if row is None or int(row["hcm_count"]) != 1:
            return HcmCounterpartCurrentFact(case_no, _missing(case_no), 0, False, 0, False)
        count = int(row["beclass_count"])
        consistent = count == 1 and int(row["consistent_mapping_count"]) == 1
        return HcmCounterpartCurrentFact(case_no, _token(row), int(row["owner_version"]), True, count, consistent)

    def _read_beclass(self, entity_kind: str, review_item_id: str):
        if review_item_id.startswith("counterpart:"):
            query_no = review_item_id.removeprefix("counterpart:")
            row = self._one(_SYNTHETIC_BECLASS_PAIR_SQL, (query_no,))
            if row is None:
                return BeClassCounterpartCurrentFact(entity_kind, review_item_id, _missing(review_item_id), 0, False, 0, False)
            count = int(row["hcm_count"])
            consistent = count == 1 and row["bound_case_no"] is not None
            return BeClassCounterpartCurrentFact(entity_kind, review_item_id, _token(row), int(row["owner_version"]), True, count, consistent)
        review = self._one(_REVIEW_PAIR_SQL, (review_item_id,))
        if review is None:
            return BeClassCounterpartCurrentFact(entity_kind, review_item_id, _missing(review_item_id), 0, False, 0, False)
        source_key = _accepted_source_key(str(review["source_event_identity"]))
        accepted = None if source_key is None else self._one(_ACCEPTED_MAPPING_SQL, (source_key,))
        if accepted is not None and accepted["bound_case_no"] is not None:
            count = int(accepted["hcm_count"])
            consistent = count == 1
            values = {"review": dict(review), "accepted": dict(accepted)}
        else:
            issue_codes = _json_texts(review["issue_codes"])
            count = 2 if any(marker in code.lower() for code in issue_codes for marker in ("ambiguous", "duplicate", "dedup")) else 1
            consistent = False
            values = {"review": dict(review), "accepted": None}
        return BeClassCounterpartCurrentFact(entity_kind, review_item_id, fingerprint_payload(values).value, int(review["owner_version"]), True, count, consistent)

    def _one(self, sql, parameters):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            row = cursor.fetchone()
        if row is not None and not isinstance(row, Mapping):
            raise TypeError("case pairing current-fact row is invalid")
        return row


def _accepted_source_key(source_event_identity: str) -> str | None:
    prefix = "beclass-workbook:"
    if not source_event_identity.startswith(prefix):
        return None
    return "client-beclass-workbook:" + source_event_identity.removeprefix(prefix)


def _json_texts(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, (list, tuple)) or any(not isinstance(item, str) for item in parsed):
        raise ValueError("case pairing review issue codes are invalid")
    return tuple(parsed)


def _validate_scope(scope):
    if scope.owner_domain != CASE_PAIRING_ANOMALY_OWNER_DOMAIN or scope.owner_root_type != CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE:
        raise ValueError("case pairing owner scope is invalid")
    CasePairingCurrentIssueCode(scope.subject_type)


def _token(row):
    return fingerprint_payload({str(key): value for key, value in row.items()}).value


def _missing(identity):
    return fingerprint_payload({"identity": identity, "missing": True}).value


def _payload(fact):
    return {"type": type(fact).__name__, "token": fact.owner_snapshot_token, "version": fact.owner_version, "complete": fact.authoritative_complete, "active": fact.predicate_active}


_HCM_PAIR_SQL = """
SELECT (SELECT COUNT(*) FROM orders WHERE case_no=%s) AS hcm_count,
       COUNT(beclass.id) AS beclass_count,
       SUM(CASE WHEN beclass.bound_case_no=orders.case_no AND beclass.client_id=orders.client_id THEN 1 ELSE 0 END) AS consistent_mapping_count,
       GREATEST(COALESCE(MAX(beclass.id),0),COALESCE(MAX(orders.lifecycle_version),0)) AS owner_version
FROM orders LEFT JOIN beclass_records beclass ON beclass.bound_case_no=orders.case_no
WHERE orders.case_no=%s GROUP BY orders.case_no
"""
_SYNTHETIC_BECLASS_PAIR_SQL = """
SELECT beclass.id,beclass.bound_case_no,
       (SELECT COUNT(*) FROM orders WHERE case_no=beclass.bound_case_no) AS hcm_count,
       beclass.id AS owner_version
FROM beclass_records beclass WHERE beclass.query_no=%s
"""
_REVIEW_PAIR_SQL = """
SELECT root.id,root.source_event_identity,root.issue_codes,
       COALESCE(MAX(event.resulting_version),0)+root.id AS owner_version
FROM beclass_import_review_rows root
LEFT JOIN beclass_import_review_events event ON event.review_row_id=root.id
WHERE root.review_identity=%s
GROUP BY root.id,root.source_event_identity,root.issue_codes
"""
_ACCEPTED_MAPPING_SQL = """
SELECT beclass.id,beclass.bound_case_no,
       (SELECT COUNT(*) FROM orders WHERE case_no=beclass.bound_case_no) AS hcm_count
FROM admin_command_receipts receipt
JOIN beclass_records beclass ON beclass.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.root_id')) AS UNSIGNED)
WHERE receipt.command_family='client_beclass_row_intake' AND receipt.idempotency_key=%s
"""


__all__ = ["MySqlCasePairingCurrentIssueAdapter"]
