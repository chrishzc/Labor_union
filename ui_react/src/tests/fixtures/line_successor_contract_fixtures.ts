/**
 * File: line_successor_contract_fixtures.ts
 * Description: 提供 LINE safe config、M4 escalation 與 runtime target 的封閉前端契約樣本。
 */

export const LINE_SAFE_CONFIG_RESPONSE = {
  success: true,
  message: 'Success',
  data: { kind: 'rich_menus', revision: 9, state: 'configured' },
  error: null,
} as const;

export const ESCALATION_RECEIPT_RESPONSE = {
  success: true,
  message: 'Success',
  data: {
    receipt_id: 'receipt:line-successor',
    command_family: 'customer_service_human_escalation',
    operation: 'claim',
    escalation_id: 11,
    ticket_ref: 'ticket:21',
    resulting_workflow_status: 'claimed',
    resulting_hold_state: 'active',
    current_version: 'version:m4:2',
    replayed: false,
    correlation_id: 'line-successor-escalation',
    committed_at: '2026-08-21T10:00:00+00:00',
  },
  error: null,
} as const;

export const ESCALATION_VIEW_RESPONSE = {
  success: true,
  message: 'Success',
  data: {
    escalation_id: 11,
    ticket_ref: 'ticket:21',
    category: 'other',
    urgency: 'high',
    trigger_code: 'complaint',
    workflow_status: 'open',
    workflow_version: 0,
    automation_hold: 'active',
    hold_scope_label: 'opaque',
    context: {
      summary_code: 'complaint_explicit',
      policy_version: 'complaint.v1',
      category: 'other',
      redaction_version: 'm4-mask.v1',
    },
    alert_status: 'pending',
    current_version: 'version:m4:1',
    created_at: '2026-08-21T09:00:00+00:00',
    updated_at: '2026-08-21T09:00:00+00:00',
    available_actions: ['claim'],
  },
  error: null,
} as const;

export const RUNTIME_TARGETS_RESPONSE = {
  success: true,
  message: 'Success',
  data: [{
    target_id: 3,
    target_kind: 'group',
    display_label: 'LINE 告警群組 #3',
    state: 'active',
    minimum_status: 'warning',
    current_version: 'target-version-1',
    updated_at: '2026-08-21T08:00:00+00:00',
  }],
  error: null,
} as const;

export const RUNTIME_CANDIDATES_RESPONSE = {
  success: true,
  message: 'Success',
  data: [{ candidate_id: 7, display_label: '管理員 #7', line_linked: true }],
  error: null,
} as const;

export const RUNTIME_MUTATION_RESPONSE = {
  success: true,
  message: 'Success',
  data: {
    receipt_id: 'receipt:runtime-target',
    command_family: 'line_alert_target',
    operation: 'disable',
    target_id: 3,
    previous_state: 'active',
    resulting_state: 'disabled',
    current_version: 'target-version-2',
    replayed: false,
    correlation_id: 'line-successor-runtime',
    committed_at: '2026-08-21T10:00:00+00:00',
  },
  error: null,
} as const;
