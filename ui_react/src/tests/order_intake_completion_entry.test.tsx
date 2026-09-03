import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { orderIntakeCompletionClient } from '../api/orders/order_intake_completion_client';
import { OrdersManagementPage } from '../pages/OrdersManagementPage';

vi.mock('../pages/OrdersPage', async () => {
  const ReactModule = await import('react');
  const queryModule = await import('../api/orders/order_query_client');
  return {
    OrdersPage: () => {
      ReactModule.useEffect(() => {
        void queryModule.loadAllOrderSummaries(
          queryModule.ordersQueryClient.getOrderSummaries.bind(queryModule.ordersQueryClient),
          { page_size: 200, lifecycle_scope: 'unfinished' },
        );
      }, []);
      return <div data-testid="legacy-orders-page">legacy orders workbench</div>;
    },
  };
});

const ETAG = 'a'.repeat(64);
const FP1 = '1'.repeat(64);
const FP2 = '2'.repeat(64);

const incompleteSummary = {
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

const completeSummary = {
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

describe('Orders intake repair entry', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('lists every current missing field while leaving complete orders on the existing workbench', async () => {
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({
      items: [incompleteSummary, completeSummary],
      next_cursor: null,
      etag: ETAG,
    });
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153',
      lifecycle_version: 7,
      current_status: '待補件',
      target_status: '洽談中',
      missing_fields: ['client_name', 'start_date', 'service_days'],
      blockers: ['order_intake_completion_service_data_locked'],
      apply_allowed: false,
      preview_fingerprint: FP1,
    });

    render(<OrdersManagementPage />);

    const region = await screen.findByRole('region', { name: '訂單缺件補齊' });
    expect(within(region).getByText('CASE-153')).toBeInTheDocument();
    expect(within(region).getByText('客戶姓名', { selector: 'li' })).toBeInTheDocument();
    expect(within(region).getByText('約定服務開始日', { selector: 'li' })).toBeInTheDocument();
    expect(within(region).getByText('服務天數', { selector: 'li' })).toBeInTheDocument();
    expect(await within(region).findByText('服務資料已鎖定，目前不能完成進件補齊。')).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: '檢查服務資料補件' })).toBeDisabled();
    expect(within(region).queryByText('CASE-OK')).not.toBeInTheDocument();
    expect(screen.getByTestId('legacy-orders-page')).toBeInTheDocument();
  });

  it('applies typed terms repair, rechecks completion, restores normal status, and refreshes the list', async () => {
    const pendingWithName = {
      ...incompleteSummary,
      client_name: '王小明',
    };
    const repaired = {
      ...pendingWithName,
      order_status: '洽談中',
      start_date: '2026-09-10',
      service_days: 30,
    };
    vi.spyOn(ordersQueryClient, 'getOrderSummaries')
      .mockResolvedValueOnce({ items: [pendingWithName], next_cursor: null, etag: ETAG })
      .mockResolvedValueOnce({ items: [repaired], next_cursor: null, etag: ETAG });
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion')
      .mockResolvedValueOnce({
        case_no: 'CASE-153',
        lifecycle_version: 7,
        current_status: '待補件',
        target_status: '洽談中',
        missing_fields: ['start_date', 'service_days'],
        blockers: [],
        apply_allowed: false,
        preview_fingerprint: FP1,
      })
      .mockResolvedValueOnce({
        case_no: 'CASE-153',
        lifecycle_version: 8,
        current_status: '待補件',
        target_status: '洽談中',
        missing_fields: [],
        blockers: [],
        apply_allowed: true,
        preview_fingerprint: FP2,
      });
    vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue({
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
    });
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockResolvedValue({
      receipt_key: 'terms-receipt',
      case_no: 'CASE-153',
      lifecycle_version: 8,
      start_date: '2026-09-10',
      service_days: 30,
      changed_fields: ['start_date', 'service_days'],
      preview_fingerprint: FP1,
      replayed: false,
    });
    const applyCompletion = vi.spyOn(orderIntakeCompletionClient, 'applyCompletion').mockResolvedValue({
      receipt_key: 'completion-receipt',
      case_no: 'CASE-153',
      lifecycle_version: 9,
      status: '洽談中',
      preview_fingerprint: FP2,
      replayed: false,
    });

    render(<OrdersManagementPage />);

    fireEvent.change(await screen.findByLabelText('CASE-153 約定服務開始日'), {
      target: { value: '2026-09-10' },
    });
    fireEvent.change(screen.getByLabelText('CASE-153 服務天數'), {
      target: { value: '30' },
    });
    fireEvent.change(screen.getByLabelText('CASE-153 補件原因'), {
      target: { value: '補齊原始進件缺漏' },
    });
    await waitFor(() => expect(screen.getByRole('button', { name: '檢查服務資料補件' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '檢查服務資料補件' }));
    await screen.findByText('補件欄位：約定服務開始日、服務天數');
    fireEvent.click(screen.getByRole('button', { name: '確認補齊服務資料' }));

    await waitFor(() => expect(applyTerms).toHaveBeenCalledWith(
      'CASE-153',
      expect.objectContaining({ lifecycle_version: 7, preview_fingerprint: FP1 }),
      '補齊原始進件缺漏',
      expect.stringContaining('orders-intake-terms-CASE-153-'),
    ));
    await waitFor(() => expect(applyCompletion).toHaveBeenCalledWith(
      'CASE-153',
      expect.objectContaining({ lifecycle_version: 8, preview_fingerprint: FP2 }),
      '補齊原始進件缺漏',
      expect.stringContaining('orders-intake-complete-CASE-153-'),
    ));
    await waitFor(() => expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument());
    expect(screen.getByTestId('legacy-orders-page')).toBeInTheDocument();
  });
});
