/**
 * File: anomalies_page_real_data.test.tsx
 * Description: 驗證 Anomalies page 的唯讀清單與 Drawer。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_ANOMALY_SUMMARY_2,
  VALID_ANOMALY_SUMMARY_3,
  VALID_IMPORT_WARNING_TASK_HCM,
  VALID_IMPORT_WARNING_TASK_BECLASS_CLI,
  VALID_IMPORT_WARNING_TASK_HISTORICAL,
  VALID_IMPORT_WARNING_TASK_BECLASS_STF,
  VALID_IMPORT_WARNING_TASK_FINANCE,
  VALID_IMPORT_WARNING_TASK_AUTO_RESOLVED,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';
import {
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
} from './fixtures/anomalies/anomaly_detail_contract_fixtures';

describe('AnomaliesPage Real Data Integration Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([
      VALID_ANOMALY_SUMMARY_1,
      VALID_ANOMALY_SUMMARY_2,
      VALID_ANOMALY_SUMMARY_3,
    ]);

    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([
      VALID_IMPORT_WARNING_TASK_HCM,
      VALID_IMPORT_WARNING_TASK_BECLASS_CLI,
      VALID_IMPORT_WARNING_TASK_HISTORICAL,
      VALID_IMPORT_WARNING_TASK_BECLASS_STF,
      VALID_IMPORT_WARNING_TASK_FINANCE,
      VALID_IMPORT_WARNING_TASK_AUTO_RESOLVED,
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

  it('renders anomaly cards and import warning tasks from live queries', async () => {
    render(<AnomaliesPage />);

    expect(screen.getByText(/正在載入即時異常數據/)).toBeInTheDocument();
    expect(screen.getByText(/正在載入匯入警示追蹤數據/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
      expect(screen.getByText('FINANCE-002')).toBeInTheDocument();
      expect(screen.getByText('IMPORT-003')).toBeInTheDocument();
      expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument();
      expect(screen.getByText('BECLASS-CLI-002')).toBeInTheDocument();
    });

    // Check gap text on cards
    const gapTitles = screen.getAllByText('目前 typed view 未納入摘要欄位');
    expect(gapTitles.length).toBeGreaterThanOrEqual(3);

    for (const surfaceId of [
      'anomalies.page',
      'anomalies.kpis',
      'anomalies.category-filters',
      'anomalies.status-filters',
      'anomalies.list',
      'anomalies.import-warnings',
    ]) {
      expect(
        document.querySelector(`[data-surface-id="${surfaceId}"]`)
      ).toBeVisible();
    }
  });

  it('displays accurate KPI counts based on live anomalies', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });

    // VALID_ANOMALY_SUMMARY_1: blocking + open -> critical=1, open=1
    // VALID_ANOMALY_SUMMARY_2: warning + claimed -> warning=1, claimed=1
    // VALID_ANOMALY_SUMMARY_3: warning + resolved -> resolved (not active warning)
    const kpiValues = screen.getAllByText('1 筆');
    expect(kpiValues.length).toBe(4); // critical, warning, open, claimed all equal 1
  });

  it('filters anomaly cards by domain category tabs', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
      expect(screen.getByText('FINANCE-002')).toBeInTheDocument();
      expect(screen.getByText('IMPORT-003')).toBeInTheDocument();
    });

    // Filter by '排班調度'
    const schedTab = screen.getByRole('button', { name: '排班調度' });
    await act(async () => {
      fireEvent.click(schedTab);
    });

    expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    expect(screen.queryByText('FINANCE-002')).not.toBeInTheDocument();
    expect(screen.queryByText('IMPORT-003')).not.toBeInTheDocument();

    // Filter by '客戶帳務'
    const finTab = screen.getByRole('button', { name: '客戶帳務' });
    await act(async () => {
      fireEvent.click(finTab);
    });

    expect(screen.queryByText('SCHEDULE-001')).not.toBeInTheDocument();
    expect(screen.getByText('FINANCE-002')).toBeInTheDocument();
    expect(screen.queryByText('IMPORT-003')).not.toBeInTheDocument();

    // Reset to '全部 (3)'
    const allTab = screen.getByRole('button', { name: /全部 \(3\)/ });
    await act(async () => {
      fireEvent.click(allTab);
    });

    expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    expect(screen.getByText('FINANCE-002')).toBeInTheDocument();
    expect(screen.getByText('IMPORT-003')).toBeInTheDocument();
  });

  it('filters anomaly cards by status filter pills', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });

    // Filter by open
    const openPill = screen.getByRole('button', { name: /🟡 待處理 \(1\)/ });
    await act(async () => {
      fireEvent.click(openPill);
    });

    expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    expect(screen.queryByText('FINANCE-002')).not.toBeInTheDocument();
    expect(screen.queryByText('IMPORT-003')).not.toBeInTheDocument();

    // Filter by claimed
    const claimedPill = screen.getByRole('button', { name: /🔵 已認領 \(1\)/ });
    await act(async () => {
      fireEvent.click(claimedPill);
    });

    expect(screen.queryByText('SCHEDULE-001')).not.toBeInTheDocument();
    expect(screen.getByText('FINANCE-002')).toBeInTheDocument();
    expect(screen.queryByText('IMPORT-003')).not.toBeInTheDocument();

    // Filter by resolved
    const resolvedPill = screen.getByRole('button', { name: /✅ 已排除/ });
    await act(async () => {
      fireEvent.click(resolvedPill);
    });

    expect(screen.queryByText('SCHEDULE-001')).not.toBeInTheDocument();
    expect(screen.queryByText('FINANCE-002')).not.toBeInTheDocument();
    expect(screen.getByText('IMPORT-003')).toBeInTheDocument();
  });

  it('opens Drawer and displays anomaly metadata, root evidence gap, and staff calendar navigation link', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });

    const drawerButtons = screen.getAllByRole('button', { name: /排查處置抽屜 ➔/ });
    // Click drawer for SCHEDULE-001 (index 0)
    await act(async () => {
      fireEvent.click(drawerButtons[0]);
    });

    await waitFor(() => {
      expect(screen.getByText(/⚠️ 異常排查與修復處置/)).toBeInTheDocument();
    });

    for (const surfaceId of [
      'anomalies.drawer',
      'anomalies.drawer.root-evidence',
      'anomalies.drawer.recovery',
    ]) {
      expect(
        document.querySelector(`[data-surface-id="${surfaceId}"]`)
      ).toBeVisible();
    }
    expect(
      screen.queryByText(VALID_ANOMALY_SUMMARY_1.fingerprint)
    ).not.toBeInTheDocument();

    expect(screen.getByText(/領域 \(Domain\)：/)).toBeInTheDocument();
    expect(screen.getByText(/資料版本：/)).toBeInTheDocument();
    expect(screen.getByText(/條件作用中：/)).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="anomalies.drawer.root-evidence"]')).toHaveTextContent('finance_import_row_identity');

    // Check staff calendar navigation link
    const navLink = screen.getByRole('link', { name: /前往排班調度 ➔/ });
    expect(navLink).toBeInTheDocument();
    expect(navLink).toHaveAttribute('href', '#scheduling');
    expect(screen.getByText(/目標日期: 2026-08-20/)).toBeInTheDocument();
    expect(screen.getByText(/月嫂 ID: #14/)).toBeInTheDocument();
  });

  it('opens Drawer for anomaly without calendar navigation and renders gap fallback', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('FINANCE-002')).toBeInTheDocument();
    });

    const drawerButtons = screen.getAllByRole('button', { name: /排查處置抽屜 ➔/ });
    // Click drawer for FINANCE-002 (index 1)
    await act(async () => {
      fireEvent.click(drawerButtons[1]);
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /FINANCE-002/ })).toBeInTheDocument();
    });

    expect(screen.queryByRole('link', { name: /前往排班調度 ➔/ })).not.toBeInTheDocument();
  });

  it('renders import warning task list with lane badges, status labels, issue codes, and navigation link', async () => {
    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument();
      expect(screen.getByText('BECLASS-CLI-002')).toBeInTheDocument();
      expect(screen.getByText('HIST-ORD-003')).toBeInTheDocument();
    });

    // Check HCM Task content
    const hcmBadges = screen.getAllByText('HCM 匯入');
    expect(hcmBadges.length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText('身分證字號')).toBeInTheDocument();
    expect(screen.getByText('A12****789')).toBeInTheDocument();
    expect(screen.getByText('hcm_field_missing:身分證字號')).toBeInTheDocument();
    expect(screen.getByText('缺少身分證字號')).toBeInTheDocument();

    // Check navigation link to data import
    const importNavLinks = screen.getAllByRole('link', { name: /前往匯入中心 ➔/ });
    expect(importNavLinks.length).toBeGreaterThanOrEqual(1);
    expect(importNavLinks[0]).toHaveAttribute('href', '#data-import');
  });

  it('handles query errors independently with retry functionality', async () => {
    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockRejectedValueOnce(new Error('網路連線逾時'));

    render(<AnomaliesPage />);

    await waitFor(() => {
      expect(screen.getByText(/載入異常資料失敗：網路連線逾時/)).toBeInTheDocument();
    });

    // Import warnings should still load successfully
    expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument();

    // Click retry for anomalies
    const retryBtn = screen.getByRole('button', { name: /重試/ });
    await act(async () => {
      fireEvent.click(retryBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
    });
  });
});
