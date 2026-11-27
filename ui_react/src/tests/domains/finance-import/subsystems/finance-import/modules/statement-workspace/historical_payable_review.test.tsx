import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import type { HistoricalPayableAuditItem } from '../../../../../../../api/accounts_payable/accounts_payable_query_schemas';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
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

const sameNamePayroll: CaseAccounting = {
  ...formalPayroll, payable_ntd: 60000,
  staff_items: [{
    identity: 'original-42', direction: 'payable', label: '月嫂付款', party: '同名月嫂',
    expected_ntd: 48000, actual_ntd: 0, has_payment: false, remaining_ntd: 48000,
    version: '1', due_date: null,
  }, {
    identity: 'original-43', direction: 'payable', label: '月嫂付款', party: '同名月嫂',
    expected_ntd: 12000, actual_ntd: 0, has_payment: false, remaining_ntd: 12000,
    version: '1', due_date: '2026-10-15',
  }],
  staff_accounting_availability: [{
    assignment_id: 17, staff_id: 42, party: '同名月嫂', obligation_identities: ['original-42'],
    status: 'formal', estimated_self_pay_date: null, estimated_subsidy_date: null, pending_reasons: [],
  }, {
    assignment_id: 18, staff_id: 43, party: '同名月嫂', obligation_identities: ['original-43'],
    status: 'formal', estimated_self_pay_date: null, estimated_subsidy_date: null, pending_reasons: [],
  }],
};

it.each([
  { staffId: 42, amount: '48,000', otherAmount: '12,000', dueDate: '待確認' },
  { staffId: 43, amount: '12,000', otherAmount: '48,000', dueDate: '2026-10-15' },
])('沒有同步回執時唯讀查回同名月嫂 $staffId 的正式應付', async ({ staffId, amount, otherAmount, dueDate }) => {
  const query = vi.spyOn(financeAccountingClient, 'query').mockResolvedValue(sameNamePayroll);
  const sync = vi.spyOn(accountsPayableQueryClient, 'synchronizeHistorical');
  const supplement = vi.spyOn(accountsPayableQueryClient, 'recordHistoricalUnpaid');
  const post = vi.spyOn(transport, 'post');
  const onSaved = vi.fn();
  render(<HistoricalPayableEditor item={{ ...pending, staff_id: staffId, recipient_name: '同名月嫂' }} onSaved={onSaved} />);

  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));

  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent(`月嫂編號 ${staffId} · 正式應付 NT$ ${amount} · 付款日 ${dueDate}`));
  expect(region.getByRole('status')).not.toHaveTextContent(`NT$ ${otherAmount}`);
  expect(region.getByRole('status')).not.toHaveTextContent('60,000');
  expect(region.getByRole('status')).not.toHaveTextContent('同步成功');
  expect(query).toHaveBeenCalledWith(pending.case_no, expect.any(AbortSignal));
  expect(sync).not.toHaveBeenCalled();
  expect(supplement).not.toHaveBeenCalled();
  expect(post).not.toHaveBeenCalled();
  expect(onSaved).not.toHaveBeenCalled();
});

it.each(['rejected', 'missing'])('同步回應 %s 後仍可查核，不重送同步', async outcome => {
  const sync = vi.spyOn(accountsPayableQueryClient, 'synchronizeHistorical');
  if (outcome === 'rejected') sync.mockRejectedValue(new Error('response lost'));
  else sync.mockResolvedValue(undefined);
  const query = vi.spyOn(financeAccountingClient, 'query').mockResolvedValue(sameNamePayroll);
  const post = vi.spyOn(transport, 'post');
  const onSaved = vi.fn();
  render(<HistoricalPayableEditor item={pending} onSaved={onSaved} />);

  fireEvent.click(screen.getByRole('button', { name: '同步月嫂應付' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '同步月嫂應付' })).toBeEnabled());
  expect(query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('正式應付 NT$ 48,000'));
  expect(sync).toHaveBeenCalledOnce();
  expect(query).toHaveBeenCalledOnce();
  expect(post).not.toHaveBeenCalled();
  expect(onSaved).not.toHaveBeenCalled();
});

