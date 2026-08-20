/**
 * File: challenger_g2_orders_client_resilience.test.ts
 * Description: 挑戰 Orders query 的 abort、timeout、auth、conflict 與 fresh-token failure paths。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createOrdersQueryClient,
  getOrderDetail,
  getOrderSummaries,
} from '../api/orders/order_query_client';
import {
  ApiAbortError,
  ApiHttpError,
  ApiTimeoutError,
  OrderConflictError,
  OrderNotModifiedError,
  OrderRetiredEndpointError,
  OrderServiceUnavailableError,
} from '../api/orders/order_query_errors';
import { transport } from '../api/shared/transport';
import { realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';

const success = {
  success: true,
  message: 'Success',
  data: realisticOrderSummaryPage,
  error: null,
};

describe('G2 Orders resilience challenger', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('volatile-token');
  });

  it.each([
    new ApiAbortError(),
    new ApiTimeoutError(10_000),
  ])('preserves transport cancellation semantics: %s', async (error) => {
    vi.spyOn(transport, 'get').mockRejectedValue(error);
    await expect(getOrderSummaries()).rejects.toBe(error);
  });

  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
  ] as const)('does not relabel auth HTTP %i as an Orders business fact', async (status, code) => {
    const error = new ApiHttpError(status, code, code);
    vi.spyOn(transport, 'get').mockRejectedValue(error);
    await expect(getOrderSummaries()).rejects.toBe(error);
  });

  it('maps 503, 410, and 304 without reading permissive raw dictionaries', async () => {
    const get = vi.spyOn(transport, 'get');
    get.mockRejectedValueOnce(new ApiHttpError(503, 'unavailable', 'later', true));
    await expect(getOrderSummaries()).rejects.toThrow(OrderServiceUnavailableError);
    get.mockRejectedValueOnce(new ApiHttpError(410, 'gone', 'retired'));
    await expect(getOrderSummaries()).rejects.toThrow(OrderRetiredEndpointError);
    get.mockRejectedValueOnce(new ApiHttpError(304, 'not_modified', 'same'));
    await expect(getOrderSummaries()).rejects.toThrow(OrderNotModifiedError);
  });

  it('fails conflict metadata closed when the typed error envelope drifts', async () => {
    vi.spyOn(transport, 'get').mockRejectedValue(new ApiHttpError(409, 'conflict', 'stale', false, {
      current_version: 99,
      domain_blockers: ['UNTRUSTED_LEGACY_SHAPE'],
    }));
    let caught: unknown;
    try {
      await getOrderDetail('CASE-1');
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(OrderConflictError);
    expect(caught).toMatchObject({ currentVersion: null, domainBlockers: [] });
  });

  it('uses a new volatile token after logout instead of retaining a constructor snapshot', async () => {
    const token = vi.spyOn(sessionClient, 'getToken')
      .mockReturnValueOnce('before-logout')
      .mockReturnValueOnce(null);
    const get = vi.spyOn(transport, 'get').mockResolvedValue(success);
    const client = createOrdersQueryClient();
    await client.getOrderSummaries();
    await client.getOrderSummaries();
    expect(token).toHaveBeenCalledTimes(2);
    expect(get.mock.calls.map((call) => call[1]?.token)).toEqual(['before-logout', null]);
  });

  it('keeps concurrent request signals independent', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(success);
    const first = new AbortController();
    const second = new AbortController();
    await Promise.all([
      getOrderSummaries({}, { signal: first.signal }),
      getOrderSummaries({}, { signal: second.signal }),
    ]);
    expect(get.mock.calls[0][1]?.signal).toBe(first.signal);
    expect(get.mock.calls[1][1]?.signal).toBe(second.signal);
  });
});
