/**
 * File: matching_coordination_schemas.ts
 * Description: 嚴格解碼 M3 查詢、Preview、Apply 的公開傳輸契約。
 */
import { z } from 'zod';

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const isoDateTime = z.string().datetime({ offset: true });
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const identity = z.string().min(1).max(191);
const reason = z.string().min(1).max(500);
const positiveInt = z.number().int().positive();
const nonnegativeInt = z.number().int().nonnegative();

export const MatchingSourceKindSchema = z.enum([
  'orders_terms',
  'orders_service_dates',
  'scheduling_availability',
  'scheduling_effective_generation',
  'staff_profile_definition',
  'staff_profile_values',
  'staff_lifecycle',
  'matching_criteria_snapshot',
  'candidate_pool',
  'matching_package',
  'incumbent_assignment',
  'leave_request_or_outcome',
  'assignment_conversion_reference',
]);

const sourceKindOrder = MatchingSourceKindSchema.options;

export const MatchingSourceVersionSchema = z
  .object({
    source_kind: MatchingSourceKindSchema,
    source_id: identity,
    version: z.union([z.number().int(), z.string()]),
    fingerprint: z.union([sha256, z.literal('not_consulted')]),
  })
  .strict();

export const MatchingSourceTupleSchema = z
  .object({
    items: z.array(MatchingSourceVersionSchema),
  })
  .strict()
  .superRefine((value, context) => {
    if (
      value.items.length !== sourceKindOrder.length ||
      value.items.some((item, index) => item.source_kind !== sourceKindOrder[index])
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'source_versions 必須使用完整且固定的來源順序',
      });
    }
  });

export const MatchingCriteriaSnapshotSchema = z
  .object({
    snapshot_id: identity,
    case_no: z.string().min(1).max(50),
    criteria_version: nonnegativeInt,
    criteria: z.array(z.tuple([z.string(), z.unknown()])),
    source_versions: z.array(MatchingSourceVersionSchema),
    fingerprint: sha256,
    created_at: isoDateTime,
    superseded_by: identity.nullable(),
  })
  .strict();

export const MatchingCriteriaResultSchema = z
  .object({
    code: z.string().min(1).max(80),
    status: z.enum([
      'matched',
      'not_matched',
      'source_not_ready',
      'not_consulted',
    ]),
    source_version: MatchingSourceVersionSchema,
    detail: z.string().max(500),
  })
  .strict();

export const WillingnessStateSchema = z.enum([
  'unconfirmed',
  'pending',
  'willing',
  'unwilling',
  'expired',
  'stale',
  'recontact_previewed',
  'recontact_queued',
  'silent_excluded',
]);

export const StableRejectionReasonSchema = z.enum([
  'region_mismatch',
  'service_date_conflict',
  'unavailable_period',
  'waiting_lock_conflict',
  'buffer_conflict',
  'staff_retired',
  'preference_not_ready',
  'preference_mismatch',
  'coverage_incomplete',
  'line_binding_missing',
  'willingness_unconfirmed',
  'incumbent_occupied',
  'due_date_outside_window',
  'criteria_source_stale',
  'candidate_expired',
]);

export const MatchingCandidateResultSchema = z
  .object({
    candidate_id: identity,
    staff_id: positiveInt,
    eligibility: z.enum(['eligible', 'ineligible', 'expired', 'stale']),
    criteria_results: z.array(MatchingCriteriaResultSchema),
    rejection_reasons: z.array(z.string()),
    coverage_evidence: z.array(isoDate),
    willingness: WillingnessStateSchema,
    notification_lineage: z.array(z.string()),
    staff_name: z.string().max(100),
  })
  .strict();

export const MatchingPackageSegmentSchema = z
  .object({
    staff_id: positiveInt,
    service_dates: z.array(isoDate),
    sequence: positiveInt,
  })
  .strict();

export const MatchingPackageSchema = z
  .object({
    package_id: identity,
    version: nonnegativeInt,
    mode: z.enum(['single', 'multi_segment']),
    segments: z.array(MatchingPackageSegmentSchema),
    required_service_dates: z.array(isoDate),
    candidate_results: z.array(MatchingCandidateResultSchema),
    criteria_snapshot_id: identity,
    source_versions: MatchingSourceTupleSchema,
    blockers: z.array(z.string()),
    warnings: z.array(z.string()),
    state: z.enum([
      'proposed',
      'awaiting_caregiver_willingness',
      'awaiting_customer_decision',
      'no_candidate',
      'rematch_required',
    ]),
    fingerprint: sha256,
  })
  .strict();

