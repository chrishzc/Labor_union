"""Pure business oracles for month/quarter/year membership and whole-period guards."""
from datetime import date
import pytest
from domains.government_subsidy.period_reconciliation import (
    PeriodReconciliationConflict,SubsidyPeriod,SubsidyPeriodLine,require_exact_period_receipt,
)


def test_months_quarters_and_year_share_identical_membership_and_totals():
    lines=tuple(SubsidyPeriodLine(f'CASE-{month}',date(2026,month,28),month*1000,None) for month in range(1,13))
    amount=lambda period:sum(line.amount_ntd for line in lines if period.contains(line.service_end_date))
    assert sum(amount(SubsidyPeriod('month',2026,m)) for m in range(1,13))==78000
    assert sum(amount(SubsidyPeriod('quarter',2026,q)) for q in range(1,5))==amount(SubsidyPeriod('year',2026,1))==78000
    for q in range(1,5):
        assert sum(amount(SubsidyPeriod('month',2026,m)) for m in range((q-1)*3+1,q*3+1))==amount(SubsidyPeriod('quarter',2026,q))


def test_coverage_is_symmetric_across_units_and_respects_boundaries():
    quarter=SubsidyPeriod('quarter',2026,1)
    assert quarter.overlaps(SubsidyPeriod('month',2026,3))
    assert SubsidyPeriod('month',2026,3).overlaps(quarter)
    assert quarter.overlaps(SubsidyPeriod('year',2026,1))
    assert not quarter.overlaps(SubsidyPeriod('month',2026,4))
    assert not quarter.contains(date(2026,4,1))
    assert SubsidyPeriod('year',2026,1).end==date(2027,1,1)


@pytest.mark.parametrize('lines,amount,code',[
    ((),100,'incomplete'),
    ((SubsidyPeriodLine('A',date(2026,1,1),None,'missing'),),100,'incomplete'),
    ((SubsidyPeriodLine('A',date(2026,1,1),12000,None),),11999,'amount_mismatch'),
    ((SubsidyPeriodLine('A',date(2026,1,1),0,None),),0,'amount_mismatch'),
])
def test_no_partial_case_allocation_can_hide_a_period_mismatch(lines,amount,code):
    with pytest.raises(PeriodReconciliationConflict,match=code):require_exact_period_receipt(lines,amount)


@pytest.mark.parametrize('unit,index',[('month',13),('quarter',5),('year',2),('invalid',1)])
def test_invalid_period(unit,index):
    with pytest.raises(ValueError,match='period_invalid'):SubsidyPeriod(unit,2026,index)


class _ZeroServiceAmountCursor:
    def __init__(self, *, control=None, frozen=(), status='成立後未服務', end_date=None):
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.connection = SimpleNamespace(commit=Mock(side_effect=AssertionError('outer UoW owns commit')))
        self.control = control
        self.frozen = tuple(dict(row) for row in frozen)
        self.order = {'status':status, 'end_date':end_date}
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if sql.startswith('INSERT INTO government_subsidy_amount_controls'):
            case_no, year, mode, computed, effective = params
            self.control = {'case_no':case_no, 'period_year':year, 'amount_mode':mode,
                            'computed_ntd':computed, 'effective_ntd':effective}

    def fetchone(self):
        sql = self.calls[-1][0]
        if sql.startswith('SELECT * FROM government_subsidy_amount_controls'):
            return self.control
        if sql.startswith('SELECT amount_mode,effective_ntd FROM government_subsidy_amount_controls'):
            return self.control
        if sql.startswith('SELECT effective_ntd FROM government_subsidy_amount_controls'):
            return self.control
        if sql.startswith('SELECT status,COALESCE'):
            return self.order
        if sql.startswith('SELECT aggregate_version'):
            return {'aggregate_version':1}
        raise AssertionError(sql)

    def fetchall(self):
        assert self.calls[-1][0].startswith('SELECT member.amount_ntd')
        return self.frozen


