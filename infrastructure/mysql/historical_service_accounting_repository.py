"""MySQL owner adapter for count-based historical service accounting."""

from __future__ import annotations

from contextlib import contextmanager
import json

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import AssignmentRateSnapshot, PayrollPolicyKind
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingReceipt,
    StoredHistoricalServiceAccountingReceipt,
    _command_fingerprint,
)


class MySqlHistoricalServiceAccountingRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool) -> HistoricalServiceAccountingFacts:
        lock = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(_ROOT_SQL + lock, (case_no,))
            root = cursor.fetchone()
            if root is None:
                raise ValueError("historical_order_not_found")
            cursor.execute(_ASSIGNMENTS_SQL + lock, (int(root["adoption_receipt_id"]),))
            rows = tuple(cursor.fetchall())
            adjustment_rows = _load_adjustments(
                cursor,
                tuple(int(row["assignment_id"]) for row in rows),
                lock,
            )
        adjustments = {
            int(row["assignment_id"]): MoneyNTD(int(row["amount_ntd"]))
            for row in adjustment_rows
        }
        assignments = tuple(
            HistoricalServiceAccountingAssignmentFacts(
                f"assignment:{int(row['assignment_id'])}",
                int(row["staff_id"]),
                str(row["staff_name"]),
                AssignmentRateSnapshot(
                    f"assignment:{int(row['assignment_id'])}",
                    str(row["payroll_policy_version"]),
                    PayrollPolicyKind(str(row["payroll_policy_kind"])),
                    MoneyNTD(int(row["payroll_hourly_rate_ntd"])),
                ),
                adjustments.get(int(row["assignment_id"]), MoneyNTD(0)),
            )
            for row in rows
        )
        return HistoricalServiceAccountingFacts(
            str(root["case_no"]),
            OrderLifecycleStatus(str(root["status"])),
            int(root["lifecycle_version"]),
            int(root["adoption_receipt_id"]),
            str(root["source_event_identity"]),
            int(root["historical_day_revision"]),
            int(root["client_finance_version"]),
            int(root["payroll_version"]),
            int(root["service_days"]),
            int(root["service_hours_per_day"]),
            MoneyNTD(int(root["floor_fee"])),
            str(root["identity_status"]),
            assignments,
            str(root["client_policy_version"]),
            MoneyNTD(int(root["client_hourly_rate_ntd"])),
        )

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM historical_service_day_events "
                "WHERE idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _object(row["result_snapshot"])
        return StoredHistoricalServiceAccountingReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalServiceAccountingReceipt(
                str(payload["case_no"]),
                int(payload["resulting_historical_day_revision"]),
                int(payload["resulting_client_finance_version"]),
                int(payload["resulting_payroll_version"]),
                int(payload["total_actual_service_days"]),
                int(payload["client_obligation_amount_ntd"]),
                int(payload["staff_obligation_amount_ntd"]),
                PreviewFingerprint(str(payload["preview_fingerprint"])),
            ),
        )

    def persist(self, request, candidate):
        resulting_day_revision = candidate.facts.historical_day_revision + 1
        resulting_client_version = candidate.facts.client_finance_version + 1
        resulting_payroll_version = candidate.facts.payroll_version + 1
        receipt = HistoricalServiceAccountingReceipt(
            candidate.facts.case_no,
            resulting_day_revision,
            resulting_client_version,
            resulting_payroll_version,
            candidate.service_days.total_actual_service_days,
            candidate.client_finance.total_receivable.amount,
            candidate.payroll.total_payable.amount,
            candidate.fingerprint,
        )
        result_snapshot = _receipt_payload(receipt)
        command_fingerprint = _command_fingerprint(request).value
        event_identity = f"historical-service-days:{command_fingerprint}"
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_service_day_events "
                "(event_identity,case_no,historical_adoption_receipt_id,expected_day_revision,"
                "resulting_day_revision,total_actual_service_days,total_actual_service_hours,"
                "historical_floor_fee_ntd,client_obligation_amount_ntd,staff_obligation_amount_ntd,"
                "preview_fingerprint,command_fingerprint,idempotency_key,actor_id,reason,correlation_id,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_identity,
                    candidate.facts.case_no,
                    candidate.facts.adoption_receipt_id,
                    candidate.facts.historical_day_revision,
                    resulting_day_revision,
                    candidate.service_days.total_actual_service_days,
                    candidate.service_days.total_actual_service_hours,
                    candidate.service_days.historical_floor_fee_ntd,
                    candidate.client_finance.total_receivable.amount,
                    candidate.payroll.total_payable.amount,
                    candidate.fingerprint.value,
                    command_fingerprint,
                    request.idempotency_key.value,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                    _json(result_snapshot),
                ),
            )
            event_id = int(cursor.lastrowid)
            _insert_items(cursor, event_id, candidate)
            _write_client_obligation(cursor, request, candidate, event_identity, resulting_client_version)
            _write_staff_obligations(cursor, request, candidate, event_identity, resulting_payroll_version)
            _advance_versions(cursor, candidate, resulting_client_version, resulting_payroll_version)
            _write_payroll_outbox(cursor, request, candidate, resulting_payroll_version)
            cursor.execute(
                "INSERT INTO historical_service_day_projections "
                "(case_no,current_event_id,historical_adoption_receipt_id,day_revision,total_actual_service_days,total_actual_service_hours) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "current_event_id=VALUES(current_event_id),historical_adoption_receipt_id=VALUES(historical_adoption_receipt_id),"
                "day_revision=VALUES(day_revision),total_actual_service_days=VALUES(total_actual_service_days),"
                "total_actual_service_hours=VALUES(total_actual_service_hours)",
                (
                    candidate.facts.case_no,
                    event_id,
                    candidate.facts.adoption_receipt_id,
                    resulting_day_revision,
                    candidate.service_days.total_actual_service_days,
                    candidate.service_days.total_actual_service_hours,
                ),
            )
            cursor.execute(
                "INSERT INTO historical_service_accounting_outbox "
                "(event_id,intent_key,intent_type,bounded_snapshot) VALUES (%s,%s,'historical_service_accounting_applied',%s)",
                (event_id, f"{request.idempotency_key.value}:applied", _json(result_snapshot)),
            )
        return receipt


