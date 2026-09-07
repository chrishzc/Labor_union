import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  type CoreStageCode,
} from '../api/orders/order_core_stage_projection_schemas';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const mocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
  getOrderDetail: vi.fn(),
  getOrderTerms: vi.fn(),
  getAssignmentPlan: vi.fn(),
  queryTerms: vi.fn(),
  previewTerms: vi.fn(),
  applyTerms: vi.fn(),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: mocks.getCoreStageTimelines,
  },
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: mocks.loadSummaries,
  ordersQueryClient: {
    getOrderSummaries: vi.fn(),
    getOrderDetail: mocks.getOrderDetail,
    getOrderTerms: mocks.getOrderTerms,
    getAssignmentPlan: mocks.getAssignmentPlan,
  },
}));

vi.mock('../api/orders/order_terms_mutation_client', () => ({
  orderTermsMutationClient: {
    query: mocks.queryTerms,
    preview: mocks.previewTerms,
    apply: mocks.applyTerms,
  },
}));

const STAGE_LABELS: Readonly<Record<CoreStageCode, string>> = {
  intake_validation: '進件與資料完整性驗證',
  matching_pool: '建立候選月嫂池',
  caregiver_line_delivery: '詢問月嫂接案意願',
  caregiver_willingness_reply: '等待月嫂意願回覆',
  formal_recommendation: '推薦月嫂給客戶確認',
  caregiver_contract: '月嫂契約簽署',
  deposit_settlement: '客戶定金核銷',
  client_contract: '客戶契約簽署',
  confirmed_service_dates: '正式服務日期確認',
  formal_service: '正式排班與服務履約',
  service_completion: '完工／服務完成確認',
  client_settlement: '客戶端結算',
  staff_payout: '月嫂端結算',
};

