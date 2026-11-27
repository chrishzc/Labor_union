import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import type { HistoricalPayableAuditItem } from '../../../../../../../api/accounts_payable/accounts_payable_query_schemas';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { monthlyAccountingClient } from '../../../../../../../api/finance_import/monthly_accounting_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';
import { HistoricalPayableEditor, HistoricalPayableLookup } from '../../../../../../../components/HistoricalPayableReview';
import { FinancePage } from '../../../../../../../pages/FinancePage';

vi.mock('../../../../../../../components/FinanceCaseAccounting', () => ({
  FinanceCaseAccounting: () => null,
}));

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

type StaffAvailability = NonNullable<CaseAccounting['staff_accounting_availability']>[number];

const selectedAssignment: StaffAvailability = {
  assignment_id: 17, staff_id: 42, party: '合成月嫂甲', obligation_identities: ['original-42'],
  status: 'formal', estimated_self_pay_date: '2026-10-20', estimated_subsidy_date: null,
  estimated_amount_ntd: 39000, pending_reasons: ['historical_payroll_funding_pending'],
};
const sameNameUnconfirmed: StaffAvailability = {
  assignment_id: 18, staff_id: 43, party: selectedAssignment.party, obligation_identities: [],
  status: 'needs_review', estimated_self_pay_date: '2026-10-20', estimated_subsidy_date: null,
  estimated_amount_ntd: 27000, pending_reasons: ['payroll_rate_policy_not_found'],
};
const sameNameAccounting: CaseAccounting = {
  ...formalPayroll,
  staff_accounting_availability: [sameNameUnconfirmed, selectedAssignment],
};

const bothFormalAccounting: CaseAccounting = {
  ...sameNameAccounting,
  payable_ntd: 80100,
  staff_items: [...sameNameAccounting.staff_items, {
    identity: 'original-43', direction: 'payable', label: '月嫂付款', party: selectedAssignment.party,
    expected_ntd: 32100, actual_ntd: 0, has_payment: false, remaining_ntd: 32100,
    version: '1', due_date: '2026-10-25',
  }],
  staff_accounting_availability: [selectedAssignment, {
    ...sameNameUnconfirmed, status: 'formal', obligation_identities: ['original-43'], pending_reasons: [],
  }],
};

async function recheckAfterSyncTimeout(item: HistoricalPayableAuditItem, accounting?: CaseAccounting) {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-contract-token');
  const post = vi.spyOn(transport, 'post').mockRejectedValue(new ApiTimeoutError(10_000));
  const get = vi.spyOn(transport, 'get');
  if (accounting) {
    get.mockResolvedValue({ success: true, message: '已查詢', data: accounting });
  } else {
    get.mockRejectedValue(new ApiTimeoutError(10_000));
  }

  const { container } = render(<HistoricalPayableEditor item={item} onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '同步月嫂應付' }));
  const recheck = await screen.findByRole('button', { name: '重新查核' });
  expect(post).toHaveBeenCalledExactlyOnceWith(
    '/api/v1/orders/CASE-OLD-1/payroll/sync-historical-baseline-obligations',
    undefined,
    expect.any(Object),
  );

  const callsBeforeRecheck = get.mock.calls.length;
  await act(async () => { fireEvent.click(recheck); });

  const recheckCalls = get.mock.calls.slice(callsBeforeRecheck);
  if (item.staff_id !== null || recheckCalls.length > 0) {
    expect(recheckCalls).toEqual([
      ['/api/v1/finance-import/cases/CASE-OLD-1/accounting', expect.any(Object)],
    ]);
  }
  expect(post).toHaveBeenCalledTimes(1);
  expect(container).not.toHaveTextContent(/同步成功|同步完成/);
  return container;
}

it('DS-02 同案同名依原選取月嫂查回正式金額，原付款日未定且不重送同步', async () => {
  const result = await recheckAfterSyncTimeout(pending, sameNameAccounting);

  expect(result).toHaveTextContent(/正式應付[^\d]*48,000/);
  expect(result).toHaveTextContent(/付款日[^\d]*待確認/);
  expect(result).not.toHaveTextContent(/39,000|27,000|2026-10-20/);
});

