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
  it('uses closed business labels and omits unavailable settlement state', () => {
    expect(adaptClientReceiptQuery(RECEIPT_RESPONSE.data).obligations[0]).not.toHaveProperty('settlementStatus');
    expect(adaptStaffPayablesQuery(STAFF_PAYABLES_RESPONSE.data).obligations[0].payoutStatus).toBe('待付款');
    expect(adaptAccountsPayablePreview(ACCOUNTS_PAYABLE_RESPONSE.data).rows[0].bankDisplay).toContain('********9012');
    expect(adaptFinanceImportBatch(FINANCE_BATCH_RESPONSE.data[0]).status).toBe('review');
    expect(adaptFinanceImportManifest(FINANCE_MANIFEST_RESPONSE.data).digest).toBe(`${'b'.repeat(12)}…`);
  });

  it('fails closed for unknown payable status and event type', () => {
    const adapted = adaptStaffPayablesQuery({
      ...STAFF_PAYABLES_RESPONSE.data,
      obligations: [{ ...STAFF_PAYABLES_RESPONSE.data.obligations[0], payout_status: 'future_status' }],
      events: [{ id: 9, event_type: 'future_event', amount_ntd: 500, occurred_on: '2026-08-01', finance_import_row_id: null, reversal_of_event_id: null, reconciliation_reference: 'REF-9' }],
    });

    expect(adapted.obligations[0].payoutStatus).toBe('狀態待確認');
    expect(adapted.events[0].type).toBe('其他付款紀錄');
  });
});
