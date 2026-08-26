/**
 * File: data_import_no_fake_mutation.test.tsx
 * Description: 驗證退役／跨域匯入不再佔用操作頁，active Apply只會在成功Preview後出現。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { DataImportPage } from '../pages/DataImportPage';

describe('DataImportPage zero fake mutation gate', () => {
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
  const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false);

  beforeEach(() => {
    alertSpy.mockClear();
    confirmSpy.mockClear();
    vi.spyOn(hcmImportResultClient, 'query').mockResolvedValue({ items: [], next_cursor: null });
  });

  it('does not render retired HCM historical or cross-domain bank controls', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText(/目前沒有可查詢的 HCM 匯入結果/)).toBeInTheDocument());
    for (const id of ['imports.hcm-historical.preview', 'imports.hcm-historical.apply', 'imports.bank-statements.preview', 'imports.bank-statements.apply']) {
      expect(document.querySelector(`[data-control-id="${id}"]`), id).toBeNull();
    }
    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('exposes active Preview but no Apply control before a successful Preview', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText(/目前沒有可查詢的 HCM 匯入結果/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /工作簿資料匯入/i }));
    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="imports.hcm-current.preview"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="imports.hcm-current.apply"]')).toBeNull();
    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});
