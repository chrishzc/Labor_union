/**
 * File: anomaly_query_schemas.ts
 * Description: Anomalies 四個唯讀 GET 的嚴格 Zod 契約。
 */
import { z } from 'zod';

// ============================================================================
// 1. Staff Calendar Navigation Model (Nested inside AnomalySummaryView)
// ============================================================================

export const StaffCalendarNavigationViewSchema = z
  .object({
    staff_id: z.number().int().positive(),
    target_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  })
  .strict();

export type StaffCalendarNavigationView = z.infer<
  typeof StaffCalendarNavigationViewSchema
>;

// ============================================================================
// 2. Anomaly Summary Model (GET /api/v1/anomalies?include_snapshot=false)
// ============================================================================

export const AnomalySeverityEnum = z.enum(['warning', 'blocking']);
export type AnomalySeverity = z.infer<typeof AnomalySeverityEnum>;

export const AnomalyWorkflowStatusEnum = z.enum(['open', 'claimed', 'resolved']);
export type AnomalyWorkflowStatus = z.infer<typeof AnomalyWorkflowStatusEnum>;

export const AnomalySummaryViewSchema = z
  .object({
    fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
    definition_code: z.string().min(1),
    source_domain: z.string().min(1),
    source_identity: z.string().min(1),
    source_version: z.number().int().nonnegative(),
    severity: AnomalySeverityEnum,
    predicate_active: z.boolean(),
    workflow_status: AnomalyWorkflowStatusEnum,
    workflow_version: z.number().int().nonnegative(),
    display_snapshot: z.null().optional(),
    staff_calendar_navigation: StaffCalendarNavigationViewSchema.nullable().optional(),
  })
  .strict();

export type AnomalySummaryView = z.infer<typeof AnomalySummaryViewSchema>;

// ============================================================================
// 3. Import Warning Task Model (GET /api/v1/import-warning-tracking/tasks)
// ============================================================================

export const ImportWarningTrackingStatusEnum = z.enum([
  'open',
  'awaiting_external_confirmation',
  'response_recorded',
  'reimport_requested',
  'closed',
  'auto_resolved',
]);
export type ImportWarningTrackingStatus = z.infer<
  typeof ImportWarningTrackingStatusEnum
>;

export const ImportWarningNavigationActionEnum = z.enum([
  'hcm_import_center',
  'historical_order_import_center',
  'client_beclass_import_center',
  'staff_beclass_import_center',
  'finance_import_recovery_center',
]);
export type ImportWarningNavigationAction = z.infer<
  typeof ImportWarningNavigationActionEnum
>;

export const ImportWarningTaskViewSchema = z
  .object({
    occurrence_identity: z.string().min(1),
    owning_lane: z.string().min(1),
    logical_code: z.string().min(1),
    field_path: z.string().min(1),
    masked_subject: z.string().min(1),
    issue_codes: z.array(z.string()),
    tracking_status: ImportWarningTrackingStatusEnum,
    tracking_version: z.number().int().positive(),
    evidence_reference: z.string().nullable().optional(),
    display_message: z.string().min(1).max(200),
    navigation_action: ImportWarningNavigationActionEnum.nullable().optional(),
  })
  .strict();

export type ImportWarningTaskView = z.infer<typeof ImportWarningTaskViewSchema>;

// ============================================================================
// 4. Lazy Drawer GET models
// ============================================================================

export const AnomalyTimelineEventSchema = z
  .object({
    action: z.string().min(1),
    expected_workflow_version: z.number().int().nonnegative(),
    resulting_workflow_version: z.number().int().nonnegative(),
    actor: z.string().min(1),
    reason: z.string().min(1),
    correlation_id: z.string().min(1),
    created_at: z.string().min(1),
  })
  .strict();

export type AnomalyTimelineEvent = z.infer<typeof AnomalyTimelineEventSchema>;

export const AnomalyDomainActionViewSchema = z
  .object({
    action_key: z.string().min(1),
    label: z.string().min(1),
    owning_domain: z.string().min(1),
    form_schema_key: z.string().min(1),
    source_binding_keys: z.array(z.string()),
    source_bindings: z.null(),
    required_operator_inputs: z.array(z.string()),
    preview_operation: z.string().min(1),
    apply_operation: z.string().nullable(),
    required_capability: z.string().nullable(),
    completion_predicate: z.string().min(1),
    action_contract_version: z.number().int().positive(),
    requires_preview: z.boolean(),
  })
  .strict();

export type AnomalyDomainActionView = z.infer<
  typeof AnomalyDomainActionViewSchema
>;

/**
 * Detail summary intentionally accepts only the list contract's null snapshot.
 * A non-null raw snapshot therefore becomes an explicit unavailable state.
 */
export const AnomalyDetailViewSchema = z
  .object({
    summary: AnomalySummaryViewSchema,
    timeline: z.array(AnomalyTimelineEventSchema),
    available_actions: z.array(AnomalyDomainActionViewSchema),
  })
  .strict();

export type AnomalyDetailView = z.infer<typeof AnomalyDetailViewSchema>;

export const ImportWarningReferralViewSchema = z
  .object({
    occurrence_identity: z.string().min(1),
    expected_version: z.number().int().positive(),
    owning_lane: z.literal('hcm'),
    logical_code: z.string().min(1),
    field_path: z.string().min(1),
    masked_subject: z.string().min(1),
    display_message: z.string().min(1).max(200),
    navigation_action: z.literal('hcm_import_center'),
    action_kind: z.enum(['owner_preview_apply', 'wait_for_counterpart']),
    target_command: z.literal('preview_hcm_resubmission').nullable(),
  })
  .strict();

export type ImportWarningReferralView = z.infer<
  typeof ImportWarningReferralViewSchema
>;

// ============================================================================
// 4. Response Envelope Schemas (Strict BaseResponse<T>)
// ============================================================================

export function createStrictEnvelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z
    .object({
      success: z.boolean(),
      message: z.string(),
      data: dataSchema,
      error: z.string().nullable().optional(),
    })
    .strict();
}

export const AnomalySummariesResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: z.array(AnomalySummaryViewSchema),
    error: z.string().nullable().optional(),
  })
  .strict();

export type AnomalySummariesResponse = z.infer<
  typeof AnomalySummariesResponseSchema
>;

export const ImportWarningTasksResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: z.array(ImportWarningTaskViewSchema),
    error: z.string().nullable().optional(),
  })
  .strict();

export type ImportWarningTasksResponse = z.infer<
  typeof ImportWarningTasksResponseSchema
>;

export const AnomalyDetailResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: AnomalyDetailViewSchema,
    error: z.string().nullable().optional(),
  })
  .strict();

export type AnomalyDetailResponse = z.infer<typeof AnomalyDetailResponseSchema>;

export const ImportWarningReferralResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: ImportWarningReferralViewSchema,
    error: z.string().nullable().optional(),
  })
  .strict();

export type ImportWarningReferralResponse = z.infer<
  typeof ImportWarningReferralResponseSchema
>;
