/**
 * File: eligibility_collision_schemas.ts
 * Description: 定義 Scheduling 資格、衝突與覆蓋的 strict GET 回應契約。
 */
import { z } from 'zod';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
export const SchedulingEligibilityDateSchema = z.string().regex(ISO_DATE);
export const SchedulingEligibilityDateTimeSchema = z.string().datetime({ offset: true });

export const SchedulingQualificationCheckStatusSchema = z.enum(['pass', 'fail', 'unknown']);
export const SchedulingEligibilityStateSchema = z.enum(['eligible', 'ineligible', 'partial', 'unavailable']);
export const SchedulingAvailabilityStateSchema = z.enum(['available', 'blocked', 'requires_review', 'unknown']);
export const SchedulingCoverageStateSchema = z.enum(['complete', 'incomplete', 'requires_review', 'unavailable']);
export const SchedulingCollisionKindSchema = z.enum([
  'assignment_interval',
  'official_schedule',
  'waiting_deposit_lock',
  'seven_day_buffer',
  'staff_unavailability',
  'legacy_schedule',
  'data_integrity',
]);
export const SchedulingCollisionSeveritySchema = z.enum(['hard_block', 'requires_review']);

export const SchedulingQualificationCheckSchema = z.strictObject({
  code: z.string().min(1).max(100),
  status: SchedulingQualificationCheckStatusSchema,
  owner: z.string().min(1).max(191),
  source_identity: z.string().min(1).max(191),
  source_version: z.number().int().nonnegative().nullable(),
  detail: z.string().min(1).max(500),
});

export const SchedulingCollisionSchema = z.strictObject({
  kind: SchedulingCollisionKindSchema,
  severity: SchedulingCollisionSeveritySchema,
  staff_id: z.number().int().positive(),
  case_no: z.string().min(1).max(50).nullable(),
  assignment_id: z.number().int().positive().nullable(),
  source_id: z.number().int().positive().nullable(),
  collision_date: SchedulingEligibilityDateSchema.nullable(),
  start_date: SchedulingEligibilityDateSchema.nullable(),
  end_date: SchedulingEligibilityDateSchema.nullable(),
  owner: z.string().min(1).max(191),
  source_identity: z.string().min(1).max(191),
  detail: z.string().min(1).max(500),
});

export const SchedulingCoverageSchema = z.strictObject({
  start_date: SchedulingEligibilityDateSchema.nullable(),
  end_date: SchedulingEligibilityDateSchema.nullable(),
  required_day_count: z.number().int().nonnegative().nullable(),
  available_day_count: z.number().int().nonnegative().nullable(),
  missing_dates: z.array(SchedulingEligibilityDateSchema),
  review_dates: z.array(SchedulingEligibilityDateSchema),
  status: SchedulingCoverageStateSchema,
});

export const SchedulingStaffEligibilityCollisionSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  eligibility: SchedulingEligibilityStateSchema,
  availability: SchedulingAvailabilityStateSchema,
  qualification_checks: z.array(SchedulingQualificationCheckSchema),
  collisions: z.array(SchedulingCollisionSchema),
  coverage: SchedulingCoverageSchema,
  partial_data: z.array(z.string()),
});

export const SchedulingEligibilityCollisionProjectionSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  case_status: z.string().min(1).max(50),
  as_of: SchedulingEligibilityDateSchema,
  evaluated_at: SchedulingEligibilityDateTimeSchema,
  scheduling_version: z.number().int().nonnegative().nullable(),
  staff: z.array(SchedulingStaffEligibilityCollisionSchema),
  partial_data: z.array(z.string()),
});

export const SchedulingEligibilityCollisionResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: SchedulingEligibilityCollisionProjectionSchema.nullable(),
  error: z.string().nullable().optional(),
});

export type SchedulingQualificationCheck = z.infer<typeof SchedulingQualificationCheckSchema>;
export type SchedulingCollision = z.infer<typeof SchedulingCollisionSchema>;
export type SchedulingCoverage = z.infer<typeof SchedulingCoverageSchema>;
export type SchedulingStaffEligibilityCollision = z.infer<typeof SchedulingStaffEligibilityCollisionSchema>;
export type SchedulingEligibilityCollisionProjection = z.infer<typeof SchedulingEligibilityCollisionProjectionSchema>;
