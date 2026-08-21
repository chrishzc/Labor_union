/**
 * File: holiday_client.test.ts
 * Description: 驗證國定假日 client 的 strict decode、fresh token、horizon 與 typed failure。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createHolidayClient,
  type HolidayClient,
} from '../api/scheduling/holiday_client';
import {
  HolidayContractError,
  HolidayUnauthenticatedError,
  HolidayValidationError,
} from '../api/scheduling/holiday_errors';
import {
  HOLIDAY_APPLY_REQUEST,
  HOLIDAY_APPLY_RESPONSE,
  HOLIDAY_PREVIEW_REQUEST,
  HOLIDAY_PREVIEW_RESPONSE,
  HOLIDAY_QUERY,
  HOLIDAY_QUERY_RESPONSE,
} from './fixtures/holiday_contract_fixtures';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setSession(token = 'holiday-token-a'): void {
  sessionClient.setSession(token, {
    id: 7,
    username: 'holiday-test-admin',
    display_name: '國定假日測試管理員',
    role: 'system_admin',
  });
}

describe('holiday client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    setSession();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('以最新 memory token 查詢 typed horizon，且不帶 mutation header', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(HOLIDAY_QUERY_RESPONSE));
    const client: HolidayClient = createHolidayClient();

    const calendar = await client.query(HOLIDAY_QUERY, {
      correlationId: 'holiday-query-correlation',
    });

    expect(calendar).toEqual(HOLIDAY_QUERY_RESPONSE.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe(
      '/api/v1/holidays?from_date=2026-01-01&to_date=2026-12-31',
    );
    expect(options?.method).toBe('GET');
    const headers = new Headers(options?.headers);
    expect(headers.get('Authorization')).toBe('Bearer holiday-token-a');
    expect(headers.get('X-Correlation-ID')).toBe('holiday-query-correlation');
    expect(headers.get('Idempotency-Key')).toBeNull();
    expect(options?.body).toBeUndefined();
  });

  it('Preview 與 Apply 僅送出完整 server contract，Apply 保留 caller stable key', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(HOLIDAY_PREVIEW_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(HOLIDAY_APPLY_RESPONSE));
    const client = createHolidayClient();

    await client.preview(HOLIDAY_PREVIEW_REQUEST, {
      correlationId: 'holiday-preview-correlation',
    });
    setSession('holiday-token-b');
    await client.apply(HOLIDAY_APPLY_REQUEST, {
      correlationId: 'holiday-apply-correlation',
      idempotencyKey: 'holiday-apply-idempotency-001',
    });

    const calls = vi.mocked(globalThis.fetch).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0]?.[0]).toBe('/api/v1/holidays/preview');
    expect(calls[0]?.[1]?.method).toBe('POST');
    expect(JSON.parse(String(calls[0]?.[1]?.body))).toEqual(HOLIDAY_PREVIEW_REQUEST);
    expect(new Headers(calls[0]?.[1]?.headers).get('Idempotency-Key')).toBeNull();
    expect(calls[1]?.[0]).toBe('/api/v1/holidays/apply');
    expect(calls[1]?.[1]?.method).toBe('POST');
    expect(JSON.parse(String(calls[1]?.[1]?.body))).toEqual(HOLIDAY_APPLY_REQUEST);
    expect(new Headers(calls[1]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer holiday-token-b',
    );
    expect(new Headers(calls[1]?.[1]?.headers).get('Idempotency-Key')).toBe(
      'holiday-apply-idempotency-001',
    );
  });

  it('未登入、半組 horizon、缺 Apply identity 在 fetch 前 fail closed', async () => {
    globalThis.fetch = vi.fn();
    const client = createHolidayClient();
    sessionClient.clearSession();

    await expect(client.query(HOLIDAY_QUERY)).rejects.toBeInstanceOf(
      HolidayUnauthenticatedError,
    );
    setSession();
    await expect(
      client.query({ from_date: HOLIDAY_QUERY.from_date, to_date: '2025-12-31' }),
    ).rejects.toBeInstanceOf(HolidayValidationError);
    await expect(
      client.apply(HOLIDAY_APPLY_REQUEST, { correlationId: 'missing-key' } as never),
    ).rejects.toBeInstanceOf(HolidayValidationError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('success envelope、payload extra 與 null data 一律轉成 strict contract error', async () => {
    const client = createHolidayClient();
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ ...HOLIDAY_QUERY_RESPONSE, unexpected: true }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ...HOLIDAY_QUERY_RESPONSE,
          data: { ...HOLIDAY_QUERY_RESPONSE.data, unexpected: true },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ success: true, message: 'ok', data: null, error: null }),
      );

    await expect(client.query(HOLIDAY_QUERY)).rejects.toBeInstanceOf(
      HolidayContractError,
    );
    await expect(client.query(HOLIDAY_QUERY)).rejects.toBeInstanceOf(
      HolidayContractError,
    );
    await expect(client.query(HOLIDAY_QUERY)).rejects.toBeInstanceOf(
      HolidayValidationError,
    );
  });

  it('不把未知 HTTP failure 當成成功，並保留 typed conflict code', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(
        {
          detail: {
            error: {
              category: 'conflict',
              code: 'stale_preview',
              message: '版本已過期',
              field_errors: [],
              domain_blockers: ['calendar_version'],
              retryable: false,
              correlation_id: 'holiday-http-conflict',
              current_version: null,
            },
          },
        },
        409,
      ));
    const client = createHolidayClient();
    await expect(client.query(HOLIDAY_QUERY)).rejects.toMatchObject({
      status: 409,
      publicCode: 'stale_preview',
    });
  });
});
