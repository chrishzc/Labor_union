/**
 * File: staff_payables_query_adapter.ts
 * Description: 將Staff Payables查詢映射為唯讀view且不推導paid狀態。
 */
import type { StaffPayablesQuery } from '../../api/staff_payables/staff_payables_query_schemas';
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
      payoutStatus: item.payout_status,
    })),
    events: source.events.map((item) => ({ id: item.id, type: item.event_type, amount: `NT$ ${item.amount_ntd.toLocaleString()}`, occurredOn: item.occurred_on, reference: item.reconciliation_reference })),
  };
}
