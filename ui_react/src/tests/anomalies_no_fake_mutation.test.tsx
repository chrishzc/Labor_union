/**
 * File: anomalies_no_fake_mutation.test.tsx
 * Description: 驗證 Claim／Resolve／root repair 仍鎖定，query-only 互動不產生假 mutation。
 */

import { describe, it, expect, vi, beforeEach, type MockInstance } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_ANOMALY_SUMMARY_2,
  VALID_ANOMALY_SUMMARY_3,
  VALID_IMPORT_WARNING_TASK_HCM,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';
import {
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
} from './fixtures/anomalies/anomaly_detail_contract_fixtures';

describe('Anomalies no fake root mutation verification suite', () => {
  let alertSpy: MockInstance;
  let confirmSpy: MockInstance;
  let promptSpy: MockInstance;
  let fetchSpy: MockInstance;

  beforeEach(() => {
    vi.restoreAllMocks();

    alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false);
    promptSpy = vi.spyOn(window, 'prompt').mockImplementation(() => null);
    fetchSpy = vi.spyOn(globalThis, 'fetch');

    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([
      VALID_ANOMALY_SUMMARY_1,
      VALID_ANOMALY_SUMMARY_2,
      VALID_ANOMALY_SUMMARY_3,
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

  it('verifies claim buttons on anomaly cards are strictly disabled and trigger no side effects', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });

    const claimButtons = screen.getAllByRole('button', { name: /🔵 認領此案/ });
    expect(claimButtons.length).toBe(3);

    for (const btn of claimButtons) {
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute('data-control-id', 'anomalies.card.claim');
      expect(btn).toHaveAttribute('title', expect.stringContaining('[查詢模式]'));

      // Attempt click
      fireEvent.click(btn);
    }

    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it('keeps generic Resolve disabled when no registered Finance correction form exists', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });

    const drawerButtons = screen.getAllByRole('button', { name: /排查處置抽屜 ➔/ });
    await act(async () => {
      fireEvent.click(drawerButtons[0]);
    });

    await waitFor(() => {
      expect(screen.getByText(/⚠️ 異常排查與修復處置/)).toBeInTheDocument();
    });

    expect(screen.getByText('此異常沒有已註冊的 Finance Import correction 表單；請依 owning Domain 的 typed action 處理。')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).toBeNull();

    // Check resolve button
    const resolveBtn = screen.getByRole('button', { name: /確認排除異常/ });
    expect(resolveBtn).toBeDisabled();
    expect(resolveBtn).toHaveAttribute('data-control-id', 'anomalies.drawer.resolve');
    expect(resolveBtn).toHaveAttribute('title', expect.stringContaining('通用 Resolve'));

    // Attempt click
    fireEvent.click(resolveBtn);

    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it('guarantees zero non-GET requests and zero dialog invocations across query-only anomaly interactions', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });

    // Category click
    const schedTab = screen.getByRole('button', { name: '排班調度' });
    await act(async () => {
      fireEvent.click(schedTab);
    });

    // Status filter click
    const openPill = screen.getByRole('button', { name: /🟡 待處理/ });
    await act(async () => {
      fireEvent.click(openPill);
    });

    // Open drawer
    const drawerBtn = screen.getByRole('button', { name: /排查處置抽屜 ➔/ });
    await act(async () => {
      fireEvent.click(drawerBtn);
    });

    // Close drawer
    const closeBtn = screen.getByRole('button', { name: '關閉' });
    await act(async () => {
      fireEvent.click(closeBtn);
    });

    // Verify dialogs
    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(promptSpy).not.toHaveBeenCalled();

    // Verify non-GET calls
    const nonGetCalls = fetchSpy.mock.calls.filter((call) => {
      const init = call[1];
      const method = init?.method?.toUpperCase();
      return method && method !== 'GET';
    });
    expect(nonGetCalls.length).toBe(0);
  });
});
