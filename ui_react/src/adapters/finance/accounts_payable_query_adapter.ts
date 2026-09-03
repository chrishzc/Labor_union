/**
 * File: accounts_payable_query_adapter.ts
 * Description: 將masked Accounts Payable preview映射為唯讀會計清單。
 */
import type { AccountsPayablePreview } from '../../api/accounts_payable/accounts_payable_query_schemas';

const PAYMENT_TYPE_LABELS: Record<string, string> = {
  staff_payable: '月嫂服務費',
  client_subsidy_return: '客戶補助款退回',
  client_refund: '客戶退款',
  government_overpayment_return: '政府溢付款退回',
};

export function adaptAccountsPayablePreview(source: AccountsPayablePreview) {
  return {
    targetPaymentDate: source.target_payment_date,
    rowCount: source.row_count,
    totalAmount: `NT$ ${source.total_amount_ntd.toLocaleString()}`,
    rows: source.rows.map((row, index) => ({
      id: `${row.payment_type}-${row.payment_date}-${index}`,
      paymentDate: row.payment_date,
      paymentType: PAYMENT_TYPE_LABELS[row.payment_type] ?? '其他付款',
      recipientName: row.recipient_name,
      bankDisplay: `${row.bank_code} ${row.bank_account}`,
      identityDisplay: row.recipient_identity_card,
      amount: `NT$ ${row.amount_ntd.toLocaleString()}`,
      caseNumbers: row.case_numbers,
    })),
  };
}
