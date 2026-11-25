"""
File: test_client_finance_cancellation_direction.py
Description: 驗證取消帳務方向與金額的 server-owned typed contract。
"""

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from api.schemas.order_cancellation import ClientFinanceActionView
from domains.client_finance.obligation_planning import (
    ClientChargeDay,
    ClientFinanceDirection,
    ClientSubsidyReturnPlan,
    ClientObligationAction,
    ClientObligationActionKind,
    ClientFinanceTermsSourceFacts,
    ClientFinanceTermsFacts,
    ClientPaymentTerms,
    ExistingClientStageObligation,
    build_client_finance_cancellation_impact,
    build_late_service_end_receipt_balance,
    build_client_finance_rate_correction_candidate,
    build_client_finance_terms_candidate,
    build_client_finance_terms_impact,
)
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_terms_read_model import (
    _materialize_contract_client_finance_facts,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.money import MoneyNTD


def _rate_correction_facts(day_count: int) -> ClientFinanceTermsFacts:
    return ClientFinanceTermsFacts(
        "CASE-RATE-CORRECTION",
        4,
        8,
        MoneyNTD(1000),
        tuple(
            ClientChargeDay(date(2026, 10, 1) + timedelta(days=i), False)
            for i in range(day_count)
        ),
        ClientPaymentTerms(
            5, MoneyNTD(450), date(2026, 9, 1), date(2026, 10, 1), None,
        ),
        (),
    )


@pytest.mark.parametrize(
    "first_due,expected_due",
    [(date(2026, 10, 1), date(2026, 10, 16)),
     (date(2026, 12, 22), date(2027, 1, 6)),
     (date(2028, 2, 20), date(2028, 3, 6))],
)
def test_second_due_date_is_first_planned_due_plus_fifteen_days(first_due, expected_due):
    facts = _rate_correction_facts(30)
    facts = replace(
        facts,
        charge_days=tuple(ClientChargeDay(first_due + timedelta(days=i), False) for i in range(30)),
        payment_terms=replace(facts.payment_terms, first_payment_due_date=first_due),
    )
    candidate = build_client_finance_terms_candidate(facts, "second-planned-date")
    second = next(plan for plan in candidate.stage_plans if plan.payment_stage is PaymentStage.SECOND)
    assert second.amount.amount == 36000
    assert second.due_date == expected_due


def test_second_due_date_is_absent_when_no_second_payment_is_due():
    facts = _rate_correction_facts(20)
    facts = replace(facts, payment_terms=replace(facts.payment_terms, second_payment_due_date=date(2026, 10, 20)))
    candidate = build_client_finance_terms_candidate(facts, "no-second-planned-date")
    second = next(plan for plan in candidate.stage_plans if plan.payment_stage is PaymentStage.SECOND)
    assert second.amount.amount == 0
    assert second.due_date is None


@pytest.mark.parametrize('original_due', [date(2026, 10, 16), None])
def test_paid_second_stage_refund_preserves_its_source_due_date(original_due):
    facts = replace(_rate_correction_facts(5), existing_obligations=(
        ExistingClientStageObligation('paid-second', PaymentStage.SECOND,
            MoneyNTD(36000), MoneyNTD(36000), original_due, True),
    ))
    candidate = build_client_finance_terms_candidate(facts, 'cancel-paid-second')
    action = next(item for item in candidate.actions if item.payment_stage is PaymentStage.SECOND)
    assert action.action is ClientObligationActionKind.CREATE_REFUND
    assert action.direction is ClientFinanceDirection.REFUND_DUE
    assert action.direction_amount_ntd == 36000
    assert action.after_due_date == original_due


def test_cancellation_settlement_applies_cash_to_rendered_service_before_fee():
    case_no = "CASE-SERVED"
    service_day = date(2026, 8, 1)
    assignment = AssignmentCandidate(
        f"{case_no}:g2:a1", 1, 7, 1, service_day, service_day, (service_day,), 8,
    )
    scheduling = SchedulingGenerationCandidate(case_no, 2, 1, 2, (1,), (assignment,), ())
    terms = OrderTerms(service_day, 2, 8, MoneyNTD(0), ServiceTimeTerms(None, None, None))
    source = ClientFinanceTermsSourceFacts(
        case_no, 5,
        ClientPaymentTerms(0, MoneyNTD(500), date(2026, 7, 1), service_day, None),
        (), (),
    )
    impact = build_client_finance_cancellation_impact(
        source, terms, scheduling, "historical-cancellation:served",
        net_cash_received=MoneyNTD(6000), fee=MoneyNTD(2500),
        fee_reason="approved fee", processed_on=service_day,
    )
    summary = impact.cancellation_settlement
    assert (summary.service_due_ntd, summary.net_received_ntd, summary.fee_received_ntd) == (4000, 6000, 2000)
    assert (summary.refund_due_ntd, summary.additional_charge_due_ntd) == (0, 500)
    adjustment, = impact.actions
    assert adjustment.action is ClientObligationActionKind.CREATE_ADJUSTMENT
    assert adjustment.direction_amount_ntd == 500


def test_rate_correction_before_matching_advances_version_without_obligations():
    candidate = build_client_finance_rate_correction_candidate(
        _rate_correction_facts(0), "beclass-rate-correction:9",
    )
    assert (candidate.expected_account_version, candidate.resulting_account_version) == (4, 5)
    assert candidate.actions == candidate.stage_plans == ()
    assert candidate.settlement.deposit_settled is False
    assert candidate.settlement.all_formal_obligations_settled is False


def test_rate_correction_with_40_service_dates_keeps_all_stage_amounts():
    candidate = build_client_finance_rate_correction_candidate(
        _rate_correction_facts(40), "beclass-rate-correction:9",
    )
    assert [len(plan.service_dates) for plan in candidate.stage_plans] == [5, 15, 20]
    assert [plan.amount.amount for plan in candidate.stage_plans] == [19000, 54000, 72000]


def test_rate_correction_does_not_bypass_missing_dates_for_existing_obligations():
    facts = replace(
        _rate_correction_facts(0),
        existing_obligations=(ExistingClientStageObligation(
            "client-obligation:CASE-RATE-CORRECTION:deposit",
            PaymentStage.DEPOSIT,
            MoneyNTD(12000),
            MoneyNTD(0),
            date(2026, 9, 1),
            False,
        ),),
    )
    with pytest.raises(ValueError, match="deposit service days exceed official service days"):
        build_client_finance_rate_correction_candidate(facts, "beclass-rate-correction:9")


def test_rate_correction_limits_deposit_to_existing_formal_service_dates():
    facts = _rate_correction_facts(3)
    candidate = build_client_finance_rate_correction_candidate(
        facts, "beclass-rate-correction:9",
    )
    assert [len(stage.service_dates) for stage in candidate.stage_plans] == [3, 0, 0]
    assert [stage.amount.amount for stage in candidate.stage_plans] == [11800, 0, 0]
    assert candidate.payment_terms.deposit_service_days == facts.payment_terms.deposit_service_days == 5


@pytest.mark.parametrize("paid", [False, True])
def test_shortened_service_keeps_original_terms_and_cash_with_owner_difference(paid):
    original = _rate_correction_facts(5)
    original_plan = build_client_finance_terms_candidate(original, "before-early-end")
    deposit = original_plan.stage_plans[0]
    recorded = ExistingClientStageObligation(
        "original-deposit", PaymentStage.DEPOSIT, deposit.amount,
        deposit.amount if paid else MoneyNTD(0), deposit.due_date, paid,
    )
    shorter = replace(original, charge_days=original.charge_days[:2], existing_obligations=(recorded,))
    candidate = build_client_finance_terms_candidate(shorter, "early-end")
    assert [stage.amount.amount for stage in candidate.stage_plans] == [8200, 0, 0]
    assert candidate.payment_terms.deposit_service_days == 5
    assert shorter.payment_terms == original.payment_terms
    assert recorded.contracted_amount == MoneyNTD(19000)
    assert recorded.net_settled_amount == (MoneyNTD(19000) if paid else MoneyNTD(0))
    action = candidate.actions[0]
    assert action.action is (ClientObligationActionKind.CREATE_REFUND if paid else ClientObligationActionKind.REPLACE_OPEN)
    assert action.direction_amount_ntd == (10800 if paid else 0)
    from domains.client_finance.obligation_planning import confirmed_zero_payment_stages
    current = replace(shorter, existing_obligations=())
    assert confirmed_zero_payment_stages(current) == {PaymentStage.FIRST, PaymentStage.SECOND}


def test_full_subsidy_terms_do_not_create_client_service_principal() -> None:
    dates = tuple(date(2026, 8, day) for day in range(1, 16))
    scheduling = SchedulingGenerationCandidate(
        "CASE-FULL-SUBSIDY",
        2,
        1,
        2,
        (1,),
        (
            AssignmentCandidate(
                "CASE-FULL-SUBSIDY:g2:a1",
                1,
                7,
                1,
                dates[0],
                dates[-1],
                dates,
                120,
            ),
        ),
        (),
    )
    source = ClientFinanceTermsSourceFacts(
        "CASE-FULL-SUBSIDY",
        3,
        ClientPaymentTerms(
            0,
            MoneyNTD(350),
            date(2026, 7, 1),
            date(2026, 8, 1),
            date(2026, 8, 15),
        ),
        (),
        (),
        identity_status="社福",
    )
    terms = OrderTerms(
        dates[0],
        15,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(None, None, None),
    )

    candidate = build_client_finance_terms_impact(
        source,
        terms,
        scheduling,
        "actual-start:full-subsidy",
    )

    assert sum(plan.amount.amount for plan in candidate.stage_plans) == 0


def test_shared_contract_finance_reader_preserves_full_subsidy_waiver() -> None:
    start = date(2026, 10, 1)
    charge_days = tuple(
        ClientChargeDay(start + timedelta(days=offset), False)
        for offset in range(15)
    )
    source = ClientFinanceTermsSourceFacts(
        case_no="115000010",
        account_version=3,
        payment_terms=ClientPaymentTerms(
            deposit_service_days=5,
            client_hourly_rate=MoneyNTD(350),
            deposit_due_date=date(2026, 9, 20),
            first_payment_due_date=date(2026, 10, 1),
            second_payment_due_date=date(2026, 10, 15),
        ),
        double_pay_dates=(),
        existing_obligations=(),
        identity_status="社福",
    )

    facts = _materialize_contract_client_finance_facts(
        {"case_no": "115000010", "service_hours_per_day": 8, "floor_fee": 0},
        charge_days,
        source,
    )
    candidate = build_client_finance_terms_candidate(facts, "test-full-subsidy")

    assert facts.client_service_charge_waived is True
    assert sum(stage.amount.amount for stage in candidate.stage_plans) == 0


def _action(
    kind: ClientObligationActionKind,
    before: int,
    after: int,
    direction: ClientFinanceDirection,
    direction_amount: int,
) -> ClientObligationAction:
    return ClientObligationAction(
        kind,
        PaymentStage.FIRST,
        "client-obligation:CASE-1:first",
        MoneyNTD(before),
        MoneyNTD(after),
        MoneyNTD(abs(after - before)),
        date(2026, 8, 1),
        date(2026, 8, 2),
        None,
        direction,
        direction_amount,
    )


@pytest.mark.parametrize(
    ("kind", "before", "after", "direction", "amount"),
    (
        (
            ClientObligationActionKind.CREATE_STAGE,
            0,
            8000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            8000,
        ),
        (
            ClientObligationActionKind.REPLACE_OPEN,
            8000,
            10000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            2000,
        ),
        (
            ClientObligationActionKind.REPLACE_OPEN,
            10000,
            8000,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
        (
            ClientObligationActionKind.REPLACE_OPEN,
            8000,
            8000,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
        (
            ClientObligationActionKind.CANCEL_OPEN,
            8000,
            0,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
        (
            ClientObligationActionKind.CREATE_ADJUSTMENT,
            8000,
            10000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            2000,
        ),
        (
            ClientObligationActionKind.CREATE_REFUND,
            10000,
            8000,
            ClientFinanceDirection.REFUND_DUE,
            2000,
        ),
        (
            ClientObligationActionKind.UNCHANGED,
            8000,
            8000,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
    ),
)
def test_action_accepts_canonical_direction_mapping(
    kind, before, after, direction, amount
) -> None:
    action = _action(kind, before, after, direction, amount)

    assert action.direction is direction
    assert action.direction_amount_ntd == amount


def test_action_rejects_direction_inferred_from_action_or_signed_amount() -> None:
    with pytest.raises(ValueError, match="client_finance_direction_mismatch"):
        _action(
            ClientObligationActionKind.CREATE_REFUND,
            10000,
            8000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            2000,
        )

    with pytest.raises(ValueError, match="client_finance_direction_amount_mismatch"):
        _action(
            ClientObligationActionKind.CREATE_REFUND,
            10000,
            8000,
            ClientFinanceDirection.REFUND_DUE,
            1,
        )


def test_api_view_requires_direction_and_nonnegative_direction_amount() -> None:
    payload = {
        "action": "create_refund",
        "payment_stage": "first",
        "obligation_identity": "client-obligation:CASE-1:first",
        "before_amount": {"amount": 10000},
        "after_amount": {"amount": 8000},
        "obligation_amount": {"amount": 2000},
        "before_due_date": date(2026, 8, 1),
        "after_due_date": date(2026, 8, 2),
        "source_obligation_identity": None,
        "direction": "refund_due",
        "direction_amount_ntd": 2000,
    }

    assert ClientFinanceActionView.model_validate(payload).direction == "refund_due"
    with pytest.raises(ValueError):
        ClientFinanceActionView.model_validate({**payload, "direction_amount_ntd": -1})
    with pytest.raises(ValueError, match="financial direction amount must be positive"):
        ClientFinanceActionView.model_validate({**payload, "direction_amount_ntd": 0})
    with pytest.raises(ValueError, match="no_finance_change direction amount must be zero"):
        ClientFinanceActionView.model_validate(
            {
                **payload,
                "direction": "no_finance_change",
                "direction_amount_ntd": 1,
            }
        )


class _Cursor:
    def __init__(self):
        self.statements = []
        self.lastrowid = 20
        self.rowcount = 1

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        if "INSERT INTO client_obligation_events" in statement:
            self.lastrowid += 1

    def fetchall(self):
        return ()

    def fetchone(self):
        if ' paid ' in self.statements[-1][0]:return {'paid':0}
        if ' recovered ' in self.statements[-1][0]:return {'recovered':0}
        if 'SELECT COALESCE(SUM(' in self.statements[-1][0]:return {'amount':0}
        return None


class _PaymentTermsCursor(_Cursor):
    def __init__(self, saved_due):
        super().__init__()
        self.terms = {
            "policy_version": "client-v1", "client_hourly_rate_ntd": 450,
            "deposit_service_days": 5, "deposit_due_date": date(2026, 9, 1),
            "first_payment_due_date": date(2026, 10, 1),
            "second_payment_due_date": saved_due, "current_event_id": 10,
        }

    def fetchone(self):
        if 'FROM client_payment_terms ' in self.statements[-1][0]:
            return self.terms
        return super().fetchone()


@pytest.mark.parametrize("before_status", ["歷史訂單－服務完成", "訂單取消", "訂單成立"])
def test_cancellation_defers_government_sync_until_orders_saves_terminal_facts(monkeypatch, before_status):
    from unittest.mock import Mock
    from domains.orders.lifecycle import OrderLifecycleStatus
    import infrastructure.mysql.client_finance_terms_writer as finance_writer
    import infrastructure.mysql.government_period_difference_repository as government_writer
    from infrastructure.mysql.order_cancellation_repository import MySqlOrderCancellationRepository
    from subsystems.orders.cancellation_workflow import CancellationOrderPersistenceCommand

    calls = []
    order = {"status": before_status}

    class TerminalCursor(_Cursor):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, parameters):
            super().execute(statement, parameters)
            if statement.startswith("UPDATE orders SET"):
                order["status"] = parameters[2]
                calls.append("orders_terminal")

    cursor = TerminalCursor()
    connection = SimpleNamespace(cursor=lambda: cursor, commit=Mock())
    cursor.connection = connection
    monkeypatch.setattr(finance_writer, "_persist_payment_terms", lambda *_args: False)
    monkeypatch.setattr(finance_writer, "_advance_account_version", lambda *_args: calls.append("finance_account"))
    monkeypatch.setattr(finance_writer, "_save_cancellation_settlement", lambda *_args: calls.append("finance_receipt"))
    monkeypatch.setattr(finance_writer, "_append_outbox", lambda *_args: calls.append("finance_outbox"))

    def synchronize_government(_cursor, case_no, key, actor, reason):
        assert (case_no, key, actor, reason) == ("CASE-TERMINAL", "terminal-sync", "admin", "confirmed zero service")
        assert order["status"] == OrderLifecycleStatus.ESTABLISHED_UNSERVED.value
        calls.append("government_final")

    monkeypatch.setattr(government_writer, "synchronize_government_case_amount", synchronize_government)
    candidate = SimpleNamespace(
        case_no="CASE-TERMINAL", stage_plans=(), payment_terms=None, actions=(),
        cancellation_settlement=object(), subsidy_return_plan=None,
    )
    command = ClientFinanceImpactPersistenceCommand(
        candidate, IdempotencyKey("terminal-sync"), ActorContext("admin"),
        "confirmed zero service", CorrelationId("terminal-sync"), "orders_cancellation", 9,
    )

    finance_writer.persist_client_finance_terms_impact(cursor, command)
    assert calls == ["finance_account", "finance_receipt", "finance_outbox"]
    assert order["status"] == before_status

    MySqlOrderCancellationRepository(connection).update_cancelled_order(CancellationOrderPersistenceCommand(
        command.candidate.case_no, 1, 2, None, None,
        OrderLifecycleStatus.ESTABLISHED_UNSERVED, command.actor, command.reason, command.idempotency_key,
    ))

    assert calls == ["finance_account", "finance_receipt", "finance_outbox", "orders_terminal", "government_final"]
    connection.commit.assert_not_called()


def test_non_cancellation_terms_keep_government_sync_after_finance_persistence(monkeypatch):
    import infrastructure.mysql.client_finance_terms_writer as finance_writer
    import infrastructure.mysql.government_period_difference_repository as government_writer

    calls = []
    monkeypatch.setattr(finance_writer, "_persist_payment_terms", lambda *_args: True)
    monkeypatch.setattr(finance_writer, "_advance_account_version", lambda *_args: calls.append("finance_account"))
    monkeypatch.setattr(finance_writer, "_append_outbox", lambda *_args: calls.append("finance_outbox"))
    monkeypatch.setattr(government_writer, "synchronize_government_case_amount", lambda *_args: calls.append("government_terms"))
    candidate = SimpleNamespace(
        case_no="CASE-TERMS", stage_plans=(), payment_terms=None, actions=(), subsidy_return_plan=None,
    )
    command = ClientFinanceImpactPersistenceCommand(
        candidate, IdempotencyKey("terms-sync"), ActorContext("admin"),
        "service terms corrected", CorrelationId("terms-sync"), "orders_terms", 9,
    )

    finance_writer.persist_client_finance_terms_impact(_Cursor(), command)

    assert calls == ["finance_account", "finance_outbox", "government_terms"]


@pytest.mark.parametrize("days,saved_due,expected,writes", [
    (30, None, date(2026, 10, 16), True),
    (30, date(2026, 10, 20), date(2026, 10, 16), True),
    (30, date(2026, 10, 16), date(2026, 10, 16), False),
    (20, date(2026, 10, 16), None, True),
])
def test_finance_writer_synchronizes_second_due_date_and_terms_event(days, saved_due, expected, writes):
    candidate = build_client_finance_terms_candidate(_rate_correction_facts(days), "CASE-DATE-WRITE")
    cursor = _PaymentTermsCursor(saved_due)
    command = ClientFinanceImpactPersistenceCommand(
        candidate, IdempotencyKey("terms-date-sync"), ActorContext("admin"),
        "second planned due date", CorrelationId("terms-date-sync"), "contract-completion", 9,
    )
    persist_client_finance_terms_impact(cursor, command)
    events = [params for sql, params in cursor.statements
              if "INSERT INTO client_payment_terms_events" in sql]
    updates = [params for sql, params in cursor.statements
               if "UPDATE client_payment_terms SET" in sql]
    assert bool(events) is writes
    assert bool(updates) is writes
    if writes:
        assert events[0][6] == updates[0][0] == expected
        assert events[0][7] == candidate.expected_account_version
        assert updates[0][7] == cursor.terms["current_event_id"]


def test_cancellation_writer_persists_subsidy_return_as_separate_client_payable():
    cursor = _Cursor()
    plan = ClientSubsidyReturnPlan(
        "client-subsidy-return:CASE-1:terminal",
        MoneyNTD(14_400),
        date(2026, 10, 15),
    )
    candidate = SimpleNamespace(
        case_no="CASE-1",
        expected_account_version=5,
        resulting_account_version=6,
        stage_plans=(),
        payment_terms=None,
        actions=(),
        subsidy_return_plan=plan,
        fingerprint=PreviewFingerprint("a" * 64),
    )
    command = ClientFinanceImpactPersistenceCommand(
        candidate,
        IdempotencyKey("cancel-client-finance-1"),
        ActorContext("admin"),
        "mid-service cancellation",
        CorrelationId("cancel-client-finance-test"),
        "order-cancellation",
        9,
    )

    persist_client_finance_terms_impact(cursor, command)

    event = next(
        values
        for statement, values in cursor.statements
        if "INSERT INTO client_obligation_events" in statement
    )
    projection = next(
        values
        for statement, values in cursor.statements
        if "INSERT INTO client_obligations" in statement
    )
    assert event[2:5] == ("subsidy_return", "payable_to_client", "established")
    assert event[6] == 14_400
    assert projection[2:7] == (
        "subsidy_return",
        "payable_to_client",
        None,
        14_400,
        date(2026, 10, 15),
    )


@pytest.mark.parametrize("rate,expected", [(300, 8200), (350, 9400)])
def test_formal_terms_candidate_uses_enabled_holiday_in_original_single_write_plan(rate, expected):
    day = date(2026, 1, 1)
    source = ClientFinanceTermsSourceFacts("HOLIDAY-NEW", 2,
        ClientPaymentTerms(0, MoneyNTD(rate), day, day, None), (day,), ())
    terms = OrderTerms(day, 2, 8, MoneyNTD(1000), ServiceTimeTerms(None, None, None))
    assignment = AssignmentCandidate("new-assignment", None, 7, 1, day, date(2026, 1, 2),
        (day, date(2026, 1, 2)), 16)
    scheduling = SchedulingGenerationCandidate("HOLIDAY-NEW", 1, 0, 1, (), (assignment,), ())
    candidate = build_client_finance_terms_impact(source, terms, scheduling, "holiday-new")
    assert candidate.expected_account_version == 2
    assert candidate.resulting_account_version == 3
    assert sum(stage.amount.amount for stage in candidate.stage_plans) == expected


@pytest.mark.parametrize("status", ["歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成"])
def test_historical_terms_source_does_not_consume_current_holiday_calendar(status, monkeypatch):
    from infrastructure.mysql.order_terms_read_model import _enabled_holiday_dates
    import infrastructure.mysql.scheduling_holiday_query as holiday_adapter
    def unavailable_calendar(connection):
        raise AssertionError("historical case must not query current holidays")
    monkeypatch.setattr(holiday_adapter, "MySqlSchedulingHolidayQuery", unavailable_calendar)
    assert _enabled_holiday_dates(SimpleNamespace(connection=object()), {"status": status}, False) == ()


@pytest.mark.parametrize("lock", [False, True])
def test_general_terms_source_borrows_enabled_holidays_with_matching_lock_mode(lock, monkeypatch):
    from infrastructure.mysql.order_terms_read_model import _enabled_holiday_dates
    import infrastructure.mysql.order_terms_read_model as read_model
    import infrastructure.mysql.scheduling_holiday_query as holiday_adapter
    monkeypatch.setattr(read_model, "_historical_precision_restarted", lambda cursor, case_no, lock: False)
    calls = []
    enabled, disabled = date(2026, 1, 1), date(2027, 1, 1)
    class CalendarQuery:
        def __init__(self, connection):
            self.connection = connection
        def query(self, start, end, *, lock):
            calls.append(lock)
            return SimpleNamespace(holidays=(
                SimpleNamespace(holiday_date=enabled, is_double_pay_default=True),
                SimpleNamespace(holiday_date=disabled, is_double_pay_default=False),
            ))
    monkeypatch.setattr(holiday_adapter, "MySqlSchedulingHolidayQuery", CalendarQuery)
    assert _enabled_holiday_dates(SimpleNamespace(connection=object()), {"case_no": "ordinary-holiday", "status": "訂單成立"}, lock) == (enabled,)
    assert calls == [lock]



@pytest.mark.parametrize("lock", [False, True])
def test_precision_restart_source_excludes_holidays_after_establishment(lock, monkeypatch):
    from infrastructure.mysql.order_terms_read_model import _enabled_holiday_dates
    import infrastructure.mysql.scheduling_holiday_query as holiday_adapter

    class Cursor:
        connection = object()

        def execute(self, statement, parameters):
            assert "orders_historical_precision_restart" in statement
            assert ("FOR UPDATE" in statement) is lock
            assert parameters == ("restarted-history", "訂單成立")

        def fetchone(self):
            return {"id": 17}

    def forbidden(connection):
        raise AssertionError("precisely restarted historical source must not query holiday flags")

    monkeypatch.setattr(holiday_adapter, "MySqlSchedulingHolidayQuery", forbidden)
    assert _enabled_holiday_dates(Cursor(), {"case_no": "restarted-history", "status": "訂單成立"}, lock) == ()


def test_legacy_social_without_effective_limit_defers_holiday_premium():
    from domains.client_finance.obligation_planning import ClientChargeDay, ClientFinanceTermsFacts, _daily_charge
    day = date(2026, 1, 1)
    facts = ClientFinanceTermsFacts("legacy-social", 0, 8, MoneyNTD(0),
        (ClientChargeDay(day, True),), ClientPaymentTerms(0, MoneyNTD(350), day, day, None), (),
        identity_status="社福")
    assert _daily_charge(facts, facts.charge_days[0]) == MoneyNTD(0)


@pytest.mark.parametrize("identity", ["補助市民", "原住民"])
def test_legacy_holiday_funding_with_floor_fee_does_not_invent_effective_limit(identity):
    from domains.client_finance.obligation_planning import ClientChargeDay, ClientFinanceTermsFacts, _holiday_funding_pending
    day = date(2026, 1, 1)
    facts = ClientFinanceTermsFacts("legacy-limit-missing", 0, 8, MoneyNTD(500),
        (ClientChargeDay(day, True),), ClientPaymentTerms(0, MoneyNTD(350), day, day, None), (),
        identity_status=identity)
    assert _holiday_funding_pending(facts) is True

@pytest.mark.parametrize(
    ("service_due", "fee", "net_cash", "pending_before", "bank_receipt", "expected"),
    [
        (0, 0, 0, 0, 5000, (5000, 5000, 5000, 0, 0)),
        (2000, 0, 0, 0, 5000, (5000, 3000, 3000, 0, 0)),
        (0, 500, 0, 0, 5000, (5000, 4500, 4500, 0, 500)),
        (2000, 500, 0, 0, 2100, (2100, 0, 0, 400, 100)),
        # Net cash already excludes formal prior refunds; open refunds still count once.
        (2000, 0, 3500, 1500, 5000, (8500, 6500, 5000, 0, 0)),
    ],
)
def test_late_receipt_plans_refund_without_recreating_receivable(
    service_due: int, fee: int, net_cash: int, pending_before: int,
    bank_receipt: int, expected: tuple[int, int, int, int, int],
):
    result = build_late_service_end_receipt_balance(
        service_due=MoneyNTD(service_due), authorized_fee=MoneyNTD(fee),
        net_cash_before=MoneyNTD(net_cash), confirmed_bank_receipt=MoneyNTD(bank_receipt),
        existing_pending_refund=MoneyNTD(pending_before),
    )
    assert (
        result.net_received_ntd, result.pending_refund_ntd, result.new_refund_ntd,
        result.additional_charge_due_ntd, result.fee_received_ntd,
    ) == expected


@pytest.mark.parametrize(
    ("net_cash", "pending_before", "code"),
    [(5000, 0, "late_service_end_receipt_prior_unresolved_refund"),
     (0, 10000, "late_service_end_receipt_existing_refund_requires_review")],
)
def test_late_receipt_does_not_change_unidentified_existing_refund_balance(
    net_cash: int, pending_before: int, code: str,
):
    with pytest.raises(ValueError, match=code):
        build_late_service_end_receipt_balance(
            service_due=MoneyNTD(0), authorized_fee=MoneyNTD(0),
            net_cash_before=MoneyNTD(net_cash), confirmed_bank_receipt=MoneyNTD(5000),
            existing_pending_refund=MoneyNTD(pending_before),
        )


@pytest.mark.parametrize("terminal", ["訂單取消", "成立後未服務", "訂單完成"])
def test_late_sinopac_owner_preview_requires_real_case_and_prices_earned_service(monkeypatch, terminal: str):
    from infrastructure.mysql import client_service_end_receipt_preview as module

    occurred = date(2026, 10, 1)
    order = {
        "case_no": "116000001", "status": terminal, "lifecycle_version": 3,
        "service_days": 1, "actual_start_date": occurred, "actual_end_date": occurred,
    }
    bank = {
        "format_id": "sinopac", "direction": "incoming", "transaction_date": occurred,
        "currency": "TWD", "credit": 5000, "debit": 0, "reconciliation_status": "pending",
        "canonical_fact_version": 3, "effective_classification_type": "client_receipt", "bank_references": {"銷帳編號": "99781699116001"},
    }

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, parameters):
            assert sql.startswith("SELECT")
            if "FROM client_finance_accounts" in sql:
                self.row = {"aggregate_version": 2}
            elif "FROM finance_import_rows" in sql:
                self.row = bank
            elif "FROM order_terms_apply_receipts" in sql:
                self.row = {"id": 1}
            elif "FROM client_obligations" not in sql:
                raise AssertionError(sql)

        def fetchone(self):
            return self.row

        def fetchall(self):
            return ()

    monkeypatch.setattr(module, "select_order", lambda *args, **kwargs: order)
    monkeypatch.setattr(module, "query_case_net_cash", lambda *args: 0)
    monkeypatch.setattr(module, "query_cancellation_accounting",
                        lambda *args: SimpleNamespace(service_due_ntd=0, fee_ntd=0))
    monkeypatch.setattr(module, "resolve_client_virtual_account",
                        lambda *args: {"result": "resolved", "case_no": order["case_no"]})
    monkeypatch.setattr(module, "load_calculable_client_finance_facts",
                        lambda *args, **kwargs: (SimpleNamespace(charge_days=(ClientChargeDay(occurred, False),)), None))
    monkeypatch.setattr(module, "_build_stage_plans", lambda facts: (SimpleNamespace(amount=MoneyNTD(2000)),))
    connection = SimpleNamespace(cursor=Cursor)
    result = module.preview_client_service_end_receipt(connection, row_id=10, case_no=order["case_no"])
    assert result.bank_amount_ntd == 5000
    assert result.balance.pending_refund_ntd == (3000 if terminal == "訂單完成" else 5000)
    changed = module.preview_client_service_end_receipt(connection, row_id=10, case_no=order["case_no"], lock=True)
    assert changed.fingerprint == result.fingerprint

    order["status"] = "服務中"
    with pytest.raises(ValueError, match="late_service_end_receipt_completion_not_verified"):
        module.preview_client_service_end_receipt(connection, row_id=10, case_no=order["case_no"])
    order["status"] = terminal
    bank["direction"] = "outgoing"
    with pytest.raises(ValueError, match="late_service_end_receipt_requires_sinopac_income"):
        module.preview_client_service_end_receipt(connection, row_id=10, case_no=order["case_no"])


@pytest.mark.parametrize("earned", [0, 2000])
def test_late_receipt_writer_persists_original_credit_and_linked_refund(monkeypatch, earned: int):
    from infrastructure.mysql import client_service_end_receipt_writer as writer
    from infrastructure.mysql.client_service_end_receipt_preview import (
        ClientServiceEndReceiptPreview, LateReceiptOpenBalance,
    )

    fingerprint = PreviewFingerprint("a" * 64)
    existing = (LateReceiptOpenBalance("earned-first", "first", "receivable_from_client", earned, 8),) if earned else ()
    preview = ClientServiceEndReceiptPreview(
        32, "116000001", date(2026, 10, 1), 5000, earned, 0, 2,
        build_late_service_end_receipt_balance(
            service_due=MoneyNTD(earned), authorized_fee=MoneyNTD(0), net_cash_before=MoneyNTD(0),
            confirmed_bank_receipt=MoneyNTD(5000), existing_pending_refund=MoneyNTD(0),
        ), existing, fingerprint,
    )
    writes = []
    class Cursor:
        lastrowid = 15
        rowcount = 1
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def execute(self, statement, args):
            writes.append((statement, args))
    connection = SimpleNamespace(cursor=Cursor)
    monkeypatch.setattr(writer, "preview_client_service_end_receipt",
                        lambda *_args, **kwargs: preview if kwargs["lock"] else pytest.fail("missing lock"))
    monkeypatch.setattr(writer, "_insert_refund_recipient_snapshot", lambda *args, **kwargs: None)
    result = writer.apply_client_service_end_receipt(
        connection, expected=preview, key=IdempotencyKey("one-source"), actor=ActorContext("finance"),
        reason="matched bank reference",
    )
    assert result.allocation_count == int(earned > 0)
    assert writes[0][0].startswith("INSERT INTO client_ledger_entries")
    assert writes[0][1][1:3] == (32, 5000)
    refund_event = next(args for sql, args in writes if sql.startswith("INSERT INTO client_obligation_events"))
    assert refund_event[0:4] == (result.refund_identity, "116000001", 5000 - earned, "sinopac-service-end-ledger:15")
    pending = [args for sql, args in writes if sql.startswith("INSERT INTO client_obligations")]
    assert len(pending) == 1 and pending[0][3] == 5000 - earned
    allocations = [args for sql, args in writes if sql.startswith("INSERT INTO client_ledger_obligation_allocations")]
    assert allocations == ([(15, "earned-first", earned, 1)] if earned else [])
    assert len([1 for sql, _ in writes if sql.startswith("INSERT INTO client_ledger_entries")]) == 1
    assert not any("UPDATE orders" in sql or "staff_schedule" in sql for sql, _ in writes)

    writes.clear()
    invalid = replace(preview, fingerprint=PreviewFingerprint("b" * 64))
    with pytest.raises(ValueError, match="late_service_end_receipt_preview_stale"):
        writer.apply_client_service_end_receipt(connection, expected=invalid, key=IdempotencyKey("stale"),
                                               actor=ActorContext("finance"), reason="stale")
    assert writes == []
