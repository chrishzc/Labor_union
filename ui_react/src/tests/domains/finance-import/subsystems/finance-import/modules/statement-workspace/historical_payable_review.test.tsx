import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import type { HistoricalPayableAuditItem } from '../../../../../../../api/accounts_payable/accounts_payable_query_schemas';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { transport } from '../../../../../../../api/shared/transport';
import { HistoricalPayableEditor, HistoricalPayableLookup } from '../../../../../../../components/HistoricalPayableReview';

const pending: HistoricalPayableAuditItem = {
  case_no: 'CASE-OLD-1', staff_id: 42, recipient_name: '合成月嫂甲',
  obligation_identity: null, current_event_id: null, amount_due_ntd: null, balance_ntd: null,
  order_due_date: null, effective_due_date: null, source: 'order_facts',
  disposition: 'date_not_formed', reason: '尚未建立月嫂應付帳務及付款日。',
};
const formalPayroll: CaseAccounting = {
  case_no: pending.case_no, client_name: '合成客戶', pending_warning_count: 0,
  receivable_ntd: null, received_ntd: null, payable_ntd: 48000, paid_ntd: 0,
  client_items: [], transactions: [], warnings: [],
  staff_items: [{
    identity: 'original-42', direction: 'payable', label: '月嫂付款', party: '合成月嫂甲',
    expected_ntd: 48000, actual_ntd: 0, has_payment: false, remaining_ntd: 48000,
    version: '1', due_date: null,
  }],
  staff_accounting_availability: [{
    assignment_id: 17, staff_id: 42, party: '合成月嫂甲', obligation_identities: ['original-42'],
    status: 'formal', estimated_self_pay_date: null, estimated_subsidy_date: null,
    pending_reasons: ['historical_payroll_funding_pending'],
  }, {
    assignment_id: 18, staff_id: 43, party: '合成月嫂乙', obligation_identities: [],
    status: 'needs_review', estimated_self_pay_date: null, estimated_subsidy_date: null,
    pending_reasons: ['payroll_rate_policy_not_found'],
  }],
};

afterEach(() => vi.restoreAllMocks());

it('帶入同案及月嫂，同步後重新查核清冊', async () => {
  const lookup = vi.spyOn(accountsPayableQueryClient, 'lookupHistorical')
    .mockResolvedValueOnce([pending])
    .mockResolvedValueOnce([{
      ...pending, obligation_identity: 'original-42', current_event_id: 1,
      amount_due_ntd: 12000, balance_ntd: 12000, effective_due_date: '2026-10-15',
      source: 'formal_obligation', disposition: 'selected_month', reason: '列入所選付款月份。',
    }]);
  const sync = vi.spyOn(accountsPayableQueryClient, 'synchronizeHistorical')
    .mockResolvedValue({
      case_no: pending.case_no, action: 'created', assignment_id: 17,
      staff_id: 42, obligation_identity: 'original-42',
    });
  const readback = vi.spyOn(financeAccountingClient, 'query').mockResolvedValue(formalPayroll);

  function Workspace() {
    const [selected, setSelected] = useState<HistoricalPayableAuditItem>();
    const [revision, setRevision] = useState(0);
    return <>
      <HistoricalPayableLookup month="2026-10" revision={revision} onCase={setSelected} />
      {selected && <HistoricalPayableEditor item={selected} onSaved={() => setRevision(value => value + 1)} />}
    </>;
  }

  render(<Workspace />);
  fireEvent.click(screen.getByText('查未列入原因'));
  fireEvent.change(screen.getByLabelText('案號、月嫂完整姓名或公會編號'), { target: { value: '合成月嫂甲' } });
  fireEvent.click(screen.getByRole('button', { name: '查核歷史月嫂款' }));
  fireEvent.click(await screen.findByRole('button', { name: '查看本案帳務' }));
  expect(screen.getByRole('heading', { name: '合成月嫂甲 · 應付清冊查核' })).toBeInTheDocument();
  expect(screen.queryByLabelText('原付款日')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '同步月嫂應付' }));
  await waitFor(() => expect(sync).toHaveBeenCalledWith('CASE-OLD-1'));
  expect(await screen.findByText(/列入所選付款月份/)).toBeInTheDocument();
  expect(lookup).toHaveBeenCalledTimes(2);
  expect(readback).toHaveBeenCalledWith('CASE-OLD-1');
});

it('已結清款項只顯示查核原因', () => {
  render(<HistoricalPayableEditor item={{
    ...pending, disposition: 'paid_or_settled', obligation_identity: 'original-42',
    current_event_id: 1, amount_due_ntd: 12000, balance_ntd: 0, reason: '已有結清證據。',
  }} onSaved={vi.fn()} />);
  expect(screen.getByText('已有結清證據。')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '更正應付' })).not.toBeInTheDocument();
});

it('顯示歷史歸屬更正的待核對原因，無成功回報或清冊重讀', async () => {
  vi.spyOn(transport, 'post').mockResolvedValue({
    success: true,
    data: { details: [{
      case_no: pending.case_no, action: 'skipped', reason: 'historical_payroll_attribution_pending',
      detail: '請核對原出款證據，並回到歷史服務歸屬更正。',
    }] },
  });
  const onSaved = vi.fn();
  render(<HistoricalPayableEditor item={pending} onSaved={onSaved} />);

  fireEvent.click(screen.getByRole('button', { name: '同步月嫂應付' }));

  expect(await screen.findByRole('status')).toHaveTextContent('請核對原出款證據，並回到歷史服務歸屬更正。');
  expect(onSaved).not.toHaveBeenCalled();
});

it.each([17, 99])('同步回執逐人讀回應付，驗證指派 %s 與另一人的缺項', async assignmentId => {
  vi.spyOn(transport, 'post').mockResolvedValue({
    success: true,
    data: {
      details: [{
        case_no: pending.case_no,
        action: 'created',
        items: [{
          action: 'created', assignment_id: assignmentId, staff_id: 42, obligation_identity: 'original-42',
          due_date: null, payment_arrangement_pending: true, pending_reason: 'historical_payroll_funding_pending',
        }, {
          action: 'skipped', assignment_id: 18, staff_id: 43, reason: 'payroll_rate_policy_not_found',
        }],
      }],
    },
  });
  const query = vi.spyOn(financeAccountingClient, 'query').mockResolvedValue(formalPayroll);
  const onSaved = vi.fn();
  render(<HistoricalPayableEditor item={pending} onSaved={onSaved} />);

  fireEvent.click(screen.getByRole('button', { name: '同步月嫂應付' }));

  const status = await screen.findByRole('status');
  expect(query).toHaveBeenCalledWith(pending.case_no);
  expect(status).toHaveTextContent('合成月嫂乙 · 請查核本案保存的月嫂時薪。');
  if (assignmentId === 17) {
    expect(status).toHaveTextContent('合成月嫂甲 · 正式應付 NT$ 48,000 · 付款安排待確認');
  } else {
    expect(status).toHaveTextContent('尚未查回對應指派的正式應付');
    expect(status).not.toHaveTextContent('NT$ 48,000');
  }
  expect(onSaved).toHaveBeenCalledOnce();
});
