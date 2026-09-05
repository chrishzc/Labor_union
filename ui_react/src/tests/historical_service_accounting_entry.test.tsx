/**
 * File: historical_service_accounting_entry.test.tsx
 * Description: 驗證歷史訂單實際服務天數入口由資料中心移至帳務作業，且重用既有 workbench。
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { historicalServiceAccountingClient } from '../api/orders/historical_service_accounting_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { NAV_ITEMS } from '../components/MasterLayout';
import { DataImportPage } from '../pages/DataImportPage';
import { HistoricalServiceAccountingPage } from '../pages/HistoricalServiceAccountingPage';

const summaryPage = {
  items: [
    {
      case_no: 'CASE-001',
      client_name: '王小明',
      order_status: 'historical_service_completed',
      staff_name: null,
      identity_status: null,
      start_date: null,
      end_date: null,
      actual_start_date: null,
      actual_end_date: null,
      historical_source_start_date: null,
      historical_source_end_date: null,
      service_days: 30,
      total_employer_self_pay_payable: 0,
    },
  ],
  next_cursor: null,
  etag: 'a'.repeat(64),
} as any;

describe('historical service accounting entry ownership', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('removes the workbench from data center and exposes it under finance navigation', async () => {
    vi.spyOn(hcmImportResultClient, 'query').mockResolvedValue({ items: [] } as any);
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(summaryPage);

    const dataCenter = render(<DataImportPage />);
    await waitFor(() => expect(hcmImportResultClient.query).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('region', { name: '歷史訂單實際服務天數與帳務' })).not.toBeInTheDocument();
    dataCenter.unmount();

    render(<HistoricalServiceAccountingPage />);
    expect(screen.getByRole('heading', { name: /歷史訂單實際服務天數設定/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '歷史訂單實際服務天數與帳務' })).toBeInTheDocument();

    expect(NAV_ITEMS.find((item) => item.id === 'historical-service-accounting')).toMatchObject({
      label: '歷史服務天數',
      section: 'finance',
    });
  });

  it('loads order summaries into a selector and preserves the existing query call', async () => {
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(summaryPage);
    const query = vi.spyOn(historicalServiceAccountingClient, 'query').mockResolvedValue({
      case_no: 'CASE-001',
      lifecycle_status: 'historical_service_completed',
      contracted_service_days: 30,
      service_hours_per_day: 24,
      assignments: [],
    } as any);

    render(<HistoricalServiceAccountingPage />);

    const selector = await screen.findByRole('combobox', { name: '案件編號' });
    await waitFor(() => expect(selector).not.toBeDisabled());
    expect(screen.getByRole('option', { name: 'CASE-001｜王小明｜historical_service_completed' })).toBeInTheDocument();

    fireEvent.change(selector, { target: { value: 'CASE-001' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢服務帳務' }));

    await waitFor(() => expect(query).toHaveBeenCalledWith('CASE-001'));
  });
});