def _insert_items(cursor, event_id, candidate):
    payroll = {item.assignment_identity: item for item in candidate.payroll.assignments}
    facts = {item.assignment_identity: item for item in candidate.facts.assignments}
    rows = []
    for ordinal, allocation in enumerate(candidate.service_days.allocations, start=1):
        assignment = facts[allocation.assignment_identity]
        payable = payroll[allocation.assignment_identity]
        rows.append((
            event_id,
            _assignment_id(allocation.assignment_identity),
            allocation.staff_id,
            ordinal,
            allocation.actual_service_days,
            allocation.actual_service_hours,
            allocation.floor_fee_ntd,
            payable.total_payable.amount,
            assignment.rate_snapshot.policy_version,
            assignment.rate_snapshot.policy_kind.value,
            assignment.rate_snapshot.hourly_rate.amount,
        ))
    cursor.executemany(
        "INSERT INTO historical_service_day_items "
        "(event_id,assignment_id,staff_id,item_ordinal,actual_service_days,actual_service_hours,"
        "floor_fee_allocated_ntd,staff_obligation_amount_ntd,payroll_policy_version,payroll_policy_kind,hourly_rate_ntd) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        rows,
    )


def _write_client_obligation(cursor, request, candidate, source_identity, resulting_version):
    before = _previous_client_amount(cursor, candidate.facts.case_no)
    after = candidate.client_finance.total_receivable.amount
    delta = after - before
    if delta == 0:
        return
    direction = "receivable_from_client" if delta > 0 else "payable_to_client"
    identity = (
        f"historical-service:{candidate.facts.case_no}:"
        f"revision:{candidate.facts.historical_day_revision + 1}:client:{direction}"
    )
    amount = abs(delta)
    cursor.execute(
        "SELECT obligation_identity FROM client_obligations WHERE obligation_identity=%s FOR UPDATE",
        (identity,),
    )
    if cursor.fetchone() is not None:
        raise ValueError("historical_accounting_obligation_binding_invalid")
    cursor.execute(
        "INSERT INTO client_obligation_events "
        "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,"
        "before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,"
        "idempotency_key,actor,reason) VALUES (%s,%s,'adjustment',%s,'established',0,%s,NULL,NULL,%s,NULL,%s,%s,%s,%s)",
        (
            identity,
            candidate.facts.case_no,
            direction,
            amount,
            source_identity,
            candidate.facts.client_finance_version,
            f"{request.idempotency_key.value}:client",
            request.actor.actor_id,
            request.reason,
        ),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_obligations "
        "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) "
        "VALUES (%s,%s,'adjustment',%s,NULL,%s,NULL,'open',%s,%s)",
        (identity, candidate.facts.case_no, direction, amount, event_id, resulting_version),
    )


