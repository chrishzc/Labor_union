import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRosterPage } from '../../../../../../../pages/ClientRosterPage';

const mocks = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));

const item = {
  client_id: 7, case_no: 'CASE-001', name: '王小明', phone: '0912345678', city: '新竹市',
  baby_info: '雙胞胎', service_days: 26, requires_cooking: true,
  planned_start_date: '2026-10-01', order_status: 'matching',
};

describe('ClientRosterPage', () => {
  beforeEach(() => {
    mocks.list.mockReset();
    mocks.list.mockResolvedValue({ items: [item], next_cursor: null });
  });

  it('requests server filters, displays roster fields, and exposes no mutation controls', async () => {
    render(<ClientRosterPage />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
    expect(screen.getByText('雙胞胎')).toBeInTheDocument();
    expect(screen.getByText('26')).toBeInTheDocument();
    expect(screen.getAllByText('需要').length).toBeGreaterThan(1);
    expect(screen.queryByRole('button', { name: /儲存|更新|刪除|編輯/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('搜尋客戶名冊清單'), { target: { value: '王' } });
    fireEvent.change(screen.getByLabelText('寶寶資訊篩選'), { target: { value: 'true' } });
    fireEvent.change(screen.getByLabelText('服務天數篩選'), { target: { value: '26' } });
    fireEvent.change(screen.getByLabelText('下廚需求篩選'), { target: { value: 'false' } });
    fireEvent.click(screen.getByRole('button', { name: '套用篩選' }));

    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({
      query: '王', hasBabyInfo: true, serviceDays: 26, requiresCooking: false,
      sortBy: 'case_no', sortOrder: 'asc', limit: 100,
    }));
  });

  it('clears filters through another unfiltered server request and sorts through the server', async () => {
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: /服務天數/ }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'service_days', sortOrder: 'asc', limit: 100 })));
    fireEvent.click(screen.getByRole('button', { name: '清除篩選' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
  });
});
