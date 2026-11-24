from datetime import date
from types import SimpleNamespace

import pytest
import infrastructure.mysql.payroll_rebuild_repository as mysql_rebuild

from domains.payroll.calculation import (
    OfficialAssignmentServiceFacts,
    PayrollTerms,
    PayrollPolicyKind,
    rate_snapshot,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.payroll.rebuild_workflow import (
    ExistingStaffObligation,
    PayrollRebuildError,
    PayrollRebuildFacts,
    PayrollRebuildRequest,
    PayrollRebuildWorkflow,
    StaffObligationActionKind,
    StoredPayrollReceipt,
)


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.persisted = []
        self.load_modes = []

    def load(self, case_no, *, for_update):
        assert case_no == self.facts.case_no
        self.load_modes.append(for_update)
        return self.facts

    def find_receipt(self, key):
        return self.receipt

    def persist_rebuild(self, persistence):
        self.persisted.append(persistence)


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def commit(self):
        self.committed = True


def _facts(existing=(), version=4, due_date=date(2026, 9, 15)):
    identity = "assignment:8"
    return PayrollRebuildFacts(
        "CASE-1",
        version,
        (OfficialAssignmentServiceFacts(identity, 17, (date(2026, 8, 1),)),),
        (rate_snapshot(identity, "policy-1", PayrollPolicyKind.CITIZEN),),
        PayrollTerms(1, 8, MoneyNTD(1000)),
        (),
        existing,
        due_date,
    )


def _request(preview, *, version=4, key="payroll-rebuild-1"):
    return PayrollRebuildRequest(
        "CASE-1",
        ExpectedVersion(version),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("admin"),
        "Rebuild root-fact payroll obligations.",
        CorrelationId("payroll-rebuild-test"),
    )


def test_zero_service_termination_blocks_rebuild_and_automatic_sync_preserves_obligations():
    from dataclasses import replace
    from domains.orders.lifecycle import OrderLifecycleStatus
    from shared_kernel.fingerprints import PreviewFingerprint

    existing = ExistingStaffObligation("assignment:8", "original", MoneyNTD(0), True,
                                      date(2026, 9, 15))
    facts = replace(_facts((existing,)), order_status=OrderLifecycleStatus.ESTABLISHED_UNSERVED)
    repository, uow = _Repository(facts), _UnitOfWork()
    workflow = PayrollRebuildWorkflow(repository, lambda: uow)
    with pytest.raises(PayrollRebuildError) as preview_error:
        workflow.preview("CASE-1")
    assert preview_error.value.error.code == "payroll_zero_service_terminated"
    assert preview_error.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    request = _request(SimpleNamespace(fingerprint=PreviewFingerprint("a" * 64)))
    with pytest.raises(PayrollRebuildError) as apply_error:
        workflow.apply(request)
    assert apply_error.value.error.code == "payroll_zero_service_terminated"
    assert workflow.synchronize_in_unit_of_work(
        "CASE-1", actor=request.actor, key=request.idempotency_key, correlation_id=request.correlation_id,
    ) == facts.staff_payment_due_date
    assert repository.persisted == []
    assert repository.facts.existing_obligations == (existing,)
    assert not uow.committed


def test_mysql_service_facts_crossing_decimal_id_boundary_can_be_calculated():
    from domains.payroll.calculation import build_case_payroll_candidate
    facts = mysql_rebuild._service_facts(
        ({"id": 9, "staff_id": 17}, {"id": 10, "staff_id": 18}),
        {9: ({"work_date": date(2026, 10, 1)},), 10: ({"work_date": date(2026, 10, 2)},)},
    )
    result = build_case_payroll_candidate(facts,
        tuple(rate_snapshot(item.assignment_identity, "policy-1", PayrollPolicyKind.CITIZEN) for item in facts),
        PayrollTerms(2, 8, MoneyNTD(0)), ())
    assert {item.staff_id: item.total_payable.amount for item in result.assignments} == {17: 2400, 18: 2400}


@pytest.fixture
def payroll_schedule_sql():
    import sqlite3

    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    raw.create_function("CONCAT", 2, lambda left, right: str(left) + str(right))
    raw.executescript("""
        CREATE TABLE staff_schedule(assignment_id INTEGER,generation_id INTEGER,work_date TEXT,
            is_work_day INTEGER,effective_marker INTEGER,service_hours_override INTEGER);
        CREATE TABLE case_staff_assignments(id INTEGER PRIMARY KEY,generation_id INTEGER,
            case_no TEXT,staff_id INTEGER);
        CREATE TABLE scheduling_rebuild_lineage(rebuild_event_id INTEGER,new_assignment_id INTEGER,
            old_assignment_identity TEXT,lineage_ordinal INTEGER);
        CREATE TABLE scheduling_command_receipts(rebuild_event_id INTEGER,command_family TEXT);
    """)

    class Cursor:
        def execute(self, statement, parameters):
            assert statement.startswith("SELECT ")
            self.result = raw.execute(statement.replace("%s", "?").replace(" FOR UPDATE", ""), parameters)

        def fetchall(self):
            return tuple({key: date.fromisoformat(row[key]) if key == "work_date" else row[key]
                          for key in row.keys()} for row in self.result.fetchall())

    try:
        yield raw, Cursor()
    finally:
        raw.close()


def _schedule_payroll(cursor, generation, assignments, *, days=2, hours=4, tiered=False):
    from decimal import Decimal
    from domains.payroll.calculation import AssignmentRateSnapshot, build_case_payroll_candidate
    from domains.payroll.tiered_rates import TieredPayrollRate

    schedules = mysql_rebuild._load_schedules(
        cursor, {"effective_generation_id": generation, "service_days": days}, assignments, True,
    )
    facts = mysql_rebuild._service_facts(assignments, mysql_rebuild._schedule_index(assignments, schedules))
    rates = tuple(AssignmentRateSnapshot(
        item.assignment_identity, "frozen-policy", PayrollPolicyKind.CITIZEN, MoneyNTD(300),
        TieredPayrollRate(300, 500, Decimal(4), False) if tiered else None,
    ) for item in facts)
    result = build_case_payroll_candidate(facts, rates, PayrollTerms(days, hours, MoneyNTD(1001)), ())
    return facts, result


@pytest.mark.parametrize(("operation", "days", "hours"), [
    ("normal", 2, 4), ("merge", 2, 4), ("split", 1, 8), ("restore", 2, 4),
])
@pytest.mark.parametrize("tiered", [False, True])
def test_date_only_adjustments_preserve_original_payroll_hours_floor_fee_and_tiers(
    payroll_schedule_sql, operation, days, hours, tiered,
):
    raw, cursor = payroll_schedule_sql
    assignments = ({"id": 9, "staff_id": 17},)
    raw.execute("INSERT INTO case_staff_assignments VALUES (9,1,'CASE-1',17)")
    raw.executemany("INSERT INTO staff_schedule VALUES (9,1,?,1,1,NULL)",
                    [(f"2026-10-0{ordinal}",) for ordinal in range(1, days + 1)])
    baseline = _schedule_payroll(cursor, 1, assignments, days=days, hours=hours, tiered=tiered)
    if operation != "normal":
        raw.execute("UPDATE staff_schedule SET effective_marker=NULL")
        actual = [("2026-10-03", 4), ("2026-10-04", 4)] if operation == "split" else [("2026-10-03", 8)]
        raw.executemany("INSERT INTO staff_schedule VALUES (9,1,?,1,1,?)", actual)
        if operation == "restore":
            raw.execute("UPDATE staff_schedule SET effective_marker=CASE WHEN service_hours_override IS NULL THEN 1 END")
    changes = raw.total_changes
    assert _schedule_payroll(cursor, 1, assignments, days=days, hours=hours, tiered=tiered) == baseline
    assert baseline[1].assignments[0].actual_hours == 8
    assert baseline[1].earned_floor_fee == MoneyNTD(1001)
    assert baseline[1].total_payable == MoneyNTD(4201 if tiered else 3401)
    assert raw.total_changes == changes


def test_cross_caregiver_merge_keeps_both_original_payees_and_floor_allocations(payroll_schedule_sql):
    raw, cursor = payroll_schedule_sql
    assignments = ({"id": 9, "staff_id": 17}, {"id": 10, "staff_id": 18})
    raw.executemany("INSERT INTO case_staff_assignments VALUES (?,1,'CASE-1',?)", [(9, 17), (10, 18)])
    raw.executemany("INSERT INTO staff_schedule VALUES (?,1,?,1,1,NULL)", [(9, "2026-10-01"), (10, "2026-10-02")])
    baseline = _schedule_payroll(cursor, 1, assignments)
    raw.execute("UPDATE staff_schedule SET effective_marker=NULL")
    raw.execute("INSERT INTO staff_schedule VALUES (9,1,'2026-10-03',1,1,8)")
    assert _schedule_payroll(cursor, 1, assignments) == baseline
    assert {item.staff_id: item.total_payable.amount for item in baseline[1].assignments} == {17: 1700, 18: 1701}
    raw.execute("UPDATE staff_schedule SET effective_marker=CASE WHEN service_hours_override IS NULL THEN 1 END")
    assert _schedule_payroll(cursor, 1, assignments) == baseline


@pytest.mark.parametrize("neutral_hops", [1, 2])
def test_neutral_actual_start_lineage_preserves_payee_with_zero_actual_dates(payroll_schedule_sql, neutral_hops):
    raw, cursor = payroll_schedule_sql
    raw.executemany("INSERT INTO case_staff_assignments VALUES (?,1,'CASE-1',?)", [(9, 17), (10, 18)])
    raw.executemany("INSERT INTO staff_schedule VALUES (?,1,?,1,NULL,NULL)", [(9, "2026-10-01"), (10, "2026-10-02")])
    baseline = _schedule_payroll(cursor, 1, ({"id": 9, "staff_id": 17}, {"id": 10, "staff_id": 18}))
    for generation in range(2, neutral_hops + 2):
        owner, other = generation * 10 - 1, generation * 10
        raw.executemany("INSERT INTO case_staff_assignments VALUES (?,?,'CASE-1',?)",
                        [(owner, generation, 17), (other, generation, 18)])
        raw.execute("INSERT INTO staff_schedule VALUES (?,?,'2026-10-05',1,1,8)", (owner, generation))
        raw.execute("INSERT INTO scheduling_command_receipts VALUES (?,'orders_actual_start_rebuild')", (generation,))
        raw.executemany("INSERT INTO scheduling_rebuild_lineage VALUES (?,?,?,?)", [
            (generation, owner, f"assignment:{owner - 10}", 1),
            (generation, other, f"assignment:{other - 10}", 2),
        ])
    facts, result = _schedule_payroll(cursor, generation, ({"id": owner, "staff_id": 17}, {"id": other, "staff_id": 18}))
    assert {item.staff_id: item.service_dates for item in facts} == {
        item.staff_id: item.service_dates for item in baseline[0]}
    assert {item.staff_id: (item.actual_hours, item.service_salary, item.floor_fee_allocated)
            for item in result.assignments} == {
        item.staff_id: (item.actual_hours, item.service_salary, item.floor_fee_allocated)
        for item in baseline[1].assignments}
    assert {item.assignment_identity for item in facts} == {f"assignment:{owner}", f"assignment:{other}"}


@pytest.mark.parametrize(("family", "override"), [("orders_terms_rebuild", 4), ("orders_actual_start_rebuild", None)])
def test_financial_rebuild_and_complete_current_basis_do_not_inherit_older_dates(payroll_schedule_sql, family, override):
    raw, cursor = payroll_schedule_sql
    raw.executemany("INSERT INTO case_staff_assignments VALUES (?,?,'CASE-1',17)", [(9, 1), (19, 2)])
    raw.executemany("INSERT INTO staff_schedule VALUES (9,1,?,1,NULL,NULL)", [("2026-10-01",), ("2026-10-02",)])
    raw.executemany("INSERT INTO staff_schedule VALUES (19,2,?,1,1,?)", [("2026-10-03", override), ("2026-10-04", override)])
    raw.execute("INSERT INTO scheduling_command_receipts VALUES (2,?)", (family,))
    raw.execute("INSERT INTO scheduling_rebuild_lineage VALUES (2,19,'assignment:9',1)")
    facts, result = _schedule_payroll(cursor, 2, ({"id": 19, "staff_id": 17},))
    assert facts[0].service_dates == (date(2026, 10, 3), date(2026, 10, 4))
    assert result.total_payable == MoneyNTD(3401)


@pytest.mark.parametrize("financial_identity", [None, "assignment:source"])
def test_floor_fee_allocation_preserves_prefix_order_and_conserves_shared_basis(financial_identity):
    from domains.payroll.calculation import build_case_payroll_candidate

    facts = tuple(OfficialAssignmentServiceFacts(
        identity, staff_id, (date(2026, 10, staff_id - 16),),
        financial_assignment_identity=financial_identity,
    ) for identity, staff_id in (("assignment:1", 17), ("assignment:10", 18)))
    rates = tuple(rate_snapshot(item.assignment_identity, "policy-1", PayrollPolicyKind.CITIZEN)
                  for item in facts)

    result = build_case_payroll_candidate(facts, rates, PayrollTerms(2, 4, MoneyNTD(1001)), ())

    assert {item.assignment_identity: item.floor_fee_allocated for item in result.assignments} == {
        "assignment:1": MoneyNTD(501), "assignment:10": MoneyNTD(500),
    }
    assert sum(item.floor_fee_allocated.amount for item in result.assignments) == 1001


@pytest.mark.parametrize("effective_amount,allowed", [(3400, True), (3500, False)])
def test_automatic_completion_accepts_only_unchanged_handover_entitlement(effective_amount, allowed):
    existing = ExistingStaffObligation("assignment:8", "original", MoneyNTD(effective_amount), True,
        date(2026, 9, 15), handover_corrections_exist=True)
    repository = _Repository(_facts((existing,)))
    repository.resolve_handover_obligations = lambda facts: facts
    workflow = PayrollRebuildWorkflow(repository, None)
    arguments = {"actor": ActorContext("admin"), "key": IdempotencyKey("completion"), "correlation_id": CorrelationId("test")}
    if allowed:
        assert workflow.synchronize_in_unit_of_work("CASE-1", **arguments) == date(2026, 9, 15)
    else:
        with pytest.raises(ValueError, match="payroll_handover_settlement_required"):
            workflow.synchronize_in_unit_of_work("CASE-1", **arguments)
    assert repository.persisted == []
    assert repository.load_modes == [True]


def test_generic_rebuild_blocks_handover_roots_instead_of_recreating_their_full_paid_amount():
    from shared_kernel.fingerprints import PreviewFingerprint

    existing = ExistingStaffObligation("assignment:8", "original", MoneyNTD(3400), True,
                                       date(2026, 9, 15), handover_corrections_exist=True)
    repository, uow = _Repository(_facts((existing,))), _UnitOfWork()
    workflow = PayrollRebuildWorkflow(repository, lambda: uow)
    with pytest.raises(ValueError, match="payroll_handover_settlement_required"):
        workflow.preview("CASE-1")
    request = _request(SimpleNamespace(fingerprint=PreviewFingerprint("a" * 64)))
    with pytest.raises(PayrollRebuildError) as caught:
        workflow.apply(request)
    assert caught.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert repository.persisted == []
    assert uow.committed is False


def test_preview_classifies_create_replace_frozen_and_removed_actions():
    create = PayrollRebuildWorkflow(_Repository(_facts()), _UnitOfWork).preview("CASE-1")
    total = create.payroll.total_payable
    replace = ExistingStaffObligation("assignment:8", "old-8", MoneyNTD(1), False, date(2026, 9, 15))
    frozen = ExistingStaffObligation("assignment:8", "old-8", MoneyNTD(1), True, date(2026, 9, 15))
    removed = ExistingStaffObligation("assignment:9", "old-9", MoneyNTD(20), False, date(2026, 9, 15))

    replace_preview = PayrollRebuildWorkflow(_Repository(_facts((replace,))), _UnitOfWork).preview("CASE-1")
    frozen_preview = PayrollRebuildWorkflow(_Repository(_facts((frozen,))), _UnitOfWork).preview("CASE-1")
    removed_preview = PayrollRebuildWorkflow(_Repository(_facts((removed,))), _UnitOfWork).preview("CASE-1")

    assert create.actions[0].action is StaffObligationActionKind.CREATE
    assert create.actions[0].after_amount == total
    assert replace_preview.actions[0].action is StaffObligationActionKind.REPLACE_UNPAID
    assert frozen_preview.actions[0].action is StaffObligationActionKind.APPEND_FROZEN_DELTA
    assert removed_preview.actions[0].action is StaffObligationActionKind.CREATE
    assert removed_preview.actions[1].action is StaffObligationActionKind.REPLACE_UNPAID
    assert removed_preview.actions[1].after_amount == MoneyNTD(0)


def test_preview_rebuilds_unpaid_obligation_when_orders_first_forms_due_date():
    existing = ExistingStaffObligation(
        "assignment:8",
        "old-8",
        MoneyNTD(3400),
        False,
        None,
    )

    preview = PayrollRebuildWorkflow(
        _Repository(_facts((existing,))),
        _UnitOfWork,
    ).preview("CASE-1")

    assert preview.actions[0].action is StaffObligationActionKind.REPLACE_UNPAID
    assert preview.actions[0].before_amount == preview.actions[0].after_amount
    assert preview.actions[0].due_date == date(2026, 9, 15)


def test_preview_does_not_rewrite_existing_non_null_due_date():
    existing = ExistingStaffObligation(
        "assignment:8",
        "old-8",
        MoneyNTD(3400),
        False,
        date(2026, 9, 15),
    )

    preview = PayrollRebuildWorkflow(
        _Repository(_facts((existing,), due_date=date(2026, 10, 15))),
        _UnitOfWork,
    ).preview("CASE-1")

    assert preview.actions[0].action is StaffObligationActionKind.UNCHANGED
    assert preview.actions[0].due_date == date(2026, 9, 15)


def test_apply_persists_one_fresh_preview_and_replays_matching_idempotency_key():
    repository = _Repository(_facts())
    unit_of_work = _UnitOfWork()
    workflow = PayrollRebuildWorkflow(repository, lambda: unit_of_work)
    preview = workflow.preview("CASE-1")
    request = _request(preview)

    receipt = workflow.apply(request)
    repository.receipt = StoredPayrollReceipt(repository.persisted[0].command_fingerprint, receipt)
    replay = workflow.apply(request)

    assert repository.load_modes == [False, True]
    assert len(repository.persisted) == 1
    assert receipt.payroll_version == 5
    assert receipt.action_count == 1
    assert replay == receipt
    assert unit_of_work.committed is True


def test_apply_rejects_stale_preview_version_with_typed_conflict():
    repository = _Repository(_facts(version=5))
    workflow = PayrollRebuildWorkflow(repository, _UnitOfWork)
    preview = PayrollRebuildWorkflow(_Repository(_facts()), _UnitOfWork).preview("CASE-1")

    with pytest.raises(PayrollRebuildError) as raised:
        workflow.apply(_request(preview, version=4))

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "payroll_candidate_stale"


@pytest.mark.parametrize('identity,amount,hours,expected', [
    ('補助市民',24000,8,date(2026,11,15)),
    ('社福',24000,8,date(2026,11,15)),
    ('社福',0,8,date(2026,12,15)),
])
def test_official_schedule_can_form_missing_payment_date_without_waiting_for_completion(identity,amount,hours,expected):
    root={'staff_payment_due_date':None,'order_status':'訂單完成','actual_end_date':date(2026,10,12),'client_payable_ntd':amount,'identity_status':identity,'service_days':10,'service_hours_per_day':hours,'floor_fee':0}
    assert mysql_rebuild._payment_due_date(root)==expected
    root['staff_payment_due_date']=date(2026,9,15)
    assert mysql_rebuild._payment_due_date(root)==date(2026,9,15)
    root.update(staff_payment_due_date=None,order_status='服務中')
    assert mysql_rebuild._payment_due_date(root)==expected
    root['actual_end_date']=None
    assert mysql_rebuild._payment_due_date(root) is None


@pytest.mark.parametrize("completed_on", [None, date(2026, 10, 31)])
def test_bound_pricing_rebuild_preserves_the_original_payment_date(completed_on):
    assert mysql_rebuild._payment_due_date({
        "staff_payment_due_date": date(2026, 12, 15),
        "pricing_policy_id": 1,
        "actual_end_date": completed_on,
    }) == date(2026, 12, 15)


def test_created_obligation_persists_preview_payment_date_instead_of_null_compatibility_field(monkeypatch):
    owner={'due_date':None}
    monkeypatch.setattr(mysql_rebuild,'_assignment_owner',lambda *_:owner)
    monkeypatch.setattr(mysql_rebuild,'_insert_event',lambda *_,**__:1)
    saved=[]
    monkeypatch.setattr(mysql_rebuild,'_insert_projection',lambda _cursor,_persistence,snapshot,*_:saved.append(dict(snapshot)))
    action=SimpleNamespace(assignment_identity='assignment:6',obligation_identity='obligation:6',after_amount=MoneyNTD(24000),due_date=date(2026,11,15))
    mysql_rebuild._create_service_obligation(None,None,action,1)
    assert saved[0]['due_date']==date(2026,11,15)


@pytest.mark.parametrize('stored_due_date', [None, date(2026, 11, 15)])
def test_missing_due_date_successor_uses_fresh_preview_before_orders_save(monkeypatch, stored_due_date):
    class Cursor:
        rowcount = 1

        def execute(self, statement, parameters):
            self.statement = statement
            self.parameters = parameters

    monkeypatch.setattr(mysql_rebuild, '_obligation_owner', lambda *_: {'due_date': None})
    monkeypatch.setattr(mysql_rebuild, '_assignment_owner', lambda *_: {'due_date': stored_due_date})
    monkeypatch.setattr(mysql_rebuild, '_insert_event', lambda *_, **__: 1)
    monkeypatch.setattr(mysql_rebuild, '_due_date_successor_identity', lambda *_: 'dated-successor')
    saved = []
    monkeypatch.setattr(mysql_rebuild, '_insert_projection',
                        lambda _cursor, _persistence, owner, *_: saved.append(dict(owner)))
    persistence = SimpleNamespace(request=SimpleNamespace(case_no='CASE-1'),
                                  receipt=SimpleNamespace(payroll_version=5))
    action = SimpleNamespace(
        assignment_identity='assignment:6', obligation_identity='original',
        before_amount=MoneyNTD(5800), after_amount=MoneyNTD(5800), due_date=date(2026, 11, 15),
    )
    mysql_rebuild._replace_missing_due_date(Cursor(), persistence, action, 1)
    assert saved == [{'due_date': date(2026, 11, 15)}]


def test_missing_due_date_successor_rejects_different_existing_orders_date(monkeypatch):
    class Cursor:
        rowcount = 1

        def execute(self, *_):
            pass

    monkeypatch.setattr(mysql_rebuild, '_obligation_owner', lambda *_: {'due_date': None})
    monkeypatch.setattr(mysql_rebuild, '_assignment_owner', lambda *_: {'due_date': date(2026, 12, 15)})
    monkeypatch.setattr(mysql_rebuild, '_insert_event', lambda *_, **__: 1)
    monkeypatch.setattr(mysql_rebuild, '_due_date_successor_identity', lambda *_: 'dated-successor')
    monkeypatch.setattr(mysql_rebuild, '_insert_projection',
                        lambda *_: pytest.fail('conflicting date must not establish a successor'))
    persistence = SimpleNamespace(request=SimpleNamespace(case_no='CASE-1'),
                                  receipt=SimpleNamespace(payroll_version=5))
    action = SimpleNamespace(
        assignment_identity='assignment:6', obligation_identity='original',
        before_amount=MoneyNTD(5800), after_amount=MoneyNTD(5800), due_date=date(2026, 11, 15),
    )
    with pytest.raises(ValueError, match='staff_obligation_due_date_stale'):
        mysql_rebuild._replace_missing_due_date(Cursor(), persistence, action, 1)


@pytest.fixture
def monthly_sql_connection():
    import sqlite3

    raw = sqlite3.connect(':memory:')
    raw.row_factory = sqlite3.Row
    raw.executescript('''
        CREATE TABLE orders(case_no TEXT PRIMARY KEY, staff_payment_due_date DATE);
        CREATE TABLE staff_obligations(
            obligation_identity TEXT PRIMARY KEY, assignment_id INTEGER, case_no TEXT,
            staff_id INTEGER, direction TEXT, amount_due_ntd INTEGER, due_date DATE,
            status TEXT, source_obligation_identity TEXT
        );
        CREATE TABLE staff_obligation_installments(
            obligation_identity TEXT, amount_ntd INTEGER, due_date DATE
        );
        CREATE TABLE payroll_amount_controls(
            obligation_identity TEXT, settlement_base_ntd INTEGER, effective_ntd INTEGER
        );
    ''')

    class Cursor:
        def __enter__(self):
            self.cursor = raw.cursor()
            return self

        def __exit__(self, *_):
            self.cursor.close()

        def execute(self, statement, parameters):
            assert statement.startswith('SELECT ')
            self.cursor.execute(
                statement.replace('%s', '?').replace('%%', '%'),
                tuple(value.isoformat() if isinstance(value, date) else value for value in parameters),
            )

        def fetchall(self):
            return [dict(row, due_date=date.fromisoformat(row['due_date'])) for row in self.cursor.fetchall()]

    class Connection:
        def cursor(self):
            return Cursor()

    try:
        yield raw, mysql_rebuild.MySqlPayrollRebuildRepository(Connection())
    finally:
        raw.close()


def _seed_monthly_paid_root(raw, root_due=None, order_due='2026-11-15'):
    raw.execute('INSERT INTO orders VALUES (?,?)', ('CASE-1', order_due))
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('original-paid', 1, 'CASE-1', 7, 'payable_to_staff', 13000, root_due, 'open', None))
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('staff-handover:correction', 1, 'CASE-1', 7, 'receivable_from_staff', 7200,
                 root_due, 'open', 'original-paid'))


