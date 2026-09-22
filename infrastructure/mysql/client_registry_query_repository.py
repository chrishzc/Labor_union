"""MySQL read adapter for the case-centered client registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from domains.case_import.order_information import project_order_information
from subsystems.case_import.beclass_correction_workflow import allows_manual_beclass_source
from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
from domains.client_finance.order_amount_calculation import _claim_schedule
from domains.client_finance.subsidy_coverage import normalize_subsidy_policy_identity
from domains.client_finance.subsidy_advance import subsidy_advance_due_date
from domains.payroll.payment_due_date import calculate_staff_payment_due_date
from infrastructure.mysql.order_terms_read_model import (
    load_contract_client_finance_facts,
    select_order,
)
from subsystems.client_profile.order_accounting_export import (
    OrderAccountingExportQuery,
    OrderAccountingExportRow,
)
from subsystems.government_subsidy.reconciliation_register_query import (
    build_operations_report_subsidy_rows_by_case,
)


_CLIENT_FIELDS = (
    "name", "gender", "phone", "city", "address", "residence_type",
    "delivery_type", "baby_info", "notes",
)
_BECLASS_FIELDS = (
    "name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes",
)
_SORT_COLUMNS = {
    "case_no": "o.case_no",
    "customer_name": "c.name",
    "service_days": "o.service_days",
    "expected_start_date": "o.start_date",
}
_BIRTH_COUNT_SQL = (
    "COALESCE("
    "CASE WHEN JSON_VALID(bcs.effective_values_json) THEN "
    "JSON_UNQUOTE(JSON_EXTRACT(bcs.effective_values_json, '$.multi_birth_count')) END,"
    "CASE WHEN JSON_VALID(br.survey_details) THEN "
    "JSON_UNQUOTE(JSON_EXTRACT(br.survey_details, '$.\"特殊計費:胎數\"')) END)"
)
_SUPPORTED_DISTRICTS = (
    "香山區", "東區", "北區", "竹北市", "竹東鎮", "新埔鎮", "關西鎮",
    "湖口鄉", "新豐鄉", "芎林鄉", "橫山鄉", "北埔鄉", "寶山鄉", "峨眉鄉",
    "尖石鄉", "五峰鄉", "頭份市", "竹南鎮",
)


class MySqlClientRegistryQueryRepository:
    def __init__(self, connection: Any, subsidy_projection_loader=None) -> None:
        self._connection = connection
        self._subsidy_projection_loader = (
            subsidy_projection_loader or build_operations_report_subsidy_rows_by_case
        )

    def list_page(
        self,
        *,
        query: str | None,
        multi_birth_count: str | None,
        order_status: str | None,
        requires_cooking: bool | None,
        sort_by: str | None,
        sort_order: str | None,
        limit: int,
        after: str | None,
        offset: int,
    ):
        where, parameters = _registry_filters(
            query=query,
            multi_birth_count=multi_birth_count,
            order_status=order_status,
            requires_cooking=requires_cooking,
            after=after,
        )
        if sort_by is None:
            order_by = "o.case_no ASC"
        else:
            column = _SORT_COLUMNS[sort_by]
            direction = "DESC" if sort_order == "desc" else "ASC"
            order_by = f"{column} {direction}"
            if column != "o.case_no":
                order_by += ", o.case_no ASC"
        parameters.extend((limit + 1, offset))
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,c.name,c.phone,c.city,c.address,"
                + _BIRTH_COUNT_SQL + " AS multi_birth_count,"
                "o.service_days,o.requires_cooking,"
                "o.start_date AS planned_start_date,o.status AS order_status,"
                "o.staff_payment_due_date,o.actual_end_date,c.identity_status "
                "FROM orders o JOIN clients c ON c.id=o.client_id "
                "LEFT JOIN (SELECT bound_case_no,MAX(id) AS id,MAX(survey_details) AS survey_details "
                "FROM beclass_records WHERE bound_case_no IS NOT NULL GROUP BY bound_case_no HAVING COUNT(*)=1) br "
                "ON br.bound_case_no=o.case_no "
                "LEFT JOIN beclass_record_correction_states bcs ON bcs.beclass_record_id=br.id WHERE "
                + " AND ".join(where)
                + " ORDER BY " + order_by + " LIMIT %s OFFSET %s",
                tuple(parameters),
            )
            rows = tuple(cursor.fetchall() or ())
            visible_case_nos = tuple(str(row["case_no"]) for row in rows[:limit])
            imported_virtual_accounts = _load_imported_virtual_accounts(
                cursor, visible_case_nos
            )
            obligation_dates = _load_obligation_dates(
                cursor, visible_case_nos
            )
        visible = tuple({
            **row,
            "imported_virtual_accounts": imported_virtual_accounts[str(row["case_no"])],
            "built_in_virtual_account": build_client_virtual_account(row.get("case_no")),
            "district": _client_district(row.get("city"), row.get("address")),
            **obligation_dates[str(row["case_no"])],
            **_claim_application_month(row),
        } for row in rows[:limit])
        next_cursor = str(visible[-1]["case_no"]) if len(rows) > limit and visible else None
        next_offset = offset + limit if len(rows) > limit and after is None else None
        return visible, next_cursor, next_offset


    def query_order_accounting_rows(
        self, selection: OrderAccountingExportQuery
    ) -> tuple[OrderAccountingExportRow, ...]:
        where, parameters = _registry_filters(
            query=selection.query,
            multi_birth_count=selection.multi_birth_count,
            order_status=selection.order_status,
            requires_cooking=selection.requires_cooking,
            after=None,
        )
        if selection.sort_by is None:
            order_by = "o.case_no ASC"
        else:
            column = _SORT_COLUMNS[selection.sort_by]
            direction = "DESC" if selection.sort_order == "desc" else "ASC"
            order_by = f"{column} {direction}"
            if column != "o.case_no":
                order_by += ", o.case_no ASC"
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.seq_num,o.case_no,c.name,c.identity_status,c.service_time,"
                "c.due_month,c.service_start_date,c.baby_info,o.status AS order_status,"
                "o.service_days,o.service_hours_per_day,o.requires_cooking,o.floor_fee,"
                "o.start_date AS planned_start_date,o.end_date AS planned_end_date,"
                "o.actual_start_date,o.actual_end_date,o.staff_payment_due_date,"
                "terms.deposit_due_date,terms.first_payment_due_date,terms.second_payment_due_date,"
                "deposit_ledger.occurred_on AS deposit_settled_on "
                "FROM orders o JOIN clients c ON c.id=o.client_id "
                "LEFT JOIN client_payment_terms terms ON terms.case_no=o.case_no "
                "LEFT JOIN client_deposit_settlement_projection deposit_projection "
                "ON deposit_projection.case_no=o.case_no "
                "LEFT JOIN client_ledger_entries deposit_ledger "
                "ON deposit_ledger.id=deposit_projection.latest_ledger_entry_id "
                "LEFT JOIN (SELECT bound_case_no,MAX(id) AS id,MAX(survey_details) AS survey_details "
                "FROM beclass_records WHERE bound_case_no IS NOT NULL GROUP BY bound_case_no HAVING COUNT(*)=1) br "
                "ON br.bound_case_no=o.case_no "
                "LEFT JOIN beclass_record_correction_states bcs ON bcs.beclass_record_id=br.id WHERE "
                + " AND ".join(where)
                + " ORDER BY " + order_by,
                tuple(parameters),
            )
            base_rows = tuple(cursor.fetchall() or ())
            imported_virtual_accounts = _load_imported_virtual_accounts(
                cursor, tuple(str(row["case_no"]) for row in base_rows)
            )
        subsidy_rows = self._subsidy_projection_loader(
            tuple(str(row["case_no"]) for row in base_rows),
            self._connection,
        )
        return tuple(
            self._order_accounting_row(
                row,
                subsidy_rows.get(str(row["case_no"])),
                imported_virtual_accounts[str(row["case_no"])],
            )
            for row in base_rows
        )

    def _order_accounting_row(
        self,
        row: Mapping[str, Any],
        subsidy_row: Mapping[str, Any] | None,
        imported_virtual_accounts: tuple[str, ...],
    ) -> OrderAccountingExportRow:
        case_no = str(row["case_no"])
        finance_status, _, finance = _finance_values(self._connection, case_no)
        values = finance if finance_status == "ready" and finance is not None else {}
        subsidy_amount = (
            int(Decimal(str(subsidy_row["補助款金額"])))
            if subsidy_row is not None
            else None
        )
        subsidy_service_end = (
            subsidy_row.get("服務結束") if subsidy_row is not None else None
        )
        subsidy_due_date = (
            subsidy_advance_due_date(subsidy_service_end)
            if isinstance(subsidy_service_end, date)
            else None
        )
        staff_payment_due_date = row.get("staff_payment_due_date")
        customer_payable = values.get("customer_payable_total_ntd")
        if (
            staff_payment_due_date is None
            and isinstance(subsidy_service_end, date)
            and customer_payable is not None
        ):
            staff_payment_due_date = calculate_staff_payment_due_date(
                subsidy_service_end,
                customer_payable,
                normalize_subsidy_policy_identity(
                    str(row.get("identity_status") or "")
                ) == "補助市民" and Decimal(str(customer_payable)) == 0,
            )
        claim = _claim_application_month(row)
        baby_info = str(row.get("baby_info") or "")
        return OrderAccountingExportRow(
            seq_num=row.get("seq_num"),
            case_no=case_no,
            name=row.get("name"),
            identity_status=row.get("identity_status"),
            service_time=row.get("service_time"),
            due_month=row.get("due_month"),
            hcm_service_start_date=row.get("service_start_date"),
            is_twins="雙胞胎" in baby_info or "2" in baby_info,
            order_status=row.get("order_status"),
            imported_virtual_accounts=imported_virtual_accounts,
            built_in_virtual_account=build_client_virtual_account(case_no),
            service_days=row.get("service_days"),
            service_hours_per_day=row.get("service_hours_per_day"),
            service_hours=values.get("service_hours"),
            requires_cooking=row.get("requires_cooking"),
            floor_fee_ntd=row.get("floor_fee"),
            service_unit_price_ntd=values.get("service_unit_price_ntd"),
            customer_payable_total_ntd=values.get("customer_payable_total_ntd"),
            deposit_amount_ntd=values.get("deposit_amount_ntd"),
            first_payment_amount_ntd=values.get("first_payment_amount_ntd"),
            second_payment_amount_ntd=values.get("second_payment_amount_ntd"),
            received_total_ntd=values.get("received_total_ntd"),
            customer_balance_ntd=values.get("customer_balance_ntd"),
            subsidy_return_amount_ntd=subsidy_amount,
            planned_start_date=row.get("planned_start_date"),
            planned_end_date=row.get("planned_end_date"),
            actual_start_date=row.get("actual_start_date"),
            actual_end_date=row.get("actual_end_date"),
            deposit_due_date=row.get("deposit_due_date"),
            first_payment_due_date=row.get("first_payment_due_date"),
            second_payment_due_date=row.get("second_payment_due_date"),
            deposit_settled_on=row.get("deposit_settled_on"),
            subsidy_return_due_date=subsidy_due_date,
            subsidy_return_status=None,
            staff_payment_due_date=staff_payment_due_date,
            claim_application_year=claim["claim_application_year"],
            claim_application_month=claim["claim_application_month"],
        )

    def load_detail(self, case_no: str) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,o.status AS order_status,c.client_profile_version,"
                "EXISTS(SELECT 1 FROM order_service_data_locks service_lock "
                "WHERE service_lock.case_no=o.case_no) AS service_data_locked,"
                + ",".join(f"c.{field}" for field in _CLIENT_FIELDS)
                + " FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s LIMIT 1",
                (case_no,),
            )
            client = cursor.fetchone()
            if client is None:
                return None
            cursor.execute(
                "SELECT id AS beclass_record_id,record_origin,survey_details," + ",".join(_BECLASS_FIELDS)
                + " FROM beclass_records WHERE bound_case_no=%s ORDER BY id LIMIT 2",
                (case_no,),
            )
            beclass_rows = tuple(cursor.fetchall() or ())
            state = None
            if len(beclass_rows) == 1:
                cursor.execute(
                    "SELECT aggregate_version,effective_values_json "
                    "FROM beclass_record_correction_states WHERE beclass_record_id=%s",
                    (int(beclass_rows[0]["beclass_record_id"]),),
                )
                state = cursor.fetchone()
        effective_values: dict[str, Any] = {}
        if not beclass_rows and allows_manual_beclass_source(client.get("order_status")):
            beclass_status = "ready"
            beclass_record_id = None
            beclass_source_kind = "admin_manual"
            beclass_values = {field: None for field in _BECLASS_FIELDS}
        elif not beclass_rows:
            beclass_status = "unbound"
            beclass_record_id = None
            beclass_source_kind = None
            beclass_values = None
        elif len(beclass_rows) > 1:
            beclass_status = "duplicate_binding"
            beclass_record_id = None
            beclass_source_kind = None
            beclass_values = None
        else:
            beclass_status = "ready"
            source = beclass_rows[0]
            beclass_record_id = int(source["beclass_record_id"])
            beclass_source_kind = str(source.get("record_origin") or "imported")
            effective_values = _decode((state or {}).get("effective_values_json"))
            beclass_values = {field: source.get(field) for field in _BECLASS_FIELDS}
            beclass_values.update({
                field: effective_values[field]
                for field in _BECLASS_FIELDS
                if field in effective_values
            })
        if beclass_status == "ready":
            order_information = project_order_information(
                beclass_rows[0].get("survey_details") if beclass_rows else None
            )
            order_information_values = dict(order_information.values)
            order_information_issues = (
                {} if beclass_source_kind == "admin_manual"
                else dict(order_information.issues)
            )
            if "multi_birth_count" in effective_values:
                order_information_values["multi_birth_count"] = effective_values["multi_birth_count"]
                order_information_issues.pop("multi_birth_count", None)
            beclass_values["multi_birth_count"] = order_information_values.get("multi_birth_count")
        else:
            order_information_values = None
            order_information_issues = {}
        finance_status, finance_code, finance_values = _finance_values(
            self._connection, case_no
        )
        return {
            "case_no": str(client["case_no"]),
            "client_id": int(client["client_id"]),
            "client_profile_version": int(client.get("client_profile_version") or 0),
            "client_values": {field: client.get(field) for field in _CLIENT_FIELDS},
            "beclass_status": beclass_status,
            "beclass_record_id": beclass_record_id,
            "beclass_source_kind": beclass_source_kind,
            "beclass_version": int((state or {}).get("aggregate_version") or 0),
            "beclass_values": beclass_values,
            "beclass_financial_fields_locked": bool(
                client.get("service_data_locked")
                or str(client.get("order_status") or "")
                in {
                    "服務中", "訂單完成", "訂單取消",
                    "歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成",
                }
            ),
            "order_information_values": order_information_values,
            "order_information_issues": order_information_issues,
            "finance_status": finance_status,
            "finance_code": finance_code,
            "finance_values": finance_values,
        }

    def load_change_history(self, case_no: str) -> tuple[Mapping[str, Any], ...]:
        """Read primary user-confirmed reasons without duplicating derived projections."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_type,label,reason,actor,occurred_at FROM ("
                "SELECT 'client_profile' AS event_type,'客戶主檔變更' AS label,e.reason,e.actor_id AS actor,"
                "e.created_at_utc AS occurred_at,1 AS source_order,e.id AS event_id "
                "FROM client_profile_admin_change_events e JOIN orders o ON o.client_id=e.client_id WHERE o.case_no=%s "
                "UNION ALL SELECT 'beclass_correction','BeClass 資料修正',e.reason,e.actor_id,e.created_at_utc,2,e.id "
                "FROM beclass_record_correction_events e JOIN beclass_records r ON r.id=e.beclass_record_id WHERE r.bound_case_no=%s "
                "UNION ALL SELECT 'order_terms','訂單條件變更',e.reason,e.actor,e.created_at,3,e.id "
                "FROM order_terms_change_events e WHERE e.case_no=%s "
                "UNION ALL SELECT 'service_dates','正式服務日期確認',v.reason,v.confirmed_by_actor_id,v.confirmed_at_utc,4,v.id "
                "FROM confirmed_service_date_versions v WHERE v.case_no=%s AND NULLIF(TRIM(v.reason),'') IS NOT NULL "
                "UNION ALL SELECT 'actual_start','實際開始日確認',e.reason,e.actor,e.created_at,5,e.id "
                "FROM order_actual_start_events e WHERE e.case_no=%s "
                "UNION ALL SELECT 'cancellation','訂單取消',e.reason,e.actor,e.created_at,6,e.id "
                "FROM order_cancellation_events e WHERE e.case_no=%s "
                "UNION ALL SELECT 'reopen','訂單重啟',e.reason,e.actor,e.created_at,7,e.id "
                "FROM order_reopen_events e WHERE e.case_no=%s"
                ") history ORDER BY occurred_at,source_order,event_id",
                (case_no,) * 7,
            )
            return tuple(cursor.fetchall() or ())


