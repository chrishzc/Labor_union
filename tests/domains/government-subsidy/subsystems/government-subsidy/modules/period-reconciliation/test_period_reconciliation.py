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
