/**
 * File: transport.test.ts
 * Description: 驗證 Fetch 傳輸、嚴格 Global error 與逾時中斷防護。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { transport } from '../api/shared/transport';
import {
  ApiAbortError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../api/shared/typed_errors';

const VALID_GLOBAL_TYPED_ERROR_PAYLOAD = {
  detail: {
    error: {
      category: 'conflict',
      code: 'challenge_expired',
      message: '驗證階段已過期',
      field_errors: [],
      domain_blockers: ['challenge_expired'],
      retryable: false,
      correlation_id: 'corr-transport-001',
      current_version: null,
    },
  },
};

describe('Shared API Transport Client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('應成功執行 GET 請求並正確編碼 URL 查詢參數', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true, data: { status: 'healthy' } }),
    };

    const fetchMock = vi.fn().mockResolvedValue(mockResponse);
    globalThis.fetch = fetchMock;

    const res = await transport.get<{ success: boolean; data: { status: string } }>(
      '/api/v1/health',
      {
        params: { page: 1, filter: 'active', ignored: null },
      }
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, options] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe('/api/v1/health?page=1&filter=active');
    expect(options.method).toBe('GET');
    expect(options.headers['Accept']).toBe('application/json');
    expect(res.data.status).toBe('healthy');
  });

  it('應成功執行 POST 請求並序列化 JSON Body', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true, message: '登入成功' }),
    };

    const fetchMock = vi.fn().mockResolvedValue(mockResponse);
    globalThis.fetch = fetchMock;

    const payload = { username: 'admin', password: 'password123' };
    const res = await transport.post<{ success: boolean; message: string }>(
      '/api/v1/admin/auth/login',
      payload
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, options] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe('/api/v1/admin/auth/login');
    expect(options.method).toBe('POST');
    expect(options.headers['Content-Type']).toBe('application/json');
    expect(options.body).toBe(JSON.stringify(payload));
    expect(res.message).toBe('登入成功');
  });

  it('應自動注入 Bearer Token 至 Authorization 標頭', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true, data: { user: 'admin' } }),
    };

    const fetchMock = vi.fn().mockResolvedValue(mockResponse);
    globalThis.fetch = fetchMock;

    await transport.get('/api/v1/admin/auth/me', {
      token: 'session-bearer-uuid-token',
    });

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer session-bearer-uuid-token');
  });

  it('當接收到 HTTP 401 結構化錯誤時應拋出 ApiHttpError (非可重試)', async () => {
    const mockResponse = {
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: {
          code: 'admin_credentials_invalid',
          message: '帳號或密碼錯誤',
          retryable: false,
        },
      }),
    };

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    await expect(
      transport.post('/api/v1/admin/auth/login', { username: 'bad', password: 'bad' })
    ).rejects.toThrow(ApiHttpError);

    try {
      await transport.post('/api/v1/admin/auth/login', { username: 'bad', password: 'bad' });
    } catch (err) {
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(401);
      expect(httpErr.code).toBe('admin_credentials_invalid');
      expect(httpErr.message).toBe('帳號或密碼錯誤');
      expect(httpErr.retryable).toBe(false);
    }
  });

  it('完整八欄 nested detail.error 應嚴格解碼、傳遞 login code 並保留 raw payload', async () => {
    const payload = {
      detail: {
        error: {
          ...VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error,
          code: 'login_rate_limited',
          message: '登入嘗試過於頻繁，請稍後再試',
          retryable: true,
          current_version: 4,
        },
      },
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      statusText: 'Too Many Requests',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => payload,
    });

    try {
      await transport.post('/api/v1/admin/auth/login/challenges');
      expect.unreachable('應拋出 ApiHttpError');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiHttpError);
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(429);
      expect(httpErr.code).toBe('login_rate_limited');
      expect(httpErr.message).toBe('登入嘗試過於頻繁，請稍後再試');
      expect(httpErr.retryable).toBe(true);
      expect(httpErr.raw).toBe(payload);
    }
  });

  it.each([
    {
      name: 'nested extra field',
      mutate: (error: typeof VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error) => ({
        ...error,
        unexpected: 'drift',
      }),
    },
    {
      name: 'nested missing required field',
      mutate: (error: typeof VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error) => {
        const { domain_blockers: _domainBlockers, ...withoutRequired } = error;
        return withoutRequired;
      },
    },
    {
      name: 'nested wrong primitive',
      mutate: (error: typeof VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error) => ({
        ...error,
        retryable: 'true',
      }),
    },
    {
      name: 'nested forbidden null',
      mutate: (error: typeof VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error) => ({
        ...error,
        message: null,
      }),
    },
    {
      name: 'wrapper extra field',
      mutate: (error: typeof VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error) => ({
        ...error,
        __wrapperExtra: true,
      }),
    },
  ])('malformed $name nested envelope 應退回 HTTP status 並保留 raw', async ({ mutate, name }) => {
    const malformedError = mutate(VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error);
    const payload = name === 'wrapper extra field'
      ? {
          detail: {
            error: VALID_GLOBAL_TYPED_ERROR_PAYLOAD.detail.error,
            extra: true,
            code: 'legacy_must_not_override_status',
            message: 'legacy message must not pass through',
            retryable: true,
          },
        }
      : { detail: { error: malformedError } };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => payload,
    });

    try {
      await transport.get('/api/v1/orders/CASE-001');
      expect.unreachable('應拋出 ApiHttpError');
    } catch (err) {
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(409);
      expect(httpErr.code).toBe('HTTP_409');
      expect(httpErr.message).toBe('Conflict');
      expect(httpErr.retryable).toBe(false);
      expect(httpErr.raw).toBe(payload);
    }
  });

  it('current_version 為明確 nullable 時仍應接受完整 nested envelope', async () => {
    const payload = VALID_GLOBAL_TYPED_ERROR_PAYLOAD;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => payload,
    });

    await expect(transport.get('/api/v1/orders/CASE-001')).rejects.toMatchObject({
      status: 409,
      code: 'challenge_expired',
      retryable: false,
      raw: payload,
    });
  });

  it('當接收到 HTTP 403 權限不足時應拋出 ApiHttpError', async () => {
    const mockResponse = {
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: '缺少必要能力：system.administration',
      }),
    };

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    try {
      await transport.get('/api/v1/system/status/performance-snapshot');
    } catch (err) {
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(403);
      expect(httpErr.message).toBe('缺少必要能力：system.administration');
    }
  });

  it('當接收到 HTTP 503 時應正確標記為 retryable = true', async () => {
    const mockResponse = {
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: {
          code: 'admin_session_storage_unavailable',
          message: '資料庫維護中',
          retryable: true,
        },
      }),
    };

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    try {
      await transport.get('/api/v1/admin/auth/me');
    } catch (err) {
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(503);
      expect(httpErr.retryable).toBe(true);
      expect(httpErr.message).toBe('資料庫維護中');
    }
  });

  it('當接收到 FastAPI 422 驗證錯誤時應解構欄位錯誤訊息', async () => {
    const mockResponse = {
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: [
          { loc: ['body', 'username'], msg: 'field required' },
          { loc: ['body', 'password'], msg: 'field required' },
        ],
      }),
    };

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    try {
      await transport.post('/api/v1/admin/auth/login', {});
    } catch (err) {
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(422);
      expect(httpErr.code).toBe('VALIDATION_ERROR');
      expect(httpErr.message).toContain('body.username: field required');
      expect(httpErr.message).toContain('body.password: field required');
    }
  });

  it('請求逾時應拋出 ApiTimeoutError', async () => {
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

    await expect(
      transport.get('/api/v1/slow-endpoint', { timeoutMs: 50 })
    ).rejects.toThrow(ApiTimeoutError);
  });

  it('外部主動中斷請求時應拋出 ApiAbortError', async () => {
    const controller = new AbortController();

    globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
      return new Promise((_resolve, reject) => {
        const signal = options.signal as AbortSignal;
        signal.addEventListener('abort', () => {
          const err = new Error('The user aborted a request.');
          err.name = 'AbortError';
          reject(err);
        });
      });
    });

    const promise = transport.get('/api/v1/endpoint', {
      signal: controller.signal,
      timeoutMs: 5000,
    });

    controller.abort();

    await expect(promise).rejects.toThrow(ApiAbortError);
  });

  it('網路中斷或 DNS 解析失敗應拋出 ApiNetworkError', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(transport.get('/api/v1/endpoint')).rejects.toThrow(ApiNetworkError);
  });

  it('應支援 PUT 與 DELETE 輔助方法', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true }),
    };
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    await transport.put('/api/v1/item/1', { title: 'updated' });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/item/1',
      expect.objectContaining({ method: 'PUT' })
    );

    await transport.delete('/api/v1/item/1');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/item/1',
      expect.objectContaining({ method: 'DELETE' })
    );
  });
});
