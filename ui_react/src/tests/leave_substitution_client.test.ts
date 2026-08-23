/**
 * File: leave_substitution_client.test.ts
 * Description: 驗證請假代班 client 的白名單、fresh token、strict decode 與 typed failure mapping。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createLeaveSubstitutionClient,
  listLeaveSubstitutionAssignments,
  previewLeaveSubstitution,
} from '../api/scheduling/leave_substitution_client';
import {
  LeaveSubstitutionAbortedError,
  LeaveSubstitutionConflictError,
  LeaveSubstitutionContractError,
  LeaveSubstitutionForbiddenError,
  LeaveSubstitutionNetworkError,
  LeaveSubstitutionNotFoundError,
  LeaveSubstitutionUnauthenticatedError,
  LeaveSubstitutionUnavailableError,
  LeaveSubstitutionValidationError,
} from '../api/scheduling/leave_substitution_errors';
import {
  LEAVE_APPLY_REQUEST,
  LEAVE_APPLY_RESPONSE,
  LEAVE_ASSIGNMENTS_RESPONSE,
  LEAVE_CASE_NO,
  LEAVE_PREVIEW_REQUEST,
  LEAVE_PREVIEW_RESPONSE,
  LEAVE_TYPED_CONFLICT_RESPONSE,
} from './fixtures/scheduling/leave_substitution_contract_fixtures';

function setSession(token: string): void {
  sessionClient.setSession(token, {
    id: 7,
    username: 'leave-substitution-test',
    display_name: '請假代班測試',
    role: 'system_admin',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('leave substitution client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setSession('leave-token-a');
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('只呼叫 assignments GET、帶最新 memory token 並保持單一 correlation header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(LEAVE_ASSIGNMENTS_RESPONSE));
    globalThis.fetch = fetchMock;

    const assignments = await listLeaveSubstitutionAssignments(LEAVE_CASE_NO, {
      correlationId: 'leave-assignments-correlation',
      headers: { Authorization: 'Bearer caller', 'X-Trace': 'owned' },
    });

    expect(assignments).toHaveLength(1);
    expect(assignments[0].official_schedules).toEqual([
      { schedule_id: 301, work_date: '2026-08-03' },
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(
      '/api/v1/orders/CASE-LEAVE-001/leave-substitution/assignments',
    );
    expect(options?.method).toBe('GET');
    expect(options?.body).toBeUndefined();
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer leave-token-a');
    expect(new Headers(options?.headers).get('X-Correlation-ID')).toBe(
      'leave-assignments-correlation',
    );
    expect(new Headers(options?.headers).get('X-Trace')).toBe('owned');
    expect(new Headers(options?.headers).get('Idempotency-Key')).toBeNull();
  });

  it('Preview 與 Apply 僅送出 typed body，Apply 使用 caller stable idempotency key', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(LEAVE_PREVIEW_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(LEAVE_APPLY_RESPONSE));
    globalThis.fetch = fetchMock;
    const client = createLeaveSubstitutionClient();

    await client.preview(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST, {
      correlationId: 'leave-preview-correlation',
    });
    setSession('leave-token-b');
    await client.apply(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, {
      correlationId: 'leave-apply-correlation',
      idempotencyKey: 'leave-apply-idempotency-001',
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const previewCall = fetchMock.mock.calls[0];
    expect(previewCall[0]).toBe(
      '/api/v1/orders/CASE-LEAVE-001/leave-substitution/preview',
    );
    expect(previewCall[1]?.method).toBe('POST');
    expect(JSON.parse(String(previewCall[1]?.body))).toEqual(LEAVE_PREVIEW_REQUEST);
    expect(new Headers(previewCall[1]?.headers).get('Authorization')).toBe(
      'Bearer leave-token-a',
    );
    expect(new Headers(previewCall[1]?.headers).get('Idempotency-Key')).toBeNull();

    const applyCall = fetchMock.mock.calls[1];
    expect(applyCall[0]).toBe('/api/v1/orders/CASE-LEAVE-001/leave-substitution/apply');
    expect(applyCall[1]?.method).toBe('POST');
    expect(JSON.parse(String(applyCall[1]?.body))).toEqual(LEAVE_APPLY_REQUEST);
    expect(new Headers(applyCall[1]?.headers).get('Authorization')).toBe(
      'Bearer leave-token-b',
    );
    expect(new Headers(applyCall[1]?.headers).get('X-Correlation-ID')).toBe(
      'leave-apply-correlation',
    );
    expect(new Headers(applyCall[1]?.headers).get('Idempotency-Key')).toBe(
      'leave-apply-idempotency-001',
    );
  });

  it('未登入、half-linked、缺 Apply idempotency 與非日曆日期在 fetch 前 fail closed', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    const client = createLeaveSubstitutionClient();
    sessionClient.clearSession();
    await expect(client.listAssignments(LEAVE_CASE_NO)).rejects.toBeInstanceOf(
      LeaveSubstitutionUnauthenticatedError,
    );
    setSession('leave-token-a');
    await expect(
      client.preview(LEAVE_CASE_NO, {
        ...LEAVE_PREVIEW_REQUEST,
        expected_leave_request_version: null,
      }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);
    await expect(
      client.apply(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, {
        correlationId: 'missing-idempotency',
      }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);
    await expect(
      client.preview(LEAVE_CASE_NO, {
        ...LEAVE_PREVIEW_REQUEST,
        items: [{ ...LEAVE_PREVIEW_REQUEST.items[0], work_date: '2026-02-30' }],
      }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);
    const missingDoublePay = {
      ...LEAVE_PREVIEW_REQUEST,
      items: LEAVE_PREVIEW_REQUEST.items.map(({ is_double_pay: _missing, ...item }) => item),
    } as unknown as typeof LEAVE_PREVIEW_REQUEST;
    await expect(client.preview(LEAVE_CASE_NO, missingDoublePay)).rejects.toBeInstanceOf(
      LeaveSubstitutionValidationError,
    );
    const { leave_request_id: _missing, ...withoutLinkedRequestId } = LEAVE_PREVIEW_REQUEST;
    await expect(
      client.preview(
        LEAVE_CASE_NO,
        withoutLinkedRequestId as unknown as typeof LEAVE_PREVIEW_REQUEST,
      ),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('success envelope drift、extra field 與 null data 一律轉成 contract error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      jsonResponse({ ...LEAVE_PREVIEW_RESPONSE, unexpected: true }),
    );
    await expect(
      previewLeaveSubstitution(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST),
    ).rejects.toBeInstanceOf(LeaveSubstitutionContractError);

    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      jsonResponse({ success: true, message: 'ok', data: null, error: null }),
    );
    await expect(
      previewLeaveSubstitution(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);

    const assignmentWithoutSchedules = {
      ...LEAVE_ASSIGNMENTS_RESPONSE,
      data: LEAVE_ASSIGNMENTS_RESPONSE.data.map(({ official_schedules: _ignored, ...item }) => item),
    };
    globalThis.fetch = vi.fn().mockResolvedValueOnce(jsonResponse(assignmentWithoutSchedules));
    await expect(
      listLeaveSubstitutionAssignments(LEAVE_CASE_NO),
    ).rejects.toBeInstanceOf(LeaveSubstitutionContractError);
  });

  it.each([
    [401, LeaveSubstitutionUnauthenticatedError],
    [403, LeaveSubstitutionForbiddenError],
    [404, LeaveSubstitutionNotFoundError],
    [409, LeaveSubstitutionConflictError],
    [422, LeaveSubstitutionValidationError],
    [503, LeaveSubstitutionUnavailableError],
  ])('HTTP %s maps to a typed domain error', async (status, ErrorType) => {
    const body = status === 409
      ? LEAVE_TYPED_CONFLICT_RESPONSE
      : {
          detail: {
            error: {
              category: status === 503 ? 'unavailable' : 'validation',
              code: `leave_http_${status}`,
              message: 'typed leave error',
              field_errors: [],
              domain_blockers: [],
              retryable: status === 503,
              correlation_id: `leave-http-${status}`,
              current_version: null,
            },
          },
        };
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(body, status));
    await expect(listLeaveSubstitutionAssignments(LEAVE_CASE_NO)).rejects.toBeInstanceOf(
      ErrorType,
    );
  });

  it('network 與 Abort 不會被吞掉或假稱成功', async () => {
    globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error('network down'));
    await expect(listLeaveSubstitutionAssignments(LEAVE_CASE_NO)).rejects.toBeInstanceOf(
      LeaveSubstitutionNetworkError,
    );

    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new DOMException('aborted', 'AbortError'));
    await expect(listLeaveSubstitutionAssignments(LEAVE_CASE_NO)).rejects.toBeInstanceOf(
      LeaveSubstitutionAbortedError,
    );
  });
});
