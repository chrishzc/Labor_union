/**
 * File: anomalies_detail_referral_flow.test.tsx
 * Description: 驗證 lazy detail/referral GET、Drawer stale 與 deferred controls。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_IMPORT_WARNING_TASK_HCM,
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';

describe('Anomalies lazy Drawer query flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([
      VALID_ANOMALY_SUMMARY_1,
    ]);
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([
      VALID_IMPORT_WARNING_TASK_HCM,
    ]);
    vi.spyOn(anomalyQueryClient, 'queryAnomalyDetail').mockResolvedValue(
      VALID_ANOMALY_DETAIL_VIEW
    );
    vi.spyOn(anomalyQueryClient, 'queryImportWarningReferral').mockResolvedValue(
      VALID_IMPORT_WARNING_REFERRAL_VIEW
    );
  });

  it('does not query detail until anomaly Drawer opens', async () => {
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument());
    expect(anomalyQueryClient.queryAnomalyDetail).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /排查處置抽屜 ➔/ }));
    await waitFor(() => expect(anomalyQueryClient.queryAnomalyDetail).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/後端異常詳情/)).toBeInTheDocument();
    expect(screen.getByText(/reopen：v1 → v2/)).toBeInTheDocument();
  });

  it('queries warning referral lazily and keeps transition disabled', async () => {
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument());
    expect(anomalyQueryClient.queryImportWarningReferral).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '查看警示詳情' }));
    await waitFor(() => expect(anomalyQueryClient.queryImportWarningReferral).toHaveBeenCalledTimes(1));
    expect(screen.getByText('owner_preview_apply')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '狀態變更尚未開放' })).toBeDisabled();
  });

  it('closing Drawer aborts the active request and does not leave a stale Drawer', async () => {
    let resolveDetail: ((value: typeof VALID_ANOMALY_DETAIL_VIEW) => void) | undefined;
    vi.mocked(anomalyQueryClient.queryAnomalyDetail).mockImplementation(
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
    expect(screen.queryByText(/reopen：v1 → v2/)).not.toBeInTheDocument();
  });
});
