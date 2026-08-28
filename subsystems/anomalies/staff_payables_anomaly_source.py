"""
File: staff_payables_anomaly_source.py
Description: 掃描月嫂應付款根事實並投影有界異常命令。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.source_version import daily_root_source_version

_CONSUMER_IDENTITY = "staff-payables-anomaly-source-v1"
_MAXIMUM_SCAN_ITEMS = 100
_MAXIMUM_DISPLAY_OBLIGATIONS = 20
_OVERDUE_PAYABLES_SQL = """SELECT obligations.obligation_identity, obligations.staff_id, obligations.amount_due_ntd, obligations.due_date, obligations.status AS obligation_status, COALESCE(projection.status, 'payable') AS projection_status, COALESCE(projection.balance_ntd, obligations.amount_due_ntd) AS balance_ntd, GREATEST(COALESCE(obligations.current_event_id, 0), COALESCE(obligations.payroll_version, 0), COALESCE(projection.current_event_id, 0), COALESCE(projection.aggregate_version, 0)) AS root_version FROM staff_obligations obligations LEFT JOIN staff_payable_projections projection ON projection.obligation_identity = obligations.obligation_identity WHERE obligations.direction = 'payable_to_staff' AND obligations.obligation_identity > %s ORDER BY obligations.obligation_identity LIMIT %s FOR UPDATE"""
_LATE_CHANGE_SQL = """SELECT events.id AS event_id, events.obligation_identity, events.before_amount_ntd, events.after_amount_ntd, events.due_date AS original_due_date, events.created_at, obligations.staff_id, obligations.status AS obligation_status, COALESCE(projection.status, 'payable') AS projection_status, GREATEST(events.id, COALESCE(events.resulting_payroll_version, 0), COALESCE(obligations.current_event_id, 0), COALESCE(obligations.payroll_version, 0), COALESCE(projection.current_event_id, 0), COALESCE(projection.aggregate_version, 0)) AS root_version FROM staff_obligation_events events JOIN staff_obligations obligations ON obligations.obligation_identity = events.obligation_identity LEFT JOIN staff_payable_projections projection ON projection.obligation_identity = obligations.obligation_identity WHERE events.id > %s AND obligations.direction = 'payable_to_staff' ORDER BY events.id LIMIT %s"""
_BANK_MASTER_STAFF_SQL = """SELECT obligations.staff_id, GREATEST(MAX(COALESCE(obligations.current_event_id, 0)), MAX(COALESCE(obligations.payroll_version, 0)), MAX(COALESCE(projection.current_event_id, 0)), MAX(COALESCE(projection.aggregate_version, 0))) AS root_version FROM staff_obligations obligations LEFT JOIN staff_payable_projections projection ON projection.obligation_identity = obligations.obligation_identity WHERE obligations.direction = 'payable_to_staff' AND obligations.staff_id > %s GROUP BY obligations.staff_id ORDER BY obligations.staff_id LIMIT %s"""
_BANK_MASTER_ROWS_SQL = """SELECT obligations.staff_id, obligations.obligation_identity, obligations.amount_due_ntd, obligations.status AS obligation_status, COALESCE(projection.status, 'payable') AS projection_status, bank_accounts.id AS bank_account_id, bank_accounts.is_primary, bank_accounts.bank_code, bank_accounts.branch_code, bank_accounts.account_no FROM staff_obligations obligations LEFT JOIN staff_payable_projections projection ON projection.obligation_identity = obligations.obligation_identity LEFT JOIN staff_bank_accounts bank_accounts ON bank_accounts.staff_id = obligations.staff_id WHERE obligations.direction = 'payable_to_staff' AND obligations.staff_id IN ({placeholders}) ORDER BY obligations.staff_id, obligations.obligation_identity, bank_accounts.id"""


@dataclass(frozen=True, slots=True)
class StaffPayablesAnomalyScanPage:
    requests: tuple[ProjectAlertRequest, ...]
    next_cursor: str | int | None


@dataclass(frozen=True, slots=True)
class StaffPayablesAnomalyScanCursors:
    overdue_after_obligation_identity: str | None = ""
    late_change_after_event_id: int | None = 0
    bank_master_after_staff_id: int | None = 0
    last_successful_as_of: date | None = None

    def __post_init__(self) -> None:
        for value, field in ((self.overdue_after_obligation_identity, "overdue cursor"), (self.late_change_after_event_id, "late change cursor"), (self.bank_master_after_staff_id, "bank master cursor")):
            _validate_scan_cursor(value, field)
        if isinstance(self.last_successful_as_of, datetime) or (self.last_successful_as_of is not None and not isinstance(self.last_successful_as_of, date)):
            raise TypeError("last successful as of must be a date")

    @classmethod
    def start(cls):
        return cls()


@dataclass(frozen=True, slots=True)
class StaffPayablesAnomalyConsumeResult:
    cursors: StaffPayablesAnomalyScanCursors
    projected_count: int
    active_count: int
    error: TypedError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


class BorrowedAnomalyProjectionUnitOfWork:
    def __enter__(self): return self
    def __exit__(self, exception_type, exception, traceback): return False
    def commit(self): return None
    def rollback(self): return None


def consume_staff_payables_anomaly_sources(connection, *, as_of: date, maximum_items: int = 50, cursors: StaffPayablesAnomalyScanCursors | None = None) -> StaffPayablesAnomalyConsumeResult:
    _validate_scan_inputs(as_of, maximum_items, 0)
    current = cursors or StaffPayablesAnomalyScanCursors.start()
    if current.last_successful_as_of is not None and as_of < current.last_successful_as_of:
        return StaffPayablesAnomalyConsumeResult(current, 0, 0, _typed_error(ErrorCategory.VALIDATION, "staff_payables_anomaly_source_invalid", "月嫂應付款異常掃描日期不可倒退。", as_of))
    if _all_sources_exhausted(current):
        return StaffPayablesAnomalyConsumeResult(current, 0, 0)
    try:
        connection.begin()
        pages = _scan_source_pages(connection, as_of, maximum_items, current)
        requests = tuple(request for page in pages for request in page.requests)
        _project_requests(connection, requests)
        connection.commit()
        next_cursors = StaffPayablesAnomalyScanCursors(*(_next_cursor(old, page) for old, page in zip((current.overdue_after_obligation_identity, current.late_change_after_event_id, current.bank_master_after_staff_id), pages)), as_of)
        return StaffPayablesAnomalyConsumeResult(next_cursors, len(requests), sum(request.desired.active for request in requests))
    except Exception as error:
        connection.rollback()
        category = ErrorCategory.VALIDATION if isinstance(error, (TypeError, ValueError)) else ErrorCategory.INTERNAL
        code = "staff_payables_anomaly_source_invalid" if category is ErrorCategory.VALIDATION else "transaction_failed"
        message = "月嫂應付款異常來源資料不符合契約。" if category is ErrorCategory.VALIDATION else "月嫂應付款異常投影失敗。"
        return StaffPayablesAnomalyConsumeResult(current, 0, 0, _typed_error(category, code, message, as_of))


def scan_overdue_staff_payables(cursor: Any, *, as_of: date, maximum_items: int = 50, after_obligation_identity: str = "") -> StaffPayablesAnomalyScanPage:
    _validate_scan_inputs(as_of, maximum_items, after_obligation_identity)
    cursor.execute(_OVERDUE_PAYABLES_SQL, (after_obligation_identity, maximum_items))
    rows = _mapping_rows(cursor.fetchall())
    return StaffPayablesAnomalyScanPage(tuple(_overdue_request(row, as_of) for row in rows), _next_text_cursor(rows, "obligation_identity") if len(rows) == maximum_items else None)


def scan_late_staff_payable_changes(cursor: Any, *, as_of: date, maximum_items: int = 50, after_event_id: int = 0) -> StaffPayablesAnomalyScanPage:
    _validate_scan_inputs(as_of, maximum_items, after_event_id)
    cursor.execute(_LATE_CHANGE_SQL, (after_event_id, maximum_items))
    rows = _mapping_rows(cursor.fetchall())
    return StaffPayablesAnomalyScanPage(tuple(_late_change_request(row, as_of) for row in rows), _next_integer_cursor(rows, "event_id") if len(rows) == maximum_items else None)


def scan_staff_bank_master_anomalies(cursor: Any, *, as_of: date, maximum_items: int = 50, after_staff_id: int = 0) -> StaffPayablesAnomalyScanPage:
    _validate_scan_inputs(as_of, maximum_items, after_staff_id)
    cursor.execute(_BANK_MASTER_STAFF_SQL, (after_staff_id, maximum_items))
    staff_rows = _mapping_rows(cursor.fetchall())
    staff_ids = tuple(_positive_row_id(row, "staff_id") for row in staff_rows)
    bank_rows = ()
    if staff_ids:
        cursor.execute(_BANK_MASTER_ROWS_SQL.format(placeholders=", ".join(["%s"] * len(staff_ids))), staff_ids)
        bank_rows = _mapping_rows(cursor.fetchall())
    by_staff = {staff_id: tuple(row for row in bank_rows if _positive_row_id(row, "staff_id") == staff_id) for staff_id in staff_ids}
    requests = tuple(_bank_master_request(row, by_staff[_positive_row_id(row, "staff_id")], as_of) for row in staff_rows)
    return StaffPayablesAnomalyScanPage(requests, _next_integer_cursor(staff_rows, "staff_id") if len(staff_rows) == maximum_items else None)


def _scan_source_pages(connection, as_of, maximum_items, cursors):
    with connection.cursor() as cursor:
        overdue = StaffPayablesAnomalyScanPage((), None) if cursors.overdue_after_obligation_identity is None else scan_overdue_staff_payables(cursor, as_of=as_of, maximum_items=maximum_items, after_obligation_identity=cursors.overdue_after_obligation_identity)
        late = StaffPayablesAnomalyScanPage((), None) if cursors.late_change_after_event_id is None else scan_late_staff_payable_changes(cursor, as_of=as_of, maximum_items=maximum_items, after_event_id=cursors.late_change_after_event_id)
        bank = StaffPayablesAnomalyScanPage((), None) if cursors.bank_master_after_staff_id is None else scan_staff_bank_master_anomalies(cursor, as_of=as_of, maximum_items=maximum_items, after_staff_id=cursors.bank_master_after_staff_id)
    return overdue, late, bank


def _project_requests(connection, requests):
    application = AnomalyApplication(default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedAnomalyProjectionUnitOfWork)
    for request in requests:
        application.project(request)


def _overdue_request(row, as_of):
    identity = _text(row, "obligation_identity"); due_date = _optional_date(row.get("due_date")); amount = _integer(row, "amount_due_ntd"); balance = _integer(row, "balance_ntd")
    active = (
        due_date is not None
        and due_date < as_of
        and balance > 0
        and row.get("obligation_status") != "cancelled"
        and row.get("projection_status") != "cancelled"
    )
    snapshot = {"amount_due_ntd": amount, "balance_ntd": balance, "due_date": due_date.isoformat() if due_date else None, "obligation_identity": identity, "staff_id": _positive_row_id(row, "staff_id")}
    source_version = daily_root_source_version(
        as_of=as_of,
        root_version=_nonnegative_integer(row.get("root_version"), "root version"),
    )
    return _request("PAYOUT-001", identity, source_version, active, snapshot)


def _late_change_request(row, as_of):
    event_id = _positive_row_id(row, "event_id"); source_identity = f"staff-obligation-event:{event_id}"; due_date = _optional_date(row.get("original_due_date")); event_date = _event_date(row.get("created_at"))
    snapshot = {"after_amount_ntd": _integer(row, "after_amount_ntd"), "before_amount_ntd": _integer(row, "before_amount_ntd"), "obligation_identity": _text(row, "obligation_identity"), "original_due_date": due_date.isoformat() if due_date else None, "source_event_identity": source_identity, "staff_id": _positive_row_id(row, "staff_id")}
    active = due_date is not None and event_date > due_date and row.get("obligation_status") not in {"settled", "cancelled"} and row.get("projection_status") not in {"completed", "cancelled"}
    return _request("PAYOUT-002", source_identity, _source_version(row, as_of), active, snapshot)


def _bank_master_request(staff_row, bank_rows, as_of):
    staff_id = _positive_row_id(staff_row, "staff_id"); primary = [row for row in bank_rows if row.get("bank_account_id") is not None and bool(row.get("is_primary"))]
    issue = "primary_account_missing" if not primary else "primary_account_ambiguous" if len(primary) > 1 else "primary_account_incomplete" if not _bank_account_complete(primary[0]) else None
    obligations = tuple(sorted({_text(row, "obligation_identity") for row in bank_rows}))[:_MAXIMUM_DISPLAY_OBLIGATIONS]
    active = issue is not None and any(row.get("obligation_status") not in {"settled", "cancelled"} and row.get("projection_status") not in {"completed", "cancelled"} for row in bank_rows)
    return _request("PAYOUT-003", f"staff:{staff_id}", _source_version(staff_row, as_of), active, {"bank_account_issue": issue or "", "obligation_identities": obligations, "staff_id": staff_id})


def _request(code, source_identity, source_version, active, snapshot):
    desired = DesiredAlertState(code, source_identity, source_version, active, _fingerprint_values(code, snapshot))
    event = f"staff-payables:{code}:{fingerprint_payload({'active': active, 'code': code, 'snapshot': snapshot, 'source_identity': source_identity, 'source_version': source_version}).value}"
    partition = f"staff-payables:{code}:{fingerprint_payload({'code': code, 'source_identity': source_identity}).value}"
    return ProjectAlertRequest(desired, event, _CONSUMER_IDENTITY, partition, snapshot)


def _fingerprint_values(code, snapshot):
    if code == "PAYOUT-001": return {"obligation_identity": str(snapshot["obligation_identity"])}
    if code == "PAYOUT-002": return {"obligation_identity": str(snapshot["obligation_identity"]), "source_event_identity": str(snapshot["source_event_identity"])}
    return {"staff_id": str(snapshot["staff_id"])}


def _validate_scan_inputs(as_of, maximum_items, after_cursor):
    if isinstance(as_of, datetime) or not isinstance(as_of, date): raise TypeError("as of date must be a date")
    if not isinstance(maximum_items, int) or isinstance(maximum_items, bool) or not 1 <= maximum_items <= _MAXIMUM_SCAN_ITEMS: raise ValueError("maximum items must be between 1 and 100")
    _validate_scan_cursor(after_cursor, "after cursor")


def _validate_scan_cursor(cursor, field):
    if cursor is None: return
    if isinstance(cursor, bool) or not isinstance(cursor, (str, int)) or isinstance(cursor, int) and cursor < 0: raise ValueError(f"{field} must be a non-negative cursor")


def _all_sources_exhausted(cursors): return cursors.overdue_after_obligation_identity is None and cursors.late_change_after_event_id is None and cursors.bank_master_after_staff_id is None
def _next_cursor(current, page): return page.next_cursor if page.next_cursor is not None else None
def _mapping_rows(rows):
    if not isinstance(rows, (tuple, list)) or any(not isinstance(row, Mapping) for row in rows): raise ValueError("scan rows must be mapping rows")
    return tuple(rows)
def _next_text_cursor(rows, field): return _text(rows[-1], field) if rows else None
def _next_integer_cursor(rows, field): return _positive_row_id(rows[-1], field) if rows else None
def _source_version(row, as_of): return max(_nonnegative_integer(row.get("root_version"), "root version"), as_of.toordinal())
def _integer(row, field): return _nonnegative_integer(row.get(field), field)
def _positive_row_id(row, field): return require_positive_integer(row.get(field), field)
def _nonnegative_integer(value, field):
    if isinstance(value, Decimal): value = int(value)
    return require_nonnegative_integer(value, field)
def _text(row, field): return require_canonical_text(row.get(field), field, 191)
def _optional_date(value):
    if value is None: return None
    if isinstance(value, datetime): return value.date()
    if not isinstance(value, date): raise ValueError("date value must be a date")
    return value
def _event_date(value):
    if isinstance(value, datetime): return value.date()
    return _optional_date(value) or (_ for _ in ()).throw(ValueError("event date is required"))
def _bank_account_complete(row): return all(isinstance(row.get(field), str) and row.get(field).strip() for field in ("bank_code", "branch_code", "account_no"))
def _typed_error(category, code, message, as_of): return TypedError(category, code, message, CorrelationId(f"staff-payables-anomaly-scan:{as_of.isoformat()}"))
