/**
 * File: data_browser_page_real_data.test.tsx
 * Description: 驗證 Data Browser six-source UI、loaded row Drawer 與 budget。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DataBrowserPage } from '../pages/DataBrowserPage';
import { dataBrowserQueryClient } from '../api/data_browser/data_browser_query_client';
import { VALID_DATA_BROWSER_PAGE } from './fixtures/data_browser/data_browser_query_contract_fixtures';

describe('Data Browser real-data page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(dataBrowserQueryClient, 'querySource').mockResolvedValue(VALID_DATA_BROWSER_PAGE);
    vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  });

  it('loads one source, renders six tabs, and opens Drawer without another GET', async () => {
    render(<DataBrowserPage />);
    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(1);
    expect(document.querySelectorAll('[data-control-id^="data-browser.source."]')).toHaveLength(6);

    fireEvent.click(screen.getByRole('button', { name: /檢視詳情/ }));
    expect(screen.getByText(/完整資料詳情/)).toBeInTheDocument();
    expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/RAW JSON/)).not.toBeInTheDocument();
  });

  it('copies only canonical loaded-row view with inline feedback', async () => {
    render(<DataBrowserPage />);
    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /檢視詳情/ }));
    fireEvent.click(screen.getByRole('button', { name: '複製完整資料' }));
    await waitFor(() => expect(screen.getByText('已複製完整資料')).toBeInTheDocument());
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    const copied = vi.mocked(navigator.clipboard.writeText).mock.calls[0]?.[0] ?? '';
    expect(copied).not.toMatch(/source_id|row_identity|version_identity|field_id/);
    expect(copied).toContain('"label": "訂單狀態"');
    expect(copied).toContain('"value": "服務中"');
  });

  it('retries the same cursor after a next-page failure without duplicating loaded rows', async () => {
    vi.mocked(dataBrowserQueryClient.querySource)
      .mockResolvedValueOnce({ ...VALID_DATA_BROWSER_PAGE, next_cursor: '115000001' })
      .mockRejectedValueOnce(new Error('temporary page failure'))
      .mockResolvedValueOnce({
        ...VALID_DATA_BROWSER_PAGE,
        items: VALID_DATA_BROWSER_PAGE.items.map((item) => ({
          ...item,
          row_identity: '115000002',
          display_title: '訂單 115000002',
        })),
        next_cursor: null,
      });

    render(<DataBrowserPage />);
    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '載入下一頁' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '重試下一頁' })).toBeInTheDocument());
    expect(screen.getByText('訂單 115000001')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重試下一頁' }));
    await waitFor(() => expect(screen.getByText('訂單 115000002')).toBeInTheDocument());
    expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(3);
    expect(screen.getAllByText(/訂單 11500000[12]/)).toHaveLength(2);
  });
});
