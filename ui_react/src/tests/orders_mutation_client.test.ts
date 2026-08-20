/**
 * File: orders_mutation_client.test.ts
 * Description: Orders 安全變更端點（服務日期與受控重開）嚴格解碼、標頭注入、冪等鍵與負向防偽測試。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  ordersMutationClient,
  getServiceDates,
  previewServiceDates,
  applyServiceDates,
  previewReopen,
  applyReopen,
} from '../api/orders/order_mutation_client';
import { sessionClient } from '../api/auth/session_client';
import {
  ApiDecodeError,
  ApiAbortError,
  ApiTimeoutError,
} from '../api/shared/typed_errors';
import {
  OrderMutationDomainBlockedError,
  OrderMutationConflictError,
  OrderMutationValidationError,
  OrderMutationUnavailableError,
  OrderMutationIdempotencyMismatchError,
  OrderMutationBackendGapError,
} from '../api/orders/order_mutation_errors';
import {
  ReasonSchema,
  FingerprintSchema,
  OrderReopenReceiptViewSchema,
  OrderReopenPreviewViewSchema,
} from '../api/orders/order_mutation_schemas';
import {
  realisticServiceDateQueryView,
  realisticServiceDateQueryViewConfirmed,
  realisticServiceDatePreviewView,
  realisticServiceDatePreviewPayload,
  realisticServiceDateApplyPayload,
  realisticServiceDateReceiptView,
  realisticOrderReopenPreviewView,
  realisticOrderReopenApplyPayload,
  realisticOrderReopenReceiptView,
  mockDomainBlockedErrorRaw,
  mockConflictErrorRaw,
  mockValidationErrorRaw,
  mockUnavailableErrorRaw,
  mockIdempotencyMismatchErrorRaw,
  mockFastApi401Raw,
  mockFastApi403Raw,
  mockFastApi422Raw,
} from './fixtures/orders/order_mutation_contract_fixtures';

describe('OrdersMutationClient Suite (Confirmed Service Dates & Controlled Reopen)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('test-bearer-token', {
      id: 1,
      username: 'admin',
      display_name: '管理員',
      role: 'system_admin',
      is_root: false,
      linked_line_user_id: null,
      access_control_version: 1,
      capabilities: [],
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    globalThis.fetch = originalFetch;
  });

  // ==========================================================================
  // 1. Confirmed Service Dates: Query
  // ==========================================================================
  describe('1. Confirmed Service Dates Query', () => {
    it('成功查詢服務日期確認狀態並解碼未確認狀態', async () => {
      const mockPayload = {
        success: true,
        message: '成功取得服務日期確認狀態',
        error: null,
        data: realisticServiceDateQueryView,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockPayload,
      });

      const res = await ordersMutationClient.getServiceDates('ORD-2026-0801');
      expect(res.case_no).toBe('ORD-2026-0801');
      expect(res.contracted_service_days).toBe(3);
      expect(res.current_version).toBeNull();
      expect(res.current_dates).toEqual([]);
      expect(res.suggested_dates.length).toBe(3);

      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string> | undefined;
      expect(url).toBe('/api/v1/orders/ORD-2026-0801/service-dates');
      expect(options?.method).toBe('GET');
      expect(headers?.['Authorization']).toBe('Bearer test-bearer-token');
    });

    it('成功解碼已確認之服務日期與版號', async () => {
      const mockPayload = {
        success: true,
        message: '成功取得服務日期確認狀態',
        error: null,
        data: realisticServiceDateQueryViewConfirmed,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockPayload,
      });

      const res = await getServiceDates('ORD-2026-0801');
      expect(res.current_version).toBe(1);
      expect(res.current_dates).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
      expect(res.order_version).toBe(2);
    });

    it('案件編號含特殊字元時應安全 URL 編碼', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          error: null,
          data: {
            ...realisticServiceDateQueryView,
            case_no: 'ORD/2026#01',
          },
        }),
      });

      await getServiceDates('ORD/2026#01');
      const [url] = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(url).toBe('/api/v1/orders/ORD%2F2026%2301/service-dates');
    });
  });

  // ==========================================================================
  // 2. Confirmed Service Dates: Preview
  // ==========================================================================
  describe('2. Confirmed Service Dates Preview', () => {
    it('成功預覽服務日期變更並傳入 X-Correlation-ID 標頭', async () => {
      const mockPayload = {
        success: true,
        message: '成功產生服務日期確認 Preview',
        error: null,
        data: realisticServiceDatePreviewView,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockPayload,
      });

      const res = await previewServiceDates(
        'ORD-2026-0801',
        realisticServiceDatePreviewPayload,
        { correlationId: 'corr-preview-date-01' }
      );

      expect(res.preview_fingerprint).toBe('a'.repeat(64));
      expect(res.weeks.length).toBe(1);
      expect(res.weeks[0].week_number).toBe(1);
      expect(res.weeks[0].service_day_count).toBe(3);

      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string> | undefined;
      expect(url).toBe('/api/v1/orders/ORD-2026-0801/service-dates/preview');
      expect(options?.method).toBe('POST');
      expect(headers?.['Authorization']).toBe('Bearer test-bearer-token');
      expect(headers?.['X-Correlation-ID']).toBe('corr-preview-date-01');
      expect(JSON.parse(options?.body as string)).toEqual({
        service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      });
    });
  });

  // ==========================================================================
  // 3. Confirmed Service Dates: Apply
  // ==========================================================================
  describe('3. Confirmed Service Dates Apply', () => {
    it('成功套用服務日期確認並注入 Idempotency-Key 與 X-Correlation-ID 標頭', async () => {
      const mockPayload = {
        success: true,
        message: '服務日期已確認',
        error: null,
        data: realisticServiceDateReceiptView,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockPayload,
      });

      const res = await applyServiceDates(
        'ORD-2026-0801',
        realisticServiceDateApplyPayload,
        {
          idempotencyKey: 'idem-date-apply-001',
          correlationId: 'corr-date-apply-001',
        }
      );

      expect(res.confirmed_version).toBe(1);
      expect(res.order_version).toBe(1);
      expect(res.preview_fingerprint).toBe('a'.repeat(64));

      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string> | undefined;
      expect(url).toBe('/api/v1/orders/ORD-2026-0801/service-dates/apply');
      expect(options?.method).toBe('POST');
      expect(headers?.['Authorization']).toBe('Bearer test-bearer-token');
      expect(headers?.['Idempotency-Key']).toBe('idem-date-apply-001');
      expect(headers?.['X-Correlation-ID']).toBe('corr-date-apply-001');
      expect(JSON.parse(options?.body as string)).toEqual({
        service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
        expected_order_version: 1,
        expected_scheduling_version: 1,
        preview_fingerprint: 'a'.repeat(64),
        reason: '客戶確認服務日期為 9/1 至 9/3',
      });
    });
  });

  // ==========================================================================
  // 4. Controlled Order Reopen: Preview
  // ==========================================================================
  describe('4. Controlled Order Reopen Preview', () => {
    it('成功預覽受控重開（包含 3 個版本號、requires_fresh_scheduling_preview: true 與空 restored 列表）', async () => {
      const mockPayload = {
        success: true,
        message: '成功產生訂單受控重開預覽',
        error: null,
        data: realisticOrderReopenPreviewView,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockPayload,
      });

      const res = await ordersMutationClient.previewReopen(
        'ORD-2026-0801',
        { correlationId: 'corr-reopen-preview-01' }
      );

      expect(res.order_version).toBe(3);
      expect(res.client_finance_version).toBe(2);
      expect(res.payroll_version).toBe(2);
      expect(res.cancellation_event_id).toBe(88);
      expect(res.before_status).toBe('訂單取消');
      expect(res.after_status).toBe('洽談中');
      expect(res.requires_fresh_scheduling_preview).toBe(true);
      expect(res.restored_assignment_ids).toEqual([]);
      expect(res.restored_schedule_ids).toEqual([]);
      expect(res.restored_lock_ids).toEqual([]);
      expect(res.preview_fingerprint).toBe('b'.repeat(64));

      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string> | undefined;
      expect(url).toBe('/api/v1/orders/ORD-2026-0801/reopen/preview');
      expect(options?.method).toBe('POST');
      expect(options?.body).toBeUndefined();
      expect(headers?.['X-Correlation-ID']).toBe('corr-reopen-preview-01');
    });
  });

  // ==========================================================================
  // 5. Controlled Order Reopen: Apply
  // ==========================================================================
  describe('5. Controlled Order Reopen Apply', () => {
    it('成功套用受控重開並解碼嚴格 Receipt（僅含 live schema 欄位）', async () => {
      const mockPayload = {
        success: true,
        message: '成功套用訂單受控重開',
        error: null,
        data: realisticOrderReopenReceiptView,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockPayload,
      });

      const res = await ordersMutationClient.applyReopen(
        'ORD-2026-0801',
        realisticOrderReopenApplyPayload,
        {
          idempotencyKey: 'idem-reopen-apply-001',
          correlationId: 'corr-reopen-apply-001',
        }
      );

      expect(res.case_no).toBe('ORD-2026-0801');
      expect(res.order_version).toBe(4);
      expect(res.lifecycle_status).toBe('洽談中');
      expect(res.cancellation_event_id).toBe(88);
      expect(res.requires_fresh_scheduling_preview).toBe(true);
      expect(res.preview_fingerprint).toBe('b'.repeat(64));

      const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string> | undefined;
      expect(url).toBe('/api/v1/orders/ORD-2026-0801/reopen/apply');
      expect(options?.method).toBe('POST');
      expect(headers?.['Idempotency-Key']).toBe('idem-reopen-apply-001');
      expect(headers?.['X-Correlation-ID']).toBe('corr-reopen-apply-001');
      expect(JSON.parse(options?.body as string)).toEqual({
        expected_order_version: 3,
        expected_client_finance_version: 2,
        expected_payroll_version: 2,
        preview_fingerprint: 'b'.repeat(64),
        reason: '客戶來電確認恢復需求，重新啟動案件流程',
      });
    });
  });

  // ==========================================================================
  // 6. Strict Decoder Anti-Cheat & Negative Probing
  // ==========================================================================
  describe('6. Strict Decoder Anti-Cheat & Negative Probing', () => {
    it('受控重開 Receipt 含未授權多餘欄位 (client_finance_version / payroll_version / created_at) 必須 fail closed', () => {
      const payloadWithExtra = {
        ...realisticOrderReopenReceiptView,
        client_finance_version: 2,
        payroll_version: 2,
        created_at: '2026-08-16T12:00:00Z',
      };

      const result = OrderReopenReceiptViewSchema.safeParse(payloadWithExtra);
      expect(result.success).toBe(false);
    });

    it('受控重開 Preview restored_assignment_ids 非空時必須 fail closed', () => {
      const invalidPreview = {
        ...realisticOrderReopenPreviewView,
        restored_assignment_ids: [101],
      };

      const result = OrderReopenPreviewViewSchema.safeParse(invalidPreview);
      expect(result.success).toBe(false);
    });

    it('受控重開 Preview restored_schedule_ids 非空時必須 fail closed', () => {
      const invalidPreview = {
        ...realisticOrderReopenPreviewView,
        restored_schedule_ids: [201],
      };

      const result = OrderReopenPreviewViewSchema.safeParse(invalidPreview);
      expect(result.success).toBe(false);
    });

    it('受控重開 Preview restored_lock_ids 非空時必須 fail closed', () => {
      const invalidPreview = {
        ...realisticOrderReopenPreviewView,
        restored_lock_ids: [301],
      };

      const result = OrderReopenPreviewViewSchema.safeParse(invalidPreview);
      expect(result.success).toBe(false);
    });

    it('受控重開 before_status 不為 cancelled 時必須 fail closed', () => {
      const invalidPreview = {
        ...realisticOrderReopenPreviewView,
        before_status: 'contract_signed',
      };

      const result = OrderReopenPreviewViewSchema.safeParse(invalidPreview);
      expect(result.success).toBe(false);
    });

    it('受控重開 requires_fresh_scheduling_preview 為 false 時必須 fail closed', () => {
      const invalidPreview = {
        ...realisticOrderReopenPreviewView,
        requires_fresh_scheduling_preview: false,
      };

      const result = OrderReopenPreviewViewSchema.safeParse(invalidPreview);
      expect(result.success).toBe(false);
    });

    it('Fingerprint 格式驗證：非 64-hex 字串必須被拒絕', () => {
      expect(FingerprintSchema.safeParse('short-hash').success).toBe(false);
      expect(FingerprintSchema.safeParse('A'.repeat(64)).success).toBe(false); // Uppercase rejected
      expect(FingerprintSchema.safeParse('g'.repeat(64)).success).toBe(false); // Non-hex character
      expect(FingerprintSchema.safeParse('a'.repeat(65)).success).toBe(false); // 65 chars
      expect(FingerprintSchema.safeParse('a'.repeat(64)).success).toBe(true);
    });

    it('Reason 邊界與非空防護：空字串、純空白、>500 字元必須失敗；1 字元、500 字元與中文必須成功', () => {
      expect(ReasonSchema.safeParse('').success).toBe(false);
      expect(ReasonSchema.safeParse('   ').success).toBe(false);
      expect(ReasonSchema.safeParse('a'.repeat(501)).success).toBe(false);
      expect(ReasonSchema.safeParse('a').success).toBe(true);
      expect(ReasonSchema.safeParse('a'.repeat(500)).success).toBe(true);
      expect(ReasonSchema.safeParse('  a  ').success).toBe(true);
      expect(ReasonSchema.safeParse('客戶確認重啟合約需求').success).toBe(true);
    });

    it('Idempotency-Key 為空白或格式錯誤時應於前端請求前攔截拋錯', async () => {
      await expect(
        ordersMutationClient.applyServiceDates(
          'ORD-2026-0801',
          realisticServiceDateApplyPayload,
          { idempotencyKey: '' }
        )
      ).rejects.toThrow('Idempotency-Key 長度必須介於 1 至 191 字元');

      await expect(
        ordersMutationClient.applyReopen(
          'ORD-2026-0801',
          realisticOrderReopenApplyPayload,
          { idempotencyKey: '   ' }
        )
      ).rejects.toThrow('Idempotency-Key 長度必須介於 1 至 191 字元');
    });

    it('非合法日曆日期 (如 2026-02-30) 於服務日期 Preview/Apply 必須 fail closed', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          error: null,
          data: {
            ...realisticServiceDatePreviewView,
            service_dates: ['2026-02-30'],
          },
        }),
      });

      await expect(
        ordersMutationClient.previewServiceDates(
          'ORD-2026-0801',
          realisticServiceDatePreviewPayload
        )
      ).rejects.toThrow(ApiDecodeError);
    });
  });

  // ==========================================================================
  // 7. Dynamic Token Injection & Session Switching
  // ==========================================================================
  describe('7. Dynamic Token Injection', () => {
    it('Token 不在 module load 時快取，Session 切換後每次 Request 即時讀取新 Token', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          error: null,
          data: realisticServiceDateQueryView,
        }),
      });
      globalThis.fetch = fetchMock;

      await ordersMutationClient.getServiceDates('ORD-2026-0801');
      sessionClient.setSession('replacement-bearer-token', {
        id: 2,
        username: 'admin2',
        display_name: '管理員2',
        role: 'system_admin',
        is_root: false,
        linked_line_user_id: null,
        access_control_version: 2,
        capabilities: [],
      });
      await ordersMutationClient.getServiceDates('ORD-2026-0801');

      const firstHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
      const secondHeaders = fetchMock.mock.calls[1][1]?.headers as Record<string, string>;
      expect(firstHeaders.Authorization).toBe('Bearer test-bearer-token');
      expect(secondHeaders.Authorization).toBe('Bearer replacement-bearer-token');
    });

    it('未登入 (Token 為 null) 時不應注入 Authorization 標頭', async () => {
      sessionClient.clearSession();
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'OK',
          error: null,
          data: realisticServiceDateQueryView,
        }),
      });
      globalThis.fetch = fetchMock;

      await ordersMutationClient.getServiceDates('ORD-2026-0801');
      const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
      expect(headers.Authorization).toBeUndefined();
    });
  });

  // ==========================================================================
  // 8. Typed Error Decoding & Backend Gap Normalization
  // ==========================================================================
  describe('8. Typed Error Decoding & Backend Gap Normalization', () => {
    it('Domain Blocked 409: 正確解析 Typed Error 信封並提取 domain_blockers', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockDomainBlockedErrorRaw,
      });

      try {
        await ordersMutationClient.applyReopen(
          'ORD-2026-0801',
          realisticOrderReopenApplyPayload,
          { idempotencyKey: 'idem-001' }
        );
        expect.fail('預期應拋出 OrderMutationDomainBlockedError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationDomainBlockedError);
        const mutationErr = err as OrderMutationDomainBlockedError;
        expect(mutationErr.category).toBe('domain_blocked');
        expect(mutationErr.code).toBe('reopen_blocked_by_financial_settlement');
        expect(mutationErr.domainBlockers).toEqual([
          'reopen_blocked_by_financial_settlement',
        ]);
        expect(mutationErr.correlationId).toBe('corr-reopen-001');
        expect(mutationErr.isBackendGap).toBe(false);
      }
    });

    it('Conflict 409: 正確解析過期版本衝突與 current_version', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockConflictErrorRaw,
      });

      try {
        await previewReopen('ORD-2026-0801');
        expect.fail('預期應拋出 OrderMutationConflictError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationConflictError);
        const mutationErr = err as OrderMutationConflictError;
        expect(mutationErr.category).toBe('conflict');
        expect(mutationErr.code).toBe('stale_order_version');
        expect(mutationErr.currentVersion).toBe(5);
        expect(mutationErr.isBackendGap).toBe(false);
      }
    });

    it('Validation 422: 正確解析欄位驗證錯誤清單 field_errors', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockValidationErrorRaw,
      });

      try {
        await applyReopen(
          'ORD-2026-0801',
          realisticOrderReopenApplyPayload,
          { idempotencyKey: 'idem-001' }
        );
        expect.fail('預期應拋出 OrderMutationValidationError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationValidationError);
        const mutationErr = err as OrderMutationValidationError;
        expect(mutationErr.category).toBe('validation');
        expect(mutationErr.fieldErrors.length).toBe(1);
        expect(mutationErr.fieldErrors[0].field).toBe('reason');
      }
    });

    it('Unavailable 503: 正確標記 retryable: true', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockUnavailableErrorRaw,
      });

      try {
        await applyReopen(
          'ORD-2026-0801',
          realisticOrderReopenApplyPayload,
          { idempotencyKey: 'idem-001' }
        );
        expect.fail('預期應拋出 OrderMutationUnavailableError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationUnavailableError);
        const mutationErr = err as OrderMutationUnavailableError;
        expect(mutationErr.retryable).toBe(true);
      }
    });

    it('Idempotency Mismatch 409: 正確解析冪等鍵衝突', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockIdempotencyMismatchErrorRaw,
      });

      try {
        await applyReopen(
          'ORD-2026-0801',
          realisticOrderReopenApplyPayload,
          { idempotencyKey: 'idem-001' }
        );
        expect.fail('預期應拋出 OrderMutationIdempotencyMismatchError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationIdempotencyMismatchError);
        const mutationErr = err as OrderMutationIdempotencyMismatchError;
        expect(mutationErr.category).toBe('idempotency_mismatch');
      }
    });

    it('FastAPI Pre-Route 401: 正規化為 BACKEND_GAP 且 isBackendGap: true', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockFastApi401Raw,
      });

      try {
        await getServiceDates('ORD-2026-0801');
        expect.fail('預期應拋出 OrderMutationBackendGapError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationBackendGapError);
        const mutationErr = err as OrderMutationBackendGapError;
        expect(mutationErr.status).toBe(401);
        expect(mutationErr.category).toBe('forbidden');
        expect(mutationErr.isBackendGap).toBe(true);
      }
    });

    it('FastAPI Pre-Route 403: 正規化為 BACKEND_GAP 且 isBackendGap: true', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockFastApi403Raw,
      });

      try {
        await getServiceDates('ORD-2026-0801');
        expect.fail('預期應拋出 OrderMutationBackendGapError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationBackendGapError);
        const mutationErr = err as OrderMutationBackendGapError;
        expect(mutationErr.status).toBe(403);
        expect(mutationErr.category).toBe('forbidden');
        expect(mutationErr.isBackendGap).toBe(true);
      }
    });

    it('FastAPI Pre-Route 422: 正規化為 BACKEND_GAP 且 isBackendGap: true', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockFastApi422Raw,
      });

      try {
        await applyReopen(
          'ORD-2026-0801',
          realisticOrderReopenApplyPayload,
          { idempotencyKey: 'idem-001' }
        );
        expect.fail('預期應拋出 OrderMutationBackendGapError');
      } catch (err) {
        expect(err).toBeInstanceOf(OrderMutationBackendGapError);
        const mutationErr = err as OrderMutationBackendGapError;
        expect(mutationErr.status).toBe(422);
        expect(mutationErr.category).toBe('validation');
        expect(mutationErr.isBackendGap).toBe(true);
      }
    });
  });

  // ==========================================================================
  // 9. Transport Signal & Abort
  // ==========================================================================
  describe('9. Transport Signal & Abort', () => {
    it('AbortSignal 取消時應拋出 ApiAbortError 且中斷請求', async () => {
      const controller = new AbortController();
      controller.abort();

      await expect(
        ordersMutationClient.getServiceDates('ORD-2026-0801', {
          signal: controller.signal,
        })
      ).rejects.toThrow(ApiAbortError);
    });

    it('逾時時應拋出 ApiTimeoutError', async () => {
      globalThis.fetch = vi.fn().mockImplementation(() => {
        return new Promise((_, reject) => {
          const timeoutErr = new Error('Timeout');
          timeoutErr.name = 'AbortError';
          setTimeout(() => reject(timeoutErr), 10);
        });
      });

      await expect(
        ordersMutationClient.getServiceDates('ORD-2026-0801', {
          timeoutMs: 5,
        })
      ).rejects.toThrow(ApiTimeoutError);
    });
  });
});
