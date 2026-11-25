from datetime import date
from decimal import Decimal
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from domains.scheduling.service_date_adjustment import (
    AdjustmentTarget,
    ServiceDay,
    plan_service_date_adjustment,
)
from infrastructure.mysql.service_date_adjustment_repository import (
    MySqlServiceDateAdjustmentRepository,
    _active_pairs,
    _load_formal_receipts,
    load_first_schedule_dates,
)
from subsystems.scheduling.service_date_adjustment import (
    ServiceDateAdjustmentFacts,
    ServiceDateAdjustmentIntent,
    ServiceDateAdjustmentPair,
    ServiceDateAdjustmentWorkflow,
)


def test_merge_across_staff_and_months_and_restore_only_the_paired_days():
    first, second, target, unrelated = (
        date(2026, 11, 9),
        date(2026, 12, 12),
        date(2027, 1, 10),
        date(2027, 2, 8),
    )
    original = (ServiceDay(first, 3, None), ServiceDay(second, 7, None))
    merged = plan_service_date_adjustment(
        original, Decimal(4), (first, second), (AdjustmentTarget(target, 7),)
    )
    assert merged.removed == original
    assert merged.days == (ServiceDay(target, 7, 8),)
    assert merged.total_hours == Decimal(8)

    later_day = ServiceDay(unrelated, 11, 4)
    restored = plan_service_date_adjustment(
        (*merged.days, later_day), Decimal(4), (target,), (), reverse=merged
    )
    assert restored.days == (*original, later_day)
    assert restored.total_hours == Decimal(12)


def test_either_split_result_reverses_the_pair_and_restores_original_override():
    first, second, source = date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)
    original = (ServiceDay(source, 3, 8),)
    split = plan_service_date_adjustment(
        original, Decimal(4), (source,), (AdjustmentTarget(first, 3), AdjustmentTarget(second, 7))
    )
    assert split.days == (ServiceDay(first, 3, 4), ServiceDay(second, 7, 4))
    for selected in (first, second):
        restored = plan_service_date_adjustment(
            split.days, Decimal(4), (selected,), (), reverse=split
        )
        assert restored.days == original


def test_merge_rejects_target_owned_by_an_unselected_day():
    first, second, occupied = date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)
    with pytest.raises(ValueError, match="service_date_adjustment_ownership_conflict"):
        plan_service_date_adjustment(
            (ServiceDay(first, 3, None), ServiceDay(second, 3, None), ServiceDay(occupied, 7, None)),
            Decimal(4),
            (first, second),
            (AdjustmentTarget(occupied, 3),),
        )


def test_restore_rejects_a_changed_peer():
    source, first, second = date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)
    split = plan_service_date_adjustment(
        (ServiceDay(source, 3, None),),
        Decimal(8),
        (source,),
        (AdjustmentTarget(first, 3), AdjustmentTarget(second, 7)),
    )
    with pytest.raises(ValueError, match="service_date_adjustment_stale_pair"):
        plan_service_date_adjustment(
            (ServiceDay(first, 3, 4), ServiceDay(second, 9, 4)),
            Decimal(8),
            (first,),
            (),
            reverse=split,
        )


def test_explicit_merge_accepts_one_split_day_and_an_independent_day():
    source, first, second, independent, target = (date(2026, 11, value) for value in range(1, 6))
    independent_day = ServiceDay(independent, 7, 4)
    split = plan_service_date_adjustment(
        (ServiceDay(source, 3, None), independent_day),
        Decimal(8),
        (source,),
        (AdjustmentTarget(first, 3), AdjustmentTarget(second, 7)),
    )
    repository = Mock()
    repository.load.return_value = ServiceDateAdjustmentFacts(
        "CASE-1", 3, 4, None, 12, Decimal(8),
        split.days,
        ((3, "甲"), (7, "乙")), (ServiceDateAdjustmentPair(42, split),), 2, (),
    )
    workflow = ServiceDateAdjustmentWorkflow(repository, Mock())

    preview = workflow.preview(
        "CASE-1", ServiceDateAdjustmentIntent((first, independent), (AdjustmentTarget(target, 7),)),
    )

    assert preview.change.removed == (ServiceDay(first, 3, 4), independent_day)
    assert preview.change.days == (ServiceDay(second, 7, 4), ServiceDay(target, 7, 8))
    assert preview.change.total_hours == Decimal(12)


