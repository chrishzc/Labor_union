/** Data Import remains a four-card entry and does not load persistent HCM anomalies. */
import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import { DataImportPage } from '../pages/DataImportPage';

vi.mock('../pages/CurrentAnomaliesPage', () => ({ CurrentAnomaliesPage: () => null }));

function authenticate(): void {
  sessionClient.setSession('data-import-entry-token', {
    id: 1,
    username: 'data-import-entry-admin',
    display_name: '資料匯入驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

const ACTIVE_PREVIEW_CONTROL_IDS = [
  'imports.hcm-current.preview',
  'imports.client-beclass.preview',
  'imports.staff-historical.preview',
  'imports.historic-orders.preview',
] as const;

const ACTIVE_APPLY_CONTROL_IDS = [
  'imports.hcm-current.apply',
  'imports.client-beclass.apply',
  'imports.staff-historical.apply',
  'imports.historic-orders.apply',
] as const;

describe('Data Import entry', () => {
  afterEach(() => {
    sessionClient.clearSession();
    window.history.replaceState(null, '', '#');
    vi.restoreAllMocks();
  });

  it('does not render or query the retired lower HCM anomaly workbench', async () => {
    authenticate();
    window.history.replaceState(null, '', '#data-import');
    const requests: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(String(input), 'http://admin.test').pathname;
      requests.push(path);
      if (path === SYSTEM_STATUS_ENDPOINT) {
        return new Response(JSON.stringify({
          success: true, message: '成功取得系統效能快照', error: null,
          data: { started_at: '2026-08-20T01:02:03Z', request_count: 1, average_response_time_ms: 1, p50_response_time_upper_bound_ms: 1, p95_response_time_upper_bound_ms: 1, maximum_response_time_ms: 1 },
        }), { status: 200, headers: { 'content-type': 'application/json' } });
      }
      throw new Error(`Unexpected API path: ${path}`);
    });

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('📥 批次資料匯入中心')).toBeInTheDocument());

    expect(screen.queryByText('HCM 目前待處理異常')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新整理結果' })).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="imports.hcm-results.open"]')).toBeNull();
    expect(requests).not.toContain('/api/v1/import-warning-tracking/tasks');
  });

  it('exposes four Preview controls and explains why Preview or Apply cannot run yet', () => {
    render(<DataImportPage />);

    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeInTheDocument();
    for (const [index, controlId] of ACTIVE_PREVIEW_CONTROL_IDS.entries()) {
      fireEvent.click(screen.getByRole('button', { name: ['HCM', '客戶', '月嫂', '歷史訂單'][index] }));
      const control = document.querySelector(`[data-control-id="${controlId}"]`);
      expect(control, controlId).toBeInTheDocument();
      expect(control, controlId).toBeDisabled();
      expect(screen.getByText('請先選擇 .xlsx 工作簿。')).toBeInTheDocument();
      expect(screen.getByText('預覽成功後才能確認匯入。')).toBeInTheDocument();
    }
    for (const controlId of ACTIVE_APPLY_CONTROL_IDS) {
      expect(document.querySelector(`[data-control-id="${controlId}"]`), controlId).toBeNull();
    }
  });
});