@pytest.mark.parametrize(('root_due', 'order_due', 'month', 'expected'), [
    (None, '2026-11-15', 11, 5800),
    ('2026-12-15', '2026-11-15', 11, 0),
    ('2026-12-15', '2026-11-15', 12, 5800),
    (None, None, 11, 0),
    (None, '2026-11-15', 12, 0),
])
def test_monthly_query_uses_effective_paid_entitlement_and_existing_dates(
    monthly_sql_connection, root_due, order_due, month, expected,
):
    raw, repository = monthly_sql_connection
    _seed_monthly_paid_root(raw, root_due, order_due)
    before = [tuple(row) for row in raw.execute('SELECT * FROM staff_obligations ORDER BY obligation_identity')]
    changes = raw.total_changes
    summary = repository.query_staff_month(7, 2026, month)
    assert summary.payable_total == summary.net_payable == MoneyNTD(expected)
    assert summary.receivable_total == MoneyNTD(0)
    assert tuple(item.obligation_identity for item in summary.obligations) == (('original-paid',) if expected else ())
    assert raw.total_changes == changes
    assert [tuple(row) for row in raw.execute('SELECT * FROM staff_obligations ORDER BY obligation_identity')] == before


@pytest.mark.parametrize(('settlement_base', 'effective', 'expected'), [
    (5200, 4800, 5200), (None, 4800, 4800), (0, 4800, 0),
])
def test_monthly_query_shares_existing_amount_control_precedence(
    monthly_sql_connection, settlement_base, effective, expected,
):
    raw, repository = monthly_sql_connection
    _seed_monthly_paid_root(raw)
    raw.execute('INSERT INTO payroll_amount_controls VALUES (?,?,?)',
                ('original-paid', settlement_base, effective))
    changes = raw.total_changes
    summary = repository.query_staff_month(7, 2026, 11)
    assert summary.payable_total == summary.net_payable == MoneyNTD(expected)
    assert summary.receivable_total == MoneyNTD(0)
    assert raw.total_changes == changes


