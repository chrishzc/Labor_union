/**
 * @file stress_transport_decoder.test.ts
 * @description 針對 Shared API Transport、Runtime Decoder 與 System Status Schema 的極限壓力與對抗性測試。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { z } from 'zod';
import { transport } from '../api/shared/transport';
import {
  decodePayload,
  decodeEnvelope,
} from '../api/shared/runtime_decoder';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  extractErrorCode,
  extractErrorMessage,
  isApiError,
  isRetryableError,
} from '../api/shared/typed_errors';
import {
  PerformanceSnapshotSchema,
  type PerformanceSnapshot,
} from '../api/system/system_status_schema';

describe('Adversarial & Stress Tests: Runtime Decoder & System Status Schema', () => {
  const validSnapshot: PerformanceSnapshot = {
    started_at: '2026-08-09T00:00:00Z',
    request_count: 100,
    average_response_time_ms: 15.4,
    p50_response_time_upper_bound_ms: 12,
    p95_response_time_upper_bound_ms: 30,
    maximum_response_time_ms: 150.2,
  };

  describe('1. Malformed Payloads & Root Type Boundaries', () => {
    const invalidRoots = [
      null,
      undefined,
      123,
      'string',
      true,
      false,
      [],
      [validSnapshot],
      () => {},
      Symbol('test'),
    ];

    it.each(invalidRoots)('非物件根節點應被 decodePayload 拒絕: %s', (invalidRoot) => {
      expect(() => decodePayload(PerformanceSnapshotSchema, invalidRoot)).toThrow(
        ApiDecodeError
      );
    });

    it.each(invalidRoots)('非物件根節點應被 decodeEnvelope 拒絕: %s', (invalidRoot) => {
      expect(() => decodeEnvelope(PerformanceSnapshotSchema, invalidRoot)).toThrow(
        ApiDecodeError
      );
    });
  });

  describe('2. Missing Required Fields & Partial Corruption', () => {
    it('完全空物件應拋出 ApiDecodeError 並精確指出缺少的必填欄位', () => {
      try {
        decodePayload(PerformanceSnapshotSchema, {});
        expect.unreachable('Should have thrown ApiDecodeError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiDecodeError);
        const decodeErr = err as ApiDecodeError;
        const paths = decodeErr.issues.map((i) => i.path);
        expect(paths).toContain('started_at');
        expect(paths).toContain('request_count');
        expect(decodeErr.issues.length).toBeGreaterThanOrEqual(2);
      }
    });

    it('僅缺少 started_at 時應精確報告 started_at', () => {
      const payload = { ...validSnapshot } as Partial<PerformanceSnapshot>;
      delete payload.started_at;

      try {
        decodePayload(PerformanceSnapshotSchema, payload);
        expect.unreachable('Should have thrown ApiDecodeError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiDecodeError);
        const decodeErr = err as ApiDecodeError;
        expect(decodeErr.issues.some((i) => i.path === 'started_at')).toBe(true);
      }
    });

    it('僅缺少 request_count 時應精確報告 request_count', () => {
      const payload = { ...validSnapshot } as Partial<PerformanceSnapshot>;
      delete payload.request_count;

      try {
        decodePayload(PerformanceSnapshotSchema, payload);
        expect.unreachable('Should have thrown ApiDecodeError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiDecodeError);
        const decodeErr = err as ApiDecodeError;
        expect(decodeErr.issues.some((i) => i.path === 'request_count')).toBe(true);
      }
    });
  });

  describe('3. Schema Evolution & Unknown Fields', () => {
    it('應容許伺服器回傳未定義的額外欄位 (Passthrough / Strip 行為)', () => {
      const evolvedPayload = {
        ...validSnapshot,
        unrecognized_future_field: 'v2.0_metric',
        telemetry_meta: { node_id: 'node-99', region: 'asia-east1' },
      };

      const result = decodePayload(PerformanceSnapshotSchema, evolvedPayload);
      expect(result.started_at).toBe(validSnapshot.started_at);
      expect(result.request_count).toBe(validSnapshot.request_count);
      // Zod object default strips unknown fields
      expect((result as any).unrecognized_future_field).toBeUndefined();
    });
  });

  describe('4. Type Mismatches & Mathematical Boundaries', () => {
    it('request_count 為字串數字時應被拒絕 (無隱式轉型)', () => {
      const payload = { ...validSnapshot, request_count: '100' };
      expect(() => decodePayload(PerformanceSnapshotSchema, payload)).toThrow(
        ApiDecodeError
      );
    });

    it('request_count 為浮點數時應被拒絕 (.int() 約束)', () => {
      const payload = { ...validSnapshot, request_count: 100.5 };
      expect(() => decodePayload(PerformanceSnapshotSchema, payload)).toThrow(
        ApiDecodeError
      );
    });

    it('request_count 為負數時應被拒絕 (.min(0) 約束)', () => {
      const payload = { ...validSnapshot, request_count: -1 };
      expect(() => decodePayload(PerformanceSnapshotSchema, payload)).toThrow(
        ApiDecodeError
      );
    });

    it('request_count 為 NaN 時應被拒絕', () => {
      const payload = { ...validSnapshot, request_count: NaN };
      expect(() => decodePayload(PerformanceSnapshotSchema, payload)).toThrow(
        ApiDecodeError
      );
    });

    it('request_count 為 0 時應成功通過 (極值 0)', () => {
      const payload = { ...validSnapshot, request_count: 0 };
      const res = decodePayload(PerformanceSnapshotSchema, payload);
      expect(res.request_count).toBe(0);
    });

    it('request_count 為 Number.MAX_SAFE_INTEGER 時應成功通過', () => {
      const payload = { ...validSnapshot, request_count: Number.MAX_SAFE_INTEGER };
      const res = decodePayload(PerformanceSnapshotSchema, payload);
      expect(res.request_count).toBe(Number.MAX_SAFE_INTEGER);
    });

    it('p50 / p95 百分位指標若為小數應被拒絕 (.int() 約束)', () => {
      const payloadP50 = { ...validSnapshot, p50_response_time_upper_bound_ms: 12.34 };
      expect(() => decodePayload(PerformanceSnapshotSchema, payloadP50)).toThrow(
        ApiDecodeError
      );

      const payloadP95 = { ...validSnapshot, p95_response_time_upper_bound_ms: 25.99 };
      expect(() => decodePayload(PerformanceSnapshotSchema, payloadP95)).toThrow(
        ApiDecodeError
      );
    });

    it('延遲指標若為負數小數應被拒絕', () => {
      const payload = { ...validSnapshot, average_response_time_ms: -0.0001 };
      expect(() => decodePayload(PerformanceSnapshotSchema, payload)).toThrow(
        ApiDecodeError
      );
    });

    it('nullable 欄位為 undefined 時應被拒絕 (nullable != optional)', () => {
      const payload = {
        started_at: '2026-08-09T00:00:00Z',
        request_count: 10,
        average_response_time_ms: undefined, // missing / undefined
        p50_response_time_upper_bound_ms: null,
        p95_response_time_upper_bound_ms: null,
        maximum_response_time_ms: null,
      };

      expect(() => decodePayload(PerformanceSnapshotSchema, payload)).toThrow(
        ApiDecodeError
      );
    });
  });

  describe('5. BaseResponse Envelope Adversarial Probing', () => {
    it('當 success 為 false 且帶有 error 字串時應拋出 ApiHttpError(400, BUSINESS_ERROR)', () => {
      const envelope = {
        success: false,
        error: 'AUTH_SESSION_EXPIRED',
        message: '登入階段已過期',
        data: null,
      };

      try {
        decodeEnvelope(PerformanceSnapshotSchema, envelope);
        expect.unreachable('Should have thrown ApiHttpError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiHttpError);
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(400);
        expect(httpErr.code).toBe('BUSINESS_ERROR');
        expect(httpErr.message).toBe('AUTH_SESSION_EXPIRED');
        expect(httpErr.retryable).toBe(false);
      }
    });

    it('當 success 為 false 且 error 為空時應降級使用 message', () => {
      const envelope = {
        success: false,
        error: null,
        message: '權限不足無法訪問效能遙測',
        data: null,
      };

      try {
        decodeEnvelope(PerformanceSnapshotSchema, envelope);
        expect.unreachable('Should have thrown ApiHttpError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiHttpError);
        const httpErr = err as ApiHttpError;
        expect(httpErr.message).toBe('權限不足無法訪問效能遙測');
      }
    });

    it('當 success 為 false 且 error 與 message 皆為空時應使用預設訊息', () => {
      const envelope = {
        success: false,
        error: '',
        message: '',
        data: null,
      };

      try {
        decodeEnvelope(PerformanceSnapshotSchema, envelope);
        expect.unreachable('Should have thrown ApiHttpError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiHttpError);
        const httpErr = err as ApiHttpError;
        expect(httpErr.message).toBe('後端業務執行失敗');
      }
    });

    it('當 success 為 true 但 data 為 null 時應拋出 ApiDecodeError', () => {
      const envelope = {
        success: true,
        message: 'OK',
        data: null,
      };

      expect(() => decodeEnvelope(PerformanceSnapshotSchema, envelope)).toThrow(
        ApiDecodeError
      );
    });

    it('當 success 為 true 但 data 缺少必填欄位時應拋出 ApiDecodeError 並包含內部路徑', () => {
      const envelope = {
        success: true,
        data: {
          started_at: '2026-08-09T00:00:00Z',
          // missing request_count
        },
      };

      try {
        decodeEnvelope(PerformanceSnapshotSchema, envelope);
        expect.unreachable('Should have thrown ApiDecodeError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiDecodeError);
        const decodeErr = err as ApiDecodeError;
        expect(decodeErr.issues.some((i) => i.path.includes('request_count'))).toBe(
          true
        );
      }
    });

    it('驗證布林值與數字為 0 或 false 的合法資料不會被誤判為 missing data', () => {
      const BooleanSchema = z.boolean();
      const envelope = {
        success: true,
        message: 'OK',
        data: false,
      };

      const result = decodeEnvelope(BooleanSchema, envelope);
      expect(result).toBe(false);

      const NumberSchema = z.number();
      const numEnvelope = {
        success: true,
        message: 'OK',
        data: 0,
      };
      const numResult = decodeEnvelope(NumberSchema, numEnvelope);
      expect(numResult).toBe(0);
    });
  });

  describe('6. Extreme Payload Scale & Performance', () => {
    it('應能高速解碼包含 5,000 筆快照陣列的大型資料集而不產生效能瓶頸', () => {
      const LargeArraySchema = z.array(PerformanceSnapshotSchema);
      const largeData = Array.from({ length: 5000 }, (_, i) => ({
        started_at: `2026-08-09T${String(i % 24).padStart(2, '0')}:00:00Z`,
        request_count: i,
        average_response_time_ms: i * 0.1,
        p50_response_time_upper_bound_ms: i,
        p95_response_time_upper_bound_ms: i * 2,
        maximum_response_time_ms: i * 5.5,
      }));

      const startTime = performance.now();
      const decoded = decodePayload(LargeArraySchema, largeData);
      const elapsedMs = performance.now() - startTime;

      expect(decoded.length).toBe(5000);
      expect(elapsedMs).toBeLessThan(500); // Under 500ms for 5,000 complex objects
    });
  });
});

describe('Adversarial & Stress Tests: Transport Client Edge Cases', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('1. Full HTTP Status Code Matrix & Error Parsing', () => {
    const statusCases = [
      { status: 400, expectedRetryable: false, code: 'HTTP_400' },
      { status: 401, expectedRetryable: false, code: 'HTTP_401' },
      { status: 403, expectedRetryable: false, code: 'HTTP_403' },
      { status: 404, expectedRetryable: false, code: 'HTTP_404' },
      { status: 422, expectedRetryable: false, code: 'HTTP_422' },
      { status: 500, expectedRetryable: false, code: 'HTTP_500' },
      { status: 502, expectedRetryable: true, code: 'HTTP_502' },
      { status: 503, expectedRetryable: true, code: 'HTTP_503' },
      { status: 504, expectedRetryable: true, code: 'HTTP_504' },
    ];

    it.each(statusCases)(
      'HTTP $status 預設應轉換為 ApiHttpError 且 retryable = $expectedRetryable',
      async ({ status, expectedRetryable, code }) => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status,
          statusText: `Error-${status}`,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({}),
        });

        try {
          await transport.get(`/api/v1/test-${status}`);
          expect.unreachable('Should have thrown ApiHttpError');
        } catch (err) {
          expect(err).toBeInstanceOf(ApiHttpError);
          const httpErr = err as ApiHttpError;
          expect(httpErr.status).toBe(status);
          expect(httpErr.code).toBe(code);
          expect(httpErr.retryable).toBe(expectedRetryable);
        }
      }
    );

    it('後端自訂 detail.retryable 應覆寫預設 retryable 屬性', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: {
            code: 'RATE_LIMIT_EXCEEDED',
            message: '請求過於頻繁，請稍後重試',
            retryable: true, // Overriding 400 default false
          },
        }),
      });

      try {
        await transport.get('/api/v1/rate-limited');
        expect.unreachable('Should have thrown ApiHttpError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiHttpError);
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(400);
        expect(httpErr.code).toBe('RATE_LIMIT_EXCEEDED');
        expect(httpErr.retryable).toBe(true);
      }
    });

    it('接收到 Nginx HTML 錯誤頁面 (502 Bad Gateway) 時不應拋出 JSON 解析異常', async () => {
      const htmlBody = '<html><head><title>502 Bad Gateway</title></head><body><center>nginx/1.24.0</center></body></html>';
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        headers: new Headers({ 'content-type': 'text/html; charset=utf-8' }),
        text: async () => htmlBody,
      });

      try {
        await transport.get('/api/v1/down');
        expect.unreachable('Should have thrown ApiHttpError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiHttpError);
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(502);
        expect(httpErr.message).toBe('Bad Gateway');
        expect(httpErr.retryable).toBe(true);
        expect(httpErr.raw).toBe(htmlBody);
      }
    });

    it('FastAPI 多欄位 422 驗證錯誤格式應被正確解構為 VALIDATION_ERROR', async () => {
      const validationDetail = [
        { loc: ['body', 'orders', 0, 'quantity'], msg: 'ensure this value is greater than 0' },
        { loc: ['body', 'orders', 0, 'unit_price'], msg: 'field required' },
        { loc: 'header_token', msg: 'invalid format' },
      ];

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: validationDetail }),
      });

      try {
        await transport.post('/api/v1/orders/batch', {});
        expect.unreachable('Should have thrown ApiHttpError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiHttpError);
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(422);
        expect(httpErr.code).toBe('VALIDATION_ERROR');
        expect(httpErr.message).toContain('body.orders.0.quantity: ensure this value is greater than 0');
        expect(httpErr.message).toContain('body.orders.0.unit_price: field required');
        expect(httpErr.message).toContain('header_token: invalid format');
      }
    });
  });

  describe('2. Query Parameters & URL Handling', () => {
    it('路徑中已含有 query string 時，params 應使用 & 正確串接', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
      });
      globalThis.fetch = fetchMock;

      await transport.get('/api/v1/search?category=electronics', {
        params: { page: 2, limit: 50, in_stock: true },
      });

      const [calledUrl] = fetchMock.mock.calls[0];
      expect(calledUrl).toBe('/api/v1/search?category=electronics&page=2&limit=50&in_stock=true');
    });

    it('特殊字元與中文查詢參數應正確被 URLSearchParams 編碼', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
      });
      globalThis.fetch = fetchMock;

      await transport.get('/api/v1/search', {
        params: { query: '工會 勞保 & 健保', filter: 'active+pending' },
      });

      const [calledUrl] = fetchMock.mock.calls[0];
      expect(calledUrl).toContain('query=%E5%B7%A5%E6%9C%83+%E5%8B%9E%E4%BF%9D+%26+%E5%81%A5%E4%BF%9D');
    });

    it('params 中值為 null 或 undefined 時應自動剔除', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
      });
      globalThis.fetch = fetchMock;

      await transport.get('/api/v1/items', {
        params: { active: true, nullField: null, undefinedField: undefined, zero: 0 },
      });

      const [calledUrl] = fetchMock.mock.calls[0];
      expect(calledUrl).toBe('/api/v1/items?active=true&zero=0');
    });
  });

  describe('3. Body Serialization & Header Injection', () => {
    it('傳入 FormData 時不應覆寫 Content-Type 為 application/json', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
      });
      globalThis.fetch = fetchMock;

      const formData = new FormData();
      formData.append('file', 'mock-content');

      await transport.post('/api/v1/upload', formData);

      const [, options] = fetchMock.mock.calls[0];
      expect(options.body).toBe(formData);
      expect(options.headers['Content-Type']).toBeUndefined();
    });

    it('自訂標頭應保留並可覆寫預設 Accept 標頭', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
      });
      globalThis.fetch = fetchMock;

      await transport.get('/api/v1/report.csv', {
        headers: { Accept: 'text/csv', 'X-Custom-Trace': 'trace-12345' },
      });

      const [, options] = fetchMock.mock.calls[0];
      expect(options.headers['Accept']).toBe('text/csv');
      expect(options.headers['X-Custom-Trace']).toBe('trace-12345');
    });
  });

  describe('4. AbortSignal, Timeout & Race Conditions', () => {
    it('若傳入之 externalSignal 在發起前已處於 aborted 狀態，應立即拋出 ApiAbortError 且不觸發 fetch', async () => {
      const controller = new AbortController();
      controller.abort(); // already aborted

      const fetchMock = vi.fn();
      globalThis.fetch = fetchMock;

      await expect(
        transport.get('/api/v1/immediate-cancel', { signal: controller.signal })
      ).rejects.toThrow(ApiAbortError);

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('請求超時時拋出的 ApiTimeoutError 應包含精確的 timeoutMs 屬性', async () => {
      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        return new Promise((_resolve, reject) => {
          const signal = options.signal as AbortSignal;
          signal.addEventListener('abort', () => {
            const err = new Error('The operation was aborted');
            err.name = 'AbortError';
            reject(err);
          });
        });
      });

      try {
        await transport.get('/api/v1/long-poll', { timeoutMs: 30 });
        expect.unreachable('Should have timed out');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiTimeoutError);
        const timeoutErr = err as ApiTimeoutError;
        expect(timeoutErr.timeoutMs).toBe(30);
        expect(timeoutErr.message).toContain('30 毫秒');
      }
    });

    it('當 50 個併發請求同時執行並各別超時/取消時，不應造成計時器或未補獲 Promise 洩漏', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url, options) => {
        return new Promise((resolve, reject) => {
          const signal = options.signal as AbortSignal;
          signal.addEventListener('abort', () => {
            const err = new Error('The operation was aborted');
            err.name = 'AbortError';
            reject(err);
          });

          if (url.includes('succeed')) {
            setTimeout(() => {
              resolve({
                ok: true,
                status: 200,
                headers: new Headers({ 'content-type': 'application/json' }),
                json: async () => ({ success: true }),
              });
            }, 10);
          }
        });
      });

      const promises = Array.from({ length: 50 }, (_, i) => {
        if (i % 2 === 0) {
          return transport.get(`/api/v1/succeed-${i}`, { timeoutMs: 500 });
        } else {
          return transport.get(`/api/v1/timeout-${i}`, { timeoutMs: 20 }).catch((e) => e);
        }
      });

      const results = await Promise.all(promises);
      expect(results.length).toBe(50);
      const timeouts = results.filter((r) => r instanceof ApiTimeoutError);
      expect(timeouts.length).toBe(25);
    });
  });

  describe('5. Network Failure & Exception Wrapping', () => {
    it('當 fetch 拋出非 Error 物件 (如字串) 時應安全包裝為 ApiNetworkError', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue('Fatal Socket Failure');

      try {
        await transport.get('/api/v1/socket-fail');
        expect.unreachable('Should have thrown ApiNetworkError');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiNetworkError);
        const netErr = err as ApiNetworkError;
        expect(netErr.name).toBe('ApiNetworkError');
        expect(netErr.originalError).toBe('Fatal Socket Failure');
      }
    });
  });

  describe('6. Error Utilities & Type Guards', () => {
    it('isApiError 應能精確識別所有 5 種 ApiError 子類別，並排除非 ApiError 物件', () => {
      expect(isApiError(new ApiNetworkError())).toBe(true);
      expect(isApiError(new ApiTimeoutError(1000))).toBe(true);
      expect(isApiError(new ApiAbortError())).toBe(true);
      expect(isApiError(new ApiHttpError(404, 'NOT_FOUND', 'Not found'))).toBe(true);
      expect(isApiError(new ApiDecodeError('Decode failed'))).toBe(true);

      expect(isApiError(new Error('Normal error'))).toBe(false);
      expect(isApiError(null)).toBe(false);
      expect(isApiError(undefined)).toBe(false);
      expect(isApiError({ name: 'ApiHttpError' })).toBe(false);
    });

    it('extractErrorMessage 與 extractErrorCode 應安全提取各型別訊息與代碼', () => {
      const httpErr = new ApiHttpError(403, 'PERMISSION_DENIED', 'Forbidden');
      expect(extractErrorMessage(httpErr)).toBe('Forbidden');
      expect(extractErrorCode(httpErr)).toBe('PERMISSION_DENIED');

      const nativeErr = new Error('Native Error');
      expect(extractErrorMessage(nativeErr)).toBe('Native Error');
      expect(extractErrorCode(nativeErr)).toBeUndefined();

      expect(extractErrorMessage('Direct String Error')).toBe('Direct String Error');
      expect(extractErrorMessage(null)).toBe('發生未知的系統錯誤');
    });

    it('isRetryableError 應正確辨別可重試與不可重試之錯誤', () => {
      expect(isRetryableError(new ApiTimeoutError(5000))).toBe(true);
      expect(isRetryableError(new ApiNetworkError())).toBe(true);
      expect(isRetryableError(new ApiHttpError(503, 'SERVICE_UNAVAILABLE', 'Unavailable', true))).toBe(true);
      expect(isRetryableError(new ApiHttpError(502, 'BAD_GATEWAY', 'Bad Gateway', true))).toBe(true);

      expect(isRetryableError(new ApiHttpError(400, 'BAD_REQUEST', 'Bad Request', false))).toBe(false);
      expect(isRetryableError(new ApiHttpError(401, 'UNAUTHORIZED', 'Unauthorized', false))).toBe(false);
      expect(isRetryableError(new ApiAbortError())).toBe(false);
      expect(isRetryableError(new ApiDecodeError('Decode error'))).toBe(false);
    });
  });
});
