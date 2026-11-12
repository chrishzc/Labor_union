import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRosterPage } from '../../../../../../../pages/ClientRosterPage';
import { ClientRegistrySummarySchema } from '../../../../../../../api/client_registry/client_registry_schemas';

const mocks = vi.hoisted(() => ({ list: vi.fn(), query: vi.fn() }));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));

const item = {
  client_id: 1, case_no: '115000101', imported_virtual_accounts: [], built_in_virtual_account: '99781699115101', name: '客戶甲', phone: null, city: null,
  multi_birth_count: null, service_days: 20, requires_cooking: false,
  planned_start_date: '2026-07-01', order_status: '訂單完成',
  staff_payment_due_date: '2026-09-15',
  client_obligation_dates: [
    { obligation_identity: 'c-deposit', obligation_type: 'deposit', due_date: '2026-06-20' },
    { obligation_identity: 'c-first', obligation_type: 'first', due_date: '2026-07-03' },
    { obligation_identity: 'c-second', obligation_type: 'second', due_date: null },
    { obligation_identity: 'c-return-1', obligation_type: 'subsidy_return', due_date: '2026-10-15' },
    { obligation_identity: 'c-return-2', obligation_type: 'subsidy_return', due_date: '2026-11-15' },
  ],
  staff_obligation_dates: [
    { obligation_identity: 's-one', obligation_kind: 'service_pay', staff_id: 7, staff_name: '月嫂甲', due_date: '2026-10-15' },
    { obligation_identity: 's-two', obligation_kind: 'adjustment', staff_id: 8, staff_name: '月嫂乙', due_date: '2026-08-15' },
    { obligation_identity: 's-empty', obligation_kind: 'service_pay', staff_id: 9, staff_name: null, due_date: null },
  ],
  claim_application_year: 2026, claim_application_month: 10,
};

const dateColumns = ['定金應繳日', '第一期應繳日', '第二期應繳日', '訂單月嫂應付日', '月嫂義務應付日', '客戶補助退還日', '補助預計申請年月'] as const;

async function dateCells() {
  const row = (await screen.findByText('115000101')).closest('tr')!;
  const headers = screen.getAllByRole('columnheader');
  const cells = within(row).getAllByRole('cell');
  expect(cells).toHaveLength(headers.length);
  return dateColumns.map(name => {
    const header = screen.getByRole('columnheader', { name: new RegExp(`^${name}`) });
    return cells[headers.indexOf(header)];
  });
}

describe('client roster accounting date columns', () => {
  beforeEach(() => {
    mocks.list.mockReset().mockResolvedValue({ items: [item], next_cursor: null });
    mocks.query.mockReset();
  });

  it('displays all seven columns and distinct source dates without recalculation', async () => {
    render(<ClientRosterPage />);
    const [deposit, first, second, staffDue, staffObligations, returns, claimMonth] = await dateCells();
    expect(deposit).toHaveTextContent('2026-06-20');
    expect(first).toHaveTextContent('2026-07-03');
    expect(second).toHaveTextContent('無值');
    expect(staffDue).toHaveTextContent('2026-09-15');
    expect(staffObligations).toHaveTextContent('月嫂甲／薪資：2026-10-15');
    expect(staffObligations).toHaveTextContent('月嫂乙／調整：2026-08-15');
    expect(staffObligations).toHaveTextContent('未設定 姓名未設定／薪資：無值');
    expect(returns).toHaveTextContent('2026-10-15');
    expect(returns).toHaveTextContent('2026-11-15');
    expect(claimMonth.textContent).toBe('2026-10');
    expect(mocks.query).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /儲存|更新|套用日期|重算/ })).not.toBeInTheDocument();
  });

  it('displays estimates separately when a historical case has no stored obligations', async () => {
    mocks.list.mockResolvedValue({ items: [{ ...item, order_status: '歷史訂單－服務完成', staff_payment_due_date: null,
      client_obligation_dates: [], staff_obligation_dates: [], claim_application_year: null, claim_application_month: null,
      estimated_self_funded_staff_due_date: '2026-09-15', estimated_subsidy_payment_date: '2026-10-15',
    }], next_cursor: null });
    render(<ClientRosterPage />);
    expect((await dateCells()).map(cell => cell.textContent)).toEqual(Array(dateColumns.length).fill('無值'));
    expect(screen.getByRole('columnheader', { name: '薪資預估日期' })).toBeVisible();
    expect(screen.getByRole('cell', { name: '2026-09-15', exact: true })).toBeVisible();
    expect(screen.queryByText('2026-10-15')).not.toBeInTheDocument();
  });

  it('does not lose list dates when the existing amount/detail query fails', async () => {
    mocks.query.mockRejectedValue(new Error('帳務詳情無法計算'));
    render(<ClientRosterPage />);
    const row = (await screen.findByText('115000101')).closest('tr')!;
    fireEvent.click(row);
    expect(await screen.findByRole('alert')).toHaveTextContent('帳務詳情無法計算');
    const [, , , staffDue] = await dateCells();
    expect(staffDue).toHaveTextContent('2026-09-15');
    expect(screen.getByRole('alert').closest('[role="dialog"]')).toHaveAccessibleName('案件 115000101 詳細資料');
  });

  it('distinguishes an older response without the new fields from stored nulls', async () => {
    const legacy = { client_id: 1, case_no: '115000101', imported_virtual_accounts: [], built_in_virtual_account: '99781699115101', name: null, phone: null, city: null, planned_start_date: null, order_status: null };
    const decoded = ClientRegistrySummarySchema.parse(legacy);
    mocks.list.mockResolvedValue({ items: [decoded], next_cursor: null });
    render(<ClientRosterPage />);
    expect((await dateCells()).map(cell => cell.textContent)).toEqual(Array(dateColumns.length).fill('未載入'));
  });

  it('decodes each obligation date without replacing nulls or hiding malformed fields', () => {
    const decoded = ClientRegistrySummarySchema.parse(item);
    expect(decoded.staff_obligation_dates).toEqual(item.staff_obligation_dates);
    expect(decoded.client_obligation_dates).toEqual(item.client_obligation_dates);
    expect(ClientRegistrySummarySchema.safeParse({ ...item, staff_payment_due_date: 'not-a-date' }).success).toBe(false);
  });
});
