/**
 * File: data_import_hcm_result_page.test.tsx
 * Description: 驗證DataImport顯示新增、問題、replay與歷史摘要，且Apply依Preview結果顯示。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { DataImportPage } from '../pages/DataImportPage';
import { detailedHcmResult } from './fixtures/hcm_import_result_fixtures';

describe('DataImport HCM result review', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmImportResultClient, 'query').mockResolvedValue({ items: [detailedHcmResult], next_cursor: null });
  });

  it('renders new orders, problems and replay from one recent-results query', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText('115000001')).toBeInTheDocument());
    expect(screen.getAllByText('115000002').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/行動電話/).length).toBeGreaterThan(0);
    expect(screen.getByText('115000003')).toBeInTheDocument();
    expect(screen.getByText('HCM 最近匯入紀錄與問題檢查').closest('.sr-only')).toBeNull();
    expect(hcmImportResultClient.query).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="imports.hcm-current.apply"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="imports.hcm-current.apply-guidance"]'))
      .toHaveTextContent('預覽成功後才能確認匯入。');
  });

  it('refresh costs one GET and problem action returns focus to HCM import', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText('115000001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '重新整理結果' }));
    await waitFor(() => expect(hcmImportResultClient.query).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: '回到 HCM 工作簿修正' }));
    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toHaveFocus();
    expect(hcmImportResultClient.query).toHaveBeenCalledTimes(2);
  });

  it('shows a neutral legacy summary instead of an empty-success claim', async () => {
    vi.mocked(hcmImportResultClient.query).mockResolvedValue({ items: [{ ...detailedHcmResult, row_outcomes_available: false, legacy_summary_only: true, row_outcomes: [] }], next_cursor: null });
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText(/歷史匯入摘要；本批次統計如上/)).toBeInTheDocument());
    expect(screen.queryByText('本批次沒有新增訂單。')).not.toBeInTheDocument();
  });
});