export const RefusalHistorySchema = z
  .object({
    refusal_id: identity,
    candidate_id: identity,
    snapshot_id: identity,
    reason_code: StableRejectionReasonSchema,
    affected_criteria: z.array(z.string()),
    originally_willing: z.boolean(),
    pain_resolved: z.boolean(),
  })
  .strict();

export const DynamicWillingnessLineageSchema = z
  .object({
    event_id: identity,
    candidate_id: identity,
    staff_id: positiveInt,
    snapshot_id: identity,
    source_versions: MatchingSourceTupleSchema,
    previous_state: WillingnessStateSchema,
    current_state: WillingnessStateSchema,
    reason_code: identity.nullable(),
    affected_criteria: z.array(z.string()).min(1),
  })
  .strict();

export const MatchingCoordinationQueryResponseSchema = z
  .object({
    case_no: z.string().min(1).max(50),
    snapshot: MatchingCriteriaSnapshotSchema,
    package: MatchingPackageSchema.nullable(),
    candidates: z.array(MatchingCandidateResultSchema),
    source_versions: MatchingSourceTupleSchema,
    refusal_history: z.array(RefusalHistorySchema),
    willingness_lineage: z.array(DynamicWillingnessLineageSchema),
    expected_source_versions_match: z.boolean(),
  })
  .strict();

export const MatchingCoordinationQueryRequestSchema = z
  .object({
    expected_source_versions: MatchingSourceTupleSchema.nullable()
      .optional()
      .default(null),
  })
  .strict();

export const PreviewInitialCriteriaRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema.nullable()
      .optional()
      .default(null),
  })
  .strict();

export const ApplyInitialCriteriaRequestSchema = z.object({
  reason,
  expected_source_versions: MatchingSourceTupleSchema,
  preview_fingerprint: sha256,
}).strict();

export const PreviewCriteriaDiffRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    before_snapshot_id: identity,
    after_snapshot_id: identity,
  })
  .strict();

export const RefusalRoutingSchema = z
  .object({
    candidate_id: identity,
    refusal_id: identity,
    group: z.enum([
      'group1_original_willing_reconfirm',
      'group2_pain_resolved_reprobe',
      'group3_unrelated_silent_exclude',
    ]),
    action: z.enum(['reconfirm', 'reprobe', 'silent_exclude']),
    reason_code: StableRejectionReasonSchema,
    source_snapshot_id: identity,
    diff_fingerprint: sha256,
  })
  .strict();

export const CriteriaDiffSchema = z
  .object({
    before_snapshot_id: identity,
    after_snapshot_id: identity,
    added: z.array(z.string()),
    removed: z.array(z.string()),
    changed: z.array(z.string()),
    unchanged: z.array(z.string()),
    affected_candidate_ids: z.array(z.string()),
    affected_recipient_ids: z.array(z.string()),
    resend_eligible: z.boolean(),
    diff_fingerprint: sha256,
    refusal_routes: z.array(RefusalRoutingSchema),
  })
  .strict();

export const PreviewZeroCandidateRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    criteria_snapshot_id: identity,
    policy_id: identity,
    policy_version: nonnegativeInt,
    relaxed_criteria: z.array(z.string()).min(1),
  })
  .strict();

export const ZeroCandidateAlternativeSchema = z
  .object({
    alternative_id: identity,
    policy_id: identity,
    policy_version: nonnegativeInt,
    relaxed_criteria: z.array(z.string()),
    unchanged_hard_criteria: z.array(z.string()),
    candidate_result: MatchingCandidateResultSchema.nullable(),
    risk_warnings: z.array(z.string()),
    deterministic_rank: positiveInt,
    preview_fingerprint: sha256,
  })
  .strict();

export const MatchingPackageSegmentSelectionSchema = z
  .object({
    staff_id: positiveInt,
    service_dates: z.array(isoDate).min(1),
    sequence: positiveInt,
  })
  .strict();