it('DS-02 分筆付款尚有未定日期時，只顯示各筆的正式付款日', async () => {
  const accounting: CaseAccounting = {
    ...sameNameAccounting,
    staff_items: sameNameAccounting.staff_items.map(item => ({
      ...item,
      due_date: '2026-10-30',
      funding_portions: [{
        funding_kind: 'client', amount_ntd: 30000, due_date: '2026-10-15',
        settled_ntd: 0, remaining_ntd: 30000,
      }, {
        funding_kind: 'subsidy', amount_ntd: 18000, due_date: null,
        settled_ntd: 0, remaining_ntd: 18000,
      }],
    })),
  };
  await recheckAfterSyncTimeout(pending, accounting);

  const status = screen.getByRole('status');
  expect(status).toHaveTextContent(/正式應付[^\d]*48,000/);
  expect(status).toHaveTextContent(/自備款付款日.*2026-10-15/);
  expect(status).toHaveTextContent(/補助款.*付款日待確認/);
  expect(status).not.toHaveTextContent('2026-10-30');
});

it('DS-02 同名乙尚無正式應付時，顯示保存時薪待查核，而非旁人的金額或估算', async () => {
  const result = await recheckAfterSyncTimeout({ ...pending, staff_id: 43 }, sameNameAccounting);

  expect(screen.getByRole('status')).toHaveTextContent('請查核本案保存的月嫂時薪');
  expect(result).not.toHaveTextContent(/48,000|39,000|27,000|2026-10-20/);
});

it('DS-02 正式關聯唯一但缺明細時，顯示已建帳並指出缺少正式應付明細', async () => {
  const accounting: CaseAccounting = {
    ...sameNameAccounting,
    staff_accounting_availability: [selectedAssignment, {
      ...sameNameUnconfirmed, status: 'formal', obligation_identities: ['missing-43'], pending_reasons: [],
    }],
  };
  const result = await recheckAfterSyncTimeout({ ...pending, staff_id: 43 }, accounting);

  const status = screen.getByRole('status');
  expect(status).toHaveTextContent('已建帳');
  expect(status).toHaveTextContent('找不到對應的正式應付明細');
  expect(result).not.toHaveTextContent(/48,000|39,000|27,000|2026-10-20/);
});

it('DS-02 原有更正資格不因同步結果待確認而消失，保留獨立更正入口', async () => {
  const post = vi.spyOn(transport, 'post');
  render(<HistoricalPayableEditor item={{
    ...pending, obligation_identity: 'original-42', current_event_id: 1,
    source: 'formal_obligation', disposition: 'selected_month', amount_due_ntd: 48000,
    balance_ntd: 48000, effective_due_date: '2026-10-15',
  }} recheckRequired onSaved={vi.fn()} />);

  expect(screen.getByRole('button', { name: '重新查核' })).toBeInTheDocument();
  fireEvent.click(screen.getByText('查看更正應付', { selector: 'summary' }));

  expect(screen.getByLabelText('原應付金額')).toHaveValue(48000);
  expect(screen.getByLabelText('原付款日')).toHaveValue('2026-10-15');
  expect(post).not.toHaveBeenCalled();
});

const inconclusiveCases: {
  name: string;
  staffId: HistoricalPayableAuditItem['staff_id'];
  accounting?: CaseAccounting;
}[] = [
  { name: '原選取列無人員 ID', staffId: null, accounting: sameNameAccounting },
  {
    name: '同一人有多筆無法區分的指派',
    staffId: 42,
    accounting: {
      ...sameNameAccounting,
      staff_accounting_availability: [
        sameNameUnconfirmed, selectedAssignment, { ...selectedAssignment, assignment_id: 19 },
      ],
    },
  },
  {
    name: '同一義務出現在多筆關聯',
    staffId: 42,
    accounting: {
      ...sameNameAccounting,
      staff_accounting_availability: [
        selectedAssignment, { ...sameNameUnconfirmed, obligation_identities: ['original-42'] },
      ],
    },
  },
  {
    name: '帳務回應為他案',
    staffId: 42,
    accounting: { ...sameNameAccounting, case_no: 'CASE-OLD-2' },
  },
  { name: '帳務 GET 失敗', staffId: 42 },
];

it.each(inconclusiveCases)('DS-02 $name：仍待確認，不顯示旁人金額或估算', async ({ staffId, accounting }) => {
  const result = await recheckAfterSyncTimeout({ ...pending, staff_id: staffId }, accounting);

  expect(result).toHaveTextContent('待確認');
  expect(result).not.toHaveTextContent(/48,000|39,000|27,000|2026-10-20/);
});

