/**
 * File: anomaly_detail_schemas.ts
 * Description: 驗證 Anomalies detail 與 recovery GET 的封閉 Zod 契約。
 */
import { z } from 'zod';

const identitySchema = z.string().trim().min(1).max(191);
const codeSchema = z.string().trim().min(1).max(191);
const keySchema = z.string().regex(/^[A-Za-z0-9_.:-]+$/).min(1).max(191);
const fingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const dateTimeSchema = z.string().datetime({ offset: true });
const stringListSchema = z.array(z.string().trim().min(1).max(191)).max(100);

const evidenceBase = { key: keySchema };
export const AnomalyEvidenceFieldSchema = z.discriminatedUnion('kind', [
  z.strictObject({ ...evidenceBase, kind: z.literal('identity'), value: identitySchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('masked_text'), value: identitySchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('date'), value: dateSchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('datetime'), value: dateTimeSchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('boolean'), value: z.boolean() }),
  z.strictObject({ ...evidenceBase, kind: z.literal('money_ntd'), value: z.number().int() }),
  z.strictObject({ ...evidenceBase, kind: z.literal('integer'), value: z.number().int() }),
  z.strictObject({ ...evidenceBase, kind: z.literal('code'), value: codeSchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('code_list'), value: stringListSchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('identity_list'), value: stringListSchema }),
  z.strictObject({ ...evidenceBase, kind: z.literal('detail_list'), value: stringListSchema }),
]);
export type AnomalyEvidenceField = z.infer<typeof AnomalyEvidenceFieldSchema>;

export const AnomalyDisplaySnapshotSchema = z.strictObject({
  redaction_version: z.literal('anomaly-safe.v1'),
  definition_code: codeSchema,
  fields: z.array(AnomalyEvidenceFieldSchema).max(20),
});
export type AnomalyDisplaySnapshot = z.infer<typeof AnomalyDisplaySnapshotSchema>;

export const AnomalySourceBindingSchema = z.discriminatedUnion('kind', [
  z.strictObject({ kind: z.literal('identity'), key: keySchema, value: identitySchema }),
  z.strictObject({ kind: z.literal('version'), key: keySchema, value: z.number().int().nonnegative() }),
]);
export type AnomalySourceBinding = z.infer<typeof AnomalySourceBindingSchema>;

const recoveryActionBase = {
  action_key: codeSchema,
  label: z.string().trim().min(1).max(191),
  owning_domain: codeSchema,
  form_schema_key: codeSchema,
  source_binding_keys: z.array(keySchema).max(20),
  required_operator_inputs: z.array(keySchema).max(20),
  preview_operation: codeSchema,
  apply_operation: codeSchema.nullable(),
  required_capability: codeSchema.nullable(),
  completion_predicate: codeSchema,
  action_contract_version: z.number().int().positive(),
  requires_preview: z.boolean(),
};

export const DomainActionSchema = z.strictObject({
  ...recoveryActionBase,
  source_bindings: z.array(AnomalySourceBindingSchema).max(20).nullable(),
});
export type DomainAction = z.infer<typeof DomainActionSchema>;

export const RecoveryActionSchema = z.strictObject({
  ...recoveryActionBase,
  source_bindings: z.array(AnomalySourceBindingSchema).max(20),
}).superRefine((action, context) => {
  const declared = new Set(action.source_binding_keys);
  const materialized = new Set(action.source_bindings.map((binding) => binding.key));
  const exact = declared.size === materialized.size
    && [...declared].every((key) => materialized.has(key));
  if (!exact) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['source_bindings'],
      message: 'source_bindings 必須完整對應 source_binding_keys',
    });
  }
});
export type RecoveryAction = z.infer<typeof RecoveryActionSchema>;

const severitySchema = z.enum(['warning', 'blocking']);
const workflowStatusSchema = z.enum(['open', 'claimed', 'resolved']);

