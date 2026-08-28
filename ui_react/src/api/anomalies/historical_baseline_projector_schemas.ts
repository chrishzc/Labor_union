/**
 * File: historical_baseline_projector_schemas.ts
 * Description: 嚴格解碼案件最新 Historical Baseline Projector persisted readback。
 */
import { z } from 'zod';

const fingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const identitySchema = z.string().min(1).max(191);
const domainSchema = z.string().min(1).max(100);
const caseNoSchema = z.string().min(1).max(50).regex(/^[^\s]+$/);
const dateTimeSchema = z.string().datetime({ offset: true });

export const HistoricalBaselineRepairReferralSchema = z.strictObject({
  step: z.number().int().min(1).max(11),
  contract_id: identitySchema,
  owner_domain: domainSchema,
  repair_target: identitySchema,
  repair_capability: identitySchema,
});
export type HistoricalBaselineRepairReferral = z.infer<
  typeof HistoricalBaselineRepairReferralSchema
>;

export const HistoricalBaselineAlertDisplaySchema = z.strictObject({
  case_no: caseNoSchema,
  earliest_blocked_step: z.number().int().min(1).max(11).nullable(),
  active_count: z.number().int().nonnegative(),
  repair_referrals: z.array(HistoricalBaselineRepairReferralSchema),
  projection_fingerprint: fingerprintSchema,
}).superRefine((display, context) => {
  if (display.active_count !== display.repair_referrals.length) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['active_count'],
      message: 'active_count 必須等於 repair_referrals 筆數',
    });
  }
  const earliest = display.repair_referrals.length === 0
    ? null
    : Math.min(...display.repair_referrals.map((referral) => referral.step));
  if (display.earliest_blocked_step !== earliest) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['earliest_blocked_step'],
      message: 'earliest_blocked_step 必須由 server referral 集合精確對應',
    });
  }
});

export const HistoricalBaselineDeliverySchema = z.strictObject({
  delivery_identity: fingerprintSchema,
  source_trigger_identity: identitySchema,
  payload_digest: fingerprintSchema,
  source_kind: z.enum(['baseline_confirmed', 'owner_repair']),
  source_domain: domainSchema,
  source_event_identity: identitySchema,
  source_version: z.number().int().nonnegative(),
  partition_key: identitySchema,
  projection_sequence: z.number().int().positive().nullable(),
  projector_receipt_identity: fingerprintSchema.nullable(),
  status: z.enum([
    'pending',
    'processing',
    'retryable_failed',
    'committed_unverified',
    'processed',
    'dead_letter',
  ]),
  attempt_count: z.number().int().nonnegative(),
  max_attempts: z.number().int().positive(),
  next_attempt_at: dateTimeSchema.nullable(),
  lease_expires_at: dateTimeSchema.nullable(),
  last_error_code: identitySchema.nullable(),
}).superRefine((delivery, context) => {
  if (delivery.attempt_count > delivery.max_attempts) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['attempt_count'],
      message: 'attempt_count 不得超過 max_attempts',
    });
  }
  const requiresReceipt = ['committed_unverified', 'processed'].includes(delivery.status);
  if (requiresReceipt && (delivery.projection_sequence === null || delivery.projector_receipt_identity === null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['projector_receipt_identity'],
      message: '已提交的 delivery 必須綁定 receipt 與 projection sequence',
    });
  }
  if (!requiresReceipt && delivery.projector_receipt_identity !== null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['projector_receipt_identity'],
      message: '未提交的 delivery 不得偽造 receipt binding',
    });
  }
});

export const HistoricalBaselineReceiptSchema = z.strictObject({
  projector_receipt_identity: fingerprintSchema,
  source_trigger_identity: identitySchema,
  source_trigger_version: z.number().int().nonnegative(),
  payload_digest: fingerprintSchema,
  idempotency_key: z.string().min(1).max(191).regex(/^[a-z0-9][a-z0-9._:-]{0,190}$/),
  case_no: caseNoSchema,
  order_identity: identitySchema,
  catalog_identity: fingerprintSchema,
  catalog_version: z.number().int().positive(),
  whole_vector_fingerprint: fingerprintSchema,
  whole_vector_count: z.number().int().positive(),
  emitted_occurrence_set_digest: fingerprintSchema,
  emitted_occurrence_set_count: z.number().int().nonnegative(),
  active_membership_set_digest: fingerprintSchema,
  active_membership_set_count: z.number().int().nonnegative(),
  umbrella_identity: fingerprintSchema,
  projection_sequence: z.number().int().positive(),
  current_alert_fingerprint: fingerprintSchema,
  expected_readback_digest: fingerprintSchema,
  result_state: z.enum(['projected', 'held_active']),
}).superRefine((receipt, context) => {
  const expected = receipt.active_membership_set_count === 0 ? 'projected' : 'held_active';
  if (receipt.result_state !== expected) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['result_state'],
      message: 'result_state 與 active membership count 不一致',
    });
  }
});

export const HistoricalBaselineMembershipSchema = z.strictObject({
  membership_identity: fingerprintSchema,
  set_ordinal: z.number().int().positive(),
  occurrence_identity: fingerprintSchema,
});

