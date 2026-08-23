/**
 * File: leave_substitution_schemas.ts
 * Description: 定義請假代班 assignments、Preview、Apply 與 receipt 的嚴格 Zod 契約。
 */
import { z } from 'zod';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

function isCalendarDate(value: string): boolean {
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export const LeaveSubstitutionIsoDateSchema = z
  .string()
  .regex(ISO_DATE_PATTERN, '日期必須是 YYYY-MM-DD。')
  .refine(isCalendarDate, '日期不是有效日曆日期。');

export const LeaveSubstitutionFingerprintSchema = z
  .string()
  .regex(SHA256_PATTERN, 'fingerprint 必須是小寫 SHA-256。');

export const LeaveResolutionTypeSchema = z.enum([
  'defer_following_assignments',
  'substitute',
]);

export const LeaveOfficialScheduleSummarySchema = z.strictObject({
  schedule_id: z.number().int().positive(),
  work_date: LeaveSubstitutionIsoDateSchema,
});

export const LeaveSubstitutionAssignmentSchema = z
  .strictObject({
    assignment_id: z.number().int().positive(),
    staff_id: z.number().int().positive(),
    assigned_start_date: LeaveSubstitutionIsoDateSchema,
    assigned_end_date: LeaveSubstitutionIsoDateSchema,
    official_schedules: z.array(LeaveOfficialScheduleSummarySchema),
  })
  .superRefine((assignment, context) => {
    if (assignment.assigned_end_date < assignment.assigned_start_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['assigned_end_date'],
        message: 'assigned_end_date 不得早於 assigned_start_date。',
      });
    }
  });

const leaveSubstitutionItemFields = {
  original_schedule_id: z.number().int().positive(),
  work_date: LeaveSubstitutionIsoDateSchema,
  resolution_type: LeaveResolutionTypeSchema,
  substitute_staff_id: z.number().int().positive().nullable(),
  is_double_pay: z.boolean(),
};

export const LeaveSubstitutionItemSchema = z
  .strictObject(leaveSubstitutionItemFields)
  .superRefine((item, context) => {
    if (item.resolution_type === 'substitute' && item.substitute_staff_id === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['substitute_staff_id'],
        message: 'substitute resolution requires substitute_staff_id。',
      });
    }
    if (
      item.resolution_type === 'defer_following_assignments' &&
      (item.substitute_staff_id !== null || item.is_double_pay)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['resolution_type'],
        message: 'defer resolution cannot carry substitute or double-pay data。',
      });
    }
  });

const linkedRequestIdentityFields = {
  leave_request_id: z.number().int().positive().nullable(),
  expected_leave_request_version: z.number().int().min(1).nullable(),
};

function validateLinkedRequestIdentity(
  value: { leave_request_id: number | null; expected_leave_request_version: number | null },
  context: z.RefinementCtx,
): void {
  if ((value.leave_request_id === null) !== (value.expected_leave_request_version === null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['leave_request_id'],
      message: 'leave_request_identity_pair_required',
    });
  }
}

const leaveSubstitutionCommandFields = {
  original_assignment_id: z.number().int().positive(),
  items: z.array(LeaveSubstitutionItemSchema),
  ...linkedRequestIdentityFields,
};

export const LeaveSubstitutionPreviewRequestSchema = z
  .strictObject(leaveSubstitutionCommandFields)
  .superRefine(validateLinkedRequestIdentity);

export const LeaveSubstitutionApplyRequestSchema = z
  .strictObject({
    ...leaveSubstitutionCommandFields,
    expected_order_version: z.number().int().nonnegative(),
    expected_scheduling_version: z.number().int().nonnegative(),
    expected_client_finance_version: z.number().int().nonnegative(),
    expected_payroll_version: z.number().int().nonnegative(),
    preview_fingerprint: LeaveSubstitutionFingerprintSchema,
    reason: z.string().trim().min(1).max(500),
  })
  .superRefine(validateLinkedRequestIdentity);

export const LeaveSubstitutionOutcomeSchema = z.strictObject({
  item_index: z.number().int().nonnegative(),
  original_schedule_id: z.number().int().positive(),
  original_assignment_id: z.number().int().positive(),
  original_staff_id: z.number().int().positive(),
  original_work_date: LeaveSubstitutionIsoDateSchema,
  resolution_type: z.string().min(1),
  leave_occupancy_date: LeaveSubstitutionIsoDateSchema,
  resulting_service_date: LeaveSubstitutionIsoDateSchema,
  resulting_staff_id: z.number().int().positive(),
  resulting_assignment_key: z.string().min(1),
  is_double_pay: z.boolean(),
});

export const LeaveSubstitutionCalendarDaySchema = z.strictObject({
  calendar_date: LeaveSubstitutionIsoDateSchema,
  before_kind: z.string(),
  after_kind: z.string(),
  change_kind: z.string(),
  before_staff_id: z.number().int().positive().nullable(),
  after_staff_id: z.number().int().positive().nullable(),
});

export const LeaveSubstitutionCalendarCandidateSchema = z.strictObject({
  before_service_day_count: z.number().int().nonnegative(),
  after_service_day_count: z.number().int().nonnegative(),
  before_service_start_date: LeaveSubstitutionIsoDateSchema.nullable(),
  before_service_end_date: LeaveSubstitutionIsoDateSchema.nullable(),
  after_service_start_date: LeaveSubstitutionIsoDateSchema.nullable(),
  after_service_end_date: LeaveSubstitutionIsoDateSchema.nullable(),
  contracted_service_day_count: z.number().int().nonnegative(),
  deferred_day_count: z.number().int().nonnegative(),
  substitute_day_count: z.number().int().nonnegative(),
  leave_day_count: z.number().int().nonnegative(),
  holiday_rest_day_count: z.number().int().nonnegative(),
  fixed_rest_day_count: z.number().int().nonnegative(),
  holiday_version: z.string().min(1),
  holiday_rows: z.array(z.tuple([LeaveSubstitutionIsoDateSchema, z.string()])),
  conservation_status: z.string().min(1),
  day_cells: z.array(LeaveSubstitutionCalendarDaySchema),
});