@pytest.mark.parametrize("reversed_latest", [False, True])
def test_first_schedule_uses_original_basis_after_chained_planned_adjustments(reversed_latest):
    first, second, merged, split_first, split_second = (date(2026, 11, value) for value in range(1, 6))

    def row(day, staff, hours):
        return {"service_date": day, "staff_id": staff, "service_hours_override": hours}

    def receipt(receipt_id, version, removed, inserted, reverse_id=None):
        def snapshot_days(rows):
            return [{"service_date": item["service_date"].isoformat(), "staff_id": item["staff_id"],
                     "hours_override": item["service_hours_override"]} for item in rows]

        return {"id": receipt_id, "reverse_receipt_id": reverse_id, "result_snapshot": {
            "confirmed_version": version, "scheduling_version": 3,
            "removed": snapshot_days(removed), "inserted": snapshot_days(inserted),
        }}

    original = [row(first, 3, None), row(second, 7, None)]
    merged_days = [row(merged, 7, 8)]
    split_days = [row(split_first, 3, 4), row(split_second, 7, 4)]
    receipts = [receipt(21, 4, original, merged_days), receipt(22, 5, merged_days, split_days)]
    if reversed_latest:
        receipts.append(receipt(23, 6, split_days, merged_days, reverse_id=22))
    current = merged_days if reversed_latest else split_days
    cursor = Mock()
    cursor.fetchone.return_value = {"id": 12, "version": 6 if reversed_latest else 5, "scheduling_version": 3}
    cursor.fetchall.side_effect = [
        [{"staff_id": 3}, {"staff_id": 7}],
        current,
        receipts,
    ]

    basis, actual = load_first_schedule_dates(cursor, "CASE-1", lock=False)

    assert basis == (ServiceDay(first, 3, None), ServiceDay(second, 7, None))
    assert actual == tuple(ServiceDay(item["service_date"], item["staff_id"], item["service_hours_override"])
                           for item in current)


def test_formal_adjustment_pairs_exclude_retired_receipts_even_when_dates_match():
    def receipt(receipt_id, day, scheduling_version, confirmed_version):
        return {"id": receipt_id, "reverse_receipt_id": None, "result_snapshot": {
            "confirmed_version": confirmed_version, "scheduling_version": scheduling_version,
            "removed": [], "inserted": [{"service_date": day.isoformat(), "staff_id": 7, "hours_override": 8}],
        }}

    first, second, third = (date(2026, 11, value) for value in range(1, 4))
    retired_plan = receipt(1, first, 0, 2)
    retired_formal = receipt(2, second, 5, 3)
    current_formal = receipt(3, third, 7, 4)
    cursor = Mock()
    cursor.fetchone.return_value = {"resulting_scheduling_version": 6}
    cursor.fetchall.side_effect = [
        (retired_plan, retired_formal, current_formal),
        ({"version": 2, "scheduling_version": 0}, {"version": 3, "scheduling_version": 3},
         {"version": 4, "scheduling_version": 6}),
    ]
    receipts = _load_formal_receipts(cursor, "CASE-1", {"version": 4, "scheduling_version": 6}, "")
    days = tuple(ServiceDay(day, 7, 8) for day in (first, second, third))
    assert [pair.receipt_id for pair in _active_pairs(receipts, days)] == [3]


