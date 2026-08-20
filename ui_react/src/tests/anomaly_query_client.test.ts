/**
 * File: anomaly_query_client.test.ts
 * Description: 驗證 Anomalies 四個 GET client 的 strict contract。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  queryAnomalies,
  queryImportWarningTasks,
  queryAnomalyDetail,
  queryImportWarningReferral,
  createAnomalyQueryClient,
  anomalyQueryClient,
} from '../api/anomalies/anomaly_query_client';
import {
  AnomalyQueryError,
  AnomalyUnauthenticatedError,
  AnomalyForbiddenError,
  AnomalyValidationError,
  AnomalyServiceUnavailableError,
  AnomalyNetworkError,
  AnomalyAbortedError,
  isAnomalyQueryError,
  isAnomalyUnauthenticatedError,
  isAnomalyForbiddenError,
  isAnomalyValidationError,
  isAnomalyServiceUnavailableError,
  isAnomalyNetworkError,
  isAnomalyAbortedError,
} from '../api/anomalies/anomaly_query_errors';
import {
  VALID_ANOMALIES_QUERY_RESPONSE,
  VALID_EMPTY_ANOMALIES_QUERY_RESPONSE,
  VALID_IMPORT_WARNING_TASKS_RESPONSE,
  VALID_EMPTY_IMPORT_WARNING_TASKS_RESPONSE,
  VALID_ANOMALY_SUMMARY_1,
  VALID_ANOMALY_SUMMARY_2,
  VALID_IMPORT_WARNING_TASK_HCM,
  INVALID_ANOMALY_MISSING_FINGERPRINT,
  INVALID_ANOMALY_INVALID_FINGERPRINT,
  INVALID_ANOMALY_INVALID_SEVERITY,
  INVALID_ANOMALY_INVALID_STATUS,
  INVALID_ANOMALY_EXTRA_UNKNOWN_FIELD,
  INVALID_ANOMALY_NEGATIVE_VERSION,
  INVALID_ANOMALY_INVALID_NAV_DATE,
  INVALID_TASK_MISSING_IDENTITY,
  INVALID_TASK_INVALID_STATUS,
  INVALID_TASK_ZERO_VERSION,
  INVALID_TASK_EMPTY_MESSAGE,
  INVALID_TASK_OVERLONG_MESSAGE,
  INVALID_TASK_INVALID_NAV_ACTION,
  INVALID_TASK_EXTRA_FIELD,
  CORRUPTED_ENVELOPE_PRIMITIVE,
  CORRUPTED_ENVELOPE_BUSINESS_ERROR,
  CORRUPTED_ENVELOPE_EXTRA_FIELD,
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';

describe('Anomaly Query API Client (Phase 2D Integration)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('phase2d-session-token', {
      id: 1,
      username: 'phase2d-operator',
      display_name: 'Phase 2D Operator',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  // ==========================================================================
  // 1. queryAnomalies (GET /api/v1/anomalies?include_snapshot=false)
  // ==========================================================================
  describe('queryAnomalies', () => {
    it('應正確發送請求並解析異常摘要列表 (強制 include_snapshot=false)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_ANOMALIES_QUERY_RESPONSE,
      });

      const anomalies = await queryAnomalies({
        activeOnly: true,
        limit: 50,
        offset: 10,
      });

      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
      const [calledUrl, calledOptions] = vi.mocked(globalThis.fetch).mock.calls[0];

      expect(calledUrl).toContain('/api/v1/anomalies');
      expect(calledUrl).toContain('include_snapshot=false');
      expect(calledUrl).toContain('active_only=true');
      expect(calledUrl).toContain('limit=50');
      expect(calledUrl).toContain('offset=10');
      expect(calledOptions?.method).toBe('GET');

      expect(anomalies).toHaveLength(3);
      expect(anomalies[0].fingerprint).toBe(VALID_ANOMALY_SUMMARY_1.fingerprint);
      expect(anomalies[0].severity).toBe('blocking');
      expect(anomalies[0].workflow_status).toBe('open');
      expect(anomalies[0].staff_calendar_navigation).toEqual({
        staff_id: 14,
        target_date: '2026-08-20',
      });
      expect(anomalies[0].display_snapshot).toBeNull();

      expect(anomalies[1].fingerprint).toBe(VALID_ANOMALY_SUMMARY_2.fingerprint);
      expect(anomalies[1].severity).toBe('warning');
      expect(anomalies[1].workflow_status).toBe('claimed');
      expect(anomalies[1].staff_calendar_navigation).toBeNull();
    });

    it('應支援空列表回應解析', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_ANOMALIES_QUERY_RESPONSE,
      });

      const list = await queryAnomalies();
      expect(list).toEqual([]);
    });

    it('未傳入分頁參數時，應僅包含 include_snapshot=false 參數', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_ANOMALIES_QUERY_RESPONSE,
      });

      await queryAnomalies();

      const [calledUrl] = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(calledUrl).toBe('/api/v1/anomalies?include_snapshot=false');
    });

    it('當 limit 超出範圍 (< 1 或 > 200) 時，應於前端請求前拋出 AnomalyValidationError', async () => {
      await expect(queryAnomalies({ limit: 0 })).rejects.toThrow(
        AnomalyValidationError
      );
      await expect(queryAnomalies({ limit: 201 })).rejects.toThrow(
        AnomalyValidationError
      );
      await expect(queryAnomalies({ limit: 1.5 })).rejects.toThrow(
        AnomalyValidationError
      );
    });

    it('當 offset 小於 0 或非整數時，應於前端請求前拋出 AnomalyValidationError', async () => {
      await expect(queryAnomalies({ offset: -1 })).rejects.toThrow(
        AnomalyValidationError
      );
      await expect(queryAnomalies({ offset: 2.5 })).rejects.toThrow(
        AnomalyValidationError
      );
    });
  });

  // ==========================================================================
  // 2. queryImportWarningTasks (GET /api/v1/import-warning-tracking/tasks)
  // ==========================================================================
  describe('queryImportWarningTasks', () => {
    it('應正確發送請求並解析 6 種追蹤狀態之匯入警示任務', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_IMPORT_WARNING_TASKS_RESPONSE,
      });

      const tasks = await queryImportWarningTasks({
        activeOnly: true,
        limit: 100,
      });

      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
      const [calledUrl, calledOptions] = vi.mocked(globalThis.fetch).mock.calls[0];

      expect(calledUrl).toContain('/api/v1/import-warning-tracking/tasks');
      expect(calledUrl).toContain('active_only=true');
      expect(calledUrl).toContain('limit=100');
      expect(calledOptions?.method).toBe('GET');

      expect(tasks).toHaveLength(6);
      expect(tasks[0].occurrence_identity).toBe(
        VALID_IMPORT_WARNING_TASK_HCM.occurrence_identity
      );
      expect(tasks[0].owning_lane).toBe('hcm');
      expect(tasks[0].tracking_status).toBe('open');
      expect(tasks[0].navigation_action).toBe('hcm_import_center');
      expect(tasks[0].evidence_reference).toBe('batch-20260816-01');

      expect(tasks[1].tracking_status).toBe('awaiting_external_confirmation');
      expect(tasks[1].navigation_action).toBe('client_beclass_import_center');
      expect(tasks[1].evidence_reference).toBeNull();

      expect(tasks[2].tracking_status).toBe('response_recorded');
      expect(tasks[3].tracking_status).toBe('reimport_requested');
      expect(tasks[4].tracking_status).toBe('closed');
      expect(tasks[5].tracking_status).toBe('auto_resolved');
      expect(tasks[5].navigation_action).toBeNull();
    });

    it('應支援空任務清單解析', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_IMPORT_WARNING_TASKS_RESPONSE,
      });

      const tasks = await queryImportWarningTasks();
      expect(tasks).toEqual([]);
    });

    it('分頁參數越界時應拋出 AnomalyValidationError', async () => {
      await expect(queryImportWarningTasks({ limit: 0 })).rejects.toThrow(
        AnomalyValidationError
      );
      await expect(queryImportWarningTasks({ offset: -5 })).rejects.toThrow(
        AnomalyValidationError
      );
    });
  });

  // ==========================================================================
  // 3. Strict Schema Validation & Adversarial Payloads
  // ==========================================================================
  describe('Strict Zod Schema Validation & Adversarial Rejection', () => {
    it('若異常資料缺少必要欄位 (fingerprint)，應拋出 AnomalyValidationError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_MISSING_FINGERPRINT],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });

    it('若異常資料 fingerprint 格式不符 (非 64 位十六進位)，應拋出 AnomalyValidationError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_INVALID_FINGERPRINT],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });

    it('若異常資料嚴重度枚舉不合法 (CRITICAL)，應拒絕並拋出 AnomalyValidationError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_INVALID_SEVERITY],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });

    it('若異常資料狀態枚舉不合法 (in_progress)，應拒絕並拋出 AnomalyValidationError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_INVALID_STATUS],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });

    it('若異常資料包含額外未宣告欄位，應因 .strict() 拒絕並拋出 AnomalyValidationError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_EXTRA_UNKNOWN_FIELD],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });

    it('若異常資料版本為負數或導航日期格式非 YYYY-MM-DD，應拒絕', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_NEGATIVE_VERSION],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_ANOMALY_INVALID_NAV_DATE],
          error: null,
        }),
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });

    it('若匯入警示任務缺少 occurrence_identity 或狀態枚舉不符，應拒絕', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_MISSING_IDENTITY],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_INVALID_STATUS],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );
    });

    it('若匯入警示任務版本號為 0 (必須 ge 1)，應拒絕', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_ZERO_VERSION],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );
    });

    it('若匯入警示任務訊息為空字串或超過 200 字元，應拒絕', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_EMPTY_MESSAGE],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_OVERLONG_MESSAGE],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );
    });

    it('若匯入警示任務包含額外欄位或導航動作不符，應拒絕', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_EXTRA_FIELD],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          data: [INVALID_TASK_INVALID_NAV_ACTION],
          error: null,
        }),
      });

      await expect(queryImportWarningTasks()).rejects.toThrow(
        AnomalyValidationError
      );
    });

    it('若信封為非物件或 success 為 false 或含有額外未知欄位，應拋出 AnomalyValidationError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => CORRUPTED_ENVELOPE_PRIMITIVE,
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => CORRUPTED_ENVELOPE_BUSINESS_ERROR,
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => CORRUPTED_ENVELOPE_EXTRA_FIELD,
      });

      await expect(queryAnomalies()).rejects.toThrow(AnomalyValidationError);
    });
  });

  // ==========================================================================
  // 4. HTTP Error Status & Network Taxonomy Mapping
  // ==========================================================================
  describe('HTTP Error Taxonomy & Network Mapping', () => {
    it('HTTP 401: 應映射為 AnomalyUnauthenticatedError (code: ANOMALY_QUERY_UNAUTHENTICATED, status: 401)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: '認證已過期，請重新登入',
        }),
      });

      try {
        await queryAnomalies();
        expect.unreachable('Should have thrown 401 error');
      } catch (err) {
        expect(err instanceof AnomalyQueryError).toBe(true);
        expect(isAnomalyQueryError(err)).toBe(true);
        expect(isAnomalyUnauthenticatedError(err)).toBe(true);
        const anmErr = err as AnomalyUnauthenticatedError;
        expect(anmErr.code).toBe('ANOMALY_QUERY_UNAUTHENTICATED');
        expect(anmErr.status).toBe(401);
        expect(anmErr.retryable).toBe(false);
      }
    });

    it('HTTP 403: 應映射為 AnomalyForbiddenError (code: ANOMALY_QUERY_FORBIDDEN, status: 403)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: '僅限系統管理員存取',
        }),
      });

      try {
        await queryImportWarningTasks();
        expect.unreachable('Should have thrown 403 error');
      } catch (err) {
        expect(isAnomalyForbiddenError(err)).toBe(true);
        const anmErr = err as AnomalyForbiddenError;
        expect(anmErr.code).toBe('ANOMALY_QUERY_FORBIDDEN');
        expect(anmErr.status).toBe(403);
        expect(anmErr.retryable).toBe(false);
      }
    });

    it('HTTP 422: 應映射為 AnomalyValidationError 並解析欄位錯誤', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: [
            { loc: ['query', 'limit'], msg: 'ensure this value is less than or equal to 200' },
          ],
        }),
      });

      try {
        await queryAnomalies();
        expect.unreachable('Should have thrown 422 error');
      } catch (err) {
        expect(isAnomalyValidationError(err)).toBe(true);
        const valErr = err as AnomalyValidationError;
        expect(valErr.code).toBe('ANOMALY_QUERY_VALIDATION_ERROR');
        expect(valErr.status).toBe(422);
        expect(valErr.fieldErrors).toBeDefined();
        expect(valErr.fieldErrors?.[0].field).toBe('query.limit');
      }
    });

    it('HTTP 503: 應映射為 AnomalyServiceUnavailableError 且標記 retryable: true', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: '資料庫伺服器維護中',
        }),
      });

      try {
        await queryAnomalies();
        expect.unreachable('Should have thrown 503 error');
      } catch (err) {
        expect(isAnomalyServiceUnavailableError(err)).toBe(true);
        const srvErr = err as AnomalyServiceUnavailableError;
        expect(srvErr.code).toBe('ANOMALY_QUERY_SERVICE_UNAVAILABLE');
        expect(srvErr.status).toBe(503);
        expect(srvErr.retryable).toBe(true);
      }
    });

    it('網路連線失敗應映射為 AnomalyNetworkError 且標記 retryable: true', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

      try {
        await queryAnomalies();
        expect.unreachable('Should have thrown network error');
      } catch (err) {
        expect(isAnomalyNetworkError(err)).toBe(true);
        const netErr = err as AnomalyNetworkError;
        expect(netErr.code).toBe('ANOMALY_QUERY_NETWORK_ERROR');
        expect(netErr.retryable).toBe(true);
      }
    });

    it('使用 AbortSignal 中斷請求應拋出 AnomalyAbortedError (code: ANOMALY_QUERY_ABORTED)', async () => {
      const controller = new AbortController();
      controller.abort();

      try {
        await queryAnomalies({}, { signal: controller.signal });
        expect.unreachable('Should have thrown abort error');
      } catch (err) {
        expect(isAnomalyAbortedError(err)).toBe(true);
        const abortErr = err as AnomalyAbortedError;
        expect(abortErr.code).toBe('ANOMALY_QUERY_ABORTED');
        expect(abortErr.retryable).toBe(false);
      }
    });
  });

  // ==========================================================================
  // 5. Client Options, Factory & Singleton Instance
  // ==========================================================================
  describe('Client Options, Token Injection & Factory', () => {
    it('應即時注入記憶體 Session，並拒絕 caller 覆寫 Authorization', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_ANOMALIES_QUERY_RESPONSE,
      });

      sessionClient.setSession('current-memory-session-token', {
        id: 2,
        username: 'current-operator',
        display_name: 'Current Operator',
        role: 'admin',
      });
      const customClient = createAnomalyQueryClient({
        headers: {
          Authorization: 'Bearer caller-must-not-win',
          'X-Request-Trace': 'trace-abc-123',
        },
        baseUrl: 'https://api.test.domain',
      });

      await customClient.queryAnomalies({ activeOnly: true });

      const [calledUrl, calledOptions] = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(calledUrl).toContain('https://api.test.domain/api/v1/anomalies');
      expect(calledOptions?.headers).toMatchObject({
        Authorization: 'Bearer current-memory-session-token',
        'X-Request-Trace': 'trace-abc-123',
      });
    });

    it('每次 request 重新讀取 Session，登出後在 fetch 前 fail closed', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_ANOMALIES_QUERY_RESPONSE,
      });

      await queryAnomalies();
      expect(vi.mocked(globalThis.fetch).mock.calls[0][1]?.headers).toMatchObject({
        Authorization: 'Bearer phase2d-session-token',
      });

      sessionClient.setSession('rotated-session-token', {
        id: 3,
        username: 'rotated-operator',
        display_name: 'Rotated Operator',
        role: 'admin',
      });
      await queryAnomalies();
      expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject({
        Authorization: 'Bearer rotated-session-token',
      });

      sessionClient.clearSession();
      await expect(queryAnomalies()).rejects.toBeInstanceOf(
        AnomalyUnauthenticatedError
      );
      expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    });

    it('單例 anomalyQueryClient 應正確暴露所有方法', () => {
      expect(anomalyQueryClient.queryAnomalies).toBeDefined();
      expect(anomalyQueryClient.queryImportWarningTasks).toBeDefined();
      expect(anomalyQueryClient.queryAnomalyDetail).toBeDefined();
      expect(anomalyQueryClient.queryImportWarningReferral).toBeDefined();
    });
  });

  describe('Lazy Drawer GET contracts', () => {
    it('queries typed anomaly detail only by fingerprint', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: '成功取得異常詳情',
          data: VALID_ANOMALY_DETAIL_VIEW,
          error: null,
        }),
      });

      const detail = await queryAnomalyDetail({
        fingerprint: VALID_ANOMALY_DETAIL_VIEW.summary.fingerprint,
      });
      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(url).toContain('/api/v1/anomalies/');
      expect(options?.method).toBe('GET');
      expect(detail.timeline[0].action).toBe('reopen');
    });

    it('queries warning referral with expected version and rejects invalid identity', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: '成功取得匯入警示 owning 業面導向',
          data: VALID_IMPORT_WARNING_REFERRAL_VIEW,
          error: null,
        }),
      });

      const referral = await queryImportWarningReferral({
        occurrenceIdentity: VALID_IMPORT_WARNING_REFERRAL_VIEW.occurrence_identity,
        expectedVersion: 1,
      });
      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(url).toContain('/referral?expected_version=1');
      expect(options?.method).toBe('GET');
      expect(referral.action_kind).toBe('owner_preview_apply');

      await expect(
        queryImportWarningReferral({ occurrenceIdentity: '', expectedVersion: 1 })
      ).rejects.toBeInstanceOf(AnomalyValidationError);
    });
  });

  // ==========================================================================
  // 6. Anti-Cheating & Zero Mutation Invariant
  // ==========================================================================
  describe('Zero Mutation & Pure Query Guarantee', () => {
    it('所有發出之 HTTP 請求必須 100% 為 GET 方法，絕不發出 POST/PUT/PATCH/DELETE', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_ANOMALIES_QUERY_RESPONSE,
      });

      await queryAnomalies();

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => VALID_EMPTY_IMPORT_WARNING_TASKS_RESPONSE,
      });

      await queryImportWarningTasks();

      const allCalls = vi.mocked(globalThis.fetch).mock.calls;
      for (const call of allCalls) {
        const options = call[1];
        expect(options?.method).toBe('GET');
        expect(options?.body).toBeUndefined();
      }
    });
  });
});
