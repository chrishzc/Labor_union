/**
 * File: client_receipt_query_adapter.ts
 * Description: 將Client Receipt根事實映射為唯讀view且不推導settled狀態。
 */
import type { ClientReceiptQuery } from '../../api/client_finance/client_receipt_query_schemas';

export function adaptClientReceiptQuery(source: ClientReceiptQuery) {
  return {
    caseNo: source.case_no,
    accountVersion: source.account_version,
    bankFacts: source.bank_facts.map((item) => ({
      id: item.finance_import_row_id,
      amount: `NT$ ${item.amount_ntd.toLocaleString()}`,
      transactionDate: item.transaction_date,
      fingerprint: `${item.dedup_fingerprint.slice(0, 12)}…`,
    })),
    obligations: source.obligations.map((item) => ({
      id: item.obligation_identity,
      stage: item.payment_stage,
      amountDue: `NT$ ${item.amount_due_ntd.toLocaleString()}`,
      dueDate: item.due_date ?? '—',
      settlementStatus: '後端尚未提供typed settled projection',
    })),
  };
}