export const LeaveSubstitutionApplyReadinessSchema = z.strictObject({
  status: z.string().min(1),
  blockers: z.array(z.string()),
});

export const LeaveSubstitutionImpactSchema = z.strictObject({
  expected_version: z.number().int().nonnegative(),
  resulting_version: z.number().int().nonnegative(),
  fingerprint: LeaveSubstitutionFingerprintSchema,
  blockers: z.array(z.string()),
});

export const LinkedLeaveRequestSchema = z.strictObject({
  request_id: z.number().int().positive(),
  expected_version: z.number().int().min(1),
  resolved_version: z.number().int().min(1).nullable(),
  status: z.enum(['accepted_for_processing', 'resolved']),
  receipt_key: z.string().min(1).nullable(),
  notification_intent: z.enum(['not_requested', 'enqueued']),
});

const assignmentPlanSegmentFields = {
  assignment_id: z.number().int().positive().nullable().optional(),
  candidate_key: z.string().min(1).nullable().optional(),
  staff_id: z.number().int().positive(),
  sequence: z.number().int().positive(),
  assigned_start_date: LeaveSubstitutionIsoDateSchema,
  assigned_end_date: LeaveSubstitutionIsoDateSchema,
  official_service_dates: z.array(LeaveSubstitutionIsoDateSchema),
  actual_hours: z.number().int().nonnegative().nullable().optional(),
  lineage_source_assignment_ids: z.array(z.number().int().positive()),
};

export const LeaveSubstitutionAssignmentPlanSegmentSchema = z
  .strictObject(assignmentPlanSegmentFields)
  .superRefine((assignment, context) => {
    if (assignment.assigned_end_date < assignment.assigned_start_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['assigned_end_date'],
        message: 'assigned_end_date 不得早於 assigned_start_date。',
      });
    }
  });

export const LeaveSubstitutionPreviewSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  cancelled_assignment_ids: z.array(z.number().int().positive()),
  assignments: z.array(LeaveSubstitutionAssignmentPlanSegmentSchema),
  outcomes: z.array(LeaveSubstitutionOutcomeSchema),
  client_finance_impact: LeaveSubstitutionImpactSchema,
  payroll_impact: LeaveSubstitutionImpactSchema,
  orders_impact: LeaveSubstitutionImpactSchema,
  calendar_candidate: LeaveSubstitutionCalendarCandidateSchema,
  apply_readiness: LeaveSubstitutionApplyReadinessSchema,
  linked_request: LinkedLeaveRequestSchema.nullable(),
  preview_fingerprint: LeaveSubstitutionFingerprintSchema,
});

export const LeaveSubstitutionReceiptSchema = z.strictObject({
  batch_key: z.string().min(1),
  case_no: z.string().min(1).max(50),
  order_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  outcome_event_ids: z.array(z.number().int().positive()),
  preview_fingerprint: LeaveSubstitutionFingerprintSchema,
  linked_request: LinkedLeaveRequestSchema.nullable(),
});

export const LeaveSubstitutionAssignmentsResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: z.array(LeaveSubstitutionAssignmentSchema).nullable(),
  error: z.string().nullable().optional(),
});

export const LeaveSubstitutionPreviewResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: LeaveSubstitutionPreviewSchema.nullable(),
  error: z.string().nullable().optional(),
});

export const LeaveSubstitutionApplyResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: LeaveSubstitutionReceiptSchema.nullable(),
  error: z.string().nullable().optional(),
});

export type LeaveSubstitutionIsoDate = z.infer<typeof LeaveSubstitutionIsoDateSchema>;
export type LeaveResolutionType = z.infer<typeof LeaveResolutionTypeSchema>;
export type LeaveOfficialScheduleSummary = z.infer<typeof LeaveOfficialScheduleSummarySchema>;
export type LeaveSubstitutionAssignment = z.infer<typeof LeaveSubstitutionAssignmentSchema>;
export type LeaveSubstitutionItem = z.infer<typeof LeaveSubstitutionItemSchema>;
export type LeaveSubstitutionPreviewRequest = z.infer<typeof LeaveSubstitutionPreviewRequestSchema>;
export type LeaveSubstitutionApplyRequest = z.infer<typeof LeaveSubstitutionApplyRequestSchema>;
export type LeaveSubstitutionOutcome = z.infer<typeof LeaveSubstitutionOutcomeSchema>;
export type LeaveSubstitutionCalendarDay = z.infer<typeof LeaveSubstitutionCalendarDaySchema>;
export type LeaveSubstitutionCalendarCandidate = z.infer<typeof LeaveSubstitutionCalendarCandidateSchema>;
export type LeaveSubstitutionApplyReadiness = z.infer<typeof LeaveSubstitutionApplyReadinessSchema>;
export type LeaveSubstitutionImpact = z.infer<typeof LeaveSubstitutionImpactSchema>;
export type LinkedLeaveRequest = z.infer<typeof LinkedLeaveRequestSchema>;
export type LeaveSubstitutionAssignmentPlanSegment = z.infer<typeof LeaveSubstitutionAssignmentPlanSegmentSchema>;
export type LeaveSubstitutionPreview = z.infer<typeof LeaveSubstitutionPreviewSchema>;
export type LeaveSubstitutionReceipt = z.infer<typeof LeaveSubstitutionReceiptSchema>;
