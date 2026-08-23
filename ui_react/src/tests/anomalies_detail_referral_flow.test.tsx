/**
 * File: anomalies_detail_referral_flow.test.tsx
 * Description: 驗證 lazy detail/referral GET、Drawer stale 與 deferred controls。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_IMPORT_WARNING_TASK_HCM,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';
import {
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
} from './fixtures/anomalies/anomaly_detail_contract_fixtures';

describe('Anomalies lazy Drawer query flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([
      VALID_ANOMALY_SUMMARY_1,
    ]);
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([
      VALID_IMPORT_WARNING_TASK_HCM,
    ]);
    vi.spyOn(anomalyDetailClient, 'queryAnomalyDetail').mockResolvedValue(
      VALID_ANOMALY_DETAIL_VIEW
    );
    vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockResolvedValue(
      VALID_ANOMALY_RECOVERY_CONTEXT_VIEW
    );
    vi.spyOn(anomalyQueryClient, 'queryImportWarningReferral').mockResolvedValue(
      VALID_IMPORT_WARNING_REFERRAL_VIEW
    );
  });

  it('does not query detail until anomaly Drawer opens', async () => {
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument());
    expect(anomalyDetailClient.queryAnomalyDetail).not.toHaveBeenCalled();
    expect(anomalyDetailClient.queryAnomalyRecovery).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /排查處置抽屜 ➔/ }));
    await waitFor(() => expect(anomalyDetailClient.queryAnomalyDetail).toHaveBeenCalledTimes(1));
    expect(anomalyDetailClient.queryAnomalyRecovery).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/後端異常詳情/)).toBeInTheDocument();
    await waitFor(() => {
      expect(document.querySelector('[data-surface-id="anomalies.drawer.evidence"]')).toHaveTextContent('amount_delta_ntd');
      expect(screen.getByText(/預覽財務投影修復/)).toBeInTheDocument();
    });
  });

  it('queries warning referral lazily and keeps root repair disabled', async () => {
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument());
    expect(anomalyQueryClient.queryImportWarningReferral).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '查看警示詳情' }));
    await waitFor(() => expect(anomalyQueryClient.queryImportWarningReferral).toHaveBeenCalledTimes(1));
    expect(screen.getByText('owner_preview_apply')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Claim／Resolve 與來源修復仍未開放' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '開啟追蹤狀態變更' })).toBeEnabled();
  });

  it('保留成功 detail，並將 recovery 404 限縮為局部錯誤', async () => {
    vi.mocked(anomalyDetailClient.queryAnomalyRecovery).mockRejectedValue(new Error('找不到異常 recovery context。'));
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /排查處置抽屜 ➔/ }));
    await waitFor(() => expect(document.querySelector('[data-surface-id="anomalies.drawer.evidence"]')).toHaveTextContent('amount_delta_ntd'));
    expect(screen.getByText('找不到異常 recovery context。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /確認排除異常/ })).toBeDisabled();
  });

  it('closing Drawer aborts the active request and does not leave a stale Drawer', async () => {
    let resolveDetail: ((value: typeof VALID_ANOMALY_DETAIL_VIEW) => void) | undefined;
    vi.mocked(anomalyDetailClient.queryAnomalyDetail).mockImplementation(
      () => new Promise((resolve) => { resolveDetail = resolve; })
    );
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /排查處置抽屜 ➔/ }));
    expect(screen.getByText(/異常排查與修復處置/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(screen.queryByText(/異常排查與修復處置/)).not.toBeInTheDocument();
    resolveDetail?.(VALID_ANOMALY_DETAIL_VIEW);
    await Promise.resolve();
    expect(screen.queryByText(/amount_delta_ntd/)).not.toBeInTheDocument();
  });
});