export const PreviewMatchingPackageRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    criteria_snapshot_id: identity,
    required_service_dates: z.array(isoDate).min(1),
    segments: z.array(MatchingPackageSegmentSelectionSchema).min(1).max(4),
  })
  .strict();

export const PreviewLeaveImpactRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    package_id: identity,
    criteria_snapshot_id: identity,
    receipt_key: identity,
    expected_leave_version: positiveInt,
    original_staff_id: positiveInt,
  })
  .strict();

const serviceDateShiftShape = {
  reason,
  expected_source_versions: MatchingSourceTupleSchema,
  criteria_snapshot_id: identity,
  package_id: identity.nullable().optional().default(null),
  assignment_id: positiveInt,
  original_staff_id: positiveInt,
  original_service_dates: z.array(isoDate).min(1),
  shifted_service_dates: z.array(isoDate).min(1),
};

export const PreviewServiceDateRematchRequestSchema = z
  .object(serviceDateShiftShape)
  .strict();

export const LeaveImpactPreviewResponseSchema = z
  .object({
    receipt_key: identity,
    result_state: z.enum(['leave_deferred', 'leave_substituted']),
    package_id: identity,
    criteria_snapshot_id: identity,
    rematch_required: z.boolean(),
    resolution_type: z.enum(['defer_following_assignments', 'substitute']),
    original_work_date: isoDate,
    resulting_work_date: isoDate,
    outcome_event_ids: z.array(z.string()),
    source_versions: MatchingSourceTupleSchema,
    receipt_fingerprint: sha256,
    preview_fingerprint: sha256,
    substitute_staff_id: positiveInt.nullable(),
  })
  .strict();

export const ServiceDateShiftAvailabilityConfirmationSchema = z
  .object({
    intent_id: identity,
    case_no: z.string().min(1).max(50),
    assignment_id: positiveInt,
    staff_id: positiveInt,
    original_service_dates: z.array(isoDate).min(1),
    shifted_service_dates: z.array(isoDate).min(1),
    source_fingerprint: sha256,
  })
  .strict();

export const ServiceDateShiftReassignmentReferenceSchema = z
  .object({
    queue_reference: z.string().min(1).max(500),
    case_no: z.string().min(1).max(50),
    assignment_id: positiveInt,
    staff_id: positiveInt,
    shifted_service_dates: z.array(isoDate).min(1),
    conflict_source_ids: z.array(z.string()).min(1),
    source_fingerprint: sha256,
  })
  .strict();

export const ServiceDateRematchPreviewResponseSchema = z
  .discriminatedUnion('outcome_kind', [
    z
      .object({
        outcome_kind: z.literal('availability_confirmation'),
        availability_confirmation: ServiceDateShiftAvailabilityConfirmationSchema,
        reassignment_reference: z.null(),
      })
      .strict(),
    z
      .object({
        outcome_kind: z.literal('reassignment_reference'),
        availability_confirmation: z.null(),
        reassignment_reference: ServiceDateShiftReassignmentReferenceSchema,
      })
      .strict(),
  ]);

export const PreviewRematchRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    criteria_snapshot_id: identity,
    package_id: identity.nullable().optional().default(null),
  })
  .strict();

export const ApplyCriteriaDiffRequestSchema = PreviewCriteriaDiffRequestSchema.extend({
  preview_fingerprint: sha256,
  recipient_ids: z.array(z.string()).min(1),
}).strict();

export const ApplyZeroCandidateRequestSchema = PreviewZeroCandidateRequestSchema.extend({
  alternative_id: identity,
  preview_fingerprint: sha256,
  decision: z.enum(['agree', 'disagree']),
}).strict();

export const ApplyCaregiverSelectionRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    criteria_snapshot_id: identity,
    package_id: identity,
    package_version: nonnegativeInt,
    candidate_id: identity,
    willingness: z.enum(['willing', 'unwilling']),
    reason_code: identity.nullable().optional().default(null),
    affected_criteria: z.array(z.string()).optional().default([]),
    preview_fingerprint: sha256,
  })
  .strict();

export const ApplyCustomerDecisionRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    criteria_snapshot_id: identity,
    package_id: identity,
    package_version: nonnegativeInt,
    candidate_id: identity.nullable().optional().default(null),
    decision: z.enum(['accepted', 'rejected', 'disagree']),
    preview_fingerprint: sha256,
  })
  .strict();

