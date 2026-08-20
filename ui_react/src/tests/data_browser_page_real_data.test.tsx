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

    fireEvent.click(screen.getByRole('button', { name: /檢視去敏詳情/ }));
    expect(screen.getByText(/去敏資料詳情/)).toBeInTheDocument();
    expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/RAW JSON/)).not.toBeInTheDocument();
  });

  it('copies only masked loaded-row view with inline feedback', async () => {
    render(<DataBrowserPage />);
    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /檢視去敏詳情/ }));
    fireEvent.click(screen.getByRole('button', { name: '複製去敏資料' }));
    await waitFor(() => expect(screen.getByText('已複製去敏資料')).toBeInTheDocument());
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
  });
});
