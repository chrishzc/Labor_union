from datetime import date
from types import SimpleNamespace

from infrastructure.mysql.payroll_terms_writer import (
    _action_requires_event,
    _insert_special_pay_events,
)
from shared_kernel.identities import ActorContext, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    _candidate,
    PayrollSpecialPayEventCandidate,
    PayrollTermsActionKind,
)


def test_zero_amount_payroll_action_does_not_create_an_immutable_event():
    action = SimpleNamespace(
        action=PayrollTermsActionKind.ESTABLISH,
        amount=MoneyNTD(0),
    )

    assert _action_requires_event(action) is False


def test_nonzero_payroll_action_still_creates_an_immutable_event():
    action = SimpleNamespace(
        action=PayrollTermsActionKind.CLOSE_UNPAID,
        amount=MoneyNTD(1),
    )

    assert _action_requires_event(action) is True


def test_special_pay_events_are_written_by_typed_payroll_persistence():
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, statement, values):
            self.calls.append((statement, values))

    cursor = Cursor()
    command = SimpleNamespace(
        special_pay_events=(
            PayrollSpecialPayEventCandidate(
                "case-1:g2:a1",
                1,
                (date(2026, 8, 8),),
            ),
        ),
        assignment_resolution=SimpleNamespace(
            assignment_id_by_candidate_key={"case-1:g2:a1": 41},
        ),
        idempotency_key=IdempotencyKey("leave-batch-1"),
        actor=ActorContext("scheduler"),
        reason="approved leave substitution",
    )

    _insert_special_pay_events(cursor, command)

    assert cursor.calls == [
        (
            "INSERT INTO payroll_special_pay_events "
            "(assignment_id,service_date,event_type,source_event_identity,"
            "actor,reason,idempotency_key) "
            "VALUES (%s,%s,'double_pay',%s,%s,%s,%s)",
            (
                41,
                date(2026, 8, 8),
                "leave-special-pay:"
                "ddd00c567122551ba50a92566772ef7d5fcb61a960ccc5652040a1dba138ee59",
                "scheduler",
                "approved leave substitution",
                "child:733de23f3d7d1d3d65e666fb7552b0231d3d3834b73dd3656a2a8dc488ed46ca",
            ),
        )
    ]


def test_special_pay_dates_participate_in_payroll_candidate_fingerprint():
    def facts(service_date):
        return SimpleNamespace(
            case_no="CASE-1",
            payroll_version=3,
            scheduling=SimpleNamespace(
                assignments=(
                    SimpleNamespace(
                        candidate_key="case-1:g2:a1",
                        sequence=1,
                        double_pay_dates=(service_date,),
                    ),
                )
            ),
        )

    payroll = SimpleNamespace(fingerprint=SimpleNamespace(value="payroll-facts"))

    first = _candidate(facts(date(2026, 8, 8)), payroll, (), ())
    second = _candidate(facts(date(2026, 8, 9)), payroll, (), ())

    assert first.special_pay_events[0].service_dates == (date(2026, 8, 8),)
    assert first.fingerprint != second.fingerprint