export const ApplyRematchRequestSchema = PreviewRematchRequestSchema.extend({
  preview_fingerprint: sha256,
}).strict();

export const ApplyLeaveImpactRequestSchema = z
  .object({
    reason,
    expected_source_versions: MatchingSourceTupleSchema,
    package_id: identity,
    leave_reference: identity,
    criteria_snapshot_id: identity,
    expected_leave_version: positiveInt,
    original_staff_id: positiveInt,
    preview_fingerprint: sha256,
  })
  .strict();

export const ApplyServiceDateRematchRequestSchema = z
  .object({ ...serviceDateShiftShape, preview_fingerprint: sha256 })
  .strict();

export const MatchingCrossDomainRequestSchema = z
  .object({
    request_id: identity,
    request_kind: z.enum([
      'assignment_conversion_requested',
      'rematch_requested',
    ]),
    case_no: z.string().min(1).max(50),
    package_id: identity,
    package_version: nonnegativeInt,
    criteria_snapshot_id: identity,
    candidate_id: identity.nullable(),
    source_versions: MatchingSourceTupleSchema,
    lineage_event_id: identity,
    reason,
  })
  .strict();

export const ZeroCandidateDecisionLineageSchema = z
  .object({
    event_id: identity,
    case_no: z.string().min(1).max(50),
    alternative_id: identity,
    policy_id: identity,
    policy_version: nonnegativeInt,
    decision: z.enum(['agree', 'disagree']),
    outcome_state: z.enum([
      'alternative_agreed_pending_owning_workflows',
      'awaiting_matching',
    ]),
    actor_id: identity,
    source_versions: MatchingSourceTupleSchema,
    assignment_request_id: identity.nullable(),
  })
  .strict();

export const MatchingNotificationIntentSchema = z
  .object({
    intent_id: identity,
    recipient_role: z.enum(['customer', 'caregiver']),
    recipient_subject_reference: identity,
    source_decision_event_id: identity,
    criteria_snapshot_id: identity,
    package_id: identity,
    package_version: nonnegativeInt,
    package_fingerprint: sha256,
    candidate_id: identity,
    idempotency_key: identity,
  })
  .strict();

export const MatchingCriteriaRecontactIntentSchema = z
  .object({
    intent_id: identity,
    recipient_subject_reference: identity,
    candidate_id: identity,
    staff_id: positiveInt,
    route_group: z.enum([
      'group1_original_willing_reconfirm',
      'group2_pain_resolved_reprobe',
    ]),
    action: z.enum(['reconfirm', 'reprobe']),
    reason_code: StableRejectionReasonSchema,
    before_snapshot_id: identity,
    after_snapshot_id: identity,
    diff_fingerprint: sha256,
    source_versions: MatchingSourceTupleSchema,
    idempotency_key: identity,
    package_id: identity.nullable(),
    package_version: nonnegativeInt.nullable(),
    package_fingerprint: sha256.nullable(),
  })
  .strict();

export const MatchingApplyReceiptResponseSchema = z
  .object({
    receipt_id: identity,
    command_name: z.enum([
      'ApplyInitialCriteriaSnapshot',
      'ApplyCriteriaDiffResend',
      'ApplyZeroCandidateAlternative',
      'ApplyCaregiverSelection',
      'ApplyCustomerMatchingDecision',
      'ApplyRematch',
      'ApplyLeaveImpactOnMatching',
      'ApplyServiceDateChangeRematch',
    ]),
    command_fingerprint: sha256,
    preview_fingerprint: sha256,
    source_versions: MatchingSourceTupleSchema,
    decision_event_id: identity.nullable(),
    package_id: identity.nullable(),
    outbox_intent_ids: z.array(z.string()),
    result_state: z.enum([
      'criteria_snapshotted',
      'accepted',
      'rejected',
      'disagree',
      'rematch_required',
      'unconfirmed',
      'pending',
      'willing',
      'unwilling',
      'expired',
      'intent_queued',
      'alternative_agreed_pending_owning_workflows',
      'awaiting_matching',
    ]),
    cross_domain_request: MatchingCrossDomainRequestSchema.nullable(),
    zero_candidate_decision: ZeroCandidateDecisionLineageSchema.nullable(),
    willingness_lineage: DynamicWillingnessLineageSchema.nullable(),
    notification_intents: z.array(MatchingNotificationIntentSchema),
    criteria_recontact_intents: z.array(MatchingCriteriaRecontactIntentSchema),
  })
  .strict();

