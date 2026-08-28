"""MySQL persistence for standalone Payroll rebuild and monthly query."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import json
from typing import Iterator

from pymysql.err import IntegrityError, OperationalError

from domains.payroll.calculation import (
    AssignmentRateSnapshot,
    OfficialAssignmentServiceFacts,
    PayrollAdjustment,
    PayrollPolicyKind,
    PayrollTerms,
)
from domains.payroll.monthly_aggregation import (
    MonthlyPayrollDirection,
    MonthlyPayrollObligationFact,
    build_staff_monthly_payroll_summary,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from subsystems.payroll.rebuild_workflow import (
    ExistingStaffObligation,
    PayrollRebuildFacts,
    PayrollRebuildPersistence,
    PayrollRebuildReceipt,
    StaffObligationActionKind,
    StoredPayrollReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class PayrollRebuildRepositoryUnavailable(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class PayrollRebuildMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_repository_error(error)

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_repository_error(error)


class MySqlPayrollRebuildRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool) -> PayrollRebuildFacts:
        with _cursor(self._connection) as cursor:
            root = _load_root(cursor, case_no, for_update)
            assignments = _load_assignments(cursor, root, for_update)
            schedules = _load_schedules(cursor, root, for_update)
            rates = _load_rates(cursor, assignments, for_update)
            special_dates = _load_special_dates(cursor, assignments, for_update)
            adjustments = _load_adjustments(cursor, assignments, for_update)
            obligations = _load_obligations(cursor, case_no, for_update)
        return _rebuild_facts(
            root,
            assignments,
            schedules,
            rates,
            special_dates,
            adjustments,
            obligations,
        )

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def persist_rebuild(self, persistence: PayrollRebuildPersistence) -> None:
        with _cursor(self._connection) as cursor:
            for ordinal, action in enumerate(
                persistence.preview.actions,
                start=1,
            ):
                if action.action is StaffObligationActionKind.UNCHANGED:
                    continue
                _persist_action(cursor, persistence, action, ordinal)
            _advance_version(cursor, persistence)
            _append_outbox(cursor, persistence)
            _insert_receipt(cursor, persistence)

    def query_staff_month(self, staff_id: int, year: int, month: int):
        month_start, month_end = _month_range(year, month)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _MONTHLY_OBLIGATIONS_SQL,
                (staff_id, month_start, month_end),
            )
            rows = tuple(cursor.fetchall())
        facts = tuple(_monthly_fact(row) for row in rows)
        return build_staff_monthly_payroll_summary(
            staff_id,
            year,
            month,
            facts,
        )


@contextmanager
def _cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (OperationalError, IntegrityError) as error:
        _raise_repository_error(error)


def _raise_repository_error(error) -> None:
    code = int(error.args[0]) if error.args else 0
    retryable = code in _RETRYABLE_MYSQL_CODES or code == 1062
    message = "Payroll rebuild storage is temporarily unavailable."
    if not retryable:
        message = "Payroll rebuild storage transaction failed."
    raise PayrollRebuildRepositoryUnavailable(
        message,
        retryable=retryable,
    ) from error


def _load_root(cursor, case_no, lock):
    cursor.execute(_ROOT_SELECT_SQL + _lock_clause(lock), (case_no,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("invalid_payroll_facts")
    if row["effective_generation_id"] is None:
        return dict(row)
    if row["generation_status"] != "effective":
        raise ValueError("invalid_payroll_facts")
    return dict(row)


def _load_assignments(cursor, root, lock):
    generation_id = root["effective_generation_id"]
    if generation_id is None:
        return ()
    cursor.execute(
        _ASSIGNMENT_SELECT_SQL + _lock_clause(lock),
        (generation_id,),
    )
    return tuple(cursor.fetchall())


def _load_schedules(cursor, root, lock):
    generation_id = root["effective_generation_id"]
    if generation_id is None:
        return ()
    cursor.execute(
        _SCHEDULE_SELECT_SQL + _lock_clause(lock),
        (generation_id,),
    )
    return tuple(cursor.fetchall())


def _load_rates(cursor, assignments, lock):
    return _select_assignment_rows(
        cursor,
        _RATE_SELECT_SQL,
        assignments,
        lock,
    )


def _load_special_dates(cursor, assignments, lock):
    return _select_assignment_rows(
        cursor,
        _SPECIAL_PAY_SELECT_SQL,
        assignments,
        lock,
    )


def _load_adjustments(cursor, assignments, lock):
    if lock and assignments:
        _lock_adjustments(cursor, assignments)
    return _select_assignment_rows(
        cursor,
        _ADJUSTMENT_SELECT_SQL,
        assignments,
        False,
    )


def _lock_adjustments(cursor, assignments) -> None:
    assignment_ids = tuple(int(row["id"]) for row in assignments)
    placeholders = ",".join("%s" for _ in assignment_ids)
    cursor.execute(
        "SELECT id FROM payroll_adjustment_allocations "
        f"WHERE assignment_id IN ({placeholders}) FOR UPDATE",
        assignment_ids,
    )
    cursor.fetchall()


def _load_obligations(cursor, case_no, lock):
    if lock:
        cursor.execute(
            "SELECT obligation_identity FROM staff_obligations "
            "WHERE case_no=%s FOR UPDATE",
            (case_no,),
        )
        cursor.fetchall()
    cursor.execute(_EXISTING_OBLIGATION_SELECT_SQL, (case_no,))
    return tuple(cursor.fetchall())


def _select_assignment_rows(cursor, sql, assignments, lock):
    assignment_ids = tuple(int(row["id"]) for row in assignments)
    if not assignment_ids:
        return ()
    placeholders = ",".join("%s" for _ in assignment_ids)
    cursor.execute(
        sql.format(placeholders) + _lock_clause(lock),
        assignment_ids,
    )
    return tuple(cursor.fetchall())


# Kept cohesive because every Payroll candidate must share one locked snapshot.
def _rebuild_facts(
    root,
    assignments,
    schedules,
    rates,
    special_dates,
    adjustments,
    obligations,
):
    schedules_by_assignment = _schedule_index(assignments, schedules)
    specials_by_assignment = _date_index(special_dates)
    adjustments_by_assignment = _amount_index(adjustments)
    service_facts = _service_facts(
        assignments,
        schedules_by_assignment,
        specials_by_assignment,
    )
    return PayrollRebuildFacts(
        case_no=str(root["case_no"]),
        payroll_version=int(root["aggregate_version"]),
        service_facts=service_facts,
        rate_snapshots=_rate_snapshots(rates),
        terms=_payroll_terms(root),
        adjustments=_payroll_adjustments(adjustments_by_assignment),
        existing_obligations=_existing_obligations(obligations),
        staff_payment_due_date=root["staff_payment_due_date"],
    )


def _schedule_index(assignments, schedules):
    valid_ids = {int(row["id"]) for row in assignments}
    result = {assignment_id: [] for assignment_id in valid_ids}
    for row in schedules:
        assignment_id = int(row["assignment_id"])
        if assignment_id not in result:
            raise ValueError("official_service_ownership_conflict")
        result[assignment_id].append(row)
    return result


def _date_index(rows):
    result = {}
    for row in rows:
        result.setdefault(int(row["assignment_id"]), []).append(
            row["service_date"]
        )
    return {key: tuple(values) for key, values in result.items()}


def _amount_index(rows):
    return {
        int(row["assignment_id"]): MoneyNTD(_integer_ntd(row["amount_ntd"]))
        for row in rows
    }


def _service_facts(assignments, schedules, special_dates):
    return tuple(
        OfficialAssignmentServiceFacts(
            assignment_identity=_assignment_identity(row["id"]),
            staff_id=int(row["staff_id"]),
            service_dates=tuple(
                item["work_date"] for item in schedules[int(row["id"])]
            ),
            double_pay_dates=special_dates.get(int(row["id"]), ()),
        )
        for row in assignments
    )


def _rate_snapshots(rows):
    return tuple(
        AssignmentRateSnapshot(
            _assignment_identity(row["assignment_id"]),
            str(row["policy_version"]),
            PayrollPolicyKind(str(row["policy_kind"])),
            MoneyNTD(_integer_ntd(row["hourly_rate_ntd"])),
        )
        for row in rows
    )


def _payroll_terms(root):
    return PayrollTerms(
        int(root["service_days"]),
        int(root["service_hours_per_day"]),
        MoneyNTD(_integer_ntd(root["floor_fee"])),
    )


def _payroll_adjustments(amounts):
    return tuple(
        PayrollAdjustment(_assignment_identity(key), value)
        for key, value in sorted(amounts.items())
        if not value.is_zero
    )


def _existing_obligations(rows):
    return tuple(
        ExistingStaffObligation(
            _assignment_identity(row["assignment_id"]),
            str(row["obligation_identity"]),
            MoneyNTD(_integer_ntd(row["effective_contractual_amount_ntd"])),
            bool(row["payout_history_exists"]),
            row["due_date"],
        )
        for row in rows
    )


def _persist_action(cursor, persistence, action, ordinal):
    if action.action is StaffObligationActionKind.CREATE:
        _create_service_obligation(cursor, persistence, action, ordinal)
        return
    if action.action is StaffObligationActionKind.REPLACE_UNPAID:
        if action.delta_amount.is_zero and action.due_date is not None:
            _replace_missing_due_date(cursor, persistence, action, ordinal)
            return
        _replace_unpaid_obligation(cursor, persistence, action, ordinal)
        return
    _append_frozen_delta(cursor, persistence, action, ordinal)


# Kept cohesive because event and first projection must share one owner and amount.
def _create_service_obligation(cursor, persistence, action, ordinal):
    owner = _assignment_owner(cursor, action.assignment_identity)
    event_id = _insert_event(
        cursor,
        persistence,
        action,
        ordinal,
        owner,
        obligation_identity=action.obligation_identity,
        obligation_kind="service_pay",
        direction="payable_to_staff",
        source_identity=None,
        event_type="established",
        before_amount=0,
        after_amount=action.after_amount.amount,
    )
    _insert_projection(
        cursor,
        persistence,
        owner,
        action.obligation_identity,
        "service_pay",
        "payable_to_staff",
        None,
        action.after_amount.amount,
        event_id,
    )


# Kept cohesive because immutable rebuild event and projection CAS cannot separate.
def _replace_unpaid_obligation(cursor, persistence, action, ordinal):
    owner = _obligation_owner(cursor, action.obligation_identity)
    owner["due_date"] = action.due_date
    event_id = _insert_event(
        cursor,
        persistence,
        action,
        ordinal,
        owner,
        obligation_identity=action.obligation_identity,
        obligation_kind="service_pay",
        direction="payable_to_staff",
        source_identity=None,
        event_type="rebuilt",
        before_amount=action.before_amount.amount,
        after_amount=action.after_amount.amount,
    )
    status = "open" if action.after_amount.amount > 0 else "cancelled"
    cursor.execute(
        "UPDATE staff_obligations SET amount_due_ntd=%s,due_date=%s,status=%s,"
        "current_event_id=%s,payroll_version=%s "
        "WHERE obligation_identity=%s AND case_no=%s "
        "AND payout_history_exists=0",
        (
            action.after_amount.amount,
            action.due_date,
            status,
            event_id,
            persistence.receipt.payroll_version,
            action.obligation_identity,
            persistence.request.case_no,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise ValueError("staff_obligation_frozen")


def _replace_missing_due_date(cursor, persistence, action, ordinal):
    old_owner = _obligation_owner(cursor, action.obligation_identity)
    if old_owner["due_date"] is not None:
        raise ValueError("staff_obligation_due_date_already_established")
    closed_event_id = _insert_event(
        cursor,
        persistence,
        action,
        ordinal,
        old_owner,
        obligation_identity=action.obligation_identity,
        obligation_kind="service_pay",
        direction="payable_to_staff",
        source_identity=None,
        event_type="rebuilt",
        before_amount=action.before_amount.amount,
        after_amount=0,
        idempotency_purpose="due-date-close-event",
    )
    cursor.execute(
        "UPDATE staff_obligations SET amount_due_ntd=0,status='cancelled',"
        "current_event_id=%s,payroll_version=%s "
        "WHERE obligation_identity=%s AND case_no=%s "
        "AND due_date IS NULL AND payout_history_exists=0 AND status='open'",
        (
            closed_event_id,
            persistence.receipt.payroll_version,
            action.obligation_identity,
            persistence.request.case_no,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise ValueError("staff_obligation_frozen")

    successor_identity = _due_date_successor_identity(persistence, action)
    successor_owner = _assignment_owner(cursor, action.assignment_identity)
    if successor_owner["due_date"] != action.due_date:
        raise ValueError("staff_obligation_due_date_stale")
    established_event_id = _insert_event(
        cursor,
        persistence,
        action,
        ordinal,
        successor_owner,
        obligation_identity=successor_identity,
        obligation_kind="service_pay",
        direction="payable_to_staff",
        source_identity=action.obligation_identity,
        event_type="established",
        before_amount=0,
        after_amount=action.after_amount.amount,
        idempotency_purpose="due-date-successor-event",
    )
    _insert_projection(
        cursor,
        persistence,
        successor_owner,
        successor_identity,
        "service_pay",
        "payable_to_staff",
        action.obligation_identity,
        action.after_amount.amount,
        established_event_id,
    )


# Kept cohesive because delta sign owns direction, kind, lineage, and amount.
def _append_frozen_delta(cursor, persistence, action, ordinal):
    owner = _obligation_owner(cursor, action.obligation_identity)
    delta_identity = _delta_obligation_identity(persistence, action)
    positive = action.delta_amount.amount > 0
    obligation_kind = "adjustment" if positive else "reversal"
    direction = "payable_to_staff" if positive else "receivable_from_staff"
    amount_due = abs(action.delta_amount.amount)
    event_id = _insert_event(
        cursor,
        persistence,
        action,
        ordinal,
        owner,
        obligation_identity=delta_identity,
        obligation_kind=obligation_kind,
        direction=direction,
        source_identity=action.obligation_identity,
        event_type=obligation_kind,
        before_amount=0,
        after_amount=amount_due,
    )
    _insert_projection(
        cursor,
        persistence,
        owner,
        delta_identity,
        obligation_kind,
        direction,
        action.obligation_identity,
        amount_due,
        event_id,
    )


# Kept cohesive because immutable event identity and audit columns cannot drift.
def _insert_event(
    cursor,
    persistence,
    action,
    ordinal,
    owner,
    *,
    obligation_identity,
    obligation_kind,
    direction,
    source_identity,
    event_type,
    before_amount,
    after_amount,
    idempotency_purpose="event",
):
    cursor.execute(
        _EVENT_INSERT_SQL,
        (
            obligation_identity,
            owner["assignment_id"],
            persistence.request.case_no,
            owner["staff_id"],
            obligation_kind,
            direction,
            source_identity,
            event_type,
            before_amount,
            after_amount,
            owner["due_date"],
            persistence.preview.payroll.fingerprint.value,
            persistence.preview.payroll_version,
            persistence.receipt.payroll_version,
            _child_idempotency_key(persistence, idempotency_purpose, ordinal),
            persistence.request.actor.actor_id,
            persistence.request.reason,
        ),
    )
    return int(cursor.lastrowid)


# Kept cohesive because the projection row mirrors one immutable event owner.
def _insert_projection(
    cursor,
    persistence,
    owner,
    obligation_identity,
    obligation_kind,
    direction,
    source_identity,
    amount_due,
    event_id,
):
    cursor.execute(
        _PROJECTION_INSERT_SQL,
        (
            obligation_identity,
            owner["assignment_id"],
            persistence.request.case_no,
            owner["staff_id"],
            obligation_kind,
            direction,
            source_identity,
            amount_due,
            owner["due_date"],
            event_id,
            persistence.receipt.payroll_version,
        ),
    )


def _assignment_owner(cursor, assignment_identity):
    assignment_id = _parse_assignment_identity(assignment_identity)
    cursor.execute(_ASSIGNMENT_OWNER_SELECT_SQL, (assignment_id,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("invalid_payroll_facts")
    return _owner(row)


def _obligation_owner(cursor, obligation_identity):
    cursor.execute(_OBLIGATION_OWNER_SELECT_SQL, (obligation_identity,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("invalid_payroll_facts")
    return _owner(row)


def _owner(row):
    return {
        "assignment_id": int(row["assignment_id"]),
        "staff_id": int(row["staff_id"]),
        "due_date": row["due_date"],
    }


def _advance_version(cursor, persistence) -> None:
    cursor.execute(
        "UPDATE payroll_case_accounts SET aggregate_version=%s "
        "WHERE case_no=%s AND aggregate_version=%s",
        (
            persistence.receipt.payroll_version,
            persistence.request.case_no,
            persistence.preview.payroll_version,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise ValueError("payroll_candidate_stale")


def _append_outbox(cursor, persistence) -> None:
    payload = {
        "action_count": persistence.receipt.action_count,
        "case_no": persistence.receipt.case_no,
        "payroll_version": persistence.receipt.payroll_version,
        "total_payable_ntd": persistence.receipt.total_payable.amount,
    }
    cursor.execute(
        "INSERT INTO payroll_outbox "
        "(case_no,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,'staff_obligation_changed',%s)",
        (
            persistence.request.case_no,
            _child_idempotency_key(persistence, "outbox", 1),
            _canonical_json(payload),
        ),
    )


def _insert_receipt(cursor, persistence) -> None:
    result = {
        "action_count": persistence.receipt.action_count,
        "total_payable_ntd": persistence.receipt.total_payable.amount,
    }
    cursor.execute(
        _RECEIPT_INSERT_SQL,
        (
            persistence.request.idempotency_key.value,
            persistence.command_fingerprint.value,
            persistence.receipt.preview_fingerprint.value,
            persistence.receipt.case_no,
            persistence.receipt.payroll_version,
            _canonical_json(result),
        ),
    )


def _stored_receipt(row):
    result = _json_object(row["result_snapshot"])
    receipt = PayrollRebuildReceipt(
        case_no=str(row["case_no"]),
        payroll_version=int(row["resulting_payroll_version"]),
        action_count=int(result["action_count"]),
        total_payable=MoneyNTD(_integer_ntd(result["total_payable_ntd"])),
        preview_fingerprint=PreviewFingerprint(
            str(row["preview_fingerprint"])
        ),
    )
    return StoredPayrollReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _monthly_fact(row):
    return MonthlyPayrollObligationFact(
        obligation_identity=str(row["obligation_identity"]),
        case_no=str(row["case_no"]),
        assignment_id=int(row["assignment_id"]),
        staff_id=int(row["staff_id"]),
        due_date=row["due_date"],
        direction=MonthlyPayrollDirection(str(row["direction"])),
        amount_due=MoneyNTD(_integer_ntd(row["amount_due_ntd"])),
    )


def _month_range(year, month):
    month_start = date(year, month, 1)
    if month == 12:
        return month_start, date(year + 1, 1, 1)
    return month_start, date(year, month + 1, 1)


def _delta_obligation_identity(persistence, action):
    fingerprint = fingerprint_payload(
        {
            "case_no": persistence.request.case_no,
            "source_obligation_identity": action.obligation_identity,
            "payroll_version": persistence.receipt.payroll_version,
            "delta_amount_ntd": action.delta_amount.amount,
        }
    )
    return f"staff-obligation-delta:{fingerprint.value}"


def _due_date_successor_identity(persistence, action):
    fingerprint = fingerprint_payload(
        {
            "case_no": persistence.request.case_no,
            "source_obligation_identity": action.obligation_identity,
            "due_date": action.due_date.isoformat(),
        }
    )
    return f"staff-obligation:{fingerprint.value}"


def _child_idempotency_key(persistence, purpose, ordinal):
    fingerprint = fingerprint_payload(
        {
            "parent_key": persistence.request.idempotency_key.value,
            "purpose": purpose,
            "ordinal": ordinal,
        }
    )
    return f"payroll-rebuild:{fingerprint.value}"


def _assignment_identity(assignment_id):
    return f"assignment:{int(assignment_id)}"


def _parse_assignment_identity(identity):
    prefix = "assignment:"
    if not isinstance(identity, str) or not identity.startswith(prefix):
        raise ValueError("invalid_payroll_facts")
    value = identity.removeprefix(prefix)
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("invalid_payroll_facts")
    return int(value)


def _integer_ntd(value):
    if isinstance(value, bool):
        raise ValueError("non_integer_payroll_input")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise ValueError("non_integer_payroll_input")


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("invalid_payroll_facts")
    return parsed


def _lock_clause(lock):
    return " FOR UPDATE" if lock else ""


_ROOT_SELECT_SQL = (
    "SELECT o.case_no,o.service_days,o.service_hours_per_day,o.floor_fee,"
    "o.staff_payment_due_date,account.aggregate_version,"
    "aggregate.effective_generation_id,generation.status AS generation_status "
    "FROM orders o JOIN payroll_case_accounts account ON account.case_no=o.case_no "
    "JOIN scheduling_aggregates aggregate ON aggregate.case_no=o.case_no "
    "LEFT JOIN scheduling_generations generation "
    "ON generation.id=aggregate.effective_generation_id "
    "WHERE o.case_no=%s"
)
_ASSIGNMENT_SELECT_SQL = (
    "SELECT id,staff_id FROM case_staff_assignments "
    "WHERE generation_id=%s AND status NOT IN ('cancelled','replaced') ORDER BY id"
)
_SCHEDULE_SELECT_SQL = (
    "SELECT assignment_id,work_date FROM staff_schedule "
    "WHERE generation_id=%s AND effective_marker=1 AND is_work_day=1 "
    "ORDER BY assignment_id,work_date"
)
_RATE_SELECT_SQL = (
    "SELECT assignment_id,policy_version,policy_kind,hourly_rate_ntd "
    "FROM assignment_payroll_rate_snapshots WHERE assignment_id IN ({}) "
    "ORDER BY assignment_id"
)
_SPECIAL_PAY_SELECT_SQL = (
    "SELECT assignment_id,service_date FROM payroll_special_pay_events "
    "WHERE assignment_id IN ({}) ORDER BY assignment_id,service_date"
)
_ADJUSTMENT_SELECT_SQL = (
    "SELECT assignment_id,SUM(amount_ntd) AS amount_ntd "
    "FROM payroll_adjustment_allocations WHERE assignment_id IN ({}) "
    "GROUP BY assignment_id ORDER BY assignment_id"
)
_EXISTING_OBLIGATION_SELECT_SQL = (
    "SELECT base.assignment_id,base.obligation_identity,base.due_date,"
    "base.payout_history_exists,"
    "base_event.after_amount_ntd + COALESCE(("
    "SELECT SUM(CASE WHEN child.direction='payable_to_staff' "
    "THEN child_event.after_amount_ntd ELSE -child_event.after_amount_ntd END) "
    "FROM staff_obligations child "
    "JOIN staff_obligation_events child_event "
    "ON child_event.id=child.current_event_id "
    "WHERE child.source_obligation_identity=base.obligation_identity "
    "AND child.case_no=base.case_no AND child.status<>'cancelled'"
    "),0) AS effective_contractual_amount_ntd "
    "FROM staff_obligations base "
    "JOIN staff_obligation_events base_event ON base_event.id=base.current_event_id "
    "WHERE base.case_no=%s AND base.obligation_kind='service_pay' "
    "AND base.status<>'cancelled' ORDER BY base.assignment_id"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,"
    "resulting_payroll_version,result_snapshot FROM payroll_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_ASSIGNMENT_OWNER_SELECT_SQL = (
    "SELECT assignment.id AS assignment_id,assignment.staff_id,"
    "orders.staff_payment_due_date AS due_date "
    "FROM case_staff_assignments assignment "
    "JOIN orders ON orders.case_no=assignment.case_no "
    "WHERE assignment.id=%s"
)
_OBLIGATION_OWNER_SELECT_SQL = (
    "SELECT assignment_id,staff_id,due_date FROM staff_obligations "
    "WHERE obligation_identity=%s"
)
_EVENT_INSERT_SQL = (
    "INSERT INTO staff_obligation_events "
    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,event_type,before_amount_ntd,"
    "after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
    "resulting_payroll_version,idempotency_key,actor,reason) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_PROJECTION_INSERT_SQL = (
    "INSERT INTO staff_obligations "
    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
    "current_event_id,payroll_version,payout_history_exists) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,0)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO payroll_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "resulting_payroll_version,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s)"
)
_MONTHLY_OBLIGATIONS_SQL = (
    "SELECT obligation_identity,assignment_id,case_no,staff_id,direction,"
    "amount_due_ntd,due_date FROM staff_obligations "
    "WHERE staff_id=%s AND due_date>=%s AND due_date<%s AND status='open' "
    "ORDER BY obligation_identity"
)


__all__ = [
    "MySqlPayrollRebuildRepository",
    "PayrollRebuildMySqlUnitOfWork",
    "PayrollRebuildRepositoryUnavailable",
]