function stage(code: CoreStageCode) {
  const status = code === 'intake_validation' ? 'in_progress' as const : 'completed' as const;
  return {
    ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
    code,
    label: STAGE_LABELS[code],
    owner: `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: { owner: `source-${code}`, identity: `${code}:CASE-TERMS`, version: 7 },
    occurred_at: null,
    blockers: [],
    warnings: [],
    available_read_actions: [],
    availability_reason: null,
  };
}

function corePage() {
  const stageCounts = Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0]));
  stageCounts.intake_validation = 1;
  return {
    items: [{
      case_no: 'CASE-TERMS',
      base_revision: 3,
      lifecycle_status: '訂單成立',
      branch_type: 'normal',
      current_core_stage_code: 'intake_validation',
      current_core_stage_ordinal: 1,
      historical_current_owner_stage_code: null,
      historical_current_owner_stage_ordinal: null,
      core_stages: CORE_STAGE_CODES.map(stage),
      source_projection_digest: 'd'.repeat(64),
    }],
    stage_counts: stageCounts,
    substatus_counts: {
      intake_pending: 0,
      intake_in_progress: 1,
      intake_blocked: 0,
      data_complete: 0,
      intake_unavailable: 0,
    },
    historical_lifecycle_counts: {
      unserved: 0,
      in_service: 0,
      service_completed: 0,
      accounting_completed: 0,
    },
    next_cursor: null,
    etag: 'e'.repeat(64),
  };
}

function orderTerms() {
  return {
    case_no: 'CASE-TERMS',
    order_version: 12,
    scheduling_version: 13,
    scheduling_generation: 2,
    client_finance_version: 5,
    payroll_version: 6,
    service_data_locked: false,
    terms: {
      planned_start_date: '2026-10-01',
      service_days: 20,
      service_hours_per_day: 9,
      requires_cooking: true,
      floor_fee_ntd: 0,
      service_time: { start_time: '08:00:00', end_time: '17:00:00', end_day_offset: 0 },
    },
  };
}

function refreshedOrderTerms() {
  return {
    ...orderTerms(),
    order_version: 13,
    scheduling_version: 14,
    scheduling_generation: 3,
    client_finance_version: 6,
    payroll_version: 7,
    terms: {
      ...orderTerms().terms,
      service_days: 21,
    },
  };
}

function card(): HTMLElement {
  const node = screen.getByText('CASE-TERMS').closest('article');
  if (!(node instanceof HTMLElement)) throw new Error('找不到 CASE-TERMS 案件卡');
  return node;
}

async function openTermsPanel(): Promise<HTMLElement> {
  render(<OrderWorkbenchV2Page />);
  await waitFor(() => expect(screen.getByText('CASE-TERMS')).toBeInTheDocument());
  fireEvent.click(within(card()).getByRole('button', { name: '開啟唯讀工作 Drawer' }));

  const dialog = await screen.findByRole('dialog', { name: '案件 CASE-TERMS' });
  const panel = within(dialog).getByRole('heading', { name: '進件條款預覽與套用' }).closest('section');
  if (!(panel instanceof HTMLElement)) throw new Error('找不到進件條款操作區');
  return panel;
}

async function previewAndApply(panel: HTMLElement) {
  fireEvent.change(within(panel).getByLabelText('Beta 服務天數'), { target: { value: '21' } });
  fireEvent.click(within(panel).getByRole('button', { name: '檢查訂單條款變更' }));
  await waitFor(() => expect(mocks.previewTerms).toHaveBeenCalled());
  fireEvent.change(within(panel).getByLabelText('Beta 條款變更原因'), { target: { value: '客戶確認延長一天' } });
  fireEvent.click(within(panel).getByRole('button', { name: '確認套用訂單條款' }));
}

describe('待辦看板 Beta 第 1 階訂單條款操作', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.getCoreStageTimelines.mockResolvedValue(corePage());
    mocks.loadSummaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'f'.repeat(64) });
    mocks.getOrderDetail.mockResolvedValue({
      case_no: 'CASE-TERMS',
      client_id: 88,
      staff_id: null,
      client_name: '條款測試客戶',
      staff_name: null,
      order_status: '訂單成立',
      identity_status: '一般市民',
      cancel_reason: null,
      line_group_id: null,
      contract_identity: null,
      actual_start_date: null,
      actual_end_date: null,
      deposit_date: null,
      start_date: '2026-10-01',
      end_date: '2026-10-20',
      service_days: 20,
      service_hours_per_day: 9,
      deposit_service_days: null,
      floor_fee: 0,
      custom_rest_dates: null,
    });
    mocks.getOrderTerms.mockResolvedValue(orderTerms());
    mocks.getAssignmentPlan.mockResolvedValue({
      case_no: 'CASE-TERMS',
      order_version: 12,
      scheduling_version: 13,
      scheduling_generation: 2,
      client_finance_version: 5,
      payroll_version: 6,
      contracted_service_days: 20,
      service_hours_per_day: 9,
      service_started: false,
      assignments: [],
    });
    mocks.queryTerms.mockResolvedValue(refreshedOrderTerms());
    mocks.previewTerms.mockResolvedValue({
      before: orderTerms().terms,
      after: { ...orderTerms().terms, service_days: 21 },
      order_version: 12,
      scheduling_version: 13,
      scheduling_generation: 2,
      client_finance_version: 5,
      payroll_version: 6,
      scheduling: {},
      client_finance_impact: {},
      payroll_impact: {},
      lifecycle_impact: {},
      preview_fingerprint: 'a'.repeat(64),
    });
    mocks.applyTerms.mockResolvedValue({
      case_no: 'CASE-TERMS',
      order_version: 13,
      scheduling_version: 14,
      scheduling_generation: 3,
      client_finance_version: 6,
      payroll_version: 7,
      lifecycle_status: '訂單成立',
      service_data_lock_formed: false,
      cancelled_assignment_ids: [],
      created_assignment_keys: [],
      official_service_day_count: 21,
      official_service_hours: 189,
      preview_fingerprint: 'a'.repeat(64),
    });
  });

  it('沿用既有 Preview -> 原因確認 -> Apply，並在成功後回讀正式條款投影', async () => {
    const panel = await openTermsPanel();

    fireEvent.change(within(panel).getByLabelText('Beta 服務天數'), { target: { value: '21' } });
    fireEvent.click(within(panel).getByRole('button', { name: '檢查訂單條款變更' }));

    await waitFor(() => expect(mocks.previewTerms).toHaveBeenCalledWith('CASE-TERMS', {
      proposed_terms: {
        planned_start_date: '2026-10-01',
        service_days: 21,
        service_hours_per_day: 9,
        requires_cooking: true,
        floor_fee_ntd: 0,
        service_time: { start_time: '08:00:00', end_time: '17:00:00', end_day_offset: 0 },
      },
    }));
    expect(within(panel).getByText(/版本：Order 12 · Scheduling 13 · Client Finance 5 · Payroll 6/)).toBeInTheDocument();

    fireEvent.change(within(panel).getByLabelText('Beta 條款變更原因'), { target: { value: '客戶確認延長一天' } });
    fireEvent.click(within(panel).getByRole('button', { name: '確認套用訂單條款' }));

    await waitFor(() => expect(mocks.applyTerms).toHaveBeenCalledWith(
      'CASE-TERMS',
      expect.objectContaining({
        expected_order_version: 12,
        expected_scheduling_version: 13,
        expected_client_finance_version: 5,
        expected_payroll_version: 6,
        preview_fingerprint: 'a'.repeat(64),
        reason: '客戶確認延長一天',
        proposed_terms: expect.objectContaining({ service_days: 21 }),
      }),
      expect.objectContaining({ idempotencyKey: expect.stringMatching(/^orders-terms-ui-CASE-TERMS-/) }),
    ));
    await waitFor(() => expect(mocks.queryTerms).toHaveBeenCalledWith('CASE-TERMS'));
    expect(await within(panel).findByText(/條款已套用並完成正式回讀；Order version 13，合約服務 21 日。/)).toBeInTheDocument();
    expect(within(panel).getByLabelText('Beta 服務天數')).toHaveValue(21);
  });

  it('預覽 fingerprint 不匹配時顯示可辨識錯誤並要求重新預覽', async () => {
    mocks.applyTerms.mockRejectedValueOnce(Object.assign(
      new Error('The business facts changed after Preview.'),
      { code: 'stale_preview' },
    ));
    const panel = await openTermsPanel();

    await previewAndApply(panel);

    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      '預覽已過期：正式資料已變更，請重新檢查條款變更後再套用。',
    );
    expect(within(panel).queryByRole('button', { name: '確認套用訂單條款' })).not.toBeInTheDocument();
    expect(mocks.queryTerms).not.toHaveBeenCalled();
  });

  it('版本不匹配時顯示可辨識錯誤並要求重新預覽', async () => {
    mocks.applyTerms.mockRejectedValueOnce(Object.assign(
      new Error('The order version changed before Apply.'),
      { code: 'order_version_conflict' },
    ));
    const panel = await openTermsPanel();

    await previewAndApply(panel);

    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      '版本已變更：正式資料已更新，請重新檢查條款變更後再套用。',
    );
    expect(within(panel).queryByRole('button', { name: '確認套用訂單條款' })).not.toBeInTheDocument();
    expect(mocks.queryTerms).not.toHaveBeenCalled();
  });
});
