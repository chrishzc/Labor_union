/**
 * File: staff_payables_query_adapter.ts
 * Description: 將Staff Payables查詢映射為唯讀view且不推導paid狀態。
 */
import type { StaffPayablesQuery } from '../../api/staff_payables/staff_payables_query_schemas';

const PAYOUT_STATUS_LABELS: Readonly<Record<string, string>> = {
  payable: '待付款',
  partially_paid: '部分付款',
  completed: '已完成付款',
  recovery_required: '待追償處理',
  anomaly: '待異常處理',
};

const EVENT_TYPE_LABELS: Readonly<Record<string, string>> = {
  payout: '付款',
  return: '退匯',
  reversal: '沖銷',
};

export function adaptStaffPayablesQuery(source: StaffPayablesQuery) {
  return {
    staffId: source.staff_id,
    version: source.staff_payables_version,
    obligations: source.obligations.map((item) => ({
      id: item.obligation_identity,
      caseNo: item.case_no,
      amountDue: `NT$ ${item.amount_due_ntd.toLocaleString()}`,
      dueDate: item.due_date ?? '—',
      netPaid: `NT$ ${item.net_paid_ntd.toLocaleString()}`,
      balance: `NT$ ${item.balance_ntd.toLocaleString()}`,
      payoutStatus: PAYOUT_STATUS_LABELS[item.payout_status] ?? '狀態待確認',
      payoutCompleted: item.payout_status === 'completed',
    })),
    events: source.events.map((item) => ({ id: item.id, type: EVENT_TYPE_LABELS[item.event_type] ?? '其他付款紀錄', amount: `NT$ ${item.amount_ntd.toLocaleString()}`, occurredOn: item.occurred_on, reference: item.reconciliation_reference })),
  };
}
