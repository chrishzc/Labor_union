import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRosterPage } from '../../../../../../../pages/ClientRosterPage';

const mocks = vi.hoisted(() => ({ list: vi.fn(), query: vi.fn() }));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));

const item = {
  client_id: 7, case_no: 'CASE-001', virtual_account: '99781699115001', name: '王小明', phone: '0912345678', city: '新竹市', district: '東區',
  multi_birth_count: '雙胞胎', service_days: 26, requires_cooking: true,
  planned_start_date: '2026-10-01', order_status: '洽談中',
};

describe('ClientRosterPage', () => {
  beforeEach(() => {
    mocks.list.mockReset();
    mocks.query.mockReset();
    mocks.list.mockResolvedValue({ items: [item], next_cursor: null });
    mocks.query.mockResolvedValue({
      case_no: 'CASE-001',
      client: { client_id: 7, version: 2, values: { name: '王小明', gender: '女', phone: '0912345678', city: '新竹市', address: '測試路1號', residence_type: '電梯大樓', delivery_type: '自然產', baby_info: '單胞胎', notes: '主檔註記' }, field_capabilities: {} },
      beclass: { status: 'ready', record_id: 12, source_kind: 'imported', version: 3, values: { name: '王小明', email: 'client@example.com', phone: '0922222222', tel: '03-1234567', ext: '88', city: '新竹市', zip_code: '300', address: '報名地址', admin_notes: '報名註記', multi_birth_count: '雙胞胎' }, field_capabilities: {} },
      order_information: { status: 'ready', values: { dietary_habits: '不吃牛肉', vegetarian_preference: '可以', alcohol_ratio: '少量', cooking_oil_type: '苦茶油', maternal_allergy: '無', special_care_notes: '留意睡眠', meal_preferences: '少鹽', cooking_tools: '電鍋', bath_water_prep: '家屬準備', breastfeeding_method: '親餵', holiday_pricing_terms: '同意', multi_birth_count: '雙胞胎', stair_floor_fee_mode: '電梯', parking_space_provided: true, other_babies_present: false }, field_issues: {} },
      order_terms: { status: 'ready', code: null, data: { case_no: 'CASE-001', order_version: 1, scheduling_version: 1, scheduling_generation: 1, client_finance_version: 1, payroll_version: 1, service_data_locked: false, terms: { planned_start_date: '2026-10-01', service_days: 26, service_hours_per_day: 8, requires_cooking: true, floor_fee_ntd: 0, service_time: { start_time: '09:00:00', end_time: '17:00:00', end_day_offset: 0 } } }, field_capabilities: {} },
    });
  });

  it('requests server filters, displays roster fields, and exposes no mutation controls', async () => {
    render(<ClientRosterPage />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
    expect(screen.getAllByText('雙胞胎').length).toBeGreaterThan(1);
    expect(screen.getByText('26')).toBeInTheDocument();
    expect(screen.getByText('99781699115001')).toBeInTheDocument();
    expect(screen.getByText('東區')).toBeInTheDocument();
    expect(screen.queryByText('新竹市')).not.toBeInTheDocument();
    expect(screen.getAllByText('需要').length).toBeGreaterThan(1);
    expect(screen.queryByRole('button', { name: /儲存|更新|刪除|編輯/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('搜尋客戶名冊清單'), { target: { value: '王' } });
    fireEvent.change(screen.getByLabelText('BeClass 胎數篩選'), { target: { value: '雙胞胎' } });
    fireEvent.change(screen.getByLabelText('案件／訂單狀態篩選'), { target: { value: '洽談中' } });
    fireEvent.change(screen.getByLabelText('下廚需求篩選'), { target: { value: 'false' } });
    fireEvent.click(screen.getByRole('button', { name: '套用篩選' }));

    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({
      query: '王', multiBirthCount: '雙胞胎', orderStatus: '洽談中', requiresCooking: false,
      sortBy: 'case_no', sortOrder: 'asc', limit: 100,
    }));
  });

  it('expands every registry section as read-only fields for the selected order', async () => {
    render(<ClientRosterPage />);
    fireEvent.click(await screen.findByRole('button', { name: '顯示全部欄位' }));
    await waitFor(() => expect(mocks.query).toHaveBeenCalledWith('CASE-001'));
    const detail = await screen.findByLabelText('CASE-001 全部唯讀欄位');
    expect(detail).toHaveTextContent('客戶主檔');
    expect(detail).toHaveTextContent('主檔註記');
    expect(detail).toHaveTextContent('BeClass 有效資料');
    expect(detail).toHaveTextContent('client@example.com');
    expect(detail).toHaveTextContent('BeClass 照護與特殊計費');
    expect(detail).toHaveTextContent('不吃牛肉');
    expect(detail).toHaveTextContent('訂單條件');
    expect(detail).toHaveTextContent('每日服務時數');
    expect(within(detail).queryByRole('button', { name: /儲存|更新|刪除|編輯|套用/ })).not.toBeInTheDocument();
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