type ReadbackAvailability = NonNullable<CaseAccounting['staff_accounting_availability']>[number];
const selectedAvailability: ReadbackAvailability = {
  assignment_id: 17, staff_id: 42, party: '同名月嫂', obligation_identities: ['original-42'],
  status: 'formal', estimated_self_pay_date: null, estimated_subsidy_date: null, pending_reasons: [],
};
const otherAvailability: ReadbackAvailability = {
  ...selectedAvailability, assignment_id: 18, staff_id: 43, obligation_identities: ['original-43'],
};
it.each([
  { status: 'needs_review', nonformalFirst: false },
  { status: 'needs_review', nonformalFirst: true },
  { status: 'not_established', nonformalFirst: false },
  { status: 'not_established', nonformalFirst: true },
] as const)('同人混合指派 $status，未建帳列先回 $nonformalFirst 時不顯金額，移除後才顯示', async ({ status, nonformalFirst }) => {
  const nonformal: ReadbackAvailability = {
    ...selectedAvailability, assignment_id: 99, status, obligation_identities: [],
  };
  const assignments = nonformalFirst ? [nonformal, selectedAvailability] : [selectedAvailability, nonformal];
  const mixedPayroll: CaseAccounting = {
    ...formalPayroll, staff_accounting_availability: assignments,
  };
  // 正控制只移除未建帳指派；正式指派、款項及缺付款日都保持相同。
  const uniquePayroll: CaseAccounting = {
    ...mixedPayroll,
    staff_accounting_availability: assignments.filter(person => person.assignment_id !== 99),
  };
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-readback-token');
  const get = vi.spyOn(transport, 'get')
    .mockResolvedValueOnce({ success: true, message: '', data: mixedPayroll })
    .mockResolvedValueOnce({ success: true, message: '', data: uniquePayroll });
  const post = vi.spyOn(transport, 'post');
  const sync = vi.spyOn(accountsPayableQueryClient, 'synchronizeHistorical');
  const supplement = vi.spyOn(accountsPayableQueryClient, 'recordHistoricalUnpaid');
  const onSaved = vi.fn();
  render(<HistoricalPayableEditor item={pending} onSaved={onSaved} />);
  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));

  fireEvent.click(region.getByRole('button', { name: '重新查核正式應付' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('請核對本案指派'));
  expect(region.getByRole('status')).not.toHaveTextContent('NT$');
  expect(get).toHaveBeenCalledOnce();

  fireEvent.click(region.getByRole('button', { name: '重新查核正式應付' }));
  await waitFor(() => expect(region.getByRole('status'))
    .toHaveTextContent('月嫂編號 42 · 正式應付 NT$ 48,000 · 付款日 待確認'));
  expect(region.getByRole('status')).not.toHaveTextContent('同步成功');
  expect(get).toHaveBeenCalledTimes(2);
  for (const call of get.mock.calls) {
    expect(call).toEqual([
      '/api/v1/finance-import/cases/CASE-OLD-1/accounting',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ]);
  }
  expect(post).not.toHaveBeenCalled();
  expect(sync).not.toHaveBeenCalled();
  expect(supplement).not.toHaveBeenCalled();
  expect(onSaved).not.toHaveBeenCalled();
});

const unresolvedReadbacks: { name: string; accounting: CaseAccounting; selectedIdentity?: string }[] = [
  { name: '所選月嫂缺指派編號', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [{ ...selectedAvailability, assignment_id: null }, otherAvailability],
  } },
  { name: '同人多正式指派', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [selectedAvailability, { ...selectedAvailability, assignment_id: 99 }],
  } },
  { name: '指派來源重複', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [selectedAvailability, selectedAvailability],
  } },
  { name: '義務連結重複', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [{ ...selectedAvailability, obligation_identities: ['original-42', 'original-42'] }],
  } },
  { name: '義務被另一位同名月嫂宣稱', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [selectedAvailability, { ...otherAvailability, obligation_identities: ['original-42'] }],
  } },
  { name: '兩人使用同一指派編號', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [selectedAvailability, { ...otherAvailability, assignment_id: 17 }],
  } },
  { name: '款項列重複', accounting: { ...sameNamePayroll, staff_items: [...sameNamePayroll.staff_items, ...sameNamePayroll.staff_items] } },
  { name: '回應是另一案', accounting: { ...sameNamePayroll, case_no: 'CASE-OTHER' } },
  { name: '缺正式款項', accounting: { ...sameNamePayroll, staff_items: [] } },
  { name: '款項方向錯誤', accounting: {
    ...sameNamePayroll, staff_items: sameNamePayroll.staff_items.map(row => ({ ...row, direction: 'receivable' })),
  } },
  { name: '只有另一位同名月嫂', accounting: { ...sameNamePayroll, staff_accounting_availability: [otherAvailability] } },
  { name: '只有未建帳試算', accounting: {
    ...sameNamePayroll, staff_accounting_availability: [{ ...selectedAvailability, status: 'not_established', estimated_amount_ntd: 99999 }],
  } },
  { name: '選取義務與指派不一致', selectedIdentity: 'original-43', accounting: sameNamePayroll },
];

it.each(unresolvedReadbacks)('$name 時不以同名、試算或案件總額補位', async ({ accounting, selectedIdentity }) => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue(accounting);
  const post = vi.spyOn(transport, 'post');
  render(<HistoricalPayableEditor item={{ ...pending, obligation_identity: selectedIdentity ?? null }} onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));

  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('核對'));
  expect(region.getByRole('status')).not.toHaveTextContent('NT$');
  expect(post).not.toHaveBeenCalled();
});