it.each([
  ['not_established', false], ['not_established', true],
  ['needs_review', false], ['needs_review', true],
] as const)('DS-02 同一位月嫂有正式與 %s 指派（正式在前：%s）仍待確認', async (status, formalFirst) => {
  const otherAssignment: StaffAvailability = {
    ...sameNameUnconfirmed, staff_id: selectedAssignment.staff_id, status,
  };
  const availability = formalFirst
    ? [selectedAssignment, otherAssignment]
    : [otherAssignment, selectedAssignment];
  const result = await recheckAfterSyncTimeout(pending, {
    ...sameNameAccounting, staff_accounting_availability: availability,
  });

  expect(result).toHaveTextContent('同一位月嫂有多筆歷史指派');
  expect(result).not.toHaveTextContent(/48,000|39,000|27,000|2026-10-20/);
});

it('DS-02 回清冊改選同案同名的乙，沿用同一次未知同步且查回乙自己的正式金額', async () => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-contract-token');
  const secondRow: HistoricalPayableAuditItem = {
    ...pending, staff_id: 43, reason: '第二位同名月嫂的原列待確認。',
  };
  vi.spyOn(accountsPayableQueryClient, 'lookupHistorical').mockResolvedValue([pending, secondRow]);
  vi.spyOn(monthlyAccountingClient, 'query').mockResolvedValue({
    start_month: '2026-10', end_month: '2026-10', category: 'all', as_of: '2026-10-31',
    excluded_cases: [], undated_item_count: 0, rows: [],
  });
  const post = vi.spyOn(transport, 'post').mockRejectedValue(new ApiTimeoutError(10_000));
  const get = vi.spyOn(transport, 'get').mockResolvedValue({
    success: true, message: '已查詢', data: bothFormalAccounting,
  });
  const previousUrl = window.location.href;
  window.history.replaceState(null, '', '#finance?tab=monthly');
  try {
    render(<FinancePage />);

    fireEvent.click(screen.getByText('查未列入原因'));
    fireEvent.change(screen.getByLabelText('案號、月嫂完整姓名或公會編號'), {
      target: { value: pending.recipient_name },
    });
    fireEvent.click(screen.getByRole('button', { name: '查核歷史月嫂款' }));
    const [first] = await screen.findAllByRole('button', { name: '查看本案帳務' });
    fireEvent.click(first);

    const firstReview = within(screen.getByRole('region', { name: '歷史月嫂款查核' }));
    fireEvent.click(firstReview.getByRole('button', { name: '同步月嫂應付' }));
    const firstRecheck = await firstReview.findByRole('button', { name: '重新查核' });
    expect(get).not.toHaveBeenCalled();
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => { fireEvent.click(firstRecheck); });

    const firstResult = firstReview.getByRole('status');
    expect(firstResult).toHaveTextContent(/正式應付[^\d]*48,000/);
    expect(firstResult).toHaveTextContent(/付款日[^\d]*待確認/);
    expect(firstResult).not.toHaveTextContent(/同步成功|同步完成|32,100|39,000|27,000|2026-10-20/);
    expect(firstReview.queryByText(pending.reason)).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);

    const drawer = screen.getByRole('dialog', { name: '案件帳務 · CASE-OLD-1' });
    fireEvent.click(within(drawer).getByText('關閉案件', { selector: 'button' }));
    expect(screen.queryByRole('dialog', { name: '案件帳務 · CASE-OLD-1' })).not.toBeInTheDocument();

    const [, second] = await screen.findAllByRole('button', { name: '查看本案帳務' });
    fireEvent.click(second);
    const secondRegion = screen.getByRole('region', { name: '歷史月嫂款查核' });
    const secondReview = within(secondRegion);
    expect(secondRegion).not.toHaveTextContent(/48,000/);
    const secondRecheck = await secondReview.findByRole('button', { name: '重新查核' });
    expect(get).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => { fireEvent.click(secondRecheck); });

    const secondResult = secondReview.getByRole('status');
    expect(secondResult).toHaveTextContent(/正式應付[^\d]*32,100/);
    expect(secondResult).toHaveTextContent('2026-10-25');
    expect(secondRegion).not.toHaveTextContent(/48,000|39,000|27,000|2026-10-20|同步成功|同步完成/);
    expect(get.mock.calls).toEqual([
      ['/api/v1/finance-import/cases/CASE-OLD-1/accounting', expect.any(Object)],
      ['/api/v1/finance-import/cases/CASE-OLD-1/accounting', expect.any(Object)],
    ]);
    expect(post).toHaveBeenCalledExactlyOnceWith(
      '/api/v1/orders/CASE-OLD-1/payroll/sync-historical-baseline-obligations',
      undefined,
      expect.any(Object),
    );
  } finally {
    window.history.replaceState(null, '', previousUrl);
  }
});
