import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {ClientRegistryAccountingSummary} from '../../../../../../../components/ClientRegistryAccountingSummary';
import {financeAccountingClient, type CaseAccounting} from '../../../../../../../api/finance_import/finance_accounting_client';
import {subsidyPlanLabels, subsidyPlanTargets} from '../../../../../../../components/FinanceSubsidyPlanForm';

const facts = (scheme: 'split' | 'advance' | 'direct'): CaseAccounting => ({
  case_no:'SYNTHETIC-1', client_name:'合成', receivable_ntd:0, received_ntd:0, payable_ntd:10000, paid_ntd:0,
  pending_warning_count:0, client_items:[], staff_items:[], transactions:[], warnings:[],
  customer_amount_ntd:10000, subsidy_ntd:10000, customer_burden_ntd:0, scheme,
  subsidy_plan:{case_no:'SYNTHETIC-1',version:0,events:[]},
});
afterEach(() => {cleanup(); vi.restoreAllMocks();});

it.each(['split','advance','direct'] as const)('reads %s and zero self-funding from the existing owner without saving a manual scheme', async scheme => {
  vi.spyOn(financeAccountingClient,'query').mockResolvedValue(facts(scheme));
  const save = vi.spyOn(financeAccountingClient,'saveSubsidyPlan');
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText(subsidyPlanLabels[scheme], {exact:true})).toBeInTheDocument();
  expect(screen.getByText(subsidyPlanTargets[scheme], {exact:true})).toBeInTheDocument();
  expect(screen.getByText('0 元', {exact:true})).toBeInTheDocument();
  expect(screen.getByText('尚未設定', {exact:true})).toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});

it('preserves unavailable amounts and conflicts instead of inventing a zero or overriding the manual choice', async () => {
  vi.spyOn(financeAccountingClient,'query').mockResolvedValue({...facts('split'),
    customer_burden_ntd:null, subsidy_ntd:null, scheme:'unknown', scheme_conflict:true,
    subsidy_plan:{case_no:'SYNTHETIC-1',version:1,events:[{version:1,scheme:'advance',actor:'synthetic',created_at:'2026-11-05T00:00:00Z'}]},
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText(subsidyPlanLabels.advance, {exact:true})).toBeInTheDocument();
  expect(screen.getByText('來源不足，待確認', {exact:true})).toBeInTheDocument();
  expect(screen.queryByText('0 元', {exact:true})).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('方案與正式金流事實衝突');
});

it('shows formal salary and estimated subsidy separately from the same accounting result', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...facts('advance'),
    staff_items: [{
      identity: 'synthetic-salary', direction: 'payable', label: '薪資', party: '月嫂甲',
      expected_ntd: 14400, actual_ntd: 0, has_payment: false, version: 'v1', due_date: '2026-12-15',
    }],
    subsidy_payments: [{
      recipient: 'client', party: '客戶甲', amount_ntd: 12000, due_date: '2027-01-15', source: 'estimate',
    }],
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText(/月嫂甲／薪資：14,400 元，應付日 2026-12-15/)).toBeInTheDocument();
  expect(screen.getByText(/退還客戶／客戶甲：預估 12,000 元，給付日 2027-01-15/)).toBeInTheDocument();
});

it('labels the salary as an estimate when there is no formal payable', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...facts('advance'), staff_receivable_ntd: 14400,
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText('月嫂薪資預估 14,400 元，正式應付待確認。')).toBeInTheDocument();
});
