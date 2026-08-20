/**
 * File: finance_query_clients.test.ts
 * Description: 驗證四組Finance clients的fresh Session、GET路徑、strict decode與masked AP契約。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { RECEIPT_RESPONSE, STAFF_PAYABLES_RESPONSE, ACCOUNTS_PAYABLE_RESPONSE, FINANCE_BATCH_RESPONSE, FINANCE_MANIFEST_RESPONSE } from './fixtures/finance/finance_query_contract_fixtures';
function response(body: object) { return { ok: true, status: 200, statusText: 'OK', headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }; }
describe('finance query clients', () => {
  const originalFetch = globalThis.fetch;
  beforeEach(() => sessionClient.setSession('finance-token', { id: 7, username: 'finance', display_name: 'Finance', role: 'admin' }));
  afterEach(() => { globalThis.fetch = originalFetch; sessionClient.clearSession(); });
  it('uses GET only and strictly decodes all four query families', async () => {
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
    for (const [, options] of vi.mocked(globalThis.fetch).mock.calls) {
      expect(options?.method).toBe('GET');
      expect(options?.headers).toMatchObject({ Authorization: 'Bearer finance-token' });
    }
  });
  it('rejects AP raw sensitive fields and aggregate mismatch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response({ ...ACCOUNTS_PAYABLE_RESPONSE, data: { ...ACCOUNTS_PAYABLE_RESPONSE.data, rows: [{ ...ACCOUNTS_PAYABLE_RESPONSE.data.rows[0], bank_account: '123456789012' }] } })).mockResolvedValueOnce(response({ ...ACCOUNTS_PAYABLE_RESPONSE, data: { ...ACCOUNTS_PAYABLE_RESPONSE.data, total_amount_ntd: 1 } }));
    await expect(accountsPayableQueryClient.query('2026-08')).rejects.toThrow();
    await expect(accountsPayableQueryClient.query('2026-08')).rejects.toThrow(/total_amount_ntd/);
  });
});