def _write_staff_obligations(cursor, request, candidate, source_identity, resulting_version):
    previous = _previous_staff_amounts(cursor, candidate.facts.case_no)
    obligation_states = _previous_staff_obligation_states(
        cursor, candidate.facts.case_no
    )
    for ordinal, item in enumerate(candidate.payroll.assignments, start=1):
        assignment_id = _assignment_id(item.assignment_identity)
        before = previous.get(assignment_id, 0)
        after = item.total_payable.amount
        delta = after - before
        if delta == 0:
            continue
        state = obligation_states.get(assignment_id)
        if before > 0 and state is None:
            raise ValueError("historical_accounting_obligation_binding_invalid")
        if before > 0 and not state["payout_history_exists"]:
            _rebuild_unpaid_staff_obligation(
                cursor,
                request,
                candidate,
                item,
                state,
                before,
                after,
                ordinal,
                resulting_version,
            )
            continue
        direction = "payable_to_staff" if delta > 0 else "receivable_from_staff"
        obligation_kind = "service_pay" if before == 0 else (
            "adjustment" if delta > 0 else "reversal"
        )
        event_type = "established" if before == 0 else obligation_kind
        source_obligation_identity = None if state is None else state["obligation_identity"]
        identity = (
            f"historical-service:{candidate.facts.case_no}:"
            f"revision:{candidate.facts.historical_day_revision + 1}:"
            f"assignment:{assignment_id}:{direction}"
        )
        amount = abs(delta)
        cursor.execute(
            "SELECT obligation_identity FROM staff_obligations WHERE obligation_identity=%s FOR UPDATE",
            (identity,),
        )
        if cursor.fetchone() is not None:
            raise ValueError("historical_accounting_obligation_binding_invalid")
        cursor.execute(
            "INSERT INTO staff_obligation_events "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,"
            "event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
            "resulting_payroll_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,NULL,%s,%s,%s,%s,%s,%s)",
            (
                identity,
                assignment_id,
                candidate.facts.case_no,
                item.staff_id,
                obligation_kind,
                direction,
                source_obligation_identity,
                event_type,
                amount,
                candidate.payroll.fingerprint.value,
                candidate.facts.payroll_version,
                resulting_version,
                f"{request.idempotency_key.value}:staff:{ordinal}",
                request.actor.actor_id,
                request.reason,
            ),
        )
        event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_obligations "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,"
            "amount_due_ntd,due_date,status,current_event_id,payroll_version,payout_history_exists) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NULL,'open',%s,%s,0)",
            (
                identity,
                assignment_id,
                candidate.facts.case_no,
                item.staff_id,
                obligation_kind,
                direction,
                source_obligation_identity,
                amount,
                event_id,
                resulting_version,
            ),
        )


