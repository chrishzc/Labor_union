/**
 * File: data_browser_request_budget.test.tsx
 * Description: 驗證 Data Browser tab/search/Drawer request budget。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DataBrowserPage } from '../pages/DataBrowserPage';
import { dataBrowserQueryClient } from '../api/data_browser/data_browser_query_client';
import { VALID_DATA_BROWSER_PAGE } from './fixtures/data_browser/data_browser_query_contract_fixtures';

describe('Data Browser request budget', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(dataBrowserQueryClient, 'querySource').mockImplementation(async (params) => ({
      ...VALID_DATA_BROWSER_PAGE,
      source_id: params.sourceId,
      items: VALID_DATA_BROWSER_PAGE.items.map((item) => ({
        ...item,
        source_id: params.sourceId,
      })),
    }));
  });

  it('uses one GET-equivalent client call per source/search and zero for Drawer', async () => {
    render(<DataBrowserPage />);
    await waitFor(() => expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: /客戶歷史檔案/ }));
    await waitFor(() => expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(2));

    fireEvent.change(screen.getByPlaceholderText(/搜尋案件編號/), { target: { value: '台北市' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢' }));
    await waitFor(() => expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(3));

    fireEvent.click(screen.getByRole('button', { name: /檢視去敏詳情/ }));
    expect(dataBrowserQueryClient.querySource).toHaveBeenCalledTimes(3);
  });
});