def test_monthly_query_preserves_formal_installment_amounts_and_dates(monthly_sql_connection):
    raw, repository = monthly_sql_connection
    _seed_monthly_paid_root(raw, order_due='2027-01-15')
    raw.executemany('INSERT INTO staff_obligation_installments VALUES (?,?,?)', [
        ('original-paid', 3300, '2026-11-15'), ('original-paid', 2500, '2026-12-15'),
    ])
    changes = raw.total_changes
    assert repository.query_staff_month(7, 2026, 11).net_payable == MoneyNTD(3300)
    assert repository.query_staff_month(7, 2026, 12).net_payable == MoneyNTD(2500)
    assert repository.query_staff_month(7, 2027, 1).net_payable == MoneyNTD(0)
    assert raw.total_changes == changes


@pytest.mark.parametrize(('settlement_base', 'effective'), [
    (None, None), (None, 0), (0, 4800),
])
def test_monthly_query_excludes_preserved_installments_that_do_not_conserve_entitlement(
    monthly_sql_connection, settlement_base, effective,
):
    raw, repository = monthly_sql_connection
    _seed_monthly_paid_root(raw, root_due='2027-01-15', order_due='2027-01-15')
    raw.executemany('INSERT INTO staff_obligation_installments VALUES (?,?,?)', [
        ('original-paid', 1000, '2026-11-15'), ('original-paid', 12000, '2026-12-15'),
    ])
    if settlement_base is not None or effective is not None:
        raw.execute('INSERT INTO payroll_amount_controls VALUES (?,?,?)',
                    ('original-paid', settlement_base, effective))
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('actual-receivable', 1, 'CASE-1', 7, 'receivable_from_staff', 1500,
                 '2026-11-15', 'open', None))
    original_installments = [tuple(row) for row in raw.execute(
        'SELECT * FROM staff_obligation_installments ORDER BY due_date',
    )]
    changes = raw.total_changes

    for year, month in [(2026, 11), (2026, 12), (2027, 1)]:
        summary = repository.query_staff_month(7, year, month)
        expected_receivable = 1500 if month == 11 else 0
        assert summary.payable_total == MoneyNTD(0)
        assert summary.receivable_total == MoneyNTD(expected_receivable)
        assert summary.net_payable == MoneyNTD(-expected_receivable)
        assert tuple(item.obligation_identity for item in summary.obligations) == (
            ('actual-receivable',) if expected_receivable else ()
        )

    assert raw.total_changes == changes
    assert [tuple(row) for row in raw.execute(
        'SELECT * FROM staff_obligation_installments ORDER BY due_date',
    )] == original_installments


