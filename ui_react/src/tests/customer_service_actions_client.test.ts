/**
 * File: customer_service_actions_client.test.ts
 * Description: 驗證客服 PATCH 與 LINE durable 回覆端點的 typed request、response 及 Session 邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  replyCustomerServiceTicket,
  updateCustomerServiceTicket,
} from '../api/customer_service/customer_service_client';
import { CustomerServiceRequestError } from '../api/customer_service/customer_service_errors';
import { CUSTOMER_SERVICE_DETAIL_RESPONSE_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';

function response(payload: object): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

describe('customer service action client', () => {
  beforeEach(() => {
    sessionClient.setSession('customer-service-actions-token', {
      id: 7,
      username: 'customer-service-actions',
      display_name: '客服操作測試',
      role: 'operator',
      linked_line_user_id: null,
      capabilities: [],
      is_root: false,
      access_control_version: 1,
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('以既有 PATCH 與 reply 端點送出 expected_version 及 idempotency_key', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_DETAIL_RESPONSE_FIXTURE))
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_DETAIL_RESPONSE_FIXTURE));
    vi.stubGlobal('fetch', fetchMock);

    await updateCustomerServiceTicket(31, {
      status: 'handling',
      internal_note: '已由工會接手',
      expected_version: 4,
      idempotency_key: 'line-ticket-handling-unique-1',
    });
    await replyCustomerServiceTicket(31, {
      reply_text: '工會已收到，將盡快協助。',
      resolve: false,
      internal_note: '已回覆客戶',
      expected_version: 5,
      idempotency_key: 'line-ticket-reply-unique-2',
    });

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/customer-service/tickets/31');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('PATCH');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual(
      expect.objectContaining({ expected_version: 4, idempotency_key: 'line-ticket-handling-unique-1' })
    );
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/customer-service/tickets/31/reply');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST');
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual(
      expect.objectContaining({ expected_version: 5, idempotency_key: 'line-ticket-reply-unique-2' })
    );
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe(
      'Bearer customer-service-actions-token'
    );
  });

  it('空白回覆與缺少唯一操作鍵會在網路前 fail closed', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      replyCustomerServiceTicket(31, {
        reply_text: '   ',
        resolve: false,
        internal_note: null,
        expected_version: 4,
        idempotency_key: 'line-ticket-reply-unique-3',
      })
    ).rejects.toBeInstanceOf(CustomerServiceRequestError);
    await expect(
      updateCustomerServiceTicket(31, {
        status: 'handling',
        internal_note: null,
        expected_version: 4,
        idempotency_key: '',
      })
    ).rejects.toBeInstanceOf(CustomerServiceRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
