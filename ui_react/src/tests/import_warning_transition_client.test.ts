/**
 * File: import_warning_transition_client.test.ts
 * Description: 驗證匯入警示 transition client 的 strict Preview、Apply、receipt lookup 與錯誤邊界。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  applyImportWarningTransition,
  importWarningTransitionClient,
  previewImportWarningTransition,
  queryImportWarningTransitionReceipt,
} from '../api/import_warning/import_warning_transition_client';
import { ImportWarningTransitionError } from '../api/import_warning/import_warning_transition_errors';
import {
  INVALID_WARNING_TRANSITION_PREVIEW_EXTRA_FIELD,
  INVALID_WARNING_TRANSITION_RECEIPT_IDENTITY,
  VALID_WARNING_TRANSITION_PREVIEW_RESPONSE,
  VALID_WARNING_TRANSITION_RECEIPT_LOOKUP_RESPONSE,
  VALID_WARNING_TRANSITION_RECEIPT_RESPONSE,
  VALID_WARNING_TRANSITION_REQUEST,
} from './fixtures/import_warning/import_warning_transition_contract_fixtures';

const occurrenceIdentity = 'import-warning:fixture-001';
const receiptIdentity = 'a'.repeat(64);

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('Import warning transition client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('transition-session-token', {
      id: 7,
      username: 'transition-operator',
      display_name: 'Transition Operator',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('以 session Bearer 呼叫 exact Preview／Apply path，並分離 Preview 與 terminal receipt', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(VALID_WARNING_TRANSITION_PREVIEW_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(VALID_WARNING_TRANSITION_RECEIPT_RESPONSE));
    globalThis.fetch = fetchMock;

    const preview = await previewImportWarningTransition(
      occurrenceIdentity,
      VALID_WARNING_TRANSITION_REQUEST,
      { correlationId: 'correlation-preview', idempotencyKey: 'idempotency-preview-001', headers: { Authorization: 'forged' } },
    );
    const receipt = await applyImportWarningTransition(
      occurrenceIdentity,
      VALID_WARNING_TRANSITION_REQUEST,
      { correlationId: 'correlation-apply', idempotencyKey: 'idempotency-001', headers: { authorization: 'forged' } },
    );

    expect(preview.resulting_version).toBe(8);
    expect(receipt.receipt_identity).toBe(receiptIdentity);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/v1/import-warning-tracking/tasks/${encodeURIComponent(occurrenceIdentity)}/preview`);
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/v1/import-warning-tracking/tasks/${encodeURIComponent(occurrenceIdentity)}/apply`);

    const previewOptions = fetchMock.mock.calls[0]?.[1];
    const applyOptions = fetchMock.mock.calls[1]?.[1];
    expect(previewOptions?.method).toBe('POST');
    expect(applyOptions?.method).toBe('POST');
    expect(new Headers(previewOptions?.headers).get('Authorization')).toBe('Bearer transition-session-token');
    expect(new Headers(applyOptions?.headers).get('Authorization')).toBe('Bearer transition-session-token');
    expect(new Headers(previewOptions?.headers).get('X-Correlation-ID')).toBe('correlation-preview');
    expect(new Headers(previewOptions?.headers).get('Idempotency-Key')).toBe('idempotency-preview-001');
    expect(new Headers(applyOptions?.headers).get('Idempotency-Key')).toBe('idempotency-001');
    expect(JSON.parse(String(previewOptions?.body))).toEqual(VALID_WARNING_TRANSITION_REQUEST);
    expect(JSON.parse(String(applyOptions?.body))).toEqual(VALID_WARNING_TRANSITION_REQUEST);
  });

  it('以 authenticated GET 取回 receipt，並保留 server replayed flag', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(VALID_WARNING_TRANSITION_RECEIPT_LOOKUP_RESPONSE));
    globalThis.fetch = fetchMock;

    const receipt = await queryImportWarningTransitionReceipt(receiptIdentity, {
      headers: { Authorization: 'forged' },
    });

    expect(receipt.replayed).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/v1/import-warning-tracking/receipts/${receiptIdentity}`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('GET');
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer transition-session-token');
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeUndefined();
  });

  it.each([
    ['preview extra field', INVALID_WARNING_TRANSITION_PREVIEW_EXTRA_FIELD, previewImportWarningTransition],
    ['receipt uppercase identity', INVALID_WARNING_TRANSITION_RECEIPT_IDENTITY, applyImportWarningTransition],
  ])('strictly rejects %s response', async (_label, payload, operation) => {
    globalThis.fetch = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(payload));

    const request = operation === applyImportWarningTransition
      ? applyImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-002' })
      : previewImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-preview-002' });
    await expect(request).rejects.toMatchObject({
      name: 'ImportWarningTransitionError',
      code: 'IMPORT_WARNING_CONTRACT',
      retryable: false,
    });
  });

  it('stale 與 idempotency mismatch 409 會分流為 typed errors', async () => {
    const stale = { detail: { error: { category: 'conflict', code: 'import_warning_version_conflict', message: 'stale', field_errors: [], domain_blockers: [], retryable: false, correlation_id: 'c', current_version: 9 } } };
    const mismatch = { detail: { error: { category: 'idempotency_mismatch', code: 'import_warning_idempotency_mismatch', message: 'mismatch', field_errors: [], domain_blockers: [], retryable: false, correlation_id: 'c', current_version: 8 } } };
    globalThis.fetch = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(stale, 409))
      .mockResolvedValueOnce(jsonResponse(mismatch, 409));

    await expect(previewImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-preview-003' })).rejects.toMatchObject({ code: 'IMPORT_WARNING_STALE', status: 409 });
    await expect(applyImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-003' })).rejects.toMatchObject({ code: 'IMPORT_WARNING_IDEMPOTENCY_MISMATCH', status: 409 });
  });

  it('Apply 的 network／timeout／retryable 503 一律標記 outcome_unknown', async () => {
    globalThis.fetch = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('network down'))
      .mockResolvedValueOnce(jsonResponse({ detail: 'temporarily unavailable' }, 503));

    await expect(applyImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-004' })).rejects.toMatchObject({ code: 'IMPORT_WARNING_OUTCOME_UNKNOWN', outcomeUnknown: true, retryable: true });
    await expect(applyImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-005' })).rejects.toMatchObject({ code: 'IMPORT_WARNING_OUTCOME_UNKNOWN', outcomeUnknown: true, retryable: true });
  });

  it('沒有 session token 時 fail closed 且零 fetch', async () => {
    sessionClient.clearSession();
    const fetchMock = vi.fn<typeof fetch>();
    globalThis.fetch = fetchMock;

    await expect(previewImportWarningTransition(occurrenceIdentity, VALID_WARNING_TRANSITION_REQUEST, { idempotencyKey: 'idempotency-preview-004' })).rejects.toMatchObject({
      name: 'ImportWarningTransitionError',
      code: 'IMPORT_WARNING_UNAUTHENTICATED',
      status: 401,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('保留 singleton 的三個 typed entry points', () => {
    expect(importWarningTransitionClient.preview).toBe(previewImportWarningTransition);
    expect(importWarningTransitionClient.apply).toBe(applyImportWarningTransition);
    expect(importWarningTransitionClient.queryReceipt).toBe(queryImportWarningTransitionReceipt);
    expect(ImportWarningTransitionError).toBeDefined();
  });
});
