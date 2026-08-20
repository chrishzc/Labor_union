/**
 * File: data_browser_no_fake_mutation.test.tsx
 * Description: 驗證 Data Browser correction/PATCH controls 原生鎖定。
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

  it('keeps PATCH and source correction controls disabled with zero non-GET', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    render(<DataBrowserPage />);
    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /檢視去敏詳情/ }));

    for (const id of [
      'data-browser.patch',
      'data-browser.source-correction.preview',
      'data-browser.source-correction.apply',
    ]) {
      const control = document.querySelector(`[data-control-id="${id}"]`);
      expect(control).toBeDisabled();
      if (control) fireEvent.click(control);
    }
    expect(alertSpy).not.toHaveBeenCalled();
    expect(fetchSpy.mock.calls.filter((call) => call[1]?.method && call[1]?.method !== 'GET')).toHaveLength(0);
  });
});