export const HistoricalBaselinePostCommitReadbackSchema = z.strictObject({
  readback_identity: fingerprintSchema,
  readback_attempt: z.number().int().positive(),
  expected_readback_digest: fingerprintSchema,
  actual_readback_digest: fingerprintSchema.nullable(),
  emitted_occurrence_set_digest: fingerprintSchema.nullable(),
  emitted_occurrence_set_count: z.number().int().nonnegative().nullable(),
  active_membership_set_digest: fingerprintSchema.nullable(),
  active_membership_set_count: z.number().int().nonnegative().nullable(),
  state_event_set_digest: fingerprintSchema.nullable(),
  successor_set_digest: fingerprintSchema.nullable(),
  workflow_event_set_digest: fingerprintSchema.nullable(),
  current_alert_fingerprint: fingerprintSchema.nullable(),
  result: z.enum(['exact', 'mismatch', 'unknown']),
  error_code: identitySchema.nullable(),
}).superRefine((readback, context) => {
  if ((readback.result === 'exact') !== (readback.error_code === null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['error_code'],
      message: 'readback result 與 error_code 不一致',
    });
  }
});

export const HistoricalBaselineCurrentAlertSchema = z.strictObject({
  fingerprint: fingerprintSchema,
  definition_code: z.literal('HISTORICAL-BASELINE-ROOTS-001'),
  definition_version: z.literal(1),
  source_domain: z.literal('historical_baseline'),
  source_identity: fingerprintSchema,
  source_version: z.number().int().positive(),
  predicate_active: z.boolean(),
  workflow_status: z.enum(['open', 'claimed', 'resolved']),
  workflow_version: z.number().int().nonnegative(),
  projection_version: z.number().int().nonnegative(),
  display: HistoricalBaselineAlertDisplaySchema,
}).superRefine((alert, context) => {
  if (alert.predicate_active !== (alert.display.active_count > 0)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['predicate_active'],
      message: 'alert predicate 與 active count 不一致',
    });
  }
  if ((alert.workflow_status === 'resolved') === alert.predicate_active) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['workflow_status'],
      message: 'alert workflow 與 predicate 不一致',
    });
  }
});

export const HistoricalBaselineReconciliationSchema = z.strictObject({
  status: z.enum(['processed', 'not_ready', 'outcome_unknown']),
  delivery_identity: fingerprintSchema,
  projector_receipt_identity: fingerprintSchema.nullable(),
  reason_code: identitySchema.nullable(),
  referral: z.enum([
    'none',
    'wait_for_projector_commit',
    'retry_original_trigger_reconcile',
  ]),
});

export const HistoricalBaselineProjectorReadModelSchema = z.strictObject({
  delivery: HistoricalBaselineDeliverySchema,
  receipt: HistoricalBaselineReceiptSchema.nullable(),
  active_memberships: z.array(HistoricalBaselineMembershipSchema),
  post_commit_readback: HistoricalBaselinePostCommitReadbackSchema.nullable(),
  current_alert: HistoricalBaselineCurrentAlertSchema.nullable(),
  reconciliation: HistoricalBaselineReconciliationSchema,
}).superRefine((model, context) => {
  const receiptIdentity = model.receipt?.projector_receipt_identity ?? null;
  if (model.reconciliation.delivery_identity !== model.delivery.delivery_identity) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['reconciliation', 'delivery_identity'], message: 'reconciliation delivery binding 不一致' });
  }
  if (model.reconciliation.projector_receipt_identity !== receiptIdentity
    || model.delivery.projector_receipt_identity !== receiptIdentity) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['receipt'], message: 'delivery、reconciliation 與 receipt binding 不一致' });
  }
  if (model.receipt === null) {
    if (model.active_memberships.length > 0 || model.post_commit_readback !== null || model.current_alert !== null) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['receipt'], message: '缺少 receipt 時不得提供下游投影資料' });
    }
    return;
  }
  if (model.receipt.source_trigger_identity !== model.delivery.source_trigger_identity
    || model.receipt.payload_digest !== model.delivery.payload_digest
    || model.receipt.projection_sequence !== model.delivery.projection_sequence) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['receipt'], message: 'receipt 與 delivery source binding 不一致' });
  }
  if (model.active_memberships.length !== model.receipt.active_membership_set_count) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['active_memberships'], message: 'membership rows 與 receipt count 不一致' });
  }
  if (!model.active_memberships.every((membership, index) => membership.set_ordinal === index + 1)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['active_memberships'], message: 'membership ordinal 必須連續且由 1 開始' });
  }
  if (model.current_alert === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['current_alert'], message: 'receipt 存在時必須提供 current alert' });
    return;
  }
  if (model.current_alert.source_identity !== model.receipt.umbrella_identity
    || model.current_alert.source_version !== model.receipt.projection_sequence
    || model.current_alert.display.case_no !== model.receipt.case_no
    || model.current_alert.display.active_count !== model.receipt.active_membership_set_count) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['current_alert'], message: 'current alert 與 receipt binding 不一致' });
  }
});
export type HistoricalBaselineProjectorReadModel = z.infer<
  typeof HistoricalBaselineProjectorReadModelSchema
>;

export const HistoricalBaselineProjectorEnvelopeSchema = z.strictObject({
  success: z.literal(true),
  message: z.string(),
  data: HistoricalBaselineProjectorReadModelSchema,
  error: z.null(),
});
