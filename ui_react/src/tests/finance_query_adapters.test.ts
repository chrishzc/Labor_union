/**
 * File: finance_query_adapters.test.ts
 * Description: 驗證Finance adapters只格式化server facts且不推導settled或paid。
 */
import { describe, expect, it } from 'vitest';
import { adaptClientReceiptQuery } from '../adapters/finance/client_receipt_query_adapter';
import { adaptStaffPayablesQuery } from '../adapters/finance/staff_payables_query_adapter';
import { adaptAccountsPayablePreview } from '../adapters/finance/accounts_payable_query_adapter';
import { adaptFinanceImportBatch, adaptFinanceImportManifest } from '../adapters/finance/finance_import_query_adapter';
import { RECEIPT_RESPONSE, STAFF_PAYABLES_RESPONSE, ACCOUNTS_PAYABLE_RESPONSE, FINANCE_BATCH_RESPONSE, FINANCE_MANIFEST_RESPONSE } from './fixtures/finance/finance_query_contract_fixtures';
describe('finance query adapters', () => {
  it('preserves server status and masked values without local success inference', () => {
    expect(adaptClientReceiptQuery(RECEIPT_RESPONSE.data).obligations[0].settlementStatus).toContain('尚未提供');
    expect(adaptStaffPayablesQuery(STAFF_PAYABLES_RESPONSE.data).obligations[0].payoutStatus).toBe('payable');
    expect(adaptAccountsPayablePreview(ACCOUNTS_PAYABLE_RESPONSE.data).rows[0].bankDisplay).toContain('********9012');
    expect(adaptFinanceImportBatch(FINANCE_BATCH_RESPONSE.data[0]).status).toBe('review');
    expect(adaptFinanceImportManifest(FINANCE_MANIFEST_RESPONSE.data).digest).toBe(`${'b'.repeat(12)}…`);
  });
});