@pytest.mark.parametrize("restore", [False, True])
def test_formal_adjustment_and_restore_persist_the_new_end_through_orders(restore, monkeypatch):
    from subsystems.scheduling.holiday_maintenance import HolidayCaseRepricingResult

    accounting_calls: list[tuple[str, str]] = []

    class UnchangedRepricing:
        def __init__(self, _connection: object) -> None:
            pass

        def prepare_case(self, case_no: str) -> None:
            accounting_calls.append(("prepare", case_no))

        def reprice_case(self, case_no: str, key: str, actor: str) -> HolidayCaseRepricingResult:
            accounting_calls.append(("reprice", case_no))
            return HolidayCaseRepricingResult(case_no, "unchanged", reason_code="pricing_amounts_unchanged")

    monkeypatch.setattr("infrastructure.mysql.holiday_repricing.MySqlHolidayRepricing", UnchangedRepricing)
    first, second, target = date(2026, 11, 1), date(2026, 11, 2), date(2026, 12, 3)
    original = (ServiceDay(first, 3, None), ServiceDay(second, 3, None))
    merged = plan_service_date_adjustment(original, Decimal(4), (first, second), (AdjustmentTarget(target, 3),))
    facts = ServiceDateAdjustmentFacts(
        "CASE-1", 3, 4, None, 12, Decimal(4), merged.days if restore else original,
        ((3, "Staff"),), (ServiceDateAdjustmentPair(41, merged),) if restore else (), 2, (),
    )
    intent = (ServiceDateAdjustmentIntent((target,), (), reverse_receipt_id=41) if restore
              else ServiceDateAdjustmentIntent((first, second), (AdjustmentTarget(target, 3),)))
    planning_repository = Mock()
    planning_repository.load.return_value = facts
    preview = ServiceDateAdjustmentWorkflow(planning_repository, Mock()).preview("CASE-1", intent)
    cursor = Mock(rowcount=1, lastrowid=42)
    connection = Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
    connection.cursor.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("infrastructure.mysql.service_date_adjustment_repository._write_formal", Mock())

    receipt = MySqlServiceDateAdjustmentRepository(connection).save(
        preview, intent, key="adjust-end", fingerprint="a" * 64, actor="admin",
    )

    order_writes = [call.args for call in cursor.execute.call_args_list if call.args[0].startswith("UPDATE orders ")]
    assert len(order_writes) == 1
    sql, values = order_writes[0]
    assert values == (second if restore else target, "CASE-1", 3)
    assert "actual_end_date=%s,lifecycle_version=lifecycle_version+1" in sql
    assert receipt.scheduling_version == 5
    assert accounting_calls == [("prepare", "CASE-1"), ("reprice", "CASE-1")]
    assert receipt.case_result == HolidayCaseRepricingResult(
        "CASE-1", "unchanged", reason_code="pricing_amounts_unchanged",
    )
    assert all(token not in sql for token in ("status=", "actual_start_date=", "staff_payment_due_date="))


def test_first_assignment_orders_impact_uses_the_adjusted_end(monkeypatch):
    from infrastructure.mysql.assignment_plan_impact_ports import MySqlOrdersAssignmentImpactPort

    original = (ServiceDay(date(2026, 11, 1), 3, None), ServiceDay(date(2026, 11, 2), 3, None))
    adjusted = (ServiceDay(date(2026, 12, 3), 3, 8),)
    monkeypatch.setattr("infrastructure.mysql.service_date_adjustment_repository.load_first_schedule_dates",
                        Mock(return_value=(original, adjusted)))
    builder = Mock()
    monkeypatch.setattr("infrastructure.mysql.assignment_plan_impact_ports.build_orders_assignment_impact", builder)
    facts = SimpleNamespace(assignment_plan=SimpleNamespace(effective_assignments=(), office_schedule=True))
    connection = Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=Mock())
    connection.cursor.return_value.__exit__ = Mock(return_value=False)

    MySqlOrdersAssignmentImpactPort(connection, Mock()).preview_assignment_plan(
        facts, SimpleNamespace(case_no="CASE-1"), Mock(),
    )

    assert builder.call_args.kwargs == {
        "effective_service_end": date(2026, 12, 3), "coordinated_final_day": True,
    }


def test_scheduled_end_projection_rejects_stale_order_version():
    from infrastructure.mysql.order_lifecycle_impact_writer import persist_order_scheduled_end_projection

    with pytest.raises(RuntimeError, match="order_version_conflict"):
        persist_order_scheduled_end_projection(
            Mock(rowcount=0), case_no="CASE-1", actual_end_date=date(2026, 12, 3), expected_order_version=3,
        )


def _holiday_mapping_receipt(receipt_id, removed, inserted, reverse_id=None):
    from subsystems.scheduling.service_date_adjustment import service_day_payload
    return {"id": receipt_id, "reverse_receipt_id": reverse_id, "result_snapshot": {
        "removed": [service_day_payload(day) for day in removed],
        "inserted": [service_day_payload(day) for day in inserted],
        "scheduling_version": receipt_id + 1, "confirmed_version": None,
    }}


