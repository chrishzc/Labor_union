/**
 * File: historical_operational_baseline_client.test.ts
 * Description: 驗證 Orders owned Historical Operational Baseline strict GET client。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  historicalOperationalBaselineClient,
  queryHistoricalOperationalBaselineByCase,
} from '../api/orders/historical_operational_baseline_client';
import {
  HISTORICAL_BASELINE_CASE_NO,
  HISTORICAL_OPERATIONAL_BASELINE_RESPONSE,
} from './fixtures/orders/historical_operational_baseline_contract_fixtures';

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('Orders Historical Operational Baseline strict case GET client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('orders-session', {
      id: 1,
      username: 'orders-operator',
      display_name: 'Orders Operator',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('只呼叫 Orders exact same-case GET，使用 session Bearer 且沒有 mutation surface', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(response(HISTORICAL_OPERATIONAL_BASELINE_RESPONSE));
    globalThis.fetch = fetchSpy;

    const baseline = await queryHistoricalOperationalBaselineByCase(HISTORICAL_BASELINE_CASE_NO);

    expect(baseline.current_baseline?.selected_step).toBe(3);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][0]).toBe(`/api/v1/orders/${HISTORICAL_BASELINE_CASE_NO}/historical-operational-baseline`);
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({ method: 'GET', body: undefined });
    expect(fetchSpy.mock.calls[0][1]?.headers).toMatchObject({
      Authorization: 'Bearer orders-session',
    });
    expect(Object.keys(historicalOperationalBaselineClient)).toEqual(['queryByCase']);
  });

  it.each([
    ['extra field', { ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE, data: { ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE.data, resolve: true } }],
    ['step projection drift', {
      ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE,
      data: {
        ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE.data,
        current_baseline: {
          ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE.data.current_baseline!,
          step_projection: [{ step: 2, state: 'in_progress' }],
        },
      },
    }],
  ])('將 %s strict decode failure 保留為 typed unavailable', async (_label, payload) => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(payload));

    await expect(queryHistoricalOperationalBaselineByCase(HISTORICAL_BASELINE_CASE_NO)).rejects.toMatchObject({
      name: 'HistoricalOperationalBaselineUnavailableError',
      code: 'historical_operational_baseline_contract_unavailable',
      retryable: false,
    });
  });

  it('拒絕其他案件的 Orders baseline，不把跨案資料傳給 component', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE,
      data: { ...HISTORICAL_OPERATIONAL_BASELINE_RESPONSE.data, case_no: 'CASE-OTHER' },
    }));

    await expect(queryHistoricalOperationalBaselineByCase(HISTORICAL_BASELINE_CASE_NO)).rejects.toMatchObject({
      code: 'historical_operational_baseline_contract_unavailable',
    });
  });

  it('保留 server unavailable code/retryable，不轉成空資料或假成功', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      detail: {
        error: {
          category: 'unavailable',
          code: 'historical_operational_baseline_unavailable',
          message: '歷史案件作業基準暫時無法使用。',
          field_errors: [],
          domain_blockers: [],
          retryable: true,
          correlation_id: 'hob-correlation',
          current_version: null,
        },
      },
    }, 503));

    await expect(queryHistoricalOperationalBaselineByCase(HISTORICAL_BASELINE_CASE_NO)).rejects.toMatchObject({
      name: 'HistoricalOperationalBaselineUnavailableError',
      code: 'historical_operational_baseline_unavailable',
      retryable: true,
      status: 503,
    });
  });
});