it('所選月嫂識別未知時不查別人的正式款項', () => {
  const query = vi.spyOn(financeAccountingClient, 'query');
  const post = vi.spyOn(transport, 'post');
  render(<HistoricalPayableEditor item={{ ...pending, staff_id: null }} onSaved={vi.fn()} />);
  expect(screen.getByRole('button', { name: '重新查核正式應付' })).toBeDisabled();
  expect(screen.getByText('所選月嫂識別待確認，請回清冊核對人員。')).toBeInTheDocument();
  expect(query).not.toHaveBeenCalled();
  expect(post).not.toHaveBeenCalled();
});

it('正式應付為零仍以正式金額讀回', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
    ...formalPayroll, staff_items: formalPayroll.staff_items.map(row => ({ ...row, expected_ntd: 0, remaining_ntd: 0 })),
  });
  render(<HistoricalPayableEditor item={pending} onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('正式應付 NT$ 0 · 付款日 待確認'));
});

it('已有原款項的更正面板也可唯讀重查', async () => {
  vi.spyOn(financeAccountingClient, 'query').mockResolvedValue(sameNamePayroll);
  const post = vi.spyOn(transport, 'post');
  render(<HistoricalPayableEditor item={{
    ...pending, obligation_identity: 'original-42', effective_due_date: '2026-10-15',
    disposition: 'paid_or_settled', balance_ntd: 0,
  }} onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('正式應付 NT$ 48,000'));
  expect(post).not.toHaveBeenCalled();
});

it('讀取失敗可重新唯讀查核', async () => {
  const query = vi.spyOn(financeAccountingClient, 'query')
    .mockRejectedValueOnce(new Error('read failed')).mockResolvedValueOnce(sameNamePayroll);
  const post = vi.spyOn(transport, 'post');
  render(<HistoricalPayableEditor item={pending} onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('尚未查回目前正式應付，請重新查核。');
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('正式應付 NT$ 48,000'));
  expect(query).toHaveBeenCalledTimes(2);
  expect(post).not.toHaveBeenCalled();
});

it('切換同名月嫂後不顯示前一人的延遲讀回', async () => {
  let finishFirst: (value: CaseAccounting) => void = () => { throw new Error('read not started'); };
  const firstRead = new Promise<CaseAccounting>(resolve => { finishFirst = resolve; });
  const query = vi.spyOn(financeAccountingClient, 'query').mockReturnValueOnce(firstRead).mockResolvedValueOnce(sameNamePayroll);
  const onSaved = vi.fn();
  const { rerender } = render(<HistoricalPayableEditor item={{ ...pending, recipient_name: '同名月嫂' }} onSaved={onSaved} />);
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  const signal = query.mock.calls[0]?.[1];
  rerender(<HistoricalPayableEditor item={{ ...pending, staff_id: 43, recipient_name: '同名月嫂' }} onSaved={onSaved} />);
  expect(signal?.aborted).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '重新查核正式應付' }));
  const region = within(screen.getByRole('region', { name: '正式應付唯讀查核' }));
  await waitFor(() => expect(region.getByRole('status')).toHaveTextContent('月嫂編號 43 · 正式應付 NT$ 12,000'));
  await act(async () => { finishFirst(sameNamePayroll); await firstRead; });
  expect(region.getByRole('status')).not.toHaveTextContent('48,000');
  expect(onSaved).not.toHaveBeenCalled();
});

it('同案兩位同名的查核列顯示人員編號，選取保留各自識別', async () => {
  const selectedPeople = [
    { ...pending, recipient_name: '同名月嫂', staff_id: 42 },
    { ...pending, recipient_name: '同名月嫂', staff_id: 43 },
  ];
  vi.spyOn(accountsPayableQueryClient, 'lookupHistorical').mockResolvedValue(selectedPeople);
  const onCase = vi.fn();
  render(<HistoricalPayableLookup month="2026-10" revision={0} onCase={onCase} />);
  fireEvent.click(screen.getByText('查未列入原因'));
  fireEvent.change(screen.getByLabelText('案號、月嫂完整姓名或公會編號'), { target: { value: '同名月嫂' } });
  fireEvent.click(screen.getByRole('button', { name: '查核歷史月嫂款' }));

  expect(await screen.findByText('月嫂編號 42')).toBeInTheDocument();
  expect(screen.getByText('月嫂編號 43')).toBeInTheDocument();
  for (const button of screen.getAllByRole('button', { name: '查看本案帳務' })) fireEvent.click(button);
  expect(onCase).toHaveBeenNthCalledWith(1, expect.objectContaining({ case_no: pending.case_no, staff_id: 42 }));
  expect(onCase).toHaveBeenNthCalledWith(2, expect.objectContaining({ case_no: pending.case_no, staff_id: 43 }));
});
