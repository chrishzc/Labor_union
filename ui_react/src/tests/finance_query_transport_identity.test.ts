/**
 * File: finance_query_transport_identity.test.ts
 * Description: 驗證Finance GET correlation header與Finance Import identity／cursor fail-closed契約。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { sessionClient } from '../api/auth/session_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import {
  ACCOUNTS_PAYABLE_RESPONSE,
  FINANCE_BATCH_RESPONSE,
  FINANCE_MANIFEST_RESPONSE,
  RECEIPT_RESPONSE,
  STAFF_PAYABLES_RESPONSE,
} from './fixtures/finance/finance_query_contract_fixtures';

function response(body: object) {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('Finance query transport identity', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('finance-token', { id: 7, username: 'finance', display_name: 'Finance', role: 'admin' });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('sends a distinct non-empty correlation ID on every Finance GET', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(RECEIPT_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PAYABLES_RESPONSE))
      .mockResolvedValueOnce(response(ACCOUNTS_PAYABLE_RESPONSE))
      .mockResolvedValueOnce(response(FINANCE_BATCH_RESPONSE))
      .mockResolvedValueOnce(response(FINANCE_MANIFEST_RESPONSE));

    await clientReceiptQueryClient.query('CASE-FIN-001');
    await staffPayablesQueryClient.query(11);
    await accountsPayableQueryClient.query('2026-08');
    await financeImportQueryClient.listBatches();
    await financeImportQueryClient.getManifest('BATCH-FIN-021');

    const correlationIds = vi.mocked(globalThis.fetch).mock.calls.map(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined;
      expect(init?.method).toBe('GET');
      expect(headers?.Authorization).toBe('Bearer finance-token');
      expect(headers?.['X-Correlation-ID']).toBeTruthy();
      return headers?.['X-Correlation-ID'];
    });
    expect(new Set(correlationIds).size).toBe(correlationIds.length);
  });

  it('rejects a manifest for a different requested batch identity', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response({
      ...FINANCE_MANIFEST_RESPONSE,
      data: { ...FINANCE_MANIFEST_RESPONSE.data, batch_identity: 'BATCH-OTHER-999' },
    }));

    await expect(financeImportQueryClient.getManifest('BATCH-FIN-021')).rejects.toMatchObject({
      code: 'FINANCE_IMPORT_MANIFEST_IDENTITY_MISMATCH',
    });
  });

  it('rejects review and reprocess pages whose cursor or batch scope drifts', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response({
        success: true,
        message: 'ok',
        error: null,
        data: { items: [], next_after_row_id: 99 },
      }))
      .mockResolvedValueOnce(response({
        success: true,
        message: 'ok',
        error: null,
        data: {
          items: [{
            run_id: 8,
            batch_identity: 'BATCH-OTHER-999',
            classifier_version: 'v1',
            plan_fingerprint: 'a'.repeat(64),
            selected_count: 1,
            changed_count: 0,
            dispatch_count: 0,
            reconciled_count: 0,
            pending_count: 1,
            status: 'completed',
            created_at: '2026-08-21T00:00:00+08:00',
            completed_at: '2026-08-21T00:00:01+08:00',
          }],
          next_before_run_id: null,
        },
      }));

    await expect(financeImportQueryClient.listReviewRows('BATCH-FIN-021')).rejects.toMatchObject({
      code: 'FINANCE_IMPORT_REVIEW_CURSOR_MISMATCH',
    });
    await expect(financeImportQueryClient.listReprocessRuns('BATCH-FIN-021')).rejects.toMatchObject({
      code: 'FINANCE_IMPORT_REPROCESS_IDENTITY_MISMATCH',
    });
  });

  it('rejects invalid batch cursors and ambiguous public batch identities', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response({
      ...FINANCE_BATCH_RESPONSE,
      data: [
        FINANCE_BATCH_RESPONSE.data[0],
        { ...FINANCE_BATCH_RESPONSE.data[0], batch_id: 22 },
      ],
    }));

    await expect(financeImportQueryClient.listBatches({ beforeBatchId: 0 })).rejects.toMatchObject({
      code: 'FINANCE_IMPORT_VALIDATION',
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
    await expect(financeImportQueryClient.listBatches()).rejects.toMatchObject({
      code: 'FINANCE_IMPORT_DUPLICATE_BATCH_IDENTITY',
    });
  });

  it('preserves the caller AbortSignal on a Finance Import GET', async () => {
    const controller = new AbortController();
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response(FINANCE_BATCH_RESPONSE));

    await financeImportQueryClient.listBatches({}, { signal: controller.signal });

    const fetchSignal = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.signal;
    expect(fetchSignal?.aborted).toBe(false);
    controller.abort();
    expect(fetchSignal?.aborted).toBe(true);
  });
});
