/**
 * File: customer_service_escalation_schemas.ts
 * Description: 定義 M4 escalation create/detail/claim/handling/resolve 的 strict Zod 契約。
 */

import { z } from 'zod';

export const EscalationCategorySchema = z.enum(['service_flow', 'payment_subsidy', 'service_progress', 'profile_update', 'contact_union', 'other']);
export const EscalationTriggerSchema = z.enum(['explicit_human_request', 'explicit_wrong_answer', 'binding_failure_threshold_2', 'complaint', 'runtime_critical']);
export const EscalationWorkflowStatusSchema = z.enum(['open', 'claimed', 'handling', 'resolved']);
export const EscalationHoldStateSchema = z.enum(['active', 'released']);
export const EscalationAlertStatusSchema = z.enum(['pending', 'queued', 'sent', 'failed', 'unknown']);
export const EscalationActionSchema = z.enum(['claim', 'handling', 'resolve']);

export const EscalationMaskedContextSchema = z.strictObject({
  summary_code: z.string(),
  policy_version: z.string(),
  category: z.string(),
  redaction_version: z.string(),
});

const CommandIdentityShape = {
  idempotency_key: z.string().trim().min(1).max(191),
  correlation_id: z.string().trim().min(1).max(191),
};

export const CustomerServiceEscalationCreateRequestSchema = z.strictObject({
  source_event_identity: z.string().trim().min(1).max(191),
  source_kind: z.enum(['ticket_referral', 'line_inbox', 'binding_failure', 'runtime_health']),
  source_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  trigger_code: EscalationTriggerSchema,
  trigger_policy_version: z.string().trim().min(1).max(191),
  ticket_category: EscalationCategorySchema,
  masked_context: EscalationMaskedContextSchema,
  hold_scope: z.string().trim().min(1).max(191),
  ...CommandIdentityShape,
});

export const CustomerServiceEscalationClaimRequestSchema = z.strictObject({
  expected_escalation_version: z.number().int().nonnegative(),
  ...CommandIdentityShape,
});

export const CustomerServiceEscalationHandlingRequestSchema = z.strictObject({
  expected_escalation_version: z.number().int().nonnegative(),
  expected_ticket_version: z.number().int().nonnegative(),
  ...CommandIdentityShape,
});

export const CustomerServiceEscalationResolveRequestSchema = z.strictObject({
  expected_escalation_version: z.number().int().nonnegative(),
  expected_ticket_version: z.number().int().nonnegative(),
  resolution_code: z.string().trim().min(1).max(64),
  resolution_evidence_digest: z.string().regex(/^[0-9a-f]{64}$/),
  ...CommandIdentityShape,
});

export const CustomerServiceEscalationReceiptSchema = z.strictObject({
  receipt_id: z.string().trim().min(1),
  command_family: z.literal('customer_service_human_escalation'),
  operation: z.enum(['create', 'claim', 'handling_started', 'resolve', 'replay']),
  escalation_id: z.number().int().positive(),
  ticket_ref: z.string().trim().min(1),
  resulting_workflow_status: EscalationWorkflowStatusSchema,
  resulting_hold_state: EscalationHoldStateSchema,
  current_version: z.string().trim().min(1),
  replayed: z.boolean(),
  correlation_id: z.string().trim().min(1),
  committed_at: z.string().datetime({ offset: true }),
});

export const CustomerServiceEscalationViewSchema = z.strictObject({
  escalation_id: z.number().int().positive(),
  ticket_ref: z.string().trim().min(1),
  category: EscalationCategorySchema,
  urgency: z.literal('high'),
  trigger_code: EscalationTriggerSchema,
  workflow_status: EscalationWorkflowStatusSchema,
  workflow_version: z.number().int().nonnegative(),
  automation_hold: EscalationHoldStateSchema,
  hold_scope_label: z.string().trim().min(1).max(80),
  masked_context: EscalationMaskedContextSchema,
  alert_status: EscalationAlertStatusSchema,
  current_version: z.string().trim().min(1),
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
  available_actions: z.array(EscalationActionSchema),
}).superRefine((value, context) => {
  if (new Set(value.available_actions).size !== value.available_actions.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['available_actions'], message: 'available_actions 不可重複。' });
  }
});

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });
}

export const CustomerServiceEscalationReceiptResponseSchema = envelope(CustomerServiceEscalationReceiptSchema);
export const CustomerServiceEscalationViewResponseSchema = envelope(CustomerServiceEscalationViewSchema);

export type CustomerServiceEscalationCreateRequest = z.infer<typeof CustomerServiceEscalationCreateRequestSchema>;
export type CustomerServiceEscalationClaimRequest = z.infer<typeof CustomerServiceEscalationClaimRequestSchema>;
export type CustomerServiceEscalationHandlingRequest = z.infer<typeof CustomerServiceEscalationHandlingRequestSchema>;
export type CustomerServiceEscalationResolveRequest = z.infer<typeof CustomerServiceEscalationResolveRequestSchema>;
export type CustomerServiceEscalationReceipt = z.infer<typeof CustomerServiceEscalationReceiptSchema>;
export type CustomerServiceEscalationView = z.infer<typeof CustomerServiceEscalationViewSchema>;
