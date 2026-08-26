/**
 * File: transport.ts
 * Description: 統一 Fetch 傳輸、嚴格 Global error 解碼與 HTTP fallback。
 */
import {
  ApiAbortError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from './typed_errors';
import { z } from 'zod';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  token?: string | null;
  timeoutMs?: number;
  signal?: AbortSignal;
  baseUrl?: string;
}

const DEFAULT_TIMEOUT_MS = 10000;
export const ADMIN_SESSION_UNAUTHORIZED_EVENT = 'union-admin-session-unauthorized';

const GlobalFieldErrorSchema = z.strictObject({
  field: z.string(),
  code: z.string(),
  message: z.string(),
});

const GlobalTypedErrorSchema = z.strictObject({
  category: z.enum([
    'validation',
    'forbidden',
    'not_found',
    'domain_blocked',
    'conflict',
    'idempotency_mismatch',
    'unavailable',
    'internal',
  ]),
  code: z.string(),
  message: z.string(),
  field_errors: z.array(GlobalFieldErrorSchema),
  domain_blockers: z.array(z.string()),
  retryable: z.boolean(),
  correlation_id: z.string(),
  current_version: z.number().int().nullable(),
});

const GlobalTypedErrorResponseSchema = z.strictObject({
  detail: z.strictObject({
    error: GlobalTypedErrorSchema,
  }),
});

function readProperty(value: unknown, key: string): unknown {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return undefined;
  }
  return Reflect.get(value, key);
}

export async function request<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const {
    method = 'GET',
    headers = {},
    params,
    body,
    token,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal: externalSignal,
    baseUrl = '',
  } = options;

  // Build query string
  let url = `${baseUrl}${path}`;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (val !== null && val !== undefined) {
        searchParams.append(key, String(val));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString;
    }
  }

  // Setup abort controller & timeout
  const controller = new AbortController();
  let isTimedOut = false;

  const timer = setTimeout(() => {
    isTimedOut = true;
    controller.abort();
  }, timeoutMs);

  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timer);
      throw new ApiAbortError();
    }
    externalSignal.addEventListener('abort', () => {
      controller.abort();
    });
  }

  // Prepare request headers
  const reqHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...headers,
  };

  if (token) {
    reqHeaders['Authorization'] = `Bearer ${token}`;
  }

  let serializedBody: BodyInit | undefined;
  if (body !== undefined && body !== null) {
    if (
      typeof body === 'string' ||
      body instanceof FormData ||
      body instanceof Blob ||
      body instanceof URLSearchParams
    ) {
      serializedBody = body;
    } else {
      reqHeaders['Content-Type'] = 'application/json';
      serializedBody = JSON.stringify(body);
    }
  }

  try {
    const response = await fetch(url, {
      method,
      headers: reqHeaders,
      body: serializedBody,
      signal: controller.signal,
    });

    clearTimeout(timer);

    // Parse response body
    let responseData: unknown = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        responseData = await response.json();
      } catch {
        responseData = null;
      }
    } else {
      const text = await response.text();
      try {
        responseData = JSON.parse(text);
      } catch {
        responseData = text;
      }
    }

    if (!response.ok) {
      let code = `HTTP_${response.status}`;
      let message = response.statusText || `請求失敗 (${response.status})`;
      let retryable = response.status === 503 || response.status === 502 || response.status === 504;

      const typedError = GlobalTypedErrorResponseSchema.safeParse(responseData);
      if (typedError.success) {
        code = typedError.data.detail.error.code;
        message = typedError.data.detail.error.message;
        retryable = typedError.data.detail.error.retryable;
      } else {
        const detail = readProperty(responseData, 'detail');
        if (detail !== undefined) {
          // 若 detail.error 存在但未通過完整 strict schema，禁止退回 legacy 欄位。
          if (readProperty(detail, 'error') === undefined) {
            if (typeof detail === 'string') {
              message = detail;
            } else if (Array.isArray(detail)) {
              // FastAPI 422 validation error
              code = 'VALIDATION_ERROR';
              message = detail
                .map((item) => {
                  const location = readProperty(item, 'loc');
                  const itemMessage = readProperty(item, 'msg');
                  const renderedLocation = Array.isArray(location)
                    ? location.join('.')
                    : String(location ?? 'field');
                  return `${renderedLocation}: ${String(itemMessage ?? 'invalid')}`;
                })
                .join('; ');
            } else {
              const detailCode = readProperty(detail, 'code');
              const detailMessage = readProperty(detail, 'message');
              const detailRetryable = readProperty(detail, 'retryable');
              if (typeof detailCode === 'string') code = detailCode;
              if (typeof detailMessage === 'string') message = detailMessage;
              if (typeof detailRetryable === 'boolean') {
                retryable = detailRetryable;
              }
            }
          }
        } else {
          const payloadError = readProperty(responseData, 'error');
          const payloadMessage = readProperty(responseData, 'message');
          if (typeof payloadError === 'string') {
            message = payloadError;
          } else if (typeof payloadMessage === 'string') {
            message = payloadMessage;
          }
        }
      }

      if (response.status === 401 && token && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(ADMIN_SESSION_UNAUTHORIZED_EVENT, {
          detail: { rejectedToken: token },
        }));
      }

      throw new ApiHttpError(
        response.status,
        code,
        message,
        retryable,
        responseData
      );
    }

    return responseData as T;
  } catch (error) {
    clearTimeout(timer);

    if (error instanceof ApiHttpError) {
      throw error;
    }

    if (isTimedOut) {
      throw new ApiTimeoutError(timeoutMs);
    }

    if (
      (error instanceof DOMException && error.name === 'AbortError') ||
      (error instanceof Error && error.name === 'AbortError')
    ) {
      if (isTimedOut) {
        throw new ApiTimeoutError(timeoutMs);
      }
      throw new ApiAbortError();
    }

    throw new ApiNetworkError(
      error instanceof Error ? error.message : '網路請求失敗',
      error
    );
  }
}

export const transport = {
  request,
  get: <T = unknown>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T = unknown>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'POST', body }),
  put: <T = unknown>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  delete: <T = unknown>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};

export default transport;