export const AnomalyDetailSummarySchema = z.strictObject({
  fingerprint: fingerprintSchema,
  definition_code: codeSchema,
  source_domain: codeSchema,
  source_identity: identitySchema,
  source_version: z.number().int().nonnegative(),
  severity: severitySchema,
  predicate_active: z.boolean(),
  workflow_status: workflowStatusSchema,
  workflow_version: z.number().int().nonnegative(),
  display_snapshot: AnomalyDisplaySnapshotSchema,
  staff_calendar_navigation: z
    .strictObject({
      staff_id: z.number().int().positive(),
      target_date: dateSchema,
    })
    .nullable(),
});
export type AnomalyDetailSummary = z.infer<typeof AnomalyDetailSummarySchema>;

export const AnomalyTimelineEventSchema = z.strictObject({
  action: z.enum(['claim', 'resolve', 'reopen', 'auto_resolve']),
  expected_workflow_version: z.number().int().nonnegative(),
  resulting_workflow_version: z.number().int().nonnegative(),
  actor: z.string().trim().min(1).max(191),
  reason: z.string().trim().min(1).max(191),
  correlation_id: identitySchema,
  created_at: dateTimeSchema,
});
export type AnomalyTimelineEvent = z.infer<typeof AnomalyTimelineEventSchema>;

export const AnomalyDetailViewSchema = z.strictObject({
  summary: AnomalyDetailSummarySchema,
  timeline: z.array(AnomalyTimelineEventSchema).max(100),
  available_actions: z.array(DomainActionSchema).max(20),
});
export type AnomalyDetailView = z.infer<typeof AnomalyDetailViewSchema>;

export const FinanceOccurrenceSchema = z.strictObject({
  occurrence_fingerprint: fingerprintSchema,
  definition_code: codeSchema,
  source_event_identity: identitySchema,
  finance_import_row_id: z.number().int().positive(),
  finance_import_batch_id: z.number().int().positive(),
  source_version: z.number().int().nonnegative(),
  occurred_at: dateTimeSchema,
  bounded_snapshot: AnomalyDisplaySnapshotSchema,
});
export type FinanceOccurrence = z.infer<typeof FinanceOccurrenceSchema>;

export const AnomalyRootFactSnapshotSchema = z.strictObject({
  occurred_at: dateTimeSchema,
  source_version: z.number().int().nonnegative(),
  finance_import_row_identity: identitySchema,
  finance_import_batch_identity: identitySchema,
  original_refund_ledger_entry_identity: identitySchema.nullable(),
  amount_delta_ntd: z.number().int(),
  root_condition_active: z.boolean(),
  integrity_blocker_active: z.boolean(),
  affected_order_identities: stringListSchema,
  affected_obligation_identities: stringListSchema,
  domain_blockers: z.array(codeSchema).max(20),
  reason_codes: z.array(codeSchema).max(20),
});
export type AnomalyRootFactSnapshot = z.infer<typeof AnomalyRootFactSnapshotSchema>;

export const AnomalyRecoveryContextViewSchema = z.strictObject({
  fingerprint: fingerprintSchema,
  definition_code: codeSchema,
  source_domain: codeSchema,
  source_identity: identitySchema,
  source_version: z.number().int().nonnegative(),
  severity: severitySchema,
  predicate_active: z.boolean(),
  workflow_status: workflowStatusSchema,
  workflow_version: z.number().int().nonnegative(),
  domain_blocker_active: z.boolean(),
  projection_freshness: codeSchema,
  root_fact_snapshot: AnomalyRootFactSnapshotSchema,
  occurrence_timeline: z.array(FinanceOccurrenceSchema).max(100),
  workflow_timeline: z.array(AnomalyTimelineEventSchema).max(100),
  available_actions: z.array(RecoveryActionSchema).max(20),
});
export type AnomalyRecoveryContextView = z.infer<
  typeof AnomalyRecoveryContextViewSchema
>;

function strictEnvelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({
    success: z.literal(true),
    message: z.string(),
    data,
    error: z.string().nullable().optional(),
  });
}

export const AnomalyDetailResponseSchema = strictEnvelope(AnomalyDetailViewSchema);
export type AnomalyDetailResponse = z.infer<typeof AnomalyDetailResponseSchema>;
export const AnomalyRecoveryResponseSchema = strictEnvelope(
  AnomalyRecoveryContextViewSchema
);
export type AnomalyRecoveryResponse = z.infer<typeof AnomalyRecoveryResponseSchema>;
