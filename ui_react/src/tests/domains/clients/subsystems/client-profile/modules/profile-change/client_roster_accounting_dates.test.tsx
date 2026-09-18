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

async function cells() {
  const row = (await screen.findByText('115000101')).closest('tr')!;
  return within(row).getAllByRole('cell');
}

describe('client roster accounting date columns', () => {
  beforeEach(() => {
    mocks.list.mockReset().mockResolvedValue({ items: [item], next_cursor: null });
    mocks.query.mockReset();
  });

  it('displays all seven columns and distinct source dates without recalculation', async () => {
    render(<ClientRosterPage />);
    const row = await cells();
    for (const name of ['訂金應繳日', '第一期應繳日', '第二期應繳日', '訂單月嫂應付日', '月嫂義務應付日', '客戶補助退還日', '補助預計申請年月']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument();
    }
    expect(row).toHaveLength(18);
    expect(row[11]).toHaveTextContent('2026-06-20');
    expect(row[12]).toHaveTextContent('2026-07-03');
    expect(row[13]).toHaveTextContent('無值');
    expect(row[14]).toHaveTextContent('2026-09-15');
    expect(row[15]).toHaveTextContent('月嫂甲／薪資：2026-10-15');
    expect(row[15]).toHaveTextContent('月嫂乙／調整：2026-08-15');
    expect(row[15]).toHaveTextContent('月嫂 #9／薪資：無值');
    expect(row[16]).toHaveTextContent('2026-10-15');
    expect(row[16]).toHaveTextContent('2026-11-15');
    expect(row[17].textContent).toBe('2026-10');
    expect(mocks.query).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /儲存|更新|套用日期|重算/ })).not.toBeInTheDocument();
  });

  it('keeps a historical case with no stored obligations and does not invent dates', async () => {
    mocks.list.mockResolvedValue({ items: [{ ...item, order_status: '歷史訂單－服務完成', staff_payment_due_date: null,
      client_obligation_dates: [], staff_obligation_dates: [], claim_application_year: null, claim_application_month: null,
    }], next_cursor: null });
    render(<ClientRosterPage />);
    expect((await cells()).slice(11, 18).map((cell) => cell.textContent)).toEqual(Array(7).fill('無值'));
  });

  it('does not lose list dates when the existing amount/detail query fails', async () => {
    mocks.query.mockRejectedValue(new Error('帳務詳情無法計算'));
    render(<ClientRosterPage />);
    const row = (await screen.findByText('115000101')).closest('tr')!;
    fireEvent.click(row);
    expect(await screen.findByRole('alert')).toHaveTextContent('帳務詳情無法計算');
    expect((await cells())[14]).toHaveTextContent('2026-09-15');
    expect(screen.getByRole('alert').closest('[role="dialog"]')).toHaveAccessibleName('案件 115000101 詳細資料');
  });

  it('distinguishes an older response without the new fields from stored nulls', async () => {
    const legacy = { client_id: 1, case_no: '115000101', imported_virtual_accounts: [], built_in_virtual_account: '99781699115101', name: null, phone: null, city: null, planned_start_date: null, order_status: null };
    const decoded = ClientRegistrySummarySchema.parse(legacy);
    mocks.list.mockResolvedValue({ items: [decoded], next_cursor: null });
    render(<ClientRosterPage />);
    expect((await cells()).slice(11, 18).map((cell) => cell.textContent)).toEqual(Array(7).fill('未載入'));
  });

  it('decodes each obligation date without replacing nulls or hiding malformed fields', () => {
    const decoded = ClientRegistrySummarySchema.parse(item);
    expect(decoded.staff_obligation_dates).toEqual(item.staff_obligation_dates);
    expect(decoded.client_obligation_dates).toEqual(item.client_obligation_dates);
    expect(ClientRegistrySummarySchema.safeParse({ ...item, staff_payment_due_date: 'not-a-date' }).success).toBe(false);
  });
});
