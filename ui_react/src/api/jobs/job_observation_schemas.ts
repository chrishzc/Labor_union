/**
 * File: job_observation_schemas.ts
 * Description: 背景工作安全觀察 GET 的嚴格 Zod 契約。
 */
import { z } from 'zod';

export const JobCommandTypeSchema = z.enum([
  'assignment_plan_apply',
  'finance_import_historical_reprocess_apply',
  'finance_import_batch_apply',
  'finance_import_correction_apply',
  'orders_auto_completion_apply',
  'government_subsidy_apply',
  'payroll_rebuild_apply',
  'staff_payout_apply',
]);

export const JobObservationSchema = z
  .object({
    job_id: z.string().min(1).max(191),
    command_type: JobCommandTypeSchema,
    status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']),
    attempt_count: z.number().int().nonnegative(),
    max_attempts: z.number().int().nonnegative(),
  })
  .strict();

export type JobObservation = z.infer<typeof JobObservationSchema>;

export const JobObservationResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: JobObservationSchema,
    error: z.string().nullable().optional(),
  })
  .strict();
