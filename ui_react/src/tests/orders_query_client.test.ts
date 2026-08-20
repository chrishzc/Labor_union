/**
 * File: orders_query_client.test.ts
 * Description: 驗證 Orders 八 GET allowlist、strict decode、fresh token 與 typed failures。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createOrdersQueryClient,
  getActualStart,
  getAssignmentPlan,
  getContractCompletion,
  getFormManagementContext,
  getOrderCalendarDetail,
  getOrderDetail,
  getOrderSummaries,
  getOrderTerms,
  ordersQueryClient,
} from '../api/orders/order_query_client';
import {
  ApiDecodeError,
  ApiHttpError,
  OrderNotFoundError,
  OrderValidationError,
} from '../api/orders/order_query_errors';
import { transport } from '../api/shared/transport';
import {
  realisticActualStart,
  realisticAssignmentPlan,
  realisticContractCompletion,
  realisticFormManagementContext,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
} from './fixtures/orders_real_data_fixtures';

const envelope = <T>(data: T) => ({
  success: true,
  message: 'Success',
  data,
  error: null,
});

let testTokenSequence = 0;

describe('OrdersQueryClient bounded contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    testTokenSequence += 1;
    vi.spyOn(sessionClient, 'getToken').mockReturnValue(`token-current-${testTokenSequence}`);
  });

  it('exposes exactly the eight approved query methods', () => {
    const methods = Object.getOwnPropertyNames(
      Object.getPrototypeOf(ordersQueryClient) as object
    ).filter((name) => name !== 'constructor').sort();
    expect(methods).toEqual([
      'getActualStart',
      'getAssignmentPlan',
      'getContractCompletion',
      'getFormManagementContext',
      'getOrderCalendarDetail',
      'getOrderDetail',
      'getOrderSummaries',
      'getOrderTerms',
    ]);
  });

  it.each([
    ['getOrderSummaries', () => getOrderSummaries(), '/api/v1/orders/summaries', realisticOrderSummaryPage],
    ['getOrderDetail', () => getOrderDetail('CASE 1'), '/api/v1/orders/CASE%201', realisticOrderDetail],
    ['getOrderCalendarDetail', () => getOrderCalendarDetail('CASE 1'), '/api/v1/orders/CASE%201/calendar-detail', realisticOrderCalendarDetail],
    ['getOrderTerms', () => getOrderTerms('CASE 1'), '/api/v1/orders/CASE%201/terms', realisticOrderTerms],
    ['getFormManagementContext', () => getFormManagementContext('CASE 1'), '/api/v1/orders/CASE%201/form-management-context', realisticFormManagementContext],
    ['getActualStart', () => getActualStart('CASE 1'), '/api/v1/orders/CASE%201/actual-start', realisticActualStart],
    ['getContractCompletion', () => getContractCompletion('CASE 1'), '/api/v1/orders/CASE%201/contract-completion', realisticContractCompletion],
    ['getAssignmentPlan', () => getAssignmentPlan('CASE 1'), '/api/v1/orders/CASE%201/assignment-plan', realisticAssignmentPlan],
  ] as const)('%s uses the approved GET path and strict success envelope', async (_name, call, path, data) => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(data));
    await expect(call()).resolves.toEqual(data);
    expect(get).toHaveBeenCalledOnce();
    expect(get.mock.calls[0][0]).toBe(path);
    expect(get.mock.calls[0][1]?.token).toMatch(/^token-current-/);
  });

  it('normalizes summary parameters without inventing defaults', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(realisticOrderSummaryPage));
    await getOrderSummaries({ page_size: 25, after_case_no: ' CASE-9 ', query_text: ' 林小姐 ' });
    expect(get.mock.calls[0][1]?.params).toEqual({
      page_size: 25,
      after_case_no: 'CASE-9',
      query_text: '林小姐',
    });
  });

  it.each([
    { page_size: 0 },
    { page_size: 201 },
  ])('rejects invalid summary request parameters: %o', (params) => {
    expect(() => getOrderSummaries(params)).toThrow();
  });

  it.each([
    getOrderDetail,
    getOrderCalendarDetail,
    getOrderTerms,
    getFormManagementContext,
    getActualStart,
    getContractCompletion,
    getAssignmentPlan,
  ])('rejects blank case numbers before transport', (call) => {
    const get = vi.spyOn(transport, 'get');
    expect(() => call('  ')).toThrow(OrderValidationError);
    expect(get).not.toHaveBeenCalled();
  });

  it.each([
    ['missing required', { ...realisticOrderSummaryPage, etag: undefined }],
    ['wrong primitive', { ...realisticOrderSummaryPage, items: 'not-an-array' }],
    ['extra root field', { ...realisticOrderSummaryPage, fake_stage: 'active_service' }],
    ['extra nested field', {
      ...realisticOrderSummaryPage,
      items: [{ ...realisticOrderSummaryPage.items[0], guessed_settlement: true }],
    }],
    ['null violation', { ...realisticOrderSummaryPage, etag: null }],
  ])('fails closed for %s', async (_label, data) => {
    vi.spyOn(transport, 'get').mockResolvedValue(envelope(data));
    await expect(getOrderSummaries()).rejects.toThrow(ApiDecodeError);
  });

  it.each([
    { success: true, message: 'Success', data: realisticOrderSummaryPage },
    { success: true, message: 'Success', data: realisticOrderSummaryPage, error: null, extra: true },
    { success: true, message: 'Success', data: null, error: null },
  ])('fails closed for malformed envelope', async (raw) => {
    vi.spyOn(transport, 'get').mockResolvedValue(raw);
    await expect(getOrderSummaries()).rejects.toThrow(ApiDecodeError);
  });

  it('reads the volatile token for every request instead of caching it', async () => {
    const token = vi.spyOn(sessionClient, 'getToken')
      .mockReturnValueOnce('token-a')
      .mockReturnValueOnce('token-b');
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(realisticOrderSummaryPage));
    await getOrderSummaries();
    await getOrderSummaries();
    expect(token).toHaveBeenCalledTimes(2);
    expect(get.mock.calls[0][1]?.token).toBe('token-a');
    expect(get.mock.calls[1][1]?.token).toBe('token-b');
  });

  it('shares one pending summary Promise for the same session and query', async () => {
    type SummaryEnvelope = {
      success: boolean;
      message: string;
      data: typeof realisticOrderSummaryPage;
      error: null;
    };
    let resolve!: (value: SummaryEnvelope) => void;
    const response = new Promise<SummaryEnvelope>((next) => {
      resolve = next;
    });
    const get = vi.spyOn(transport, 'get').mockReturnValue(response);
    const first = getOrderSummaries({ page_size: 50 });
    const second = getOrderSummaries({ page_size: 50 });
    expect(first).toBe(second);
    expect(get).toHaveBeenCalledOnce();
    resolve(envelope(realisticOrderSummaryPage));
    await expect(first).resolves.toEqual(realisticOrderSummaryPage);
  });

  it('evicts a failed summary flight so an explicit retry can send again', async () => {
    const get = vi.spyOn(transport, 'get')
      .mockRejectedValueOnce(new Error('temporary failure'))
      .mockResolvedValueOnce(envelope(realisticOrderSummaryPage));
    const first = getOrderSummaries();
    const duplicate = getOrderSummaries();
    expect(first).toBe(duplicate);
    await expect(first).rejects.toThrow('temporary failure');
    await expect(getOrderSummaries()).resolves.toEqual(realisticOrderSummaryPage);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('retains a fulfilled flight only for the StrictMode burst TTL', async () => {
    vi.useFakeTimers();
    try {
      const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(realisticOrderSummaryPage));
      const first = getOrderSummaries({ query_text: 'burst-case' });
      await first;
      expect(getOrderSummaries({ query_text: 'burst-case' })).toBe(first);
      expect(get).toHaveBeenCalledOnce();
      await vi.advanceTimersByTimeAsync(251);
      await expect(getOrderSummaries({ query_text: 'burst-case' })).resolves.toEqual(realisticOrderSummaryPage);
      expect(get).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('honors an explicit per-request token override', async () => {
    const token = vi.spyOn(sessionClient, 'getToken');
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(realisticOrderSummaryPage));
    const client = createOrdersQueryClient({ token: 'default-token' });
    await client.getOrderSummaries({}, { token: 'override-token' });
    expect(token).not.toHaveBeenCalled();
    expect(get.mock.calls[0][1]?.token).toBe('override-token');
  });

  it('passes AbortSignal and If-None-Match through the query boundary', async () => {
    const controller = new AbortController();
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(realisticOrderSummaryPage));
    await getOrderSummaries({}, { signal: controller.signal, ifNoneMatch: 'etag-value' });
    expect(get.mock.calls[0][1]).toMatchObject({
      signal: controller.signal,
      headers: { 'If-None-Match': 'etag-value' },
    });
  });

  it('maps not-found and conflict responses without unsafe raw casts', async () => {
    const get = vi.spyOn(transport, 'get');
    get.mockRejectedValueOnce(new ApiHttpError(404, 'not_found', 'missing'));
    await expect(getOrderDetail('CASE-404')).rejects.toThrow(OrderNotFoundError);
    get.mockRejectedValueOnce(new ApiHttpError(409, 'conflict', 'stale', false, {
      detail: {
        error: {
          category: 'conflict',
          code: 'stale',
          message: 'stale',
          field_errors: [],
          domain_blockers: ['VERSION_CHANGED'],
          retryable: false,
          correlation_id: 'corr-1',
          current_version: 7,
        },
      },
    }));
    await expect(getOrderDetail('CASE-409')).rejects.toMatchObject({
      currentVersion: 7,
      domainBlockers: ['VERSION_CHANGED'],
    });
  });
});