def _load_imported_virtual_accounts(cursor, case_nos: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {case_no: [] for case_no in case_nos}
    if not case_nos:
        return {}
    placeholders = ",".join(("%s",) * len(case_nos))
    cursor.execute(
        "SELECT case_no,virtual_account FROM client_legacy_virtual_accounts "
        "WHERE case_no IN (" + placeholders + ") ORDER BY case_no,virtual_account",
        case_nos,
    )
    for row in cursor.fetchall():
        result[str(row["case_no"])].append(str(row["virtual_account"]))
    return {case_no: tuple(accounts) for case_no, accounts in result.items()}


def _decode(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _registry_filters(
    *,
    query: str | None,
    multi_birth_count: str | None,
    order_status: str | None,
    requires_cooking: bool | None,
    after: str | None,
) -> tuple[list[str], list[object]]:
    where = ["o.case_no IS NOT NULL"]
    parameters: list[object] = []
    if after is not None:
        where.append("o.case_no > %s")
        parameters.append(after)
    if query is not None:
        where.append("CONCAT_WS(' ',o.case_no,COALESCE(c.name,''),COALESCE(c.phone,'')) LIKE %s")
        parameters.append(f"%{query}%")
    if multi_birth_count is not None:
        where.append(f"{_BIRTH_COUNT_SQL} = %s")
        parameters.append(multi_birth_count)
    if order_status is not None:
        where.append("o.status = %s")
        parameters.append(order_status)
    if requires_cooking is not None:
        where.append("o.requires_cooking = %s")
        parameters.append(requires_cooking)
    return where, parameters


def _client_district(city: object, address: object) -> str | None:
    location = f"{city or ''}{address or ''}"
    return next((district for district in _SUPPORTED_DISTRICTS if district in location), None)


def _load_obligation_dates(cursor, case_nos: tuple[str, ...]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Read stored dates for this page; do not calculate amounts or filter by month."""
    result = {
        case_no: {"client_obligation_dates": [], "staff_obligation_dates": []}
        for case_no in case_nos
    }
    if not case_nos:
        return result
    placeholders = ",".join("%s" for _ in case_nos)
    cursor.execute(
        "SELECT case_no,obligation_identity,obligation_type,due_date "
        "FROM client_obligations WHERE case_no IN (" + placeholders + ") "
        "AND status<>'cancelled' AND ("
        "(direction='receivable_from_client' AND obligation_type IN ('deposit','first','second')) "
        "OR (direction='payable_to_client' AND obligation_type='subsidy_return')) "
        "ORDER BY case_no,obligation_type,obligation_identity",
        case_nos,
    )
    for row in cursor.fetchall():
        result[str(row["case_no"])]["client_obligation_dates"].append({
            "obligation_identity": row["obligation_identity"],
            "obligation_type": row["obligation_type"],
            "due_date": row["due_date"],
        })
    cursor.execute(
        "SELECT obligations.case_no,obligations.obligation_identity,"
        "obligations.obligation_kind,obligations.due_date,obligations.staff_id,"
        "staff.name AS staff_name FROM staff_obligations obligations "
        "LEFT JOIN staff ON staff.id=obligations.staff_id "
        "WHERE obligations.case_no IN (" + placeholders + ") "
        "AND obligations.direction='payable_to_staff' AND obligations.status<>'cancelled' "
        "ORDER BY obligations.case_no,obligations.staff_id,obligations.obligation_identity",
        case_nos,
    )
    for row in cursor.fetchall():
        result[str(row["case_no"])]["staff_obligation_dates"].append({
            "obligation_identity": row["obligation_identity"],
            "obligation_kind": row["obligation_kind"],
            "due_date": row["due_date"],
            "staff_id": row["staff_id"],
            "staff_name": row["staff_name"],
        })
    return result


def _claim_application_month(row) -> dict[str, int | None]:
    # Reuse the existing owner projection. Never manufacture a day or use a
    # planned date to fill a missing actual end date in this diagnostic list.
    eligible = normalize_subsidy_policy_identity(
        str(row.get("identity_status") or "")
    ) in {"一般市民", "補助市民"}
    schedule = _claim_schedule(row.get("actual_end_date") if eligible else None)
    return {
        "claim_application_year": schedule["claim_application_year"],
        "claim_application_month": schedule["claim_application_month"],
    }


def _finance_values(connection, case_no):
    try:
        with connection.cursor() as cursor:
            order_row = select_order(cursor, case_no, lock=False)
            facts = load_contract_client_finance_facts(
                cursor, order_row, lock=False
            )
            received_total = _client_service_received_total(cursor, case_no)
            cursor.execute(
                "SELECT amount_due_ntd,due_date,status FROM client_obligations "
                "WHERE case_no=%s AND obligation_type='subsidy_return' "
                "AND direction='payable_to_client' ORDER BY obligation_identity",
                (case_no,),
            )
            subsidy_rows = tuple(cursor.fetchall() or ())
        if len(subsidy_rows) > 1:
            return "not_ready", "client_subsidy_return_ambiguous", None
        candidate = build_client_finance_terms_candidate(
            facts, f"client-registry:{case_no}"
        )
        stages = {item.payment_stage.value: item for item in candidate.stage_plans}
        customer_payable = sum(item.amount.amount for item in candidate.stage_plans)
        subsidy = subsidy_rows[0] if subsidy_rows else None
        return "ready", None, {
            "virtual_account": build_client_virtual_account(case_no),
            "service_unit_price_ntd": facts.payment_terms.client_hourly_rate.amount,
            "service_hours": len(facts.charge_days) * facts.service_hours_per_day,
            "customer_payable_total_ntd": customer_payable,
            "deposit_amount_ntd": stages["deposit"].amount.amount,
            "first_payment_amount_ntd": stages["first"].amount.amount,
            "second_payment_amount_ntd": stages["second"].amount.amount,
            "received_total_ntd": received_total,
            "customer_balance_ntd": customer_payable - received_total,
            "subsidy_return_amount_ntd": (
                int(subsidy["amount_due_ntd"]) if subsidy is not None else None
            ),
            "subsidy_return_due_date": (
                subsidy["due_date"] if subsidy is not None else None
            ),
            "subsidy_return_status": (
                str(subsidy["status"]) if subsidy is not None else None
            ),
        }
    except (ValueError, StopIteration) as error:
        return "not_ready", str(error), None


def _client_service_received_total(cursor, case_no: str) -> int:
    """Return net client cash allocated to all service receivables."""
    cursor.execute(
        "SELECT COALESCE(SUM(CASE ledger.entry_type "
        "WHEN 'receipt' THEN allocation.amount_ntd "
        "WHEN 'adjustment' THEN allocation.amount_ntd "
        "WHEN 'refund' THEN -allocation.amount_ntd "
        "WHEN 'reversal' THEN -allocation.amount_ntd END),0) "
        "AS received_total_ntd FROM client_obligations obligation "
        "JOIN client_ledger_obligation_allocations allocation "
        "ON allocation.obligation_identity=obligation.obligation_identity "
        "JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id "
        "WHERE obligation.case_no=%s "
        "AND obligation.direction='receivable_from_client' "
        "AND obligation.obligation_type IN ('deposit','first','second','adjustment')",
        (case_no,),
    )
    row = cursor.fetchone()
    return int(row["received_total_ntd"] or 0) if row is not None else 0


__all__ = ["MySqlClientRegistryQueryRepository"]
