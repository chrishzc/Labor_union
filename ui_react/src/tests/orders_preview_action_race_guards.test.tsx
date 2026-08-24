/**
 * File: orders_preview_action_race_guards.test.tsx
 * Description: 驗證Orders Preview POST在close／selection change後中止且不污染flow store。
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { schedulePrecisionClient } from '../api/scheduling/schedule_precision_client';
import { OrdersPage } from '../pages/OrdersPage';
import {
  realisticActualStart,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
  realisticContractCompletion,
} from './fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';
import {
  realisticOrderReopenPreviewView,
  realisticServiceDatePreviewView,
  realisticServiceDateQueryView,
} from './fixtures/orders/order_mutation_contract_fixtures';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

const OPERABLE_CASE_NO = 'ORD-2026-0802';

function operableOrderCard(): HTMLElement {
  const card = screen.getByText(OPERABLE_CASE_NO).closest<HTMLElement>('.order-card');
  if (!card) throw new Error(`找不到 ${OPERABLE_CASE_NO} 訂單卡片。`);
  return card;
}

describe('Orders Preview action race guards', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({ ...realisticOrderDetail, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersQueryClient, 'getOrderTerms').mockResolvedValue({ ...realisticOrderTerms, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockResolvedValue({ ...realisticContractCompletion, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue({ ...realisticOrderCalendarDetail, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue({ ...realisticActualStart, case_no: OPERABLE_CASE_NO });
    vi.spyOn(contractSigningClient, 'query').mockResolvedValue({
      case_no: OPERABLE_CASE_NO,
      staff_segments: [],
      commitment_id: null,
      client_document_sent: true,
      client_signed_received: true,
      contract_identity: 'CT-2026-0802',
      documents: [],
    });
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage)
    );
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({ ...realisticServiceDateQueryView, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValue({ ...realisticOrderReopenPreviewView, case_no: OPERABLE_CASE_NO });
    vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue({
      actual_start_date: '2026-09-01',
      actual_end_date: '2026-09-03',
      target_service_days: 3,
      total_calendar_days: 3,
      actual_work_days_count: 3,
      rest_days_count: 0,
      national_holidays_found: [],
      total_estimated_salary: null,
      weekly_stats: [],
      day_by_day: ['2026-09-01', '2026-09-02', '2026-09-03'].map((date, idx) => ({
        date,
        day_num: idx + 1,
        is_work_day: true,
        is_rest_day: false,
        holiday_name: null,
      })),
    });
  });

  afterEach(() => {
    cleanup();
    orderMutationFlowStore.clearAll();
    vi.restoreAllMocks();
  });

  async function openServiceDates(): Promise<void> {
    render(<OrdersPage />);
    await screen.findByText(OPERABLE_CASE_NO);
    fireEvent.click(within(operableOrderCard()).getByRole('button', { name: /條款與契約/ }));
    const calendarTab = await screen.findByRole('button', { name: /實質服務日曆/ });
    await act(async () => {
      fireEvent.click(calendarTab);
    });
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /產生服務週次預覽/ });
      expect(btn).not.toBeDisabled();
    });
  }

  it('aborts Service Dates Preview on drawer close and discards the late response', async () => {
    const pending = deferred<typeof realisticServiceDatePreviewView>();
    vi.mocked(ordersMutationClient.previewServiceDates).mockReturnValueOnce(pending.promise);
    await openServiceDates();

    const previewBtn = screen.getByRole('button', { name: /產生服務週次預覽/ });
    await act(async () => {
      fireEvent.click(previewBtn);
    });
    await waitFor(() => expect(ordersMutationClient.previewServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewServiceDates).mock.calls[0]?.[2]?.signal;
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    const draft = orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO);
    expect(draft?.previewView).toBeNull();
    expect(draft?.status).not.toBe('preview_ready');
  });

  it('aborts Service Dates Preview when the selected dates change', async () => {
    const pending = deferred<typeof realisticServiceDatePreviewView>();
    vi.mocked(ordersMutationClient.previewServiceDates).mockReturnValueOnce(pending.promise);
    await openServiceDates();

    const previewBtn = screen.getByRole('button', { name: /產生服務週次預覽/ });
    await act(async () => {
      fireEvent.click(previewBtn);
    });
    await waitFor(() => expect(ordersMutationClient.previewServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewServiceDates).mock.calls[0]?.[2]?.signal;

    // 透過 UI 新增事前請假觸發日期變更與 abort
    vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValueOnce({
      actual_start_date: '2026-09-01',
      actual_end_date: '2026-09-04',
      target_service_days: 3,
      total_calendar_days: 4,
      actual_work_days_count: 3,
      rest_days_count: 1,
      national_holidays_found: [],
      total_estimated_salary: null,
      weekly_stats: [],
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: false, is_rest_day: true, holiday_name: '事前請假' },
        { date: '2026-09-03', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    });
    fireEvent.change(screen.getByLabelText('事前請假日期'), { target: { value: '2026-09-02' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '新增事前請假' }));
    });
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    expect(orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO)?.status).toBe('draft_changed');
  });

  it('keeps Service Dates Preview alive when suggested dates equal the current selection', async () => {
    const pending = deferred<typeof realisticServiceDatePreviewView>();
    vi.mocked(ordersMutationClient.previewServiceDates).mockReturnValueOnce(pending.promise);
    await openServiceDates();

    const previewBtn = screen.getByRole('button', { name: /產生服務週次預覽/ });
    await act(async () => {
      fireEvent.click(previewBtn);
    });
    await waitFor(() => expect(ordersMutationClient.previewServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewServiceDates).mock.calls[0]?.[2]?.signal;

    // 重新設定相同日期
    await act(async () => {
      orderMutationFlowStore.updateServiceDatesSelection(OPERABLE_CASE_NO, orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO)?.selectedDates ?? []);
    });
    expect(signal?.aborted).toBe(false);

    await act(async () => {
      pending.resolve({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    expect(orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO)?.status).toBe('preview_ready');
  });

  it('aborts Controlled Reopen Preview on modal close and keeps the draft closed', async () => {
    const pending = deferred<typeof realisticOrderReopenPreviewView>();
    vi.mocked(ordersMutationClient.previewReopen).mockReturnValueOnce(pending.promise);
    render(<OrdersPage />);
    await screen.findByText(OPERABLE_CASE_NO);

    fireEvent.click(within(operableOrderCard()).getByRole('button', { name: /條款與契約/ }));
    const reopenTab = await screen.findByRole('button', { name: /受控重開訂單/ });
    await act(async () => {
      fireEvent.click(reopenTab);
    });
    await waitFor(() => expect(ordersMutationClient.previewReopen).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewReopen).mock.calls[0]?.[1]?.signal;
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve({ ...realisticOrderReopenPreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    const draft = orderMutationFlowStore.getReopenDraft(OPERABLE_CASE_NO);
    expect(draft?.status).toBe('closed');
    expect(draft?.previewView).toBeNull();
  });
});
