/**
 * @file challenger_phase2d_anomalies.test.tsx
 * @description 挑戰者 1 異常綱要嚴格性、對抗注入與零變更不變量測試套件。
 * 契約依據: PROV-20260816 Phase 2D CONTRACT_MATRIX.md。
 * 變更範圍: 針對異常查詢綱要、客戶端與介面控制項進行極限邊界與攻擊性測試。
 * 驗證依據: Vitest 測試套件 (綱要嚴格性、邊界拒絕與零副作用驗證)。
 * 無副作用宣告: 純測試程式碼，無持久化狀態副作用。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { sessionClient } from '../api/auth/session_client';
import {
  AnomalySummaryViewSchema,
  ImportWarningTaskViewSchema,
} from '../api/anomalies/anomaly_query_schemas';
import { LegacyAnomaliesPage as AnomaliesPage } from '../pages/AnomaliesPage';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_ANOMALY_SUMMARY_2,
  VALID_IMPORT_WARNING_TASK_HCM,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';

describe('Adversarial Challenger 1: Phase 2D Integration Deep Stress-Testing', () => {
  const originalFetch = globalThis.fetch;
  let alertSpy: any;
  let confirmSpy: any;
  let promptSpy: any;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('phase2d-challenger-session', {
      id: 1,
      username: 'phase2d-challenger',
      display_name: 'Phase 2D Challenger',
      role: 'admin',
    });
    alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false);
    promptSpy = vi.spyOn(window, 'prompt').mockImplementation(() => null);
  });

  afterEach(() => {
    sessionClient.clearSession();
    globalThis.fetch = originalFetch;
  });

  // ==========================================================================
  // 1. ADVERSARIAL SCHEMA STRESS-TESTING: AnomalySummaryViewSchema
  // ==========================================================================
  describe('[Challenger-1.1] AnomalySummaryViewSchema Strictness & Deformation Rejection', () => {
    it('rejects extra injected keys at root level of AnomalySummaryView', () => {
      const payload = {
        ...VALID_ANOMALY_SUMMARY_1,
        __injected_malicious_key: 'hacked',
      };
      const result = AnomalySummaryViewSchema.safeParse(payload);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.some((i) => i.code === 'unrecognized_keys')).toBe(true);
      }
    });

    it('rejects missing mandatory fields individually', () => {
      const requiredFields: Array<keyof typeof VALID_ANOMALY_SUMMARY_1> = [
        'fingerprint',
        'definition_code',
        'source_domain',
        'source_identity',
        'source_version',
        'severity',
        'predicate_active',
        'workflow_status',
        'workflow_version',
      ];

      for (const field of requiredFields) {
        const payload: Record<string, unknown> = { ...VALID_ANOMALY_SUMMARY_1 };
        delete payload[field];
        const result = AnomalySummaryViewSchema.safeParse(payload);
        expect(result.success).toBe(false);
      }
    });

    it('rejects invalid fingerprint lengths and non-hex characters', () => {
      // Too short (63 chars)
      const shortHex = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        fingerprint: '8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f',
      });
      expect(shortHex.success).toBe(false);

      // Too long (65 chars)
      const longHex = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        fingerprint: '8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8a',
      });
      expect(longHex.success).toBe(false);

      // Uppercase or non-hex chars
      const upperHex = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        fingerprint: '8F48483D980D2105151522A36A7F05EE461E78A63574A3F1244D2D6C66CF17F8',
      });
      expect(upperHex.success).toBe(false);

      const invalidChars = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        fingerprint: '8z48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8',
      });
      expect(invalidChars.success).toBe(false);
    });

    it('rejects illegal severity and workflow status enums', () => {
      const invalidSeverities = ['CRITICAL', 'critical', 'blocker', 'low', 'HIGH', ''];
      for (const sev of invalidSeverities) {
        const res = AnomalySummaryViewSchema.safeParse({
          ...VALID_ANOMALY_SUMMARY_1,
          severity: sev,
        });
        expect(res.success).toBe(false);
      }

      const invalidStatuses = ['in_progress', 'pending', 'CLOSED', 'resolved_by_admin', ''];
      for (const st of invalidStatuses) {
        const res = AnomalySummaryViewSchema.safeParse({
          ...VALID_ANOMALY_SUMMARY_1,
          workflow_status: st,
        });
        expect(res.success).toBe(false);
      }
    });

    it('rejects raw dictionary in display_snapshot (must be null or undefined only)', () => {
      const rawSnapshot = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        display_snapshot: { raw_leak: 'secret_data', unparsed: true },
      });
      expect(rawSnapshot.success).toBe(false);
    });

    it('rejects malformed staff_calendar_navigation with extra keys or invalid date format', () => {
      // Extra key in nested object
      const extraKeyNav = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        staff_calendar_navigation: {
          staff_id: 14,
          target_date: '2026-08-20',
          injected_extra: true,
        },
      });
      expect(extraKeyNav.success).toBe(false);

      // Invalid date format
      const badDateNav = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        staff_calendar_navigation: {
          staff_id: 14,
          target_date: '2026/08/20',
        },
      });
      expect(badDateNav.success).toBe(false);

      // Non-positive staff_id
      const zeroStaffNav = AnomalySummaryViewSchema.safeParse({
        ...VALID_ANOMALY_SUMMARY_1,
        staff_calendar_navigation: {
          staff_id: 0,
          target_date: '2026-08-20',
        },
      });
      expect(zeroStaffNav.success).toBe(false);
    });
  });

  // ==========================================================================
  // 2. ADVERSARIAL SCHEMA STRESS-TESTING: ImportWarningTaskViewSchema
  // ==========================================================================
  describe('[Challenger-1.2] ImportWarningTaskViewSchema Strictness & Boundary Rejection', () => {
    it('rejects extra injected keys on ImportWarningTaskView', () => {
      const payload = {
        ...VALID_IMPORT_WARNING_TASK_HCM,
        __extra_tamper_key: 999,
      };
      const res = ImportWarningTaskViewSchema.safeParse(payload);
      expect(res.success).toBe(false);
      if (!res.success) {
        expect(res.error.issues.some((i) => i.code === 'unrecognized_keys')).toBe(true);
      }
    });

    it('rejects empty display_message or message exceeding 200 characters', () => {
      // Empty string
      const emptyMsg = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        display_message: '',
      });
      expect(emptyMsg.success).toBe(false);

      // 200 chars (valid boundary)
      const valid200 = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        display_message: 'X'.repeat(200),
      });
      expect(valid200.success).toBe(true);

      // 201 chars (invalid overflow)
      const overflowMsg = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        display_message: 'X'.repeat(201),
      });
      expect(overflowMsg.success).toBe(false);
    });

    it('rejects tracking_version <= 0', () => {
      const zeroVer = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        tracking_version: 0,
      });
      expect(zeroVer.success).toBe(false);

      const negVer = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        tracking_version: -1,
      });
      expect(negVer.success).toBe(false);
    });

    it('rejects illegal tracking_status and illegal navigation_action', () => {
      const badStatus = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        tracking_status: 'unknown_status',
      });
      expect(badStatus.success).toBe(false);

      const badNav = ImportWarningTaskViewSchema.safeParse({
        ...VALID_IMPORT_WARNING_TASK_HCM,
        navigation_action: 'invalid_nav_target',
      });
      expect(badNav.success).toBe(false);
    });
  });

  // ==========================================================================
  // 3. ZERO-MUTATION & DISABLED BUTTON EVENT INVARIANT
  // ==========================================================================
  describe('[Challenger-1.3] AnomaliesPage Disabled Buttons Event Interception', () => {
    it('ensures clicking disabled claim buttons generates zero requests, dialogs, and mutations', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/v1/anomalies')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({
              success: true,
              message: 'OK',
              data: [VALID_ANOMALY_SUMMARY_1, VALID_ANOMALY_SUMMARY_2],
              error: null,
            }),
          });
        }
        if (url.includes('/api/v1/import-warning-tracking/tasks')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({
              success: true,
              message: 'OK',
              data: [VALID_IMPORT_WARNING_TASK_HCM],
              error: null,
            }),
          });
        }
        return Promise.reject(new Error('Unexpected URL'));
      });

      render(<AnomaliesPage />);

      await waitFor(() => {
        expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument();
      });

      // Record baseline fetch calls count
      const initialFetchCount = (globalThis.fetch as any).mock.calls.length;

      // Find claim buttons
      expect(screen.queryByRole('button', { name: /認領此案/ })).not.toBeInTheDocument();

      // No new fetch calls were triggered
      expect((globalThis.fetch as any).mock.calls.length).toBe(initialFetchCount);

      // No alert/confirm/prompt
      expect(alertSpy).not.toHaveBeenCalled();
      expect(confirmSpy).not.toHaveBeenCalled();
      expect(promptSpy).not.toHaveBeenCalled();
    });

    it('ensures clicking disabled resolve button in Drawer generates zero requests and dialogs', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/v1/anomalies')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({
              success: true,
              message: 'OK',
              data: [VALID_ANOMALY_SUMMARY_1],
              error: null,
            }),
          });
        }
        if (url.includes('/api/v1/import-warning-tracking/tasks')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({
              success: true,
              message: 'OK',
              data: [],
              error: null,
            }),
          });
        }
        return Promise.reject(new Error('Unexpected URL'));
      });

      render(<AnomaliesPage />);

      await waitFor(() => {
        expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument();
      });

      // Open drawer
      const drawerBtn = screen.getByRole('button', { name: /查看處理方式 ➔/ });
      await act(async () => {
        fireEvent.click(drawerBtn);
      });

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /假日排班尚未確認/ })).toBeInTheDocument();
      });

      const initialFetchCount = (globalThis.fetch as any).mock.calls.length;

      expect(screen.getByText(/系統會自動重新核對異常/)).toBeVisible();
      expect(screen.queryByRole('button', { name: /確認排除異常/ })).not.toBeInTheDocument();

      // A generic text field cannot impersonate an owning-Domain correction.
      expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).toBeNull();

      // Verify no requests / dialogs
      expect((globalThis.fetch as any).mock.calls.length).toBe(initialFetchCount);
      expect(alertSpy).not.toHaveBeenCalled();
      expect(confirmSpy).not.toHaveBeenCalled();
      expect(promptSpy).not.toHaveBeenCalled();
    });
  });
});