@pytest.mark.parametrize('preserve_installments', [False, True], ids=['no-plan', 'preserved-plan'])
def test_monthly_query_excludes_handover_zero_without_amount_control(
    monthly_sql_connection, preserve_installments,
):
    raw, repository = monthly_sql_connection
    _seed_monthly_paid_root(raw, root_due='2026-11-15', order_due='2027-01-15')
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('staff-handover:final-zero', 1, 'CASE-1', 7, 'receivable_from_staff', 5800,
                 '2026-11-15', 'open', 'original-paid'))
    if preserve_installments:
        raw.executemany('INSERT INTO staff_obligation_installments VALUES (?,?,?)', [
            ('original-paid', 1000, '2026-11-15'), ('original-paid', 12000, '2026-12-15'),
        ])
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('actual-receivable', 1, 'CASE-1', 7, 'receivable_from_staff', 1500,
                 '2026-11-15', 'open', None))
    assert raw.execute('SELECT COUNT(*) FROM payroll_amount_controls').fetchone()[0] == 0
    tables = ('orders', 'staff_obligations', 'staff_obligation_installments', 'payroll_amount_controls')
    before = {table: [tuple(row) for row in raw.execute(f'SELECT * FROM {table}')]
              for table in tables}
    changes = raw.total_changes

    for year, month in [(2026, 11), (2026, 12), (2027, 1)]:
        summary = repository.query_staff_month(7, year, month)
        expected_receivable = 1500 if month == 11 else 0
        assert summary.payable_total == MoneyNTD(0)
        assert summary.receivable_total == MoneyNTD(expected_receivable)
        assert summary.net_payable == MoneyNTD(-expected_receivable)
        assert tuple(item.obligation_identity for item in summary.obligations) == (
            ('actual-receivable',) if expected_receivable else ()
        )

    assert raw.total_changes == changes
    assert {table: [tuple(row) for row in raw.execute(f'SELECT * FROM {table}')]
            for table in tables} == before


def test_monthly_query_retains_genuine_receivables_and_staff_scope(monthly_sql_connection):
    raw, repository = monthly_sql_connection
    _seed_monthly_paid_root(raw)
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('actual-receivable', 1, 'CASE-1', 7, 'receivable_from_staff', 1500,
                 '2026-11-15', 'open', None))
    raw.execute('INSERT INTO staff_obligations VALUES (?,?,?,?,?,?,?,?,?)',
                ('other-staff', 2, 'CASE-1', 8, 'payable_to_staff', 9000,
                 '2026-11-15', 'open', None))
    summary = repository.query_staff_month(7, 2026, 11)
    assert summary.payable_total == MoneyNTD(5800)
    assert summary.receivable_total == MoneyNTD(1500)
    assert summary.net_payable == MoneyNTD(4300)
    assert summary.obligation_count == 2
