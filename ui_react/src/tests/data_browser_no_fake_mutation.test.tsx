/**
 * File: data_browser_no_fake_mutation.test.tsx
 * Description: 驗證 Data Browser 不暴露未實作的 correction/PATCH controls。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DataBrowserPage } from '../pages/DataBrowserPage';
import { dataBrowserQueryClient } from '../api/data_browser/data_browser_query_client';
import { VALID_DATA_BROWSER_PAGE } from './fixtures/data_browser/data_browser_query_contract_fixtures';

describe('Data Browser zero fake mutation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(dataBrowserQueryClient, 'querySource').mockResolvedValue(VALID_DATA_BROWSER_PAGE);
  });

  it('shows the read-only business boundary without fake mutation controls', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    render(<DataBrowserPage />);
    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /檢視詳情/ }));

    for (const id of [
      'data-browser.patch',
      'data-browser.source-correction.preview',
      'data-browser.source-correction.apply',
    ]) {
      const control = document.querySelector(`[data-control-id="${id}"]`);
      expect(control).not.toBeInTheDocument();
    }
    expect(screen.getByText(/此頁只提供完整資料查詢/)).toBeInTheDocument();
    expect(alertSpy).not.toHaveBeenCalled();
    expect(fetchSpy.mock.calls.filter((call) => call[1]?.method && call[1]?.method !== 'GET')).toHaveLength(0);
  });
});
