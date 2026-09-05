import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { OrderDetail, OrderSummaryItem } from '../api/orders/order_query_schemas';
import {
  orderIntakeCompletionClient,
  type IntakeCompletionPreview,
  type IntakeTermsPreview,
} from '../api/orders/order_intake_completion_client';
import { OrdersManagementPage } from '../pages/OrdersManagementPage';

const ETAG = 'a'.repeat(64);
const FP1 = '1'.repeat(64);
const FP2 = '2'.repeat(64);

const incompleteSummary: OrderSummaryItem = {
  case_no: 'CASE-153',
  client_name: '待補姓名（CASE-153）',
  order_status: '待補件',
  staff_name: null,
  identity_status: null,
  start_date: null,
  end_date: null,
  actual_start_date: null,
  actual_end_date: null,
  service_days: null,
  total_employer_self_pay_payable: null,
};

const completeSummary: OrderSummaryItem = {
  case_no: 'CASE-OK',
  client_name: '完整客戶',
  order_status: '洽談中',
  staff_name: null,
  identity_status: '一般',
  start_date: '2026-09-10',
  end_date: '2026-10-09',
  actual_start_date: null,
  actual_end_date: null,
  service_days: 30,
  total_employer_self_pay_payable: 100000,
};

const incompleteDetail: OrderDetail = {
  case_no: 'CASE-153',
  client_id: 153,
  staff_id: null,
  client_name: incompleteSummary.client_name,
  staff_name: null,
  order_status: '待補件',
  identity_status: null,
  cancel_reason: null,
  line_group_id: null,
  contract_identity: null,
  actual_start_date: null,
  actual_end_date: null,
  deposit_date: null,
  start_date: null,
  end_date: null,
  service_days: 0,
  service_hours_per_day: 0,
  deposit_service_days: null,
  floor_fee: 0,
  custom_rest_dates: null,
};

