/**
 * File: data_import_hcm_result_page.test.tsx
 * Description: 驗證DataImport只顯示每案最新未解異常，並提供符合原因的處理入口。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { DataImportPage } from '../pages/DataImportPage';

const phoneTask = {
  occurrence_identity: 'warning-phone', owning_lane: 'hcm', logical_code: 'HCM-FIELD-002',
  field_path: '行動電話', subject: '115000002', issue_codes: ['hcm_field_invalid:行動電話'],
  tracking_status: 'open' as const, tracking_version: 1, evidence_reference: null,
  display_message: '行動電話格式錯誤', navigation_action: 'hcm_import_center' as const,
};

describe('DataImport HCM result review', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([
      phoneTask,
      { ...phoneTask, occurrence_identity: 'warning-old', display_message: '較舊異常' },
      { ...phoneTask, occurrence_identity: 'other-lane', owning_lane: 'finance_import', subject: 'bank-row' },
    ]);
  });

  it('renders only the latest active HCM problem for each case', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText('案件 115000002')).toBeInTheDocument());
    expect(screen.getByText('行動電話格式錯誤')).toBeInTheDocument();
    expect(screen.queryByText('較舊異常')).not.toBeInTheDocument();
    expect(screen.queryByText('bank-row')).not.toBeInTheDocument();
    expect(screen.getByText('HCM 目前待處理異常')).toBeInTheDocument();
    expect(screen.queryByText(/hcm_field_invalid/)).not.toBeInTheDocument();
    expect(anomalyQueryClient.queryImportWarningTasks).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="imports.hcm-current.apply"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="imports.hcm-current.apply-guidance"]'))
      .toHaveTextContent('預覽成功後才能確認匯入。');
  });

  it('refreshes active anomalies and opens the controlled correction referral', async () => {
    vi.spyOn(anomalyQueryClient, 'queryImportWarningReferral').mockResolvedValue({
      occurrence_identity: 'warning-phone', expected_version: 1, owning_lane: 'hcm',
      logical_code: 'HCM-FIELD-002', field_path: '行動電話', subject: '115000002',
      display_message: '行動電話格式錯誤', navigation_action: 'hcm_import_center',
      action_kind: 'owner_preview_apply', target_command: 'preview_hcm_resubmission', review_identity: 'review-2',
    });
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText('案件 115000002')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '重新整理結果' }));
    await waitFor(() => expect(anomalyQueryClient.queryImportWarningTasks).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: '提交受控修正' }));
    await waitFor(() => expect(screen.getByText('修正案件 115000002')).toBeInTheDocument());
    expect(anomalyQueryClient.queryImportWarningReferral).toHaveBeenCalledTimes(1);
  });

  it('shows the empty state when there are no active HCM anomalies', async () => {
    vi.mocked(anomalyQueryClient.queryImportWarningTasks).mockResolvedValue([]);
    render(<DataImportPage />);
    await waitFor(() => expect(screen.getByText('目前沒有待處理的 HCM 異常。')).toBeInTheDocument());
  });
});