def test_zero_service_corrects_frozen_amount_without_end_date_and_keeps_original_bank_snapshot(monkeypatch):
    from unittest.mock import Mock
    from infrastructure.mysql import government_period_difference_repository as writer
    from subsystems.government_subsidy import reconciliation_register_query as register

    original = ({'amount_ntd':12000, 'period_year':2025},)
    cursor = _ZeroServiceAmountCursor(frozen=original)
    claim_query = Mock(side_effect=AssertionError('zero service must not rejoin claim membership'))
    append = Mock()
    monkeypatch.setattr(register, '_select_established_cases', claim_query)
    monkeypatch.setattr(writer, '_append_case_correction', append)
    writer.synchronize_government_case_amount(cursor, 'ZERO-1', 'zero-source', 'synthetic', 'Confirmed zero service')
    assert cursor.control == {'case_no':'ZERO-1', 'period_year':2025, 'amount_mode':'automatic',
                              'computed_ntd':0, 'effective_ntd':0}
    append.assert_called_once()
    assert append.call_args.args[:3] == (cursor, 'ZERO-1', -12000)
    assert cursor.frozen == original
    claim_query.assert_not_called()
    assert not any(sql.startswith(('UPDATE government_subsidy_period_members',
                                   'UPDATE government_subsidy_period_entries', 'DELETE')) for sql, _ in cursor.calls)
    writer.synchronize_government_case_amount(cursor, 'ZERO-1', 'zero-source', 'synthetic', 'Confirmed zero service')
    append.assert_called_once()
    assert sum(sql.startswith('INSERT INTO government_subsidy_amount_changes') for sql, _ in cursor.calls) == 1


def test_zero_service_recomputes_manual_control_without_replacing_approved_effective_amount(monkeypatch):
    from unittest.mock import Mock
    from infrastructure.mysql import government_period_difference_repository as writer
    control = {'case_no':'ZERO-2', 'period_year':2024, 'amount_mode':'manual',
               'computed_ntd':12000, 'effective_ntd':9000}
    cursor = _ZeroServiceAmountCursor(control=control)
    append = Mock()
    monkeypatch.setattr(writer, '_append_case_correction', append)
    writer.synchronize_government_case_amount(cursor, 'ZERO-2', 'zero-manual', 'synthetic', 'Confirmed zero service')
    assert cursor.control == {**control, 'computed_ntd':0}
    append.assert_not_called()


def test_nonterminal_missing_end_date_keeps_amount_unknown_without_writing_a_zero(monkeypatch):
    from unittest.mock import Mock
    from infrastructure.mysql import government_period_difference_repository as writer
    control = {'case_no':'ACTIVE-1', 'period_year':2024, 'amount_mode':'automatic',
               'computed_ntd':12000, 'effective_ntd':12000}
    cursor = _ZeroServiceAmountCursor(control=control, status='服務中')
    append = Mock()
    monkeypatch.setattr(writer, '_append_case_correction', append)
    writer.synchronize_government_case_amount(cursor, 'ACTIVE-1', 'incomplete-source', 'synthetic', 'Missing date')
    assert cursor.control == control
    append.assert_not_called()
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE')) for sql, _ in cursor.calls)


@pytest.mark.parametrize('end_date', [None, date(2026, 11, 20)])
@pytest.mark.parametrize('control', [
    None,
    {'case_no':'ZERO-READ', 'period_year':2025, 'amount_mode':'automatic',
     'computed_ntd':0, 'effective_ntd':0},
])
def test_zero_service_frozen_readback_uses_owner_zero_instead_of_original_amount(monkeypatch, end_date, control):
    from unittest.mock import Mock
    from infrastructure.mysql import government_period_difference_repository as owner
    from subsystems.government_subsidy import reconciliation_register_query as register

    original = ({'amount_ntd':12000, 'period_year':2025},)
    cursor = _ZeroServiceAmountCursor(control=control, frozen=original, end_date=end_date)
    line = SubsidyPeriodLine('ZERO-READ', date(2025, 5, 1), 12000, None)
    claim_query = Mock(side_effect=AssertionError('zero service must not rejoin claim membership'))
    monkeypatch.setattr(register, '_select_established_cases', claim_query)

    item = owner.recorded_case_amount_control(cursor.connection, cursor, line)

    assert (item.case_no, item.mode, item.computed_ntd, item.effective_ntd) == ('ZERO-READ', 'automatic', 0, 0)
    assert cursor.control == control
    assert cursor.frozen == original
    assert line.amount_ntd == 12000
    claim_query.assert_not_called()
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE')) for sql, _ in cursor.calls)