describe('Orders intake repair entry', () => {
  beforeEach(() => {
    // Exercise the real card, Drawer and intake panel. Other owner queries may
    // fail without hiding the intake owner's independent facts and actions.
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockRejectedValue(new Error('stage unavailable'));
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockRejectedValue(new Error('card unavailable'));
    vi.spyOn(ordersQueryClient, 'getOrderTerms').mockRejectedValue(new Error('terms unavailable'));
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockRejectedValue(new Error('contract unavailable'));
    vi.spyOn(contractSigningClient, 'query').mockRejectedValue(new Error('signing unavailable'));
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue(incompleteDetail);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('opens missing fields and owner blockers inside the existing Drawer without a second list-top workbench', async () => {
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({
      items: [incompleteSummary, completeSummary],
      next_cursor: null,
      etag: ETAG,
    });
    const previewCompletion = vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153',
      lifecycle_version: 7,
      current_status: '待補件',
      target_status: '洽談中',
      missing_fields: ['client_name', 'start_date', 'service_days'],
      blockers: ['order_intake_completion_service_data_locked'],
      apply_allowed: false,
      preview_fingerprint: FP1,
    });
    const applyName = vi.spyOn(orderIntakeCompletionClient, 'applyClientName').mockRejectedValue(new Error('unexpected name apply'));
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockRejectedValue(new Error('unexpected terms apply'));
    const applyCompletion = vi.spyOn(orderIntakeCompletionClient, 'applyCompletion').mockRejectedValue(new Error('unexpected completion apply'));

    render(<OrdersManagementPage />);
    await screen.findByText('CASE-153');
    expect(screen.getByText('CASE-OK')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '訂單缺件' })).not.toBeInTheDocument();
    expect(previewCompletion).not.toHaveBeenCalled();
    const contractButtons = screen.getAllByRole('button', { name: '📑 條款與契約' });
    expect(contractButtons).toHaveLength(2);
    contractButtons.forEach((button) => expect(button).toBeEnabled());
    screen.getAllByRole('button', { name: '👩‍🍼 媒合與正式排班' }).forEach((button) => expect(button).toBeEnabled());

    fireEvent.click(contractButtons[0]!);
    const region = await screen.findByRole('region', { name: '訂單缺件' });
    expect(region.closest('.drawer-body')).not.toBeNull();
    await within(region).findByText('缺少資料：客戶姓名、服務開始日、服務天數');
    expect(within(region).getByText('服務資料已鎖定，目前不能完成進件補齊。')).toBeInTheDocument();
    expect(within(region).queryByLabelText('客戶姓名')).not.toBeInTheDocument();
    expect(within(region).queryByLabelText('服務開始日')).not.toBeInTheDocument();
    expect(within(region).queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
    expect(screen.getByText('完整客戶')).toBeInTheDocument();
    expect(applyName).not.toHaveBeenCalled();
    expect(applyTerms).not.toHaveBeenCalled();
    expect(applyCompletion).not.toHaveBeenCalled();
  });

  it('previews and explicitly applies terms and completion inside the Drawer, then reads back the updated list', async () => {
    // Both the Drawer and panel read detail; model owner state rather than
    // returning different facts merely because an extra reader called first.
    let phase = 0;
    const pendingWithName = { ...incompleteSummary, client_name: '補件測試客戶' };
    const summaries = vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockImplementation(async () => ({
      items: [{
        ...pendingWithName,
        order_status: phase === 2 ? '洽談中' : '待補件',
        start_date: phase > 0 ? '2026-09-10' : null,
        service_days: phase > 0 ? 30 : null,
      }],
      next_cursor: null,
      etag: ETAG,
    }));
    vi.mocked(ordersQueryClient.getOrderDetail).mockImplementation(async () => ({
      ...incompleteDetail,
      client_name: pendingWithName.client_name,
      order_status: phase === 2 ? '洽談中' : '待補件',
      start_date: phase > 0 ? '2026-09-10' : null,
      service_days: phase > 0 ? 30 : 0,
    }));
    const readyCompletion: IntakeCompletionPreview = {
      case_no: 'CASE-153',
      lifecycle_version: 8,
      current_status: '待補件',
      target_status: '洽談中',
      missing_fields: [],
      blockers: [],
      apply_allowed: true,
      preview_fingerprint: FP2,
    };
    const previewCompletion = vi.spyOn(orderIntakeCompletionClient, 'previewCompletion')
      .mockImplementation(async (): Promise<IntakeCompletionPreview> => phase === 0 ? {
        ...readyCompletion,
        lifecycle_version: 7,
        missing_fields: ['start_date', 'service_days'],
        apply_allowed: false,
        preview_fingerprint: FP1,
      } : phase === 1 ? readyCompletion : {
        ...readyCompletion,
        lifecycle_version: 9,
        current_status: '洽談中',
        apply_allowed: false,
        preview_fingerprint: '3'.repeat(64),
      });
    const termsPreview: IntakeTermsPreview = {
      case_no: 'CASE-153',
      lifecycle_version: 7,
      before_start_date: null,
      before_service_days: null,
      after_start_date: '2026-09-10',
      after_service_days: 30,
      changed_fields: ['start_date', 'service_days'],
      blockers: [],
      apply_allowed: true,
      preview_fingerprint: FP1,
    };
    const previewTerms = vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue(termsPreview);
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockImplementation(async () => {
      phase = 1;
      return {
        receipt_key: 'terms-receipt',
        case_no: 'CASE-153',
        lifecycle_version: 8,
        start_date: '2026-09-10',
        service_days: 30,
        changed_fields: termsPreview.changed_fields,
        preview_fingerprint: FP1,
        replayed: false,
      };
    });
    const applyCompletion = vi.spyOn(orderIntakeCompletionClient, 'applyCompletion').mockImplementation(async () => {
      phase = 2;
      return {
        receipt_key: 'completion-receipt',
        case_no: 'CASE-153',
        lifecycle_version: 9,
        status: '洽談中',
        preview_fingerprint: FP2,
        replayed: false,
      };
    });

    render(<OrdersManagementPage />);
    fireEvent.click(await screen.findByRole('button', { name: '📑 條款與契約' }));
    const region = await screen.findByRole('region', { name: '訂單缺件' });
    fireEvent.change(await within(region).findByLabelText('服務開始日'), { target: { value: '2026-09-10' } });
    fireEvent.change(within(region).getByLabelText('服務天數'), { target: { value: '30' } });
    fireEvent.click(within(region).getByRole('button', { name: '檢查日期／天數補件影響' }));
    const confirmTerms = await within(region).findByRole('button', { name: '確認套用日期／天數補件' });
    expect(previewTerms).toHaveBeenCalledWith('CASE-153', '2026-09-10', 30);
    expect(confirmTerms).toBeDisabled();
    expect(applyTerms).not.toHaveBeenCalled();
    expect(applyCompletion).not.toHaveBeenCalled();
    fireEvent.change(within(region).getByLabelText('補件原因（套用時必填）'), { target: { value: '補齊原始進件缺漏' } });
    expect(confirmTerms).toBeEnabled();
    fireEvent.click(confirmTerms);

    const confirmCompletion = await within(region).findByRole('button', { name: '確認完成進件補齊' });
    await waitFor(() => expect(confirmCompletion).toBeEnabled());
    expect(applyTerms).toHaveBeenCalledTimes(1);
    expect(applyTerms).toHaveBeenCalledWith(
      'CASE-153', termsPreview, '補齊原始進件缺漏',
      expect.stringContaining('orders-intake-terms-CASE-153-'),
    );
    expect(previewCompletion).toHaveBeenCalledTimes(2);
    expect(applyCompletion).not.toHaveBeenCalled();
    fireEvent.click(confirmCompletion);

    await waitFor(() => expect(screen.queryByRole('region', { name: '訂單缺件' })).not.toBeInTheDocument());
    expect(applyCompletion).toHaveBeenCalledTimes(1);
    expect(applyCompletion).toHaveBeenCalledWith(
      'CASE-153', readyCompletion, '補齊原始進件缺漏',
      expect.stringContaining('orders-intake-completion-CASE-153-'),
    );
    expect(previewCompletion).toHaveBeenCalledTimes(3);
    expect(summaries).toHaveBeenCalledTimes(3);
    expect(screen.getByText('伺服器狀態：洽談中')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument();
  });
});
