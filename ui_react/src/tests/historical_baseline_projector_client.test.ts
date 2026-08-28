/**
 * File: historical_baseline_projector_client.test.ts
 * Description: 驗證 HPROJ 同案 strict GET client、binding 與 typed unavailable。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  historicalBaselineProjectorClient,
  queryHistoricalBaselineProjectorByCase,
} from '../api/anomalies/historical_baseline_projector_client';
import {
  HISTORICAL_BASELINE_CASE_NO,
  HISTORICAL_BASELINE_PROJECTOR_RESPONSE,
} from './fixtures/anomalies/historical_baseline_projector_contract_fixtures';

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('Historical Baseline Projector strict case GET client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('hproj-session', {
      id: 1,
      username: 'hproj-operator',
      display_name: 'HPROJ Operator',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('只呼叫 exact same-case GET，使用 session Bearer 且沒有 mutation surface', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(response(HISTORICAL_BASELINE_PROJECTOR_RESPONSE));
    globalThis.fetch = fetchSpy;

    const projection = await queryHistoricalBaselineProjectorByCase(HISTORICAL_BASELINE_CASE_NO);

    expect(projection.receipt?.case_no).toBe(HISTORICAL_BASELINE_CASE_NO);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][0]).toBe(`/api/v1/orders/${HISTORICAL_BASELINE_CASE_NO}/historical-baseline-projector`);
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({ method: 'GET', body: undefined });
    expect(fetchSpy.mock.calls[0][1]?.headers).toMatchObject({
      Authorization: 'Bearer hproj-session',
    });
    expect(Object.keys(historicalBaselineProjectorClient)).toEqual(['queryByCase']);
  });

  it.each([
    ['extra field', { ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE, data: { ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data, resolve: true } }],
    ['membership count drift', {
      ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE,
      data: {
        ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data,
        receipt: { ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data.receipt, active_membership_set_count: 1 },
      },
    }],
    ['earliest referral drift', {
      ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE,
      data: {
        ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data,
        current_alert: {
          ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data.current_alert!,
          display: { ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data.current_alert!.display, earliest_blocked_step: 8 },
        },
      },
    }],
  ])('將 %s strict decode failure 保留為 typed unavailable', async (_label, payload) => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(payload));

    await expect(queryHistoricalBaselineProjectorByCase(HISTORICAL_BASELINE_CASE_NO)).rejects.toMatchObject({
      name: 'HistoricalBaselineProjectorUnavailableError',
      code: 'historical_baseline_projection_contract_unavailable',
      retryable: false,
    });
  });

  it('拒絕其他案件的 receipt/readback，不把跨案資料傳給 component', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE,
      data: {
        ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data,
        receipt: { ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data.receipt, case_no: 'CASE-OTHER' },
        current_alert: {
          ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data.current_alert!,
          display: { ...HISTORICAL_BASELINE_PROJECTOR_RESPONSE.data.current_alert!.display, case_no: 'CASE-OTHER' },
        },
      },
    }));

    await expect(queryHistoricalBaselineProjectorByCase(HISTORICAL_BASELINE_CASE_NO)).rejects.toMatchObject({
      code: 'historical_baseline_projection_contract_unavailable',
    });
  });

  it('保留 server unavailable code/retryable，不轉成空資料或假成功', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      detail: {
        error: {
          category: 'unavailable',
          code: 'historical_baseline_projection_unavailable',
          message: '歷史基線 projector readback 暫時無法使用。',
          field_errors: [],
          domain_blockers: [],
          retryable: true,
          correlation_id: 'hproj-correlation',
          current_version: null,
        },
      },
    }, 503));

    await expect(queryHistoricalBaselineProjectorByCase(HISTORICAL_BASELINE_CASE_NO)).rejects.toMatchObject({
      name: 'HistoricalBaselineProjectorUnavailableError',
      code: 'historical_baseline_projection_unavailable',
      retryable: true,
      status: 503,
    });
  });
});
