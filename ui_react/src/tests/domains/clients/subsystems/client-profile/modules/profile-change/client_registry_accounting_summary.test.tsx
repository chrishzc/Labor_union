import {cleanup, render, screen, within} from '@testing-library/react';
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

it('shows verified historical exemption without creating periods or claiming payment and settlement', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...facts('split'), historical_stages:true, full_subsidy:true, full_subsidy_eligibility:true,
    customer_amount_ntd:0, customer_burden_ntd:0, staff_receivable_ntd:null,
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText('全額補助／免自備，客戶應付 0 元')).toBeInTheDocument();
  const original=within(screen.getByRole('region', {name:'歷史客戶原款項'}));
  expect(original.getByText('沒有原期款證據；免自備判定不代表原款已付或帳務結清。')).toBeInTheDocument();
  expect(original.queryByRole('row')).not.toBeInTheDocument();
  expect(screen.getByText('尚無月嫂應付明細。')).toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('preserves same-period original identities, dates, balances and historical payment evidence during conflicts', async () => {
  const original={direction:'receivable' as const,label:'第一期',party:'合成',expected_ntd:1000,
    actual_ntd:400,remaining_ntd:600,has_payment:true,version:'1',due_date:'2025-12-31',payment_stage:'first' as const};
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...facts('split'),historical_stages:true,full_subsidy:false,full_subsidy_eligibility:true,
    scheme:'unknown',scheme_conflict:true,accounting_pending_reasons:['historical_original_client_amount_requires_review'],
    client_items:[{...original,identity:'original-a',source_event_identity:'source-a'},
      {...original,identity:'original-b',actual_ntd:0,remaining_ntd:1000,payment_evidence:'historical_paid',payment_date:'2025-12-20'}],
    transactions:[{identity:'receipt-a',item_identity:'original-a',occurred_on:'2025-12-20',kind:'receipt',amount_ntd:500,bank:'legacy'},
      {identity:'reversal-a',item_identity:'original-a',occurred_on:'2025-12-21',kind:'reversal',amount_ntd:-100,bank:'legacy'},
      {identity:'unallocated-a',item_identity:'unallocated',occurred_on:'2025-12-22',kind:'receipt',amount_ntd:200,bank:'manual'}],
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  const originalRows=within(await screen.findByRole('region',{name:'歷史客戶原款項'}));
  expect(originalRows.getAllByRole('row')).toHaveLength(3);
  expect(originalRows.getByText('original-a').closest('tr')).toHaveTextContent('2025-12-31');
  expect(originalRows.getByText('original-a').closest('tr')).toHaveTextContent('待收 600 元');
  expect(originalRows.getByText('source-a')).toBeInTheDocument();
  expect(originalRows.getByText('original-b').closest('tr')).toHaveTextContent('歷史已付證據，非銀行入帳');
  expect(originalRows.getByText('original-b').closest('tr')).toHaveTextContent('2025-12-20');
  expect(originalRows.getByText(/2025-12-21.*沖正.*-100 元/)).toBeInTheDocument();
  expect(screen.getByRole('region',{name:'期別待確認的原收付款'})).toHaveTextContent('2025-12-22');
  expect(screen.getByRole('region',{name:'期別待確認的原收付款'})).toHaveTextContent('200 元');
  expect(screen.getByText('原客戶款項與免自備判定不相容，請核對原帳。')).toBeInTheDocument();
  expect(screen.queryByText('全額補助／免自備，客戶應付 0 元')).not.toBeInTheDocument();
});

it('keeps each formal payable visible beside another person missing a rate and government subsidy evidence', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...facts('split'),historical_stages:true,subsidy_ntd:null,subsidy_pending_reason:'pricing_policy_source_missing',
    staff_items:[{identity:'salary-a',direction:'payable',label:'薪資',party:'月嫂甲',expected_ntd:14400,
      actual_ntd:0,remaining_ntd:14400,has_payment:false,version:'1',due_date:'2026-12-07'}],
    staff_accounting_availability:[{assignment_id:1,staff_id:1,party:'月嫂甲',obligation_identities:['salary-a'],
      status:'formal',pending_reasons:[],estimated_self_pay_date:null,estimated_subsidy_date:null},
      {assignment_id:2,staff_id:2,party:'月嫂乙',obligation_identities:[],status:'needs_review',
        pending_reasons:['payroll_rate_policy_not_found'],estimated_self_pay_date:null,estimated_subsidy_date:null}],
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText(/月嫂甲／薪資：14,400 元，應付日 2026-12-07/)).toBeInTheDocument();
  const availability=within(screen.getByRole('region',{name:'歷史月嫂應付依據'}));
  expect(availability.getByText('月嫂乙')).toBeInTheDocument();
  expect(availability.getByText('缺少本人的有效計薪費率。')).toBeInTheDocument();
  expect(screen.getByText('缺少本案有效費率政策，政府補助金額待確認。')).toBeInTheDocument();
});

it('does not present an estimated historical client return as an established refund', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...facts('advance'), historical_stages:true,
    subsidy_payments:[{recipient:'client',party:'客戶甲',amount_ntd:12000,due_date:'2027-01-15',source:'estimate'}],
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  expect(await screen.findByText('給付款項待確認。')).toBeInTheDocument();
  expect(screen.queryByText(/退還客戶／客戶甲：預估/)).not.toBeInTheDocument();
});

it.each([['receipt','原收款'],['refund','原退款'],['reversal','沖正'],['refund_reversal','退款沖正']])(
  'labels an unallocated %s from its formal kind while preserving the original amount', async (kind,label) => {
    vi.spyOn(financeAccountingClient,'query').mockResolvedValue({
      ...facts('split'), historical_stages:true,
      transactions:[{identity:'source-transaction',item_identity:'unallocated',occurred_on:'2025-12-22',kind,amount_ntd:200,bank:'manual'}],
    });
    render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
    const evidence=await screen.findByRole('region',{name:'期別待確認的原收付款'});
    expect(evidence).toHaveTextContent(`人工補登 · ${label} · 200 元`);
  },
);

it('shows the exact stale historical payment identity without treating it as current payment', async () => {
  vi.spyOn(financeAccountingClient,'query').mockResolvedValue({
    ...facts('split'),historical_stages:true,full_subsidy:false,scheme:'unknown',
    accounting_pending_reasons:['historical_client_payment_evidence_stale'],
    stale_payment_evidence_identities:['original-payment:stale:1'],
  });
  render(<ClientRegistryAccountingSummary caseNo="SYNTHETIC-1" revision={0}/>);
  const evidence=await screen.findByRole('region',{name:'歷史付款證據待核對'});
  expect(evidence).toHaveTextContent('歷史付款證據已過期待核對');
  expect(evidence).toHaveTextContent('original-payment:stale:1');
  expect(screen.queryByText('歷史已付證據，非銀行入帳')).not.toBeInTheDocument();
  expect(screen.queryByText('全額補助／免自備，客戶應付 0 元')).not.toBeInTheDocument();
});
