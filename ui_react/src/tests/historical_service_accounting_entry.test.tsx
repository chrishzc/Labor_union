/**
 * File: historical_service_accounting_entry.test.tsx
 * Description: 驗證歷史訂單實際服務天數入口由資料中心移至帳務作業，且重用既有 workbench。
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { NAV_ITEMS } from '../components/MasterLayout';
import { DataImportPage } from '../pages/DataImportPage';
import { HistoricalServiceAccountingPage } from '../pages/HistoricalServiceAccountingPage';

describe('historical service accounting entry ownership', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('removes the workbench from data center and exposes it under finance navigation', async () => {
    vi.spyOn(hcmImportResultClient, 'query').mockResolvedValue({ items: [] } as any);

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
});
