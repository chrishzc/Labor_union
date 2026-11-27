/**
 * File: client_roster_page.test.tsx
 * Description: 驗證客戶名冊分頁查詢、欄位篩選排序、共用 Excel 式欄寬／顯示／凍結排版及詳情抽屜互動。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';
import { ClientRosterPage } from '../../../../../../../pages/ClientRosterPage';
import { importFieldIssueHref, loadCurrentImportFieldIssuesForCases, type ImportFieldIssue } from '../../../../../../../api/case_import/import_field_issues';
import { orderCancellationClient, type OrderCancellationQuery } from '../../../../../../../api/orders/order_cancellation_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { orderTermsMutationClient, type OrderTermsQuery } from '../../../../../../../api/orders/order_terms_mutation_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
const linkedOrderQuery = vi.hoisted(() => vi.fn());
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: {
  getAssignmentPlan: vi.fn().mockResolvedValue({ case_no: 'CASE-001', assignments: [] }),
  getOrderDetail: linkedOrderQuery,
} }));

const mocks = vi.hoisted(() => ({ list: vi.fn(), query: vi.fn(), history: vi.fn(), filterOptions: vi.fn(), downloadOrderAccounting: vi.fn(), downloadCaseInspection: vi.fn() }));
const bootstrapMocks = vi.hoisted(() => ({ status: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
const intakeMocks = vi.hoisted(() => ({ previewCompletion: vi.fn(), previewTerms: vi.fn(), applyTerms: vi.fn() }));
const accountMocks = vi.hoisted(() => ({ query: vi.fn(), apply: vi.fn() }));
vi.mock('../../../../../../../api/client_finance/case_virtual_account_client', () => ({ caseVirtualAccountClient: accountMocks }));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));
vi.mock('../../../../../../../api/case_import/import_field_issues', async (original) => ({
  ...await original<typeof import('../../../../../../../api/case_import/import_field_issues')>(),
  loadCurrentImportFieldIssuesForCases: vi.fn().mockResolvedValue([]),
}));
vi.mock('../../../../../../../api/case_import/case_architecture_bootstrap_client', () => ({ caseArchitectureBootstrapClient: bootstrapMocks }));
vi.mock('../../../../../../../api/orders/order_intake_completion_client', () => ({
  orderIntakeCompletionClient: intakeMocks,
  intakeBlockerMessage: (code: string) => code,
  intakeRepairErrorMessage: (error: unknown) => error instanceof Error ? error.message : '補件失敗',
}));

const item = {
  client_id: 7, case_no: 'CASE-001', imported_virtual_accounts: ['009978160011500001', '009978160011500009'], built_in_virtual_account: '99781699115001', name: '王小明', phone: '0912345678', city: '新竹市', district: '東區',
  multi_birth_count: '雙胞胎', service_days: 26, service_type: '週休2日', requires_cooking: true,
  planned_start_date: '2026-10-01', order_status: '洽談中',
};

const orderTerms: OrderTermsQuery = {
  case_no: item.case_no, order_version: 1, scheduling_version: 1, scheduling_generation: 1,
  client_finance_version: 1, payroll_version: 1, service_data_locked: false,
  terms: {
    planned_start_date: '2026-10-01', service_days: 26, service_hours_per_day: 8,
    requires_cooking: true, floor_fee_ntd: 0,
    service_time: { start_time: '09:00:00', end_time: '17:00:00', end_day_offset: 0 },
  },
};

const cookingIssue: ImportFieldIssue = {
  source: 'client_beclass', owner: 'order_terms', field: 'requires_cooking', source_field: '煮食需求',
  code: 'service_data_locked', message: '案件服務資料已鎖定，無法補寫煮食需求。',
};

describe('ClientRosterPage', () => {
  let termsQuery: MockInstance<typeof orderTermsMutationClient.query>;

  beforeEach(() => {
    window.localStorage.clear();
    linkedOrderQuery.mockReset().mockResolvedValue({ case_no: item.case_no, order_status: '訂單取消' });
    termsQuery = vi.spyOn(orderTermsMutationClient, 'query').mockResolvedValue(orderTerms);
    mocks.list.mockReset();
    mocks.query.mockReset();
    mocks.history.mockReset().mockResolvedValue([]);
    mocks.filterOptions.mockReset();
    mocks.downloadOrderAccounting.mockReset();
    mocks.downloadCaseInspection.mockReset();
    Object.values(bootstrapMocks).forEach((mock) => mock.mockReset());
    Object.values(intakeMocks).forEach((mock) => mock.mockReset());
    Object.values(accountMocks).forEach((mock) => mock.mockReset());
    accountMocks.query.mockResolvedValue({ case_no: 'CASE-001', imported_virtual_accounts: [], built_in_virtual_account: null, mapping_ids: [] });
    mocks.list.mockResolvedValue({ items: [item], next_cursor: null, next_offset: null });
    mocks.filterOptions.mockImplementation(async (field: string) => ({ values: field === 'requires_cooking' ? ['true', 'false', null] : field === 'multi_birth_count' ? ['單胞胎', '雙胞胎', null] : ['洽談中', '訂單成立', '服務中', null], next_offset: null }));
    mocks.query.mockResolvedValue({
      case_no: 'CASE-001', service_type: '週休2日',
      client: { client_id: 7, version: 2, values: { name: '王小明', gender: '女', phone: '0912345678', email: 'hcm@example.com', city: '新竹市', address: '測試路1號', residence_type: '電梯大樓', delivery_type: '自然產', baby_info: '單胞胎', notes: '主檔註記' }, field_capabilities: {} },
      beclass: { status: 'ready', record_id: 12, source_kind: 'imported', version: 3, values: { name: '王小明', email: 'client@example.com', phone: '0922222222', tel: '03-1234567', ext: '88', city: '新竹市', zip_code: '300', address: '報名地址', admin_notes: '報名註記', multi_birth_count: '雙胞胎' }, field_capabilities: {} },
      order_information: { status: 'ready', values: { dietary_habits: '不吃牛肉', vegetarian_preference: '可以', alcohol_ratio: '少量', cooking_oil_type: '苦茶油', maternal_allergy: '無', special_care_notes: '留意睡眠', meal_preferences: '少鹽', cooking_tools: '電鍋', bath_water_prep: '家屬準備', breastfeeding_method: '親餵', multi_birth_count: '雙胞胎', stair_floor_fee_mode: '電梯', parking_space_provided: true, other_babies_present: false }, field_issues: {} },
      finance: { status: 'ready', code: null, values: { virtual_account: '99781699115001', service_unit_price_ntd: 450, service_hours: 208, customer_payable_total_ntd: 93600, deposit_amount_ntd: 18000, first_payment_amount_ntd: 75600, second_payment_amount_ntd: 0, received_total_ntd: 18000, customer_balance_ntd: 75600, subsidy_return_amount_ntd: null, subsidy_return_due_date: null, subsidy_return_status: null } },
      order_terms: { status: 'ready', code: null, data: orderTerms, field_capabilities: {} },
    });
    mocks.downloadOrderAccounting.mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'client-order-accounting.xlsx' });
    mocks.downloadCaseInspection.mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'client-case-inspection.xlsx' });
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

  afterEach(() => { termsQuery.mockRestore(); });

  it('顯示 BeClass 煮食鎖定警示在名冊的下廚料理欄', async () => {
    mocks.list.mockResolvedValue({ items: [{ ...item, requires_cooking: null }], next_cursor: null, next_offset: null });
    vi.mocked(loadCurrentImportFieldIssuesForCases).mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ case_no: item.case_no, issues: [cookingIssue] }]);
    render(<ClientRosterPage />);
    const warning = await screen.findByText(cookingIssue.message);
    expect(warning.closest('td')).toHaveTextContent('未登錄');
  });

  it('服務資料已鎖定時仍可獨立補填 BeClass 下廚料理需求', async () => {
    const detail = await mocks.query();
    const lockedTerms = { ...orderTerms, service_data_locked: true, terms: { ...orderTerms.terms, requires_cooking: null } };
    termsQuery.mockResolvedValue(lockedTerms);
    mocks.query.mockResolvedValue({
      ...detail, order_terms: { ...detail.order_terms, data: lockedTerms }, import_field_issues: [cookingIssue],
    });
    const target = new URLSearchParams(importFieldIssueHref(item.case_no, cookingIssue).split('?')[1]);
    render(<ClientRosterPage initialCaseNo={item.case_no} focusField={target.get('field') ?? undefined} />);
    const cooking = await screen.findByRole('combobox', { name: '下廚料理需求' });
    expect(cooking).toBeEnabled();
    expect(cooking).toHaveAttribute('aria-invalid', 'true');
    expect(cooking).toHaveAccessibleDescription(cookingIssue.message);
    expect(screen.getByLabelText('服務天數')).not.toHaveAttribute('aria-invalid');
    expect(screen.getByLabelText('服務天數')).toBeDisabled();
    fireEvent.change(cooking, { target: { value: 'yes' } });
    expect(cooking).toHaveValue('yes');
    expect(screen.getByLabelText('服務天數')).toBeDisabled();
  });

  it('opens the formal cancellation for a non-root operator from the selected roster case', async () => {
    const user = vi.spyOn(sessionClient, 'getUser').mockReturnValue({
      id: 7, username: 'operator', display_name: '測試人員', role: 'system_admin',
      is_root: false, access_control_version: 1, capabilities: ['system.administration'],
    });
    const query = vi.spyOn(orderCancellationClient, 'query').mockResolvedValue({
      case_no: item.case_no, lifecycle_status: '洽談中', actual_start_date: null, contracted_service_days: 26,
      service_hours_per_day: 8, service_started: false, historical_mid_service_confirmation_available: false,
      service_data_locked: false, order_version: 1, scheduling_version: 1, scheduling_generation: 1,
      client_finance_version: 1, payroll_version: 1, confirmed_service_days: [], caregiver_options: [],
    });
    try {
      render(<ClientRosterPage initialCaseNo={item.case_no} />);
      fireEvent.click(await screen.findByRole('button', { name: '取消訂單' }));
      expect(await screen.findByRole('button', { name: '預覽取消帳務' })).toBeVisible();
      expect(query).toHaveBeenCalledWith(item.case_no, expect.any(AbortSignal));
      expect(screen.queryByRole('button', { name: '刪除此案件' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: '返回案件詳細資料' }));
      expect(await screen.findByLabelText('CASE-001 案件資料編輯')).toBeVisible();
    } finally {
      query.mockRestore();
      user.mockRestore();
    }
  });

  it.each([true, false])('opens controlled reopen from cancelled roster detail when the row is listed: %s', async (listed) => {
    const user = vi.spyOn(sessionClient, 'getUser').mockReturnValue({
      id: 7, username: 'operator', display_name: '測試人員', role: 'system_admin',
      is_root: false, access_control_version: 1, capabilities: ['system.administration'],
    });
    mocks.list.mockResolvedValue({ items: listed ? [{ ...item, order_status: '訂單取消' }] : [], next_cursor: null, next_offset: null });
    try {
      render(<ClientRosterPage initialCaseNo={item.case_no} />);
      fireEvent.click(await screen.findByRole('button', { name: '重開訂單' }));
      const panel = await screen.findByRole('region', { name: '案件 CASE-001 重開取消案件' });
      expect(within(panel).getByRole('button', { name: '重開訂單' })).toBeVisible();
      expect(screen.queryByRole('button', { name: '取消訂單' })).not.toBeInTheDocument();
    } finally {
      user.mockRestore();
    }
  });

  it.each([true, false])('更正歷史零服務後回讀並更新案件詳情，是否在本頁：%s', async (listed) => {
    orderMutationFlowStore.clearAll();
    const user = vi.spyOn(sessionClient, 'getUser').mockReturnValue({
      id: 7, username: 'operator', display_name: '測試人員', role: 'system_admin',
      is_root: false, access_control_version: 1, capabilities: ['system.administration'],
    });
    const facts: OrderCancellationQuery = {
      case_no: item.case_no, lifecycle_status: '訂單取消', actual_start_date: null, contracted_service_days: 26,
      service_hours_per_day: 8, service_started: false, historical_mid_service_confirmation_available: false,
      service_data_locked: false, order_version: 1, scheduling_version: null, scheduling_generation: null,
      client_finance_version: null, payroll_version: null, confirmed_service_days: [], caregiver_options: [],
      historical_unserved_correction: {
        blockers: [], review_codes: ['historical_unserved_not_historical', 'historical_unserved_establishment_evidence_missing'],
        establishment_lifecycle_event_ids: [], establishment_adoption_receipt_ids: [],
        establishment_owner_status: null, historical_adoption_receipt_ids: [], historical_absence_event_ids: [],
        actual_service_evidence: [], actual_start_date: null, actual_end_date: null, prior_fee_ntd: 0,
        prior_fee_reason: '', net_cash_received_ntd: 0, prior_cancellation_event_id: 3,
        client_obligations: [], payroll_obligations: [],
      },
    };
    const fingerprint = 'c'.repeat(64);
    const query = vi.spyOn(orderCancellationClient, 'query').mockResolvedValueOnce(facts).mockResolvedValue({
      ...facts, lifecycle_status: '成立後未服務', order_version: 2, historical_unserved_correction: null,
    });
    const preview = vi.spyOn(orderCancellationClient, 'preview').mockResolvedValue({
      cancellation_date: '2026-10-01', actual_start_date: null, actual_end_date: null, confirmed_service_days: [],
      official_service_day_count: 0, official_service_hours: 0, order_version: 1, scheduling_version: null,
      scheduling_generation: null, client_finance_version: null, payroll_version: null,
      scheduling: null, client_finance_impact: null, payroll_impact: null,
      lifecycle_impact: { case_no: item.case_no, before_status: '訂單取消', after_status: '成立後未服務',
        actual_end_date: null, cancellation_effective: true, fingerprint },
      preview_fingerprint: fingerprint,
    });
    const apply = vi.spyOn(orderCancellationClient, 'apply').mockResolvedValue({
      case_no: item.case_no, lifecycle_status: '成立後未服務', order_version: 2, scheduling_version: null,
      scheduling_generation: null, client_finance_version: null, payroll_version: null, actual_end_date: null,
      official_service_day_count: 0, official_service_hours: 0, cancelled_assignment_ids: [],
      created_assignment_keys: [], preview_fingerprint: fingerprint,
    });
    const page = { items: listed ? [{ ...item, order_status: '訂單取消' }] : [], next_cursor: null, next_offset: null };
    mocks.list.mockResolvedValue(page);
    try {
      render(<ClientRosterPage initialCaseNo={listed ? undefined : item.case_no} />);
      const rosterRow = listed ? await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }) : null;
      if (rosterRow) fireEvent.click(rosterRow);
      const dialog = await screen.findByRole('dialog', { name: '案件 CASE-001 詳細資料' });
      const drawer = within(dialog);
      fireEvent.click(await drawer.findByRole('button', { name: '更正歷史零服務' }));
      expect(query).toHaveBeenCalledWith(item.case_no, expect.any(AbortSignal));
      expect(drawer.getByRole('heading', { name: '歷史零服務更正' })).toBeVisible();
      const previewButton = await drawer.findByRole('button', { name: '預覽零服務更正' });
      expect(previewButton).toBeDisabled();
      fireEvent.click(drawer.getByRole('checkbox', { name: '我確認將本案更正為成立後未服務' }));
      expect(previewButton).toBeEnabled();
      fireEvent.click(previewButton);
      expect(preview).toHaveBeenCalledWith(item.case_no, [], expect.any(AbortSignal), {
        historical_unserved_correction: { reason: '', evidence_source: '', confirmed_actual_service_day_count: 0 },
      });
      expect(apply).not.toHaveBeenCalled();
      const detail = await mocks.query();
      mocks.query.mockResolvedValue({ ...detail });
      mocks.list.mockResolvedValue({ ...page, items: listed ? [{ ...item, order_status: '成立後未服務' }] : [] });
      linkedOrderQuery.mockResolvedValue({ case_no: item.case_no, order_status: '成立後未服務' });
      const confirmButton = await drawer.findByRole('button', { name: '確認更正為成立後未服務' });
      const orderReadsBeforeApply = linkedOrderQuery.mock.calls.length;
      fireEvent.click(confirmButton);
      await drawer.findByText('本案已完成更正，無須再次操作。');
      expect(query).toHaveBeenCalledTimes(2);
      const returnButton = drawer.getByRole('button', { name: '返回案件詳細資料' });
      await waitFor(() => expect(returnButton).toBeEnabled());
      expect(mocks.list).toHaveBeenCalledTimes(2);
      if (rosterRow) {
        expect(within(rosterRow).getByText('成立後未服務')).toBeVisible();
      } else {
        await waitFor(() => expect(linkedOrderQuery.mock.calls.slice(orderReadsBeforeApply)).toContainEqual([
          item.case_no, { signal: expect.any(AbortSignal) },
        ]));
      }
      fireEvent.click(returnButton);
      expect(await drawer.findByLabelText('CASE-001 案件資料編輯')).toBeVisible();
      await waitFor(() => {
        expect(drawer.queryByRole('button', { name: '更正歷史零服務' })).not.toBeInTheDocument();
        expect(drawer.queryByRole('button', { name: '取消訂單' })).not.toBeInTheDocument();
      });
      expect(drawer.queryByRole('heading', { name: '歷史零服務更正' })).not.toBeInTheDocument();
    } finally {
      orderMutationFlowStore.clearAll();
      apply.mockRestore();
      preview.mockRestore();
      query.mockRestore();
      user.mockRestore();
    }
  });

  it.each([
    { status: '洽談中', canManage: true },
    { status: '歷史訂單－服務中', canManage: true },
    { status: '成立後未服務', canManage: true },
    { status: null, canManage: true },
    { status: '訂單取消', canManage: false },
  ])('狀態 $status 且管理權限為 $canManage 時隱藏歷史更正', async ({ status, canManage }) => {
    const user = vi.spyOn(sessionClient, 'getUser').mockReturnValue({
      id: 7, username: 'operator', display_name: '測試人員', role: 'system_admin', is_root: false,
      access_control_version: 1, capabilities: canManage ? ['system.administration'] : [],
    });
    mocks.list.mockResolvedValue({ items: [{ ...item, order_status: status }], next_cursor: null, next_offset: null });
    try {
      render(<ClientRosterPage />);
      fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
      const drawer = within(await screen.findByRole('dialog', { name: '案件 CASE-001 詳細資料' }));
      expect(await drawer.findByLabelText('CASE-001 案件資料編輯')).toBeVisible();
      expect(drawer.queryByRole('button', { name: '更正歷史零服務' })).not.toBeInTheDocument();
    } finally {
      user.mockRestore();
    }
  });

  it('requests server filters, displays roster fields, and exposes no mutation controls', async () => {
    mocks.list.mockResolvedValueOnce({
      items: [
        item,
        { ...item, case_no: 'CASE-002', imported_virtual_accounts: [], built_in_virtual_account: '99781699115002', name: null, service_days: null, service_type: null, district: null, multi_birth_count: null, requires_cooking: null },
        { ...item, case_no: 'CASE-003', imported_virtual_accounts: [], built_in_virtual_account: null, name: null, service_days: null, service_type: null, district: null, multi_birth_count: null, requires_cooking: null },
      ],
      next_cursor: null, next_offset: null,
    });
    render(<ClientRosterPage />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
    expect(screen.getByText('雙胞胎')).toBeInTheDocument();
    expect(screen.getByText('26')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '服務方式' })).toBeInTheDocument();
    expect(screen.getByText('週休2日')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '虛擬帳號' })).toBeInTheDocument();
    expect(screen.getByText('009978160011500001')).toBeInTheDocument();
    expect(screen.getByText('009978160011500009')).toBeInTheDocument();
    expect(screen.queryByText('99781699115001')).not.toBeInTheDocument();
    expect(screen.getByText('99781699115002')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: '開啟案件 CASE-003 詳細資料' })).getAllByRole('cell')[1]).toHaveTextContent(/^—$/);
    expect(screen.getByText('東區')).toBeInTheDocument();
    expect(screen.queryByText('新竹市')).not.toBeInTheDocument();
    expect(screen.getByText('需要')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /儲存|更新|刪除|編輯/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('搜尋客戶名冊清單'), { target: { value: '王' } });
    fireEvent.click(screen.getByRole('button', { name: '搜尋' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ query: '王' })));
    for (const [label, option] of [['BeClass 胎數', '雙胞胎'], ['案件／訂單狀態', '洽談中'], ['下廚需求', '不需要']]) {
      fireEvent.click(screen.getByRole('button', { name: `${label}篩選` }));
      const dialog = screen.getByRole('dialog', { name: `${label}篩選選項` });
      await within(dialog).findByRole('checkbox', { name: option });
      fireEvent.click(within(dialog).getByRole('button', { name: '取消全選' }));
      fireEvent.click(within(dialog).getByRole('checkbox', { name: option }));
      fireEvent.click(within(dialog).getByRole('button', { name: '確定' }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      await waitFor(() => expect(screen.getByRole('button', { name: `${label}篩選（已套用）` })).toBeEnabled());
    }

    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({
      query: '王', columnFilters: [
        { field: 'multi_birth_count', operator: 'in', values: ['雙胞胎'] },
        { field: 'order_status', operator: 'in', values: ['洽談中'] },
        { field: 'requires_cooking', operator: 'in', values: ['false'] },
      ],
      sortBy: 'case_no', sortOrder: 'asc', limit: 100,
    }));
  });

  it('keeps the drawer locked until the saved account and roster list both refresh', async () => {
    const account = '99781699114999';
    accountMocks.apply.mockResolvedValue({ case_no: 'CASE-001', before: [], virtual_account: account });
    let finishList!: (value: unknown) => void;
    const listReadback = new Promise(resolve => { finishList = resolve; });
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const panel = await screen.findByRole('region', { name: '虛擬帳號設定' });
    await within(panel).findByLabelText('匯入虛擬帳號');
    fireEvent.change(within(panel).getByLabelText('匯入虛擬帳號'), { target: { value: account } });
    expect(within(panel).queryByLabelText('虛擬帳號修改原因')).not.toBeInTheDocument();
    accountMocks.query.mockResolvedValue({ case_no: 'CASE-001', imported_virtual_accounts: [account], built_in_virtual_account: null, mapping_ids: [1] });
    mocks.list.mockReturnValueOnce(listReadback);
    fireEvent.click(within(panel).getByRole('button', { name: /^儲存虛擬帳號$/ }));
    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    await act(async () => finishList({ items: [{ ...item, imported_virtual_accounts: [account] }], next_cursor: null, next_offset: null }));
    await within(panel).findByText('虛擬帳號已儲存，名冊資料已更新。');
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).not.toBeDisabled();
    expect(within(screen.getByRole('table')).getByText(account)).toBeInTheDocument();
  });

  it.each(['東區', '北區', '香山區', '竹北市'])('leaves an unrecognized district blank even when city is %s', async (city) => {
    mocks.list.mockResolvedValue({ items: [{ ...item, city, district: null }], next_cursor: null, next_offset: null });
    render(<ClientRosterPage />);
    const row = await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' });
    const headers = screen.getAllByRole('columnheader');
    const districtIndex = headers.findIndex((header) => header.textContent?.startsWith('行政區'));
    expect(districtIndex).toBeGreaterThanOrEqual(0);
    expect(within(row).getAllByRole('cell')[districtIndex]).toBeEmptyDOMElement();
  });

  it.each(['東區', '北區', '香山區', '竹北市'])('displays the district supplied by the address projection: %s', async (district) => {
    mocks.list.mockResolvedValue({ items: [{ ...item, city: '其他地區', district }], next_cursor: null, next_offset: null });
    render(<ClientRosterPage />);
    const row = await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' });
    expect(within(row).getByRole('cell', { name: district })).toBeInTheDocument();
  });

  it('opens every registry section in the system drawer when the order row is selected', async () => {
    render(<ClientRosterPage />);
    const orderRow = await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' });
    expect(screen.queryByRole('button', { name: /顯示全部欄位|收合全部欄位/ })).not.toBeInTheDocument();
    fireEvent.click(orderRow);
    await waitFor(() => expect(mocks.query).toHaveBeenCalledWith('CASE-001', undefined, true));
    expect(screen.getByRole('dialog', { name: '案件 CASE-001 詳細資料' })).toBeInTheDocument();
    const detail = await screen.findByLabelText('CASE-001 案件資料編輯');
    expect(detail).toHaveTextContent('客戶主檔');
    expect(within(detail).getByLabelText('客戶備註（主檔）')).toHaveValue('主檔註記');
    const profile = within(detail).getByRole('region', { name: '客戶主檔' });
    expect(within(profile).getByLabelText('Email', { exact: true })).toHaveValue('hcm@example.com');
    expect(within(detail).getAllByLabelText('Email', { exact: true })).toHaveLength(1);
    expect(detail).toHaveTextContent('報名問卷資料（BeClass）');
    const registration = within(detail).getByRole('region', { name: '報名問卷資料（BeClass）' });
    expect(within(registration).queryByLabelText(/Email/)).not.toBeInTheDocument();
    expect(detail).toHaveTextContent('BeClass 照護與特殊計費');
    expect(within(detail).getByLabelText('飲食習慣與中藥接受度')).toHaveValue('不吃牛肉');
    expect(detail).toHaveTextContent('訂單條件');
    expect(await within(detail).findByLabelText('每日服務時數')).toHaveValue(8);
    expect(detail).toHaveTextContent('服務方式');
    expect(detail).toHaveTextContent('週休2日');
    expect(within(detail).getByRole('heading', { name: '客戶帳務' })).toBeVisible();
    expect(detail).toHaveTextContent('客戶應付總額');
    expect(detail).toHaveTextContent('450');
    expect(within(detail).getAllByRole('button', { name: '儲存' })).toHaveLength(3);
    expect(within(detail).queryByRole('button', { name: '預覽變更' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    expect(screen.queryByRole('dialog', { name: '案件 CASE-001 詳細資料' })).not.toBeInTheDocument();
    expect(orderRow).toHaveFocus();
  });

  it.each([true, false])('only shows the full refund account when the detail grants visibility (%s)', async (visible) => {
    const fixture = await mocks.query();
    mocks.query.mockResolvedValue({
      ...fixture,
      beclass: {
        ...fixture.beclass, full_refund_account_visible: visible,
        values: { ...fixture.beclass.values, refund_account_no: visible ? '000000009876' : '****9876' },
      },
    });
    render(<ClientRosterPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const input = await screen.findByLabelText('退款帳號（文字，保留前導零）');
    expect(input).toHaveAttribute('type', visible ? 'text' : 'password');
    expect(input).toHaveValue(visible ? '000000009876' : '****9876');
    expect(screen.queryByText(/退款帳號顯示末四碼/)).toBe(visible ? null : screen.getByText(/退款帳號顯示末四碼/));
  });

  it('clears filters through another unfiltered server request and sorts through the server', async () => {
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: '服務天數' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'service_days', sortOrder: 'asc', limit: 100 })));
    fireEvent.click(screen.getByRole('button', { name: '清除全部篩選' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'case_no', sortOrder: 'asc', limit: 100 })));
  });

  it('creates missing Client Finance bootstrap with one click and waits for readback before unlocking the drawer', async () => {
    let finish: (() => void) | undefined;
    bootstrapMocks.apply.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
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
    expect(await within(repair).findByText(/客戶帳務、月嫂薪資或排班資料尚未齊全/)).toBeInTheDocument();
    expect(within(repair).queryByRole('button', { name: '預覽帳務與排班資料' })).not.toBeInTheDocument();
    fireEvent.click(await within(repair).findByRole('button', { name: '建立帳務與排班資料' }));
    await waitFor(() => expect(bootstrapMocks.preview).toHaveBeenCalledTimes(1));
    expect(repair).toHaveTextContent('客戶時薪：350 元');
    await waitFor(() => expect(bootstrapMocks.apply).toHaveBeenCalledTimes(1));
    expect(bootstrapMocks.apply).toHaveBeenCalledWith(
      'CASE-001',
      expect.objectContaining({ client_payment_policy_version: 'client-approved-v1', client_hourly_rate_ntd: 350 }),
      expect.objectContaining({ case_no: 'CASE-001', preview_fingerprint: 'a'.repeat(64) }),
      '',
      expect.stringMatching(/^case-bootstrap-repair-/),
    );
    expect(bootstrapMocks.apply.mock.calls[0][4]).toMatch(/^case-bootstrap-repair-/);
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    await act(async () => { finish?.(); });
    await waitFor(() => expect(mocks.query).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeEnabled());
  });

  it.each(['client_finance_bootstrap_required', 'order_terms_start_date_required'])(
    'saves the missing contractual start date with one click before bootstrap repair (%s)', async (code) => {
    const unavailable = {
      ...(await mocks.query()),
      order_terms: { status: 'not_ready', code, data: null, field_capabilities: {} },
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
    expect(within(repair).queryByLabelText('服務天數')).not.toBeInTheDocument();
    fireEvent.change(within(repair).getByLabelText('約定服務開始日'), { target: { value: '2026-09-01' } });
    expect(within(repair).queryByRole('button', { name: '預覽約定服務資料' })).not.toBeInTheDocument();
    fireEvent.click(within(repair).getByRole('button', { name: '儲存約定服務資料' }));
    await waitFor(() => expect(intakeMocks.previewTerms).toHaveBeenCalledWith('CASE-001', '2026-09-01', 26));
    await waitFor(() => expect(intakeMocks.applyTerms).toHaveBeenCalledTimes(1));
    expect(intakeMocks.applyTerms).toHaveBeenCalledWith(
      'CASE-001',
      expect.objectContaining({ after_start_date: '2026-09-01', after_service_days: 26, preview_fingerprint: 'c'.repeat(64) }),
      '',
      expect.stringMatching(/^historical-terms-repair-case-bootstrap-repair-/),
    );
    expect(intakeMocks.applyTerms.mock.calls[0][3]).toMatch(/^historical-terms-repair-case-bootstrap-repair-/);
    expect(await within(repair).findByRole('button', { name: '建立帳務與排班資料' })).toBeEnabled();
    expect(repair).toHaveTextContent('約定服務資料已補齊');
    expect(bootstrapMocks.apply).not.toHaveBeenCalled();
  });

  it('asks for service days instead of sending an invalid bootstrap preview', async () => {
    const unavailable = {
      ...(await mocks.query()),
      finance: { status: 'not_ready', code: 'client_finance_bootstrap_required', values: null },
      order_terms: { status: 'not_ready', code: 'client_finance_bootstrap_required', data: null, field_capabilities: {} },
    };
    mocks.query.mockReset();
    mocks.query.mockResolvedValue(unavailable);
    bootstrapMocks.status.mockReset();
    bootstrapMocks.status.mockResolvedValue({
      case_no: 'CASE-001', ready: false, scheduling_version: 1,
      scheduling_generation: 1, service_time_complete: true,
      domain_blockers: ['missing_service_days'],
      recommendation: {
        client_payment_policy_version: 'client-approved-v1', client_hourly_rate_ntd: 350,
        deposit_service_days: 0, deposit_due_date: '2026-09-01',
        first_payment_due_date: '2026-09-15', payroll_policy_version: 'approved-rates-v1',
      },
    });
    intakeMocks.previewCompletion.mockResolvedValue({
      case_no: 'CASE-001', lifecycle_version: 7, current_status: '歷史訂單－服務中',
      target_status: '歷史訂單－服務中', current_start_date: '2026-09-15', current_service_days: 0,
      missing_fields: ['service_days'], blockers: [], apply_allowed: false,
      preview_fingerprint: 'b'.repeat(64),
    });

    render(<ClientRosterPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const repair = await screen.findByLabelText('案件初始資料修復');
    expect(await within(repair).findByText('請先補齊約定服務天數，再建立案件初始資料。')).toBeInTheDocument();
    expect(within(repair).queryByLabelText('約定服務開始日')).not.toBeInTheDocument();
    expect(within(repair).getByLabelText('服務天數')).toHaveValue(null);
    expect(within(repair).queryByRole('button', { name: '預覽帳務與排班資料' })).not.toBeInTheDocument();
    expect(bootstrapMocks.preview).not.toHaveBeenCalled();
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

  it.each([
    ['匯出訂單帳務', 'downloadOrderAccounting', '訂單帳務'],
    ['案件資料檢查匯出', 'downloadCaseInspection', '案件資料檢查'],
  ] as const)('downloads %s with the currently applied roster filters', async (button, method, label) => {
    mocks.filterOptions.mockResolvedValue({ values: ['一般市民', '補助市民', null], next_offset: null });
    const createObjectURL = vi.fn().mockReturnValue('blob:order-accounting');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');

    fireEvent.click(screen.getByRole('button', { name: '補助身分篩選' }));
    const dialog = screen.getByRole('dialog', { name: '補助身分篩選選項' });
    await within(dialog).findByRole('checkbox', { name: '補助市民' });
    expect(mocks.filterOptions).toHaveBeenCalledWith('identity_status', '');
    fireEvent.click(within(dialog).getByRole('button', { name: '取消全選' }));
    fireEvent.click(within(dialog).getByRole('checkbox', { name: '補助市民' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '確定' }));
    const columnFilters = [{ field: 'identity_status', operator: 'in', values: ['補助市民'] }];
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ columnFilters })));
    await waitFor(() => expect(screen.getByRole('button', { name: '匯出訂單帳務' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('搜尋客戶名冊清單'), { target: { value: '尚未套用的搜尋' } });
    fireEvent.click(screen.getByRole('button', { name: button }));

    await waitFor(() => expect(mocks[method]).toHaveBeenCalledWith({
      query: '', columnFilters,
      sortBy: 'case_no', sortOrder: 'asc', limit: 100,
    }));
    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:order-accounting');
    expect(await screen.findByText(`${label} Excel 已下載。`)).toBeInTheDocument();
  });

  it('combines multi-select statuses with blank cooking and keeps them across pagination', async () => {
    mocks.list.mockResolvedValue({ items: [item], next_cursor: 'CASE-001', next_offset: 100 });
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: '案件／訂單狀態篩選' }));
    let dialog = screen.getByRole('dialog');
    await within(dialog).findByRole('checkbox', { name: '訂單成立' });
    fireEvent.click(within(dialog).getByRole('button', { name: '取消全選' }));
    fireEvent.click(within(dialog).getByRole('checkbox', { name: '訂單成立' }));
    fireEvent.click(within(dialog).getByRole('checkbox', { name: '服務中' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '確定' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '下廚需求篩選' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '下廚需求篩選' }));
    dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('下廚需求篩選方式'), { target: { value: 'blank' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '確定' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '下一頁' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100, columnFilters: [
      { field: 'order_status', operator: 'in', values: ['訂單成立', '服務中'] },
      { field: 'requires_cooking', operator: 'blank', values: [] },
    ] })));
  });

  it('cancels draft changes and keeps the applied condition when a panel is reopened', async () => {
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    const trigger = screen.getByRole('button', { name: '案件／訂單狀態篩選' });
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog');
    await within(dialog).findByRole('checkbox', { name: '服務中' });
    fireEvent.click(within(dialog).getByRole('button', { name: '取消全選' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(mocks.list).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    expect(await screen.findByRole('checkbox', { name: '服務中' })).toBeChecked();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mocks.list).toHaveBeenCalledTimes(1);
  });

  it('validates date ranges, preserves empty-result headers and clears just one column', async () => {
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: '預計服務日期篩選' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('預計服務日期篩選方式'), { target: { value: 'between' } });
    fireEvent.change(within(dialog).getByLabelText('預計服務日期條件值'), { target: { value: '2026-10-31' } });
    fireEvent.change(within(dialog).getByLabelText('預計服務日期結束值'), { target: { value: '2026-10-01' } });
    expect(within(dialog).getByRole('button', { name: '確定' })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('預計服務日期條件值'), { target: { value: '2026-10-01' } });
    fireEvent.change(within(dialog).getByLabelText('預計服務日期結束值'), { target: { value: '2026-10-31' } });
    mocks.list.mockResolvedValueOnce({ items: [], next_cursor: null, next_offset: null });
    fireEvent.click(within(dialog).getByRole('button', { name: '確定' }));
    await screen.findByText('沒有符合篩選條件的案件。');
    fireEvent.click(screen.getByRole('button', { name: '預計服務日期篩選（已套用）' }));
    expect(screen.getByLabelText('預計服務日期條件值')).toHaveValue('2026-10-01');
    fireEvent.click(screen.getByRole('button', { name: '清除此欄篩選' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.not.objectContaining({ columnFilters: expect.anything() })));
  });

  it('loads and searches options beyond the visible page without truncating all-selection', async () => {
    mocks.filterOptions.mockResolvedValueOnce({ values: ['頁外客戶甲'], next_offset: 100 })
      .mockResolvedValueOnce({ values: ['頁外客戶乙'], next_offset: null })
      .mockResolvedValueOnce({ values: ['搜尋結果'], next_offset: null });
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: '客戶姓名篩選' }));
    const dialog = screen.getByRole('dialog');
    await within(dialog).findByRole('checkbox', { name: '頁外客戶甲' });
    fireEvent.click(within(dialog).getByRole('button', { name: '顯示更多選項' }));
    expect(await within(dialog).findByRole('checkbox', { name: '頁外客戶乙' })).toBeChecked();
    expect(mocks.filterOptions).toHaveBeenLastCalledWith('name', '', 100);
    fireEvent.click(within(dialog).getByRole('checkbox', { name: '頁外客戶甲' }));
    fireEvent.change(within(dialog).getByLabelText('客戶姓名搜尋選項'), { target: { value: '搜尋' } });
    expect(await within(dialog).findByRole('checkbox', { name: '搜尋結果' })).toBeChecked();
    fireEvent.click(within(dialog).getByRole('button', { name: '確定' }));
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ columnFilters: [{ field: 'name', operator: 'not_in', values: ['頁外客戶甲'] }] })));
  });

  it('shows option-loading failure and does not apply it as an empty selection', async () => {
    mocks.filterOptions.mockRejectedValue(new Error('選項查詢失敗'));
    render(<ClientRosterPage />);
    await screen.findByText('CASE-001');
    fireEvent.click(screen.getByRole('button', { name: '客戶姓名篩選' }));
    const dialog = screen.getByRole('dialog');
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('選項查詢失敗');
    expect(within(dialog).getByRole('button', { name: '確定' })).toBeDisabled();
    expect(mocks.list).toHaveBeenCalledTimes(1);
  });

  it('supports shared Excel-style column visibility, arbitrary freeze, resizer drag, and reset layout', async () => {
    mocks.list.mockResolvedValue({
      items: [item],
      next_cursor: null,
      next_offset: null,
    });

    render(<ClientRosterPage />);
    const table = await screen.findByRole('table', { name: /^客戶名冊清單/ });

    const initialHeaders = within(table).getAllByRole('columnheader');
    expect(initialHeaders).toHaveLength(19);
    expect(initialHeaders[0]).toHaveClass('is-sticky-col');
    expect(initialHeaders[0].style.left).toBe('0px');

    fireEvent.click(screen.getByRole('button', { name: /自訂顯示與凍結欄位 \(19\/19\)/ }));
    const picker = screen.getByRole('dialog', { name: '自訂顯示與凍結欄位' });

    fireEvent.click(within(picker).getByRole('button', { name: '取消全選' }));
    const lockedOnlyHeaders = within(table).getAllByRole('columnheader');
    expect(lockedOnlyHeaders).toHaveLength(1);
    expect(lockedOnlyHeaders[0]).toHaveTextContent(/^案件編號/);

    fireEvent.click(within(picker).getByRole('button', { name: '全選' }));
    expect(within(table).getAllByRole('columnheader')).toHaveLength(19);

    fireEvent.click(within(picker).getByRole('button', { name: '凍結客戶姓名' }));
    const frozenHeaders = within(table).getAllByRole('columnheader');
    expect(frozenHeaders[0]).toHaveTextContent(/^案件編號/);
    expect(frozenHeaders[1]).toHaveTextContent(/^客戶姓名/);
    expect(frozenHeaders[1]).toHaveClass('is-sticky-col');
    expect(frozenHeaders[1].style.left).toBe('120px');

    fireEvent.click(within(picker).getByRole('button', { name: '清除凍結' }));
    expect(within(table).getAllByRole('columnheader')[0]).not.toHaveClass('is-sticky-col');
    fireEvent.click(within(picker).getByRole('button', { name: '關閉' }));

    fireEvent.click(screen.getByRole('button', { name: '客戶姓名篩選' }));
    const nameFilterDialog = await screen.findByRole('dialog', { name: '客戶姓名篩選選項' });
    fireEvent.click(within(nameFilterDialog).getByRole('button', { name: '📌 凍結此欄' }));
    const reorderedHeaders = within(table).getAllByRole('columnheader');
    expect(reorderedHeaders[0]).toHaveTextContent(/^客戶姓名/);
    expect(reorderedHeaders[0]).toHaveClass('is-sticky-col');

    fireEvent.click(screen.getByRole('button', { name: '服務天數篩選' }));
    const daysFilterDialog = await screen.findByRole('dialog', { name: '服務天數篩選選項' });
    fireEvent.click(within(daysFilterDialog).getByRole('button', { name: /隱藏此欄/ }));
    expect(within(table).queryByRole('columnheader', { name: /^服務天數/ })).not.toBeInTheDocument();

    const resizer = table.querySelector('.roster-col-resizer[data-resizer-col="name"]') as HTMLElement;
    expect(resizer).not.toBeNull();
    expect((table.querySelectorAll('colgroup col')[0] as HTMLTableColElement).style.width).toBe('110px');
    fireEvent.mouseDown(resizer, { clientX: 100 });
    fireEvent.mouseMove(window, { clientX: 190 });
    fireEvent.mouseUp(window);
    expect((table.querySelectorAll('colgroup col')[0] as HTMLTableColElement).style.width).toBe('200px');

    const persisted = JSON.parse(window.localStorage.getItem('lu.roster.layout.client.v1') ?? '{}') as {
      frozenIds?: string[];
      widths?: Record<string, number>;
    };
    expect(persisted.frozenIds).toEqual(['name']);
    expect(persisted.widths?.name).toBe(200);

    fireEvent.click(screen.getByRole('button', { name: '重設預設排版' }));
    const resetHeaders = within(table).getAllByRole('columnheader');
    expect(resetHeaders).toHaveLength(19);
    expect(resetHeaders[0]).toHaveTextContent(/^案件編號/);
    expect(resetHeaders[0]).toHaveClass('is-sticky-col');
    expect(within(table).getByRole('columnheader', { name: /^服務天數/ })).toBeInTheDocument();
  });
});

vi.mock('../../../../../../../api/finance_import/finance_accounting_client', () => ({financeAccountingClient: {query: vi.fn().mockRejectedValue(new Error('synthetic unavailable summary'))}}));
