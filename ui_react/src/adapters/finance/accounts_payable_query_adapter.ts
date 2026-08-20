/**
 * File: accounts_payable_query_adapter.ts
 * Description: 將masked Accounts Payable preview映射為唯讀會計清單。
 */
import type { AccountsPayablePreview } from '../../api/accounts_payable/accounts_payable_query_schemas';
export function adaptAccountsPayablePreview(source: AccountsPayablePreview) {
  return {
    targetPaymentDate: source.target_payment_date,
    rowCount: source.row_count,
    totalAmount: `NT$ ${source.total_amount_ntd.toLocaleString()}`,
    rows: source.rows.map((row, index) => ({
      id: `${row.payment_type}-${row.payment_date}-${index}`,
      paymentDate: row.payment_date,
      paymentType: row.payment_type,
      recipientName: row.recipient_name,
      bankDisplay: `${row.bank_code} ${row.bank_account_masked}`,
      identityDisplay: row.recipient_identity_card_masked,
      amount: `NT$ ${row.amount_ntd.toLocaleString()}`,
      caseNumbers: row.case_numbers,
    })),
  };
}
