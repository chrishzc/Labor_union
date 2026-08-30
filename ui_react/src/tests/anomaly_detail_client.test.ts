/**
 * File: anomaly_detail_client.test.ts
 * Description: 驗證 Anomalies detail／recovery 的唯讀 GET 與嚴格錯誤邊界。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  anomalyDetailClient,
  queryAnomalyDetail,
  queryAnomalyRecovery,
} from '../api/anomalies/anomaly_detail_client';
import { AnomalyDetailError } from '../api/anomalies/anomaly_detail_errors';
import {
  INVALID_ANOMALY_DETAIL_EXTRA_FIELD,
  INVALID_ANOMALY_DETAIL_MALFORMED_DATE,
  INVALID_ANOMALY_DETAIL_UNKNOWN_EVIDENCE_KIND,
  INVALID_ANOMALY_RECOVERY_MALFORMED_IDENTITY,
  INVALID_ANOMALY_RECOVERY_MISSING_BINDING,
  VALID_ANOMALY_DETAIL_RESPONSE,
  VALID_ANOMALY_RECOVERY_RESPONSE,
} from './fixtures/anomalies/anomaly_detail_contract_fixtures';

const fingerprint = 'a'.repeat(64);
const issueKey = `ci_${'c'.repeat(64)}`;

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe('Anomaly detail client strict GET boundary', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('detail-session-token', {
      id: 1,
      username: 'detail-operator',
      display_name: 'Detail Operator',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('以 Bearer session 呼叫兩個 exact GET path，且不接受自訂 Authorization', async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(VALID_ANOMALY_DETAIL_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(VALID_ANOMALY_RECOVERY_RESPONSE));
    globalThis.fetch = fetchSpy;

    const detail = await queryAnomalyDetail(
      { fingerprint },
      { headers: { Authorization: 'Bearer forged-token' } }
    );
    const recovery = await queryAnomalyRecovery(
      { issueKey },
      { headers: { authorization: 'Bearer forged-token' } }
    );

    expect(detail.summary.fingerprint).toBe(fingerprint);
    expect(recovery.issue_key).toBe(issueKey);
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    const firstCall = fetchSpy.mock.calls[0];
    const secondCall = fetchSpy.mock.calls[1];
    expect(firstCall[0]).toBe(`/api/v1/anomalies/${fingerprint}`);
    expect(secondCall[0]).toBe(`/api/v1/anomalies/${issueKey}`);

    for (const call of [firstCall, secondCall]) {
      const options = call[1];
      expect(options?.method).toBe('GET');
      const headers = options?.headers as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer detail-session-token');
      expect(
        Object.entries(headers).filter(([key]) => key.toLowerCase() === 'authorization')
      ).toEqual([['Authorization', 'Bearer detail-session-token']]);
    }
  });

  it('透過 singleton 保留兩個唯讀 query entry points', () => {
    expect(anomalyDetailClient.queryAnomalyDetail).toBe(queryAnomalyDetail);
    expect(anomalyDetailClient.queryAnomalyRecovery).toBe(queryAnomalyRecovery);
  });

  it.each([
    ['unknown evidence kind', INVALID_ANOMALY_DETAIL_UNKNOWN_EVIDENCE_KIND],
    ['extra detail envelope field', INVALID_ANOMALY_DETAIL_EXTRA_FIELD],
    ['malformed detail date', INVALID_ANOMALY_DETAIL_MALFORMED_DATE],
  ])('strictly rejects %s detail response vectors', async (_label, payload) => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(payload));

    await expect(queryAnomalyDetail({ fingerprint })).rejects.toMatchObject({
      name: 'AnomalyDetailError',
      code: 'VALIDATION',
      retryable: false,
    });
  });

  it.each([
    ['recovery missing binding', INVALID_ANOMALY_RECOVERY_MISSING_BINDING],
    ['malformed recovery identity', INVALID_ANOMALY_RECOVERY_MALFORMED_IDENTITY],
  ])('strictly rejects %s recovery response vectors', async (_label, payload) => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(payload));

    await expect(queryAnomalyRecovery({ issueKey })).rejects.toMatchObject({
      name: 'AnomalyDetailError',
      code: 'VALIDATION',
      retryable: false,
    });
  });

  it.each(['', 'A'.repeat(64), 'a'.repeat(63), 'a'.repeat(65), 'not-a-fingerprint'])(
    'fails closed before fetch for invalid fingerprint %s',
    async (invalidFingerprint) => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      await expect(
        Promise.resolve().then(() => queryAnomalyDetail({ fingerprint: invalidFingerprint }))
      ).rejects.toMatchObject({
          name: 'AnomalyDetailError',
          code: 'VALIDATION',
        });
      expect(fetchSpy).not.toHaveBeenCalled();
    }
  );

  it('maps an aborted detail request to typed ABORTED without mutation methods', async () => {
    const fetchSpy = vi.fn().mockImplementation(
      (_url: string, options?: RequestInit) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        })
    );
    globalThis.fetch = fetchSpy;

    const controller = new AbortController();
    const request = queryAnomalyDetail({ fingerprint }, { signal: controller.signal });
    controller.abort();

    await expect(request).rejects.toMatchObject({
      name: 'AnomalyDetailError',
      code: 'ABORTED',
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][1]?.method).toBe('GET');
  });

  it('發出的 request 不包含 POST、PUT、PATCH、DELETE 或 request body', async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(VALID_ANOMALY_DETAIL_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(VALID_ANOMALY_RECOVERY_RESPONSE));
    globalThis.fetch = fetchSpy;

    await queryAnomalyDetail({ fingerprint });
    await queryAnomalyRecovery({ issueKey });

    expect(fetchSpy.mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);
    expect(fetchSpy.mock.calls.every(([, options]) => options?.body === undefined)).toBe(true);
    expect(
      fetchSpy.mock.calls.some(([, options]) =>
        ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options?.method ?? '')
      )
    ).toBe(false);
  });

  it('未登入時以 UNAUTHENTICATED typed error fail closed', async () => {
    sessionClient.clearSession();
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    await expect(queryAnomalyDetail({ fingerprint })).rejects.toBeInstanceOf(AnomalyDetailError);
    await expect(queryAnomalyDetail({ fingerprint })).rejects.toMatchObject({
      code: 'UNAUTHENTICATED',
      status: 401,
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
