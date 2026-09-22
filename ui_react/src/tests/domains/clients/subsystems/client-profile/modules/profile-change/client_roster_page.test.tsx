import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRosterPage } from '../../../../../../../pages/ClientRosterPage';

const mocks = vi.hoisted(() => ({ list: vi.fn(), query: vi.fn(), downloadOrderAccounting: vi.fn() }));
const bootstrapMocks = vi.hoisted(() => ({ status: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
const intakeMocks = vi.hoisted(() => ({ previewCompletion: vi.fn(), previewTerms: vi.fn(), applyTerms: vi.fn() }));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));
vi.mock('../../../../../../../api/case_import/case_architecture_bootstrap_client', () => ({ caseArchitectureBootstrapClient: bootstrapMocks }));
vi.mock('../../../../../../../api/orders/order_intake_completion_client', () => ({
  orderIntakeCompletionClient: intakeMocks,
  intakeBlockerMessage: (code: string) => code,
  intakeRepairErrorMessage: (error: unknown) => error instanceof Error ? error.message : '補件失敗',
}));

const item = {
  client_id: 7, case_no: 'CASE-001', imported_virtual_accounts: ['009978160011500001', '009978160011500009'], built_in_virtual_account: '99781699115001', name: '王小明', phone: '0912345678', city: '新竹市', district: '東區',
  multi_birth_count: '雙胞胎', service_days: 26, requires_cooking: true,
  planned_start_date: '2026-10-01', order_status: '洽談中',
};

describe('ClientRosterPage', () => {
  beforeEach(() => {
    mocks.list.mockReset();
    mocks.query.mockReset();
    mocks.downloadOrderAccounting.mockReset();
    Object.values(bootstrapMocks).forEach((mock) => mock.mockReset());
    Object.values(intakeMocks).forEach((mock) => mock.mockReset());
    mocks.list.mockResolvedValue({ items: [item], next_cursor: null, next_offset: null });
    mocks.query.mockResolvedValue({
      case_no: 'CASE-001',
      client: { client_id: 7, version: 2, values: { name: '王小明', gender: '女', phone: '0912345678', city: '新竹市', address: '測試路1號', residence_type: '電梯大樓', delivery_type: '自然產', baby_info: '單胞胎', notes: '主檔註記' }, field_capabilities: {} },
      beclass: { status: 'ready', record_id: 12, source_kind: 'imported', version: 3, values: { name: '王小明', email: 'client@example.com', phone: '0922222222', tel: '03-1234567', ext: '88', city: '新竹市', zip_code: '300', address: '報名地址', admin_notes: '報名註記', multi_birth_count: '雙胞胎' }, field_capabilities: {} },
      order_information: { status: 'ready', values: { dietary_habits: '不吃牛肉', vegetarian_preference: '可以', alcohol_ratio: '少量', cooking_oil_type: '苦茶油', maternal_allergy: '無', special_care_notes: '留意睡眠', meal_preferences: '少鹽', cooking_tools: '電鍋', bath_water_prep: '家屬準備', breastfeeding_method: '親餵', holiday_pricing_terms: '同意', multi_birth_count: '雙胞胎', stair_floor_fee_mode: '電梯', parking_space_provided: true, other_babies_present: false }, field_issues: {} },
      finance: { status: 'ready', code: null, values: { virtual_account: '99781699115001', service_unit_price_ntd: 450, service_hours: 208, customer_payable_total_ntd: 93600, deposit_amount_ntd: 18000, first_payment_amount_ntd: 75600, second_payment_amount_ntd: 0, received_total_ntd: 18000, customer_balance_ntd: 75600, subsidy_return_amount_ntd: null, subsidy_return_due_date: null, subsidy_return_status: null } },
      order_terms: { status: 'ready', code: null, data: { case_no: 'CASE-001', order_version: 1, scheduling_version: 1, scheduling_generation: 1, client_finance_version: 1, payroll_version: 1, service_data_locked: false, terms: { planned_start_date: '2026-10-01', service_days: 26, service_hours_per_day: 8, requires_cooking: true, floor_fee_ntd: 0, service_time: { start_time: '09:00:00', end_time: '17:00:00', end_day_offset: 0 } } }, field_capabilities: {} },
    });
    mocks.downloadOrderAccounting.mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'client-order-accounting.xlsx' });
    bootstrapMocks.status.mockResolvedValue({
      case_no: 'CASE-001', ready: false, scheduling_version: 0,
      scheduling_generation: 0, service_time_complete: true, domain_blockers: [],
      recommendation: {
        client_payment_policy_version: 'client-approved-v1', client_hourly_rate_ntd: 350,
        deposit_service_days: 0, deposit_due_date: '2026-09-01',
        first_payment_due_date: '2026-10-01', payroll_policy_version: 'approved-rates-v1',
      },
    });
    bootstrapMocks.preview.mockResolvedValue({
      case_no: 'CASE-001', order_version: 7, source_identity_status: '補助市民',
      client_payment_policy_version: 'client-approved-v1', client_hourly_rate_ntd: 350,
      deposit_service_days: 0, deposit_due_date: '2026-09-01', first_payment_due_date: '2026-10-01',
      payroll_policy_version: 'approved-rates-v1', payroll_policy_kind: 'subsidized_citizen',
      payroll_hourly_rate_ntd: 350, scheduling_version: 0, scheduling_generation: 0,
      mutation: 'create', preview_fingerprint: 'a'.repeat(64),
    });
    bootstrapMocks.apply.mockResolvedValue({
      case_no: 'CASE-001', order_version: 7, client_finance_version: 0, payroll_version: 0,
      scheduling_version: 0, scheduling_generation: 0, bootstrap_created: true,
      bootstrap_event_id: 81, preview_fingerprint: 'a'.repeat(64),
    });
    intakeMocks.previewCompletion.mockResolvedValue({
      case_no: 'CASE-001', lifecycle_version: 7, current_status: '歷史訂單－服務中',
      target_status: '歷史訂單－服務中', current_start_date: null, current_service_days: 26,
      missing_fields: ['start_date'], blockers: [], apply_allowed: false,
      preview_fingerprint: 'b'.repeat(64),
    });
    intakeMocks.previewTerms.mockResolvedValue({
      case_no: 'CASE-001', lifecycle_version: 7, before_start_date: null,
      before_service_days: 26, after_start_date: '2026-09-01', after_service_days: 26,
      changed_fields: ['start_date'], blockers: [], apply_allowed: true,
      preview_fingerprint: 'c'.repeat(64),
    });
    intakeMocks.applyTerms.mockResolvedValue({
      receipt_key: 'historical-terms-repair', case_no: 'CASE-001', lifecycle_version: 8,
      start_date: '2026-09-01', service_days: 26, changed_fields: ['start_date'],
      preview_fingerprint: 'c'.repeat(64), replayed: false,
    });
  });

  it('requests server filters, displays roster fields, and exposes no mutation controls', async () => {
    render(<ClientRosterPage />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
    expect(screen.getAllByText('雙胞胎').length).toBeGreaterThan(1);
    expect(screen.getByText('26')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '匯入虛擬帳號' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '內建虛擬帳號' })).toBeInTheDocument();
    expect(screen.getByText('009978160011500001')).toBeInTheDocument();
    expect(screen.getByText('009978160011500009')).toBeInTheDocument();
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

  it('opens every registry section in the system drawer when the order row is selected', async () => {
    render(<ClientRosterPage />);
    const orderRow = await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' });
    expect(screen.queryByRole('button', { name: /顯示全部欄位|收合全部欄位/ })).not.toBeInTheDocument();
    fireEvent.click(orderRow);
    await waitFor(() => expect(mocks.query).toHaveBeenCalledWith('CASE-001'));
    expect(screen.getByRole('dialog', { name: '案件 CASE-001 詳細資料' })).toBeInTheDocument();
    const detail = await screen.findByLabelText('CASE-001 全部唯讀欄位');
    expect(detail).toHaveTextContent('客戶主檔');
    expect(detail).toHaveTextContent('主檔註記');
    expect(detail).toHaveTextContent('BeClass 有效資料');
    expect(detail).toHaveTextContent('client@example.com');
    expect(detail).toHaveTextContent('BeClass 照護與特殊計費');
    expect(detail).toHaveTextContent('不吃牛肉');
    expect(detail).toHaveTextContent('訂單條件');
    expect(detail).toHaveTextContent('每日服務時數');
    expect(detail).toHaveTextContent('客戶帳務（唯讀）');
    expect(detail).toHaveTextContent('客戶應付總額');
    expect(detail).toHaveTextContent('450');
    expect(within(detail).queryByRole('button', { name: /儲存|更新|刪除|編輯|套用/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    expect(screen.queryByRole('dialog', { name: '案件 CASE-001 詳細資料' })).not.toBeInTheDocument();
    expect(orderRow).toHaveFocus();
  });

  it('clears filters through another unfiltered server request and sorts through the server', async () => {
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: /服務天數/ }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'service_days', sortOrder: 'asc', limit: 100 })));
    fireEvent.click(screen.getByRole('button', { name: '清除篩選' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
  });

  it('offers the existing Preview and Apply repair when Client Finance bootstrap is missing', async () => {
    const unavailable = {
      ...(await mocks.query()),
      finance: { status: 'not_ready', code: 'client_finance_bootstrap_required', values: null },
      order_terms: { status: 'not_ready', code: 'client_finance_bootstrap_required', data: null, field_capabilities: {} },
    };
    mocks.query.mockReset();
    mocks.query.mockResolvedValueOnce(unavailable).mockResolvedValue(unavailable);
    render(<ClientRosterPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));

    const repair = await screen.findByLabelText('案件初始資料修復');
    expect(repair).toHaveTextContent('這不是排班格式問題');
    fireEvent.click(await within(repair).findByRole('button', { name: '檢查初始資料補建內容' }));
    await waitFor(() => expect(bootstrapMocks.preview).toHaveBeenCalledTimes(1));
    expect(repair).toHaveTextContent('客戶時薪：350 元');
    fireEvent.click(within(repair).getByRole('button', { name: '確認建立案件初始資料' }));
    await waitFor(() => expect(bootstrapMocks.apply).toHaveBeenCalledTimes(1));
    expect(bootstrapMocks.apply.mock.calls[0][4]).toMatch(/^case-bootstrap-repair-/);
    await waitFor(() => expect(mocks.query).toHaveBeenCalledTimes(2));
  });

  it('lets an operator fill the missing contractual start date before bootstrap repair', async () => {
    const unavailable = {
      ...(await mocks.query()),
      finance: { status: 'not_ready', code: 'client_finance_bootstrap_required', values: null },
      order_terms: { status: 'not_ready', code: 'client_finance_bootstrap_required', data: null, field_capabilities: {} },
    };
    mocks.query.mockReset();
    mocks.query.mockResolvedValue(unavailable);
    const missingDate = {
      case_no: 'CASE-001', ready: false, scheduling_version: 1,
      scheduling_generation: 1, service_time_complete: true,
      domain_blockers: ['missing_start_date'], recommendation: null,
    };
    const repairReady = {
      ...missingDate, domain_blockers: [],
      recommendation: {
        client_payment_policy_version: 'client-approved-v1', client_hourly_rate_ntd: 350,
        deposit_service_days: 0, deposit_due_date: '2026-09-01',
        first_payment_due_date: '2026-09-01', payroll_policy_version: 'approved-rates-v1',
      },
    };
    bootstrapMocks.status.mockReset();
    bootstrapMocks.status.mockResolvedValueOnce(missingDate).mockResolvedValue(repairReady);

    render(<ClientRosterPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const repair = await screen.findByLabelText('案件初始資料修復');
    await waitFor(() => expect(intakeMocks.previewCompletion).toHaveBeenCalledWith('CASE-001'));
    fireEvent.change(within(repair).getByLabelText('約定服務開始日'), { target: { value: '2026-09-01' } });
    fireEvent.click(within(repair).getByRole('button', { name: '檢查約定服務資料' }));
    await waitFor(() => expect(intakeMocks.previewTerms).toHaveBeenCalledWith('CASE-001', '2026-09-01', 26));
    fireEvent.click(within(repair).getByRole('button', { name: '確認套用約定服務資料' }));
    await waitFor(() => expect(intakeMocks.applyTerms).toHaveBeenCalledTimes(1));
    expect(intakeMocks.applyTerms.mock.calls[0][3]).toMatch(/^historical-terms-repair-case-bootstrap-repair-/);
    expect(await within(repair).findByRole('button', { name: '檢查初始資料補建內容' })).toBeInTheDocument();
  });

  it('moves between pages for any sort and exposes the current page above the table', async () => {
    mocks.list
      .mockResolvedValueOnce({ items: [item], next_cursor: 'CASE-001', next_offset: 100 })
      .mockResolvedValueOnce({ items: [{ ...item, case_no: 'CASE-101' }], next_cursor: null, next_offset: null })
      .mockResolvedValueOnce({ items: [item], next_cursor: 'CASE-001', next_offset: 100 });
    render(<ClientRosterPage />);

    const pagination = await screen.findByRole('navigation', { name: '客戶名冊分頁' });
    expect(within(pagination).getByText('第 1 頁', { exact: false })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100, limit: 100 })));
    expect(await screen.findByText('CASE-101')).toBeInTheDocument();
    expect(within(pagination).getByText('第 2 頁', { exact: false })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '上一頁' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.not.objectContaining({ offset: expect.anything() })));
    expect(await screen.findByText('CASE-001')).toBeInTheDocument();
  });

  it('downloads order accounting with the currently applied roster filters', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:order-accounting');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');

    fireEvent.change(screen.getByLabelText('案件／訂單狀態篩選'), { target: { value: '訂單成立' } });
    fireEvent.click(screen.getByRole('button', { name: '套用篩選' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ orderStatus: '訂單成立' })));
    fireEvent.click(screen.getByRole('button', { name: '匯出訂單帳務' }));

    await waitFor(() => expect(mocks.downloadOrderAccounting).toHaveBeenCalledWith({
      query: '', multiBirthCount: undefined, orderStatus: '訂單成立', requiresCooking: undefined,
      sortBy: 'case_no', sortOrder: 'asc', limit: 100,
    }));
    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:order-accounting');
    expect(await screen.findByRole('status')).toHaveTextContent('訂單帳務 Excel 已下載。');
  });
});
