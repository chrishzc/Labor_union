/**
 * File: data_import_hcm_preview_flow.test.tsx
 * Description: 驗證舊HCM檔案Preview UI已退役，頁面只查詢匯入結果且不提供upload或Apply。
 */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { DataImportPage } from '../pages/DataImportPage';

describe('DataImport HCM Preview retirement compatibility', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmImportResultClient, 'query').mockResolvedValue({ items: [], next_cursor: null });
  });

  it('uses one result GET and exposes no file upload or Preview controls', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText(/目前沒有可查詢的 HCM 匯入receipt/)).toBeInTheDocument());
    expect(hcmImportResultClient.query).toHaveBeenCalledTimes(1);
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeNull();
    expect(document.querySelector('[data-control-id="imports.hcm-current.preview"]')).toBeNull();
    expect(document.querySelector('[data-control-id="imports.hcm-current.apply"]')).toBeNull();
  });

  it('keeps the result refresh as GET-only presentation', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(hcmImportResultClient.query).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: '重新整理結果' })).toBeEnabled();
    expect(screen.queryByText(/執行 Preview/)).not.toBeInTheDocument();
    expect(screen.queryByText(/確認寫入資料庫/)).not.toBeInTheDocument();
  });
});
