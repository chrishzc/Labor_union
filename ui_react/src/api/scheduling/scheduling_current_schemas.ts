/**
 * File: scheduling_current_schemas.ts
 * Description: 定義 current Scheduling projection 與 Global error 的嚴格 Zod 契約。
 */
import { z } from 'zod';

export const SchedulingIsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const SchedulingIsoDateTimeSchema = z.string().datetime({ offset: true });

export const SchedulingAssignmentStatusSchema = z.enum([
  'planned',
  'active',
  'completed',
]);

export const SchedulingOccupancyKindSchema = z.enum([
  'official_workday',
  'assignment_rest',
  'assignment_buffer',
  'waiting_deposit_service',
  'waiting_deposit_buffer',
  'staff_unavailability',
]);

export const SchedulingCurrentAssignmentSchema = z
  .object({
    assignment_id: z.number().int().positive(),
    case_no: z.string().min(1).max(50).nullable(),
    generation_id: z.number().int().positive(),
    scheduling_version: z.number().int().nonnegative(),
    staff_id: z.number().int().positive(),
    status: SchedulingAssignmentStatusSchema,
    assigned_start_date: SchedulingIsoDateSchema,
    assigned_end_date: SchedulingIsoDateSchema,
    first_service_at: SchedulingIsoDateTimeSchema,
    completion_at: SchedulingIsoDateTimeSchema,
    official_service_day_count: z.number().int().positive(),
    actual_hours: z.number().int().positive(),
  })
  .strict();

export const SchedulingCurrentDayEntrySchema = z
  .object({
    occupancy_kind: SchedulingOccupancyKindSchema,
    case_no: z.string().min(1).max(50).nullable(),
    assignment_id: z.number().int().positive().nullable(),
    assignment_status: SchedulingAssignmentStatusSchema.nullable(),
    lock_id: z.number().int().positive().nullable(),
    segment_id: z.number().int().positive().nullable(),
    availability_block_id: z.number().int().positive().nullable(),
    unavailability_kind: z.string().min(1).nullable(),
  })
  .strict();

export const SchedulingCurrentDaySchema = z
  .object({
    calendar_date: SchedulingIsoDateSchema,
    available: z.boolean(),
    entries: z.array(SchedulingCurrentDayEntrySchema),
  })
  .strict();

export const SchedulingCaseVersionSchema = z
  .object({
    case_no: z.string().min(1).max(50),
    scheduling_version: z.number().int().nonnegative(),
  })
  .strict();

export const SchedulingCurrentProjectionSchema = z
  .object({
    staff_id: z.number().int().positive(),
    range_start: SchedulingIsoDateSchema,
    range_end: SchedulingIsoDateSchema,
    evaluated_at: SchedulingIsoDateTimeSchema,
    assignments: z.array(SchedulingCurrentAssignmentSchema),
    days: z.array(SchedulingCurrentDaySchema),
    case_versions: z.array(SchedulingCaseVersionSchema),
    projection_token: z.string().regex(/^[0-9a-f]{64}$/),
  })
  .strict();

export const SchedulingCurrentResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: SchedulingCurrentProjectionSchema,
    error: z.string().nullable().optional(),
  })
  .strict();

const SchedulingGlobalFieldErrorSchema = z
  .object({
    field: z.string(),
    code: z.string(),
    message: z.string(),
  })
  .strict();

export const SchedulingGlobalTypedErrorResponseSchema = z
  .object({
    detail: z
      .object({
        error: z
          .object({
            category: z.enum([
              'validation',
              'forbidden',
              'not_found',
              'domain_blocked',
              'conflict',
              'idempotency_mismatch',
              'unavailable',
              'internal',
            ]),
            code: z.string(),
            message: z.string(),
            field_errors: z.array(SchedulingGlobalFieldErrorSchema),
            domain_blockers: z.array(z.string()),
            retryable: z.boolean(),
            correlation_id: z.string(),
            current_version: z.number().int().nullable(),
          })
          .strict(),
      })
      .strict(),
  })
  .strict();

export type SchedulingAssignmentStatus = z.infer<
  typeof SchedulingAssignmentStatusSchema
>;
export type SchedulingOccupancyKind = z.infer<
  typeof SchedulingOccupancyKindSchema
>;
export type SchedulingCurrentAssignment = z.infer<
  typeof SchedulingCurrentAssignmentSchema
>;
export type SchedulingCurrentDayEntry = z.infer<
  typeof SchedulingCurrentDayEntrySchema
>;
export type SchedulingCurrentDay = z.infer<typeof SchedulingCurrentDaySchema>;
export type SchedulingCaseVersion = z.infer<typeof SchedulingCaseVersionSchema>;
export type SchedulingCurrentProjection = z.infer<
  typeof SchedulingCurrentProjectionSchema
>;
export type SchedulingCurrentResponse = z.infer<
  typeof SchedulingCurrentResponseSchema
>;