def _rebuild_unpaid_staff_obligation(
    cursor,
    request,
    candidate,
    item,
    state,
    before,
    after,
    ordinal,
    resulting_version,
):
    if after <= 0 or state["direction"] != "payable_to_staff" or state["status"] != "open":
        raise ValueError("historical_accounting_obligation_binding_invalid")
    identity = state["obligation_identity"]
    cursor.execute(
        "INSERT INTO staff_obligation_events "
        "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,"
        "event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
        "resulting_payroll_version,idempotency_key,actor,reason) "
        "VALUES (%s,%s,%s,%s,%s,'payable_to_staff',%s,'rebuilt',%s,%s,NULL,%s,%s,%s,%s,%s,%s)",
        (
            identity,
            _assignment_id(item.assignment_identity),
            candidate.facts.case_no,
            item.staff_id,
            state["obligation_kind"],
            state["source_obligation_identity"],
            before,
            after,
            candidate.payroll.fingerprint.value,
            candidate.facts.payroll_version,
            resulting_version,
            f"{request.idempotency_key.value}:staff:{ordinal}:rebuild",
            request.actor.actor_id,
            request.reason,
        ),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "UPDATE staff_obligations SET amount_due_ntd=%s,current_event_id=%s,payroll_version=%s "
        "WHERE obligation_identity=%s AND case_no=%s AND amount_due_ntd=%s "
        "AND status='open' AND direction='payable_to_staff' "
        "AND NOT EXISTS (SELECT 1 FROM staff_payout_obligation_links link "
        "WHERE link.obligation_identity=staff_obligations.obligation_identity) "
        "AND NOT EXISTS (SELECT 1 FROM historical_staff_payout_obligation_links historical_link "
        "WHERE historical_link.obligation_identity=staff_obligations.obligation_identity)",
        (
            after,
            event_id,
            resulting_version,
            identity,
            candidate.facts.case_no,
            before,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise ValueError("historical_accounting_obligation_binding_invalid")


def _previous_client_amount(cursor, case_no):
    cursor.execute(
        "SELECT event.client_obligation_amount_ntd "
        "FROM historical_service_day_projections projection "
        "JOIN historical_service_day_events event ON event.id=projection.current_event_id "
        "WHERE projection.case_no=%s FOR UPDATE",
        (case_no,),
    )
    row = cursor.fetchone()
    return 0 if row is None else int(row["client_obligation_amount_ntd"])


def _previous_staff_amounts(cursor, case_no):
    cursor.execute(
        "SELECT item.assignment_id,item.staff_obligation_amount_ntd "
        "FROM historical_service_day_projections projection "
        "JOIN historical_service_day_items item ON item.event_id=projection.current_event_id "
        "WHERE projection.case_no=%s ORDER BY item.assignment_id FOR UPDATE",
        (case_no,),
    )
    return {
        int(row["assignment_id"]): int(row["staff_obligation_amount_ntd"])
        for row in cursor.fetchall()
    }


def _previous_staff_obligation_states(cursor, case_no):
    cursor.execute(
        "SELECT obligation.obligation_identity,obligation.assignment_id,"
        "obligation.obligation_kind,obligation.direction,"
        "obligation.source_obligation_identity,obligation.status,"
        "CASE WHEN EXISTS (SELECT 1 FROM staff_payout_obligation_links payout_link "
        "WHERE payout_link.obligation_identity=obligation.obligation_identity) "
        "OR EXISTS (SELECT 1 FROM historical_staff_payout_obligation_links historical_link "
        "WHERE historical_link.obligation_identity=obligation.obligation_identity) "
        "THEN 1 ELSE 0 END AS payout_history_exists "
        "FROM staff_obligations obligation WHERE obligation.case_no=%s "
        "AND obligation.obligation_identity LIKE 'historical-service:%' "
        "AND obligation.status<>'cancelled' ORDER BY obligation.assignment_id,"
        "obligation.payroll_version,obligation.obligation_identity FOR UPDATE",
        (case_no,),
    )
    grouped = {}
    for row in cursor.fetchall():
        assignment_id = int(row["assignment_id"])
        current = grouped.get(assignment_id)
        has_history = bool(row["payout_history_exists"])
        if current is None:
            grouped[assignment_id] = {
                "obligation_identity": str(row["obligation_identity"]),
                "obligation_kind": str(row["obligation_kind"]),
                "direction": str(row["direction"]),
                "source_obligation_identity": row["source_obligation_identity"],
                "status": str(row["status"]),
                "payout_history_exists": has_history,
            }
            continue
        current["payout_history_exists"] = (
            current["payout_history_exists"] or has_history
        )
        current["obligation_identity"] = str(row["obligation_identity"])
        current["obligation_kind"] = str(row["obligation_kind"])
        current["direction"] = str(row["direction"])
        current["source_obligation_identity"] = row["source_obligation_identity"]
        current["status"] = str(row["status"])
    return grouped


def _write_payroll_outbox(cursor, request, candidate, resulting_version):
    payload = {
        "case_no": candidate.facts.case_no,
        "historical_day_revision": candidate.facts.historical_day_revision + 1,
        "payroll_version": resulting_version,
        "total_payable_ntd": candidate.payroll.total_payable.amount,
        "payroll_fingerprint": candidate.payroll.fingerprint.value,
    }
    cursor.execute(
        "INSERT INTO payroll_outbox "
        "(case_no,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,'staff_obligation_changed',%s)",
        (
            candidate.facts.case_no,
            f"{request.idempotency_key.value}:payroll-outbox",
            _json(payload),
        ),
    )


def _advance_versions(cursor, candidate, client_version, payroll_version):
    cursor.execute(
        "UPDATE client_finance_accounts SET aggregate_version=%s WHERE case_no=%s AND aggregate_version=%s",
        (client_version, candidate.facts.case_no, candidate.facts.client_finance_version),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("historical_actual_service_days_candidate_stale")
    cursor.execute(
        "UPDATE payroll_case_accounts SET aggregate_version=%s WHERE case_no=%s AND aggregate_version=%s",
        (payroll_version, candidate.facts.case_no, candidate.facts.payroll_version),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("historical_actual_service_days_candidate_stale")


def _assignment_id(identity):
    value = str(identity).removeprefix("assignment:")
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    return int(value)


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "resulting_historical_day_revision": receipt.resulting_historical_day_revision,
        "resulting_client_finance_version": receipt.resulting_client_finance_version,
        "resulting_payroll_version": receipt.resulting_payroll_version,
        "total_actual_service_days": receipt.total_actual_service_days,
        "client_obligation_amount_ntd": receipt.client_obligation_amount_ntd,
        "staff_obligation_amount_ntd": receipt.staff_obligation_amount_ntd,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _object(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise ValueError("historical_accounting_obligation_binding_invalid")
    return result


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


_ROOT_SQL = (
    "SELECT o.case_no,o.status,o.lifecycle_version,o.service_days,o.service_hours_per_day,o.floor_fee,"
    "c.identity_status,client_account.aggregate_version AS client_finance_version,"
    "payroll_account.aggregate_version AS payroll_version,receipt.id AS adoption_receipt_id,"
    "receipt.source_event_identity,COALESCE(day_projection.day_revision,0) AS historical_day_revision,"
    "client_terms.policy_version AS client_policy_version,client_terms.client_hourly_rate_ntd "
    "FROM orders o JOIN clients c ON c.id=o.client_id "
    "JOIN client_finance_accounts client_account ON client_account.case_no=o.case_no "
    "JOIN payroll_case_accounts payroll_account ON payroll_account.case_no=o.case_no "
    "JOIN client_payment_terms client_terms ON client_terms.case_no=o.case_no "
    "JOIN historical_order_adoption_receipts receipt ON receipt.id=("
    "SELECT MAX(r.id) FROM historical_order_adoption_receipts r WHERE r.case_no=o.case_no AND r.outcome='adopted') "
    "LEFT JOIN historical_service_day_projections day_projection ON day_projection.case_no=o.case_no "
    "WHERE o.case_no=%s"
)
_ASSIGNMENTS_SQL = (
    "SELECT evidence.assignment_id,evidence.staff_id,staff.name AS staff_name,"
    "rate.policy_version AS payroll_policy_version,rate.policy_kind AS payroll_policy_kind,"
    "rate.hourly_rate_ntd AS payroll_hourly_rate_ntd "
    "FROM historical_order_pairing_evidence evidence "
    "JOIN case_staff_assignments assignment ON assignment.id=evidence.assignment_id "
    "JOIN staff ON staff.id=evidence.staff_id "
    "JOIN assignment_payroll_rate_snapshots rate ON rate.assignment_id=evidence.assignment_id "
    "WHERE evidence.receipt_id=%s AND evidence.assignment_id IS NOT NULL "
    "ORDER BY evidence.assignment_id"
)


def _load_adjustments(cursor, assignment_ids, lock):
    if not assignment_ids:
        return ()
    placeholders = ",".join("%s" for _ in assignment_ids)
    cursor.execute(
        "SELECT assignment_id,COALESCE(SUM(amount_ntd),0) AS amount_ntd "
        "FROM payroll_adjustment_allocations WHERE assignment_id IN ("
        + placeholders
        + ") GROUP BY assignment_id"
        + lock,
        assignment_ids,
    )
    return tuple(cursor.fetchall())


__all__ = ["MySqlHistoricalServiceAccountingRepository"]
