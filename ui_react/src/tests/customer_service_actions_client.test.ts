/**
 * File: customer_service_actions_client.test.ts
 * Description: 驗證客服管理與 LINE durable 回覆 Preview／Apply 的 typed request、receipt 及 Session 邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  applyCustomerServiceReply,
  applyCustomerServiceUpdate,
  previewCustomerServiceReply,
  previewCustomerServiceUpdate,
} from '../api/customer_service/customer_service_client';
import { CustomerServiceRequestError } from '../api/customer_service/customer_service_errors';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_RESPONSE_FIXTURE,
  CUSTOMER_SERVICE_UPDATE_APPLY_RESPONSE_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';

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

  it('管理更新與回覆只走 Preview／Apply，並送出 fingerprint、version 及冪等識別', async () => {
    const replyFingerprint = 'c'.repeat(64);
    const replyPreviewResponse = {
      success: true,
      message: 'Preview 已建立',
      data: {
        ticket_id: 31,
        before_status: 'handling',
        after_status: 'handling',
        current_version: 4,
        expected_version: 4,
        reply_character_count: 13,
        will_enqueue_delivery: true,
        preview_fingerprint: replyFingerprint,
        apply_ready: true,
      },
      error: null,
    };
    const replyApplyResponse = {
      success: true,
      message: '回覆已保存，尚未送達',
      data: {
        ticket_id: 31,
        resulting_status: 'handling',
        resulting_version: 5,
        preview_fingerprint: replyFingerprint,
        delivery_enqueued: true,
        delivery_delivered: false,
        replayed: false,
        readback: {
          ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
          ticket: { ...CUSTOMER_SERVICE_DETAIL_FIXTURE.ticket, version: 5 },
        },
      },
      error: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_RESOLVE_PREVIEW_RESPONSE_FIXTURE))
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_UPDATE_APPLY_RESPONSE_FIXTURE))
      .mockResolvedValueOnce(response(replyPreviewResponse))
      .mockResolvedValueOnce(response(replyApplyResponse));
    vi.stubGlobal('fetch', fetchMock);

    await previewCustomerServiceUpdate(31, {
      status: 'resolved', internal_note: '已由工會接手', expected_version: 4,
    }, { correlationId: 'line-ticket-update-preview-1' });
    await applyCustomerServiceUpdate(31, {
      status: 'resolved', internal_note: '已由工會接手', expected_version: 4,
      preview_fingerprint: CUSTOMER_SERVICE_RESOLVE_PREVIEW_RESPONSE_FIXTURE.data.preview_fingerprint,
    }, { correlationId: 'line-ticket-update-preview-1', idempotencyKey: 'line-ticket-update-apply-1' });
    await previewCustomerServiceReply(31, {
      reply_text: '工會已收到，將盡快協助。',
      resolve: false,
      internal_note: '已回覆客戶',
      expected_version: 4,
    }, { correlationId: 'line-ticket-reply-preview-2' });
    await applyCustomerServiceReply(31, {
      reply_text: '工會已收到，將盡快協助。', resolve: false,
      internal_note: '已回覆客戶', expected_version: 4,
      idempotency_key: 'line-ticket-reply-apply-2', preview_fingerprint: replyFingerprint,
    }, { correlationId: 'line-ticket-reply-preview-2' });

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/customer-service/tickets/31/update/preview',
      '/api/v1/customer-service/tickets/31/update/apply',
      '/api/v1/customer-service/tickets/31/reply/preview',
      '/api/v1/customer-service/tickets/31/reply/apply',
    ]);
    for (const call of fetchMock.mock.calls) {
      expect(call[1]?.method).toBe('POST');
      expect(String(call[0])).not.toMatch(/\/tickets\/31$/);
      expect(String(call[0])).not.toMatch(/\/tickets\/31\/reply$/);
    }
    expect(new Headers(fetchMock.mock.calls[3][1]?.headers).get('Authorization')).toBe(
      'Bearer customer-service-actions-token'
    );
  });

  it('空白回覆與缺少 Apply 唯一操作鍵會在網路前 fail closed', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      previewCustomerServiceReply(31, {
        reply_text: '   ',
        resolve: false,
        internal_note: null,
        expected_version: 4,
      }, { correlationId: 'line-ticket-reply-preview-3' })
    ).rejects.toBeInstanceOf(CustomerServiceRequestError);
    await expect(
      applyCustomerServiceUpdate(31, {
        status: 'handling',
        internal_note: null,
        expected_version: 4,
        preview_fingerprint: 'd'.repeat(64),
      }, { correlationId: 'line-ticket-update-apply-4', idempotencyKey: '' })
    ).rejects.toBeInstanceOf(CustomerServiceRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
