/**
 * File: customer_service_escalation_adapter.ts
 * Description: 將 M4 escalation 去敏 DTO 映射為顯示模型，不推導 action eligibility 或 hold 狀態。
 */

import {
  CustomerServiceEscalationReceiptSchema,
  CustomerServiceEscalationViewSchema,
  type CustomerServiceEscalationView,
} from '../../api/customer_service_escalations/customer_service_escalation_schemas';

export interface CustomerServiceEscalationModel {
  escalationId: number;
  ticketRef: string;
  category: string;
  categoryLabel: string;
  triggerCode: string;
  workflowStatus: string;
  workflowStatusLabel: string;
  workflowVersion: number;
  automationHold: string;
  automationHoldLabel: string;
  holdScopeLabel: string;
  maskedContext: Readonly<Record<string, string>>;
  alertStatus: string;
  currentVersion: string;
  createdAt: string;
  updatedAt: string;
  availableActions: string[];
  availableActionLabels: string[];
  deliveryTaskRef: string | null;
  deliveryOutcomeRef: string | null;
  triggerIdentity: string | null;
  attemptWindow: { attemptCount: number; maximumAttempts: number; generation: number } | null;
  ownerSelector: string | null;
}

export interface CustomerServiceEscalationReceiptModel {
  receiptId: string;
  operation: string;
  escalationId: number;
  ticketRef: string;
  workflowStatus: string;
  holdState: string;
  currentVersion: string;
  replayed: boolean;
  correlationId: string;
  committedAt: string;
}

const categoryLabels: Record<CustomerServiceEscalationView['category'], string> = {
  service_flow: '服務流程', payment_subsidy: '收費與補助', service_progress: '服務進度',
  profile_update: '修改登記資料', contact_union: '聯絡工會', other: '其他問題',
};
const statusLabels: Record<CustomerServiceEscalationView['workflow_status'], string> = {
  open: '待接手', claimed: '已接手', handling: '處理中', resolved: '已解決',
};
const actionLabels = { claim: '接手', handling: '開始處理', resolve: '解決' } as const;

export function adaptCustomerServiceEscalation(source: unknown): CustomerServiceEscalationModel {
  const value = CustomerServiceEscalationViewSchema.parse(source);
  return {
    escalationId: value.escalation_id,
    ticketRef: value.ticket_ref,
    category: value.category,
    categoryLabel: categoryLabels[value.category],
    triggerCode: value.trigger_code,
    workflowStatus: value.workflow_status,
    workflowStatusLabel: statusLabels[value.workflow_status],
    workflowVersion: value.workflow_version,
    automationHold: value.automation_hold,
    automationHoldLabel: value.automation_hold === 'active' ? '自動化暫停中' : '已解除暫停',
    holdScopeLabel: value.hold_scope_label,
    maskedContext: { ...value.masked_context },
    alertStatus: value.alert_status,
    currentVersion: value.current_version,
    createdAt: value.created_at,
    updatedAt: value.updated_at,
    availableActions: [...value.available_actions],
    availableActionLabels: value.available_actions.map((action) => actionLabels[action]),
    deliveryTaskRef: value.delivery_task_ref ?? null,
    deliveryOutcomeRef: value.delivery_outcome_ref ?? null,
    triggerIdentity: value.trigger_identity ?? null,
    attemptWindow: value.attempt_window
      ? { attemptCount: value.attempt_window.attempt_count, maximumAttempts: value.attempt_window.maximum_attempts, generation: value.attempt_window.generation }
      : null,
    ownerSelector: value.owner_selector ?? null,
  };
}

export function adaptCustomerServiceEscalationReceipt(source: unknown): CustomerServiceEscalationReceiptModel {
  const value = CustomerServiceEscalationReceiptSchema.parse(source);
  return {
    receiptId: value.receipt_id,
    operation: value.operation,
    escalationId: value.escalation_id,
    ticketRef: value.ticket_ref,
    workflowStatus: value.resulting_workflow_status,
    holdState: value.resulting_hold_state,
    currentVersion: value.current_version,
    replayed: value.replayed,
    correlationId: value.correlation_id,
    committedAt: value.committed_at,
  };
}