function responseSchema<T extends z.ZodTypeAny>(data: T) {
  return z
    .object({
      success: z.boolean(),
      message: z.string(),
      data,
      error: z.string().nullable(),
    })
    .strict();
}

export const MatchingCoordinationQueryEnvelopeSchema = responseSchema(
  MatchingCoordinationQueryResponseSchema
);
export const MatchingCriteriaSnapshotEnvelopeSchema = responseSchema(
  MatchingCriteriaSnapshotSchema
);
export const MatchingPackageEnvelopeSchema = responseSchema(MatchingPackageSchema);
export const CriteriaDiffEnvelopeSchema = responseSchema(CriteriaDiffSchema);
export const ZeroCandidateAlternativeEnvelopeSchema = responseSchema(
  ZeroCandidateAlternativeSchema
);
export const LeaveImpactPreviewEnvelopeSchema = responseSchema(
  LeaveImpactPreviewResponseSchema
);
export const ServiceDateRematchPreviewEnvelopeSchema = responseSchema(
  ServiceDateRematchPreviewResponseSchema
);
export const MatchingApplyReceiptEnvelopeSchema = responseSchema(
  MatchingApplyReceiptResponseSchema
);

export type MatchingSourceTuple = z.infer<typeof MatchingSourceTupleSchema>;
export type MatchingCoordinationQueryRequest = z.input<
  typeof MatchingCoordinationQueryRequestSchema
>;
export type MatchingCoordinationQueryResponse = z.infer<
  typeof MatchingCoordinationQueryResponseSchema
>;
export type PreviewInitialCriteriaRequest = z.input<
  typeof PreviewInitialCriteriaRequestSchema
>;
export type ApplyInitialCriteriaRequest = z.input<
  typeof ApplyInitialCriteriaRequestSchema
>;
export type PreviewCriteriaDiffRequest = z.input<
  typeof PreviewCriteriaDiffRequestSchema
>;
export type PreviewZeroCandidateRequest = z.input<
  typeof PreviewZeroCandidateRequestSchema
>;
export type PreviewMatchingPackageRequest = z.input<
  typeof PreviewMatchingPackageRequestSchema
>;
export type PreviewLeaveImpactRequest = z.input<
  typeof PreviewLeaveImpactRequestSchema
>;
export type PreviewServiceDateRematchRequest = z.input<
  typeof PreviewServiceDateRematchRequestSchema
>;
export type PreviewRematchRequest = z.input<typeof PreviewRematchRequestSchema>;
export type ApplyCriteriaDiffRequest = z.input<
  typeof ApplyCriteriaDiffRequestSchema
>;
export type ApplyZeroCandidateRequest = z.input<
  typeof ApplyZeroCandidateRequestSchema
>;
export type ApplyCaregiverSelectionRequest = z.input<
  typeof ApplyCaregiverSelectionRequestSchema
>;
export type ApplyCustomerDecisionRequest = z.input<
  typeof ApplyCustomerDecisionRequestSchema
>;
export type ApplyRematchRequest = z.input<typeof ApplyRematchRequestSchema>;
export type ApplyLeaveImpactRequest = z.input<
  typeof ApplyLeaveImpactRequestSchema
>;
export type ApplyServiceDateRematchRequest = z.input<
  typeof ApplyServiceDateRematchRequestSchema
>;
export type MatchingCriteriaSnapshot = z.infer<
  typeof MatchingCriteriaSnapshotSchema
>;
export type MatchingPackage = z.infer<typeof MatchingPackageSchema>;
export type CriteriaDiff = z.infer<typeof CriteriaDiffSchema>;
export type ZeroCandidateAlternative = z.infer<
  typeof ZeroCandidateAlternativeSchema
>;
export type LeaveImpactPreviewResponse = z.infer<
  typeof LeaveImpactPreviewResponseSchema
>;
export type ServiceDateRematchPreviewResponse = z.infer<
  typeof ServiceDateRematchPreviewResponseSchema
>;
export type MatchingApplyReceiptResponse = z.infer<
  typeof MatchingApplyReceiptResponseSchema
>;