@pytest.mark.parametrize('end_date', [None, date(2026, 11, 20)])
def test_zero_service_manual_readback_keeps_approved_amount_and_current_zero(monkeypatch, end_date):
    from unittest.mock import Mock
    from infrastructure.mysql import government_period_difference_repository as owner
    from subsystems.government_subsidy import reconciliation_register_query as register

    control = {'case_no':'ZERO-MANUAL', 'period_year':2025, 'amount_mode':'manual',
               'computed_ntd':0, 'effective_ntd':9000}
    cursor = _ZeroServiceAmountCursor(control=control, end_date=end_date)
    line = SubsidyPeriodLine('ZERO-MANUAL', date(2025, 5, 1), 12000, None)
    monkeypatch.setattr(register, '_select_established_cases', Mock(side_effect=AssertionError('not claim membership')))

    item = owner.recorded_case_amount_control(cursor.connection, cursor, line)

    assert (item.mode, item.computed_ntd, item.effective_ntd) == ('manual', 0, 9000)
    assert cursor.control == control
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE')) for sql, _ in cursor.calls)


@pytest.mark.parametrize('action,amount,mode,after,delta', [
    ('adopt_calculation', None, 'automatic', 0, -9000),
    ('manual_amount', 8000, 'manual', 8000, -1000),
])
def test_zero_service_amount_commands_use_current_zero_from_frozen_readback(
    monkeypatch, action, amount, mode, after, delta,
):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from infrastructure.mysql import government_period_difference_repository as owner
    from subsystems.government_subsidy.period_reconciliation import GovernmentDifferenceCommand

    control = {'case_no':'ZERO-COMMAND', 'period_year':2025, 'amount_mode':'manual',
               'computed_ntd':0, 'effective_ntd':9000}
    original = ({'amount_ntd':12000, 'period_year':2025},)
    cursor = _ZeroServiceAmountCursor(control=control, frozen=original)
    line = SubsidyPeriodLine('ZERO-COMMAND', date(2025, 5, 1), 12000, None)
    item = owner.recorded_case_amount_control(cursor.connection, cursor, line)
    command = GovernmentDifferenceCommand(
        SubsidyPeriod('month', 2025, 5), action, line.case_no, amount, None,
        '', 'Reviewed frozen case amount', 1, 'zero-readback:' + action, 'synthetic',
    )
    append = Mock()
    monkeypatch.setattr(owner, '_append_case_correction', append)

    owner._correct_case(cursor, command, SimpleNamespace(amount_controls=(item,)))

    assert cursor.control == {**control, 'amount_mode':mode, 'computed_ntd':0, 'effective_ntd':after}
    change, = [params for sql, params in cursor.calls if sql.startswith('INSERT INTO government_subsidy_amount_changes')]
    assert change[:5] == (line.case_no, action, 9000, after, 0)
    append.assert_called_once_with(cursor, line.case_no, delta, command.key, expected_year=2025)
    assert cursor.frozen == original
    assert line.amount_ntd == 12000
    assert not any(sql.startswith(('UPDATE government_subsidy_period_members',
                                   'UPDATE government_subsidy_period_entries', 'DELETE')) for sql, _ in cursor.calls)


def test_nonterminal_frozen_readback_with_missing_end_date_keeps_computation_unknown():
    from infrastructure.mysql import government_period_difference_repository as owner

    control = {'case_no':'ACTIVE-READ', 'period_year':2025, 'amount_mode':'automatic',
               'computed_ntd':12000, 'effective_ntd':12000}
    cursor = _ZeroServiceAmountCursor(control=control, status='服務中')
    line = SubsidyPeriodLine('ACTIVE-READ', date(2025, 5, 1), 12000, None)

    item = owner.recorded_case_amount_control(cursor.connection, cursor, line)

    assert item.computed_ntd is None
    assert item.effective_ntd == 12000
    assert cursor.control == control
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE')) for sql, _ in cursor.calls)
