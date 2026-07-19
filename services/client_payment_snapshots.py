"""Persist immutable client receivable snapshots calculated from order terms."""

from __future__ import annotations

from datetime import date, datetime
from importlib import import_module
from typing import Any, Callable, Mapping


_STAGE_NAMES = ("deposit", "first_payment", "second_payment")
_SNAPSHOT_COLUMNS = (
    "deposit_receivable",
    "deposit_due_date",
    "first_payment_receivable",
    "first_payment_due_date",
    "second_payment_receivable",
    "second_payment_due_date",
    "amount_receivable",
)
_DATE_COLUMNS = {
    "deposit_due_date",
    "first_payment_due_date",
    "second_payment_due_date",
}


def _default_calculator() -> Callable[[Mapping[str, Any], Mapping[str, Any]], Any]:
    """Adapt the real calculator's three-argument interface to this service."""
    module = import_module("services.order_amount_calculator")
    calculate = getattr(module, "calculate_order_amounts", None)
    if not callable(calculate):
        raise RuntimeError("OrderAmountCalculator does not expose calculate_order_amounts")

    def calculate_client_plan(
        order: Mapping[str, Any], collection_schedule: Mapping[str, Any]
    ) -> Any:
        return calculate(dict(order), [], dict(collection_schedule))

    return calculate_client_plan


def _date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc
    raise ValueError(f"{field} must be a date")


def _client_ledger_plan(calculated: Any) -> dict[str, Any]:
    if not isinstance(calculated, Mapping):
        raise TypeError("OrderAmountCalculator must return a mapping")
    raw_plan = calculated.get("client_ledger_plan")
    if not isinstance(raw_plan, Mapping):
        raise ValueError("client_ledger_plan must be a mapping")
    return dict(raw_plan)


def _snapshot_values(plan: Mapping[str, Any]) -> dict[str, Any]:
    stages = plan.get("stages")
    if not isinstance(stages, list):
        raise ValueError("client_ledger_plan.stages must be a list")

    by_name: dict[str, Mapping[str, Any]] = {}
    for stage in stages:
        if not isinstance(stage, Mapping):
            raise ValueError("each client collection stage must be a mapping")
        name = stage.get("stage")
        if name not in _STAGE_NAMES or name in by_name:
            raise ValueError("client collection stages must be unique canonical stages")
        by_name[name] = stage
    if set(by_name) != set(_STAGE_NAMES):
        raise ValueError("client_ledger_plan must contain all three collection stages")
    if "amount_receivable" not in plan:
        raise ValueError("client_ledger_plan.amount_receivable is required")

    snapshot: dict[str, Any] = {"amount_receivable": plan["amount_receivable"]}
    for name in _STAGE_NAMES:
        stage = by_name[name]
        if "receivable" not in stage:
            raise ValueError(f"{name}.receivable is required")
        snapshot[f"{name}_receivable"] = stage["receivable"]
        due_date = _date(stage.get("due_date"), f"{name}.due_date")
        snapshot[f"{name}_due_date"] = due_date.isoformat() if due_date else None
    return {column: snapshot[column] for column in _SNAPSHOT_COLUMNS}


def _placeholder(cursor: Any) -> str:
    module_name = type(cursor).__module__.split(".", 1)[0]
    return "?" if module_name == "sqlite3" else "%s"


def _row_values(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {column: row[column] for column in columns}
    return dict(zip(columns, row, strict=True))


def _comparable_snapshot(values: Mapping[str, Any]) -> dict[str, Any]:
    comparable = dict(values)
    for column in _DATE_COLUMNS:
        comparable[column] = _date(comparable.get(column), column)
    return comparable


def _review(reason: str) -> dict[str, Any]:
    return {
        "payment_id": None,
        "plan": None,
        "result": "review_required",
        "reason": reason,
    }


def create_client_payment_snapshot(
    cursor: Any,
    order: Mapping[str, Any],
    collection_schedule: Mapping[str, Any],
    *,
    calculator: Callable[[Mapping[str, Any], Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Create a formal three-stage receivable snapshot without later updates."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    if not isinstance(order, Mapping):
        raise TypeError("order must be a mapping")
    case_no = order.get("case_no")
    if not isinstance(case_no, str) or not case_no.strip():
        raise ValueError("order.case_no is required")
    if not isinstance(collection_schedule, Mapping):
        raise TypeError("collection_schedule must be a mapping")

    if collection_schedule.get("deposit_service_days") is None:
        return _review("deposit_service_days_missing")
    if collection_schedule.get("deposit_due_date") in (None, ""):
        return _review("deposit_due_date_missing")
    service_start_date = order.get("actual_start_date") or order.get("start_date")
    if service_start_date in (None, ""):
        return _review("service_start_date_missing")

    calculator_order = dict(order)
    calculator_order["service_start_date"] = service_start_date
    calculate = calculator or _default_calculator()
    plan = _client_ledger_plan(calculate(calculator_order, collection_schedule))
    snapshot = _snapshot_values(plan)
    placeholder = _placeholder(cursor)
    selected_columns = ("id", *_SNAPSHOT_COLUMNS)
    lock = "" if placeholder == "?" else " FOR UPDATE"

    cursor.execute(
        f"SELECT {', '.join(selected_columns)} "
        f"FROM client_payments WHERE case_no = {placeholder}{lock}",
        (case_no,),
    )
    existing = cursor.fetchone()
    if existing is not None:
        stored = _row_values(existing, selected_columns)
        payment_id = stored.pop("id")
        result = (
            "existing"
            if _comparable_snapshot(stored) == _comparable_snapshot(snapshot)
            else "review_required"
        )
        assert result in {"existing", "review_required"}
        return {"payment_id": payment_id, "plan": plan, "result": result}

    insert_columns = ("case_no", *_SNAPSHOT_COLUMNS)
    values = (case_no, *(snapshot[column] for column in _SNAPSHOT_COLUMNS))
    cursor.execute(
        f"INSERT INTO client_payments ({', '.join(insert_columns)}) "
        f"VALUES ({', '.join([placeholder] * len(insert_columns))})",
        values,
    )
    payment_id = getattr(cursor, "lastrowid", None)
    if payment_id is None:
        cursor.execute(
            f"SELECT id FROM client_payments WHERE case_no = {placeholder}",
            (case_no,),
        )
        inserted = cursor.fetchone()
        if inserted is None:
            raise RuntimeError("client payment snapshot insert did not return an id")
        payment_id = inserted[0] if not isinstance(inserted, Mapping) else inserted["id"]

    assert payment_id is not None
    return {"payment_id": payment_id, "plan": plan, "result": "created"}