@pytest.mark.parametrize("enabled", [False, True])
def test_holiday_merge_prices_both_original_financial_owners(monkeypatch, enabled):
    from infrastructure.mysql import service_date_adjustment_repository as repository
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
    from domains.client_finance.pricing_policy import (
        CasePricingTerms, HourlyRates, IdentityRule, calculate_holiday_premium,
    )
    first, second, target = date(2026, 11, 9), date(2026, 11, 12), date(2026, 11, 10)
    financial = (
        {"assignment_id": 101, "work_date": first, "financial_assignment_identity": "assignment:101"},
        {"assignment_id": 202, "work_date": second, "financial_assignment_identity": "assignment:202"},
    )
    assignments = ({"id": 101, "staff_id": 3}, {"id": 202, "staff_id": 7})
    receipt = _holiday_mapping_receipt(1,
        (ServiceDay(first, 3, None), ServiceDay(second, 7, None)), (ServiceDay(target, 3, 8),))
    monkeypatch.setattr(repository, "load_payroll_service_dates", lambda *args, **kwargs: financial)
    monkeypatch.setattr(repository, "_load_formal_receipts", lambda *args: (receipt,))
    monkeypatch.setattr(MySqlSchedulingHolidayQuery, "query", lambda *args, **kwargs: SimpleNamespace(
        holidays=(SimpleNamespace(holiday_date=target, is_double_pay_default=enabled),)))
    cursor = Mock()
    cursor.fetchall.return_value = ({"assignment_id": 101, "staff_id": 3, "work_date": target, "service_hours_override": 8},)
    cursor.fetchone.side_effect = [{"case_no": "cross-owner"}, None] * 2
    rows = repository.load_holiday_priced_service_dates(cursor, 9, assignments, 2, Decimal(4), lock=True)
    replay = repository.load_holiday_priced_service_dates(cursor, 9, assignments, 2, Decimal(4), lock=True)
    assert rows == replay
    assert [(row["assignment_id"], row["financial_assignment_identity"]) for row in rows] == [
        (101, "assignment:101"), (202, "assignment:202")]
    assert [row["holiday_hours"] for row in rows] == [Decimal(4 if enabled else 0)] * 2
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 320))
    days = tuple((Decimal(4), row["holiday_hour_segments"]) for row in rows)
    client_amount = 2800 + calculate_holiday_premium(terms, days)
    staff_amount = 2560 + calculate_holiday_premium(terms, days, payroll=True)
    assert (client_amount, staff_amount, client_amount - staff_amount) == (
        (5600, 5120, 480) if enabled else (2800, 2560, 240))


def test_holiday_mapping_exact_reverse_restores_each_original_source():
    from infrastructure.mysql.service_date_adjustment_repository import _holiday_priced_rows
    first, second, target = date(2026, 11, 9), date(2026, 11, 12), date(2026, 11, 10)
    originals = (ServiceDay(first, 3, None), ServiceDay(second, 7, None))
    merged = (ServiceDay(target, 3, 8),)
    rows = _holiday_priced_rows(
        ({"assignment_id": 101, "work_date": first}, {"assignment_id": 202, "work_date": second}),
        ({"assignment_id": 101, "staff_id": 3, "work_date": first, "service_hours_override": None},
         {"assignment_id": 202, "staff_id": 7, "work_date": second, "service_hours_override": None}),
        {101: 3, 202: 7},
        (_holiday_mapping_receipt(1, originals, merged), _holiday_mapping_receipt(2, merged, originals, 1)),
        Decimal(4), frozenset((target,)),
    )
    assert [row["holiday_hours"] for row in rows] == [0, 0]


def test_holiday_mapping_rejects_missing_per_source_split_instead_of_guessing():
    from infrastructure.mysql.service_date_adjustment_repository import _holiday_priced_rows, HolidayServiceAttributionError
    first, second, merged, left, right = (date(2026, 11, value) for value in range(1, 6))
    receipt = _holiday_mapping_receipt(1,
        (ServiceDay(first, 3, None), ServiceDay(second, 7, None)), (ServiceDay(merged, 3, 8),))
    split = _holiday_mapping_receipt(2, (ServiceDay(merged, 3, 8),),
        (ServiceDay(left, 3, 4), ServiceDay(right, 7, 4)))
    with pytest.raises(HolidayServiceAttributionError) as failure:
        _holiday_priced_rows(
            ({"assignment_id": 101, "work_date": first}, {"assignment_id": 202, "work_date": second}),
            ({"assignment_id": 101, "staff_id": 3, "work_date": left, "service_hours_override": 4},
             {"assignment_id": 202, "staff_id": 7, "work_date": right, "service_hours_override": 4}),
            {101: 3, 202: 7}, (receipt, split), Decimal(4), frozenset((left,)),
        )
    assert failure.value.code == "holiday_service_attribution_ambiguous"
    assert failure.value.missing_mapping == ("per_financial_source_to_target_hour_mapping",)
