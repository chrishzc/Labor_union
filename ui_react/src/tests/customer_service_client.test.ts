/**
 * File: customer_service_client.test.ts
 * Description: 驗證客服白名單端點、即時 Session、嚴格解碼與結案請求標頭。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  CustomerServiceClientError,
  CustomerServiceUnauthenticatedError,
  ApiDecodeError,
} from '../api/customer_service/customer_service_errors';
import {
  customerServiceClient,
  getCustomerServiceSummary,
} from '../api/customer_service/customer_service_client';
import {
  CustomerServiceDetailSchema,
  CustomerServiceEventSchema,
  CustomerServicePageSchema,
  CustomerServiceResolveApplyRequestSchema,
  CustomerServiceResolvePreviewSchema,
  CustomerServiceSummarySchema,
  CustomerServiceTicketSchema,
} from '../api/customer_service/customer_service_schemas';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_DETAIL_RESPONSE_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_PAGE_RESPONSE_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_REQUEST_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_RESPONSE_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE,
  CUSTOMER_SERVICE_TICKET_FIXTURE,
  CUSTOMER_SERVICE_UPDATE_APPLY_RESPONSE_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setTestSession(token: string): void {
  sessionClient.setSession(token, {
    id: 7,
    username: 'customer-service-test',
    display_name: '客服測試人員',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

describe('customer service client', () => {
  beforeEach(() => {
    setTestSession('customer-service-token-a');
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('只以 GET 呼叫 summary、list、detail 白名單並保留查詢參數', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE))
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_PAGE_RESPONSE_FIXTURE))
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_DETAIL_RESPONSE_FIXTURE));
    globalThis.fetch = fetchMock;

    await customerServiceClient.getSummary();
    await customerServiceClient.listTickets({
      status: 'handling',
      category: 'profile_update',
      search: 'ORD-TEST',
      page: 1,
      page_size: 25,
    });
    await customerServiceClient.getTicketDetail(31);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/customer-service/tickets/summary'
    );
    expect(fetchMock.mock.calls[0][1]?.method).toBe('GET');
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      '/api/v1/customer-service/tickets?'
    );
    expect(String(fetchMock.mock.calls[1][0])).toContain('status=handling');
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      'category=profile_update'
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      '/api/v1/customer-service/tickets/31'
    );
  });

  it('結案流程只呼叫 purpose-specific Preview 與 Apply，不呼叫 legacy PATCH/reply', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response(CUSTOMER_SERVICE_RESOLVE_PREVIEW_RESPONSE_FIXTURE)
      )
      .mockResolvedValueOnce(response(CUSTOMER_SERVICE_UPDATE_APPLY_RESPONSE_FIXTURE));
    globalThis.fetch = fetchMock;

    await customerServiceClient.previewResolve(
      31,
      CUSTOMER_SERVICE_RESOLVE_PREVIEW_REQUEST_FIXTURE,
      { correlationId: 'customer-service-preview-31' }
    );
    await customerServiceClient.applyResolve(
      31,
      CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
      {
        correlationId: 'customer-service-apply-31',
        idempotencyKey: 'customer-service-resolve-31',
      }
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/customer-service/tickets/31/update/preview'
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      '/api/v1/customer-service/tickets/31/update/apply'
    );
    for (const call of fetchMock.mock.calls) {
      expect(call[1]?.method).toBe('POST');
      expect(String(call[0])).not.toContain('/reply');
    }
    const previewHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers);
    const applyHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(previewHeaders.get('X-Correlation-ID')).toBe(
      'customer-service-preview-31'
    );
    expect(previewHeaders.get('Idempotency-Key')).toBeNull();
    expect(applyHeaders.get('X-Correlation-ID')).toBe(
      'customer-service-apply-31'
    );
    expect(applyHeaders.get('Idempotency-Key')).toBe(
      'customer-service-resolve-31'
    );
  });

  it('每個請求即時取得記憶體 Session 並拒絕呼叫者覆寫 Authorization', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(response(CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE))
    );
    globalThis.fetch = fetchMock;

    await getCustomerServiceSummary({
      headers: { Authorization: 'Bearer caller-controlled' },
    });
    setTestSession('customer-service-token-b');
    await getCustomerServiceSummary();

    const firstHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers);
    const secondHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(firstHeaders.get('Authorization')).toBe(
      'Bearer customer-service-token-a'
    );
    expect(secondHeaders.get('Authorization')).toBe(
      'Bearer customer-service-token-b'
    );
  });

  it('缺少 Session 時在送出網路請求前 fail closed', async () => {
    sessionClient.clearSession();
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    await expect(customerServiceClient.getSummary()).rejects.toBeInstanceOf(
      CustomerServiceUnauthenticatedError
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('接受 Pydantic 可缺省且可為 null 的客服查詢欄位', () => {
    const minimalTicket = {
      ticket_id: 31,
      line_user_id: 'Uabc…xyz',
      category: 'contact_union',
      status: 'handling',
      version: 4,
    };
    const minimalEvent = {
      id: 1,
      event_type: 'status_changed',
      actor_id: 'admin:7',
      created_at: '2026-08-16T10:00:00Z',
    };

    expect(CustomerServiceTicketSchema.parse(minimalTicket).client_id).toBeUndefined();
    expect(CustomerServiceEventSchema.parse(minimalEvent).message_text).toBeUndefined();
    expect(CustomerServiceTicketSchema.parse({ ...minimalTicket, client_id: null }).client_id).toBeNull();
  });

  it('將 HTTP 409 依 status 與 detail.code 映射為 typed conflict', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      response(
        {
          detail: {
            error: {
              category: 'conflict',
              code: 'customer_service_ticket_version_conflict',
              message: '版本已更新',
              field_errors: [],
              domain_blockers: [],
              retryable: false,
              correlation_id: 'customer-service-preview-31',
              current_version: 5,
            },
          },
        },
        409
      )
    );

    try {
      await customerServiceClient.previewResolve(
        31,
        CUSTOMER_SERVICE_RESOLVE_PREVIEW_REQUEST_FIXTURE,
        { correlationId: 'customer-service-preview-31' }
      );
      expect.fail('預期收到 conflict error');
    } catch (error) {
      expect(error).toBeInstanceOf(CustomerServiceClientError);
      if (error instanceof CustomerServiceClientError) {
        expect(error.category).toBe('conflict');
        expect(error.code).toBe('customer_service_ticket_version_conflict');
        expect(error.status).toBe(409);
        expect(error.correlationId).toBe('customer-service-preview-31');
        expect(error.currentVersion).toBe(5);
      }
    }
  });

  it('回應缺 required、型別錯誤、多餘欄位、null 與 enum drift 均拋 ApiDecodeError', async () => {
    const invalidPayloads = [
      {
        ...CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE,
        data: { handling: 1, resolved_today: 3 },
      },
      {
        ...CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE,
        data: { ...CUSTOMER_SERVICE_SUMMARY_FIXTURE, waiting: '2' },
      },
      {
        ...CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE,
        data: { ...CUSTOMER_SERVICE_SUMMARY_FIXTURE, unexpected: true },
      },
      { ...CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE, data: null },
      {
        ...CUSTOMER_SERVICE_PAGE_RESPONSE_FIXTURE,
        data: {
          ...CUSTOMER_SERVICE_PAGE_FIXTURE,
          items: [
            { ...CUSTOMER_SERVICE_TICKET_FIXTURE, status: 'closed' },
          ],
        },
      },
    ];

    for (const payload of invalidPayloads) {
      globalThis.fetch = vi.fn().mockResolvedValue(response(payload));
      await expect(customerServiceClient.getSummary()).rejects.toBeInstanceOf(
        ApiDecodeError
      );
    }
  });
});

describe('customer service strict schemas', () => {
  it('Ticket DTO 拒絕 missing、wrong primitive、extra、null、enum drift 與 invalid integer', () => {
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        ticket_id: undefined,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        version: '4',
      }).success
    ).toBe(false);
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        extra: true,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        status: null,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        category: 'billing',
      }).success
    ).toBe(false);
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        version: 1.5,
      }).success
    ).toBe(false);
  });

  it('Pydantic datetime 欄位接受 local／offset ISO，拒絕任意字串', () => {
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        created_at: '2026-08-16T08:00:00',
        updated_at: '2026-08-16T09:00:00+08:00',
      }).success
    ).toBe(true);
    expect(
      CustomerServiceTicketSchema.safeParse({
        ...CUSTOMER_SERVICE_TICKET_FIXTURE,
        created_at: 'not-a-datetime',
      }).success
    ).toBe(false);
    expect(
      CustomerServiceEventSchema.safeParse({
        ...CUSTOMER_SERVICE_DETAIL_FIXTURE.events[0],
        created_at: 'not-a-datetime',
      }).success
    ).toBe(false);
  });

  it('Summary、Page、Detail DTO 都拒絕未知欄位及必要欄位漂移', () => {
    expect(
      CustomerServiceSummarySchema.safeParse({
        ...CUSTOMER_SERVICE_SUMMARY_FIXTURE,
        extra: 0,
      }).success
    ).toBe(false);
    expect(
      CustomerServicePageSchema.safeParse({
        ...CUSTOMER_SERVICE_PAGE_FIXTURE,
        page_size: null,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceDetailSchema.safeParse({
        ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
        events: undefined,
      }).success
    ).toBe(false);
  });

  it('Preview DTO 拒絕 enum drift、invalid range、fingerprint 與額外欄位', () => {
    expect(
      CustomerServiceResolvePreviewSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
        after_status: 'closed',
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolvePreviewSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
        current_version: -1,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolvePreviewSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
        preview_fingerprint: 'not-a-fingerprint',
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolvePreviewSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
        receipt: true,
      }).success
    ).toBe(false);
  });

  it('Apply request 拒絕空缺、多餘欄位、null 與非法範圍', () => {
    expect(
      CustomerServiceResolveApplyRequestSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
        preview_fingerprint: undefined,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolveApplyRequestSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
        expected_version: -1,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolveApplyRequestSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
        internal_note: 123,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolveApplyRequestSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
        status: null,
      }).success
    ).toBe(false);
    expect(
      CustomerServiceResolveApplyRequestSchema.safeParse({
        ...CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE,
        unexpected: true,
      }).success
    ).toBe(false);
  });
});
