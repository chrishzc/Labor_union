/**
 * File: order_stage_projection_schemas.ts
 * Description: 嚴格解碼 Orders 七階段與十一作業步驟的唯讀 projection。
 */
import { z } from 'zod';

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const DateTimeSchema = z.string().min(1);
const StageStatusSchema = z.enum(['not_started', 'in_progress', 'blocked', 'completed', 'unavailable']);
const StageCodeSchema = z.enum([
  'intake_terms',
  'matching_willingness',
  'client_review',
  'contract_deposit',
  'date_confirmation',
  'active_service',
  'settlement_payout',
]);

export const SourceLineageSchema = z.strictObject({
  owner: z.string().min(1),
  identity: z.string().min(1).nullable(),
  version: z.number().int().nonnegative().nullable(),
});

export const ProjectionNoticeSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string(),
});

export const AvailableActionSchema = z.strictObject({
  action_id: z.string().min(1),
  method: z.literal('GET'),
  path: z.string().min(1),
});

export const SettlementProjectionSchema = z.strictObject({
  code: z.enum(['service_completion', 'client_settlement', 'staff_payout']),
  status: StageStatusSchema,
  source: SourceLineageSchema,
  occurred_at: DateTimeSchema.nullable(),
  availability_reason: z.string().min(1).nullable(),
});

export const StageProjectionSchema = z.strictObject({
  ordinal: z.number().int().min(1).max(7),
  code: StageCodeSchema,
  label: z.string().min(1),
  owner: z.string().min(1),
  status: StageStatusSchema,
  source: SourceLineageSchema,
  occurred_at: DateTimeSchema.nullable(),
  blockers: z.array(ProjectionNoticeSchema),
  warnings: z.array(ProjectionNoticeSchema),
  available_actions: z.array(AvailableActionSchema),
  availability_reason: z.string().min(1).nullable(),
  settlement: z.array(SettlementProjectionSchema),
});

export const SopStepProjectionSchema = z.strictObject({
  ordinal: z.number().int().min(1).max(11),
  code: z.string().min(1),
  label: z.string().min(1),
  owner: z.string().min(1),
  status: StageStatusSchema,
  occurred_at: DateTimeSchema.nullable(),
  blockers: z.array(ProjectionNoticeSchema),
  warnings: z.array(ProjectionNoticeSchema),
  available_actions: z.array(AvailableActionSchema),
  availability_reason: z.string().min(1).nullable(),
});

export const OrderOperationalTimelineSchema = z.strictObject({
  case_no: z.string().min(1),
  base_revision: z.number().int().nonnegative(),
  current_stage_code: StageCodeSchema.nullable(),
  stages: z.array(StageProjectionSchema).length(7),
  sop_steps: z.array(SopStepProjectionSchema).length(11),
  projection_digest: Sha256Schema,
}).superRefine((timeline, context) => {
  const stageOrdinals = timeline.stages.map((stage) => stage.ordinal);
  const stageCodes = timeline.stages.map((stage) => stage.code);
  if (new Set(stageOrdinals).size !== 7 || stageOrdinals.some((value, index) => value !== index + 1)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['stages'], message: '七階 ordinal 必須完整且不重複' });
  }
  if (new Set(stageCodes).size !== 7) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['stages'], message: '七階 code 不得重複' });
  }
  const stepOrdinals = timeline.sop_steps.map((step) => step.ordinal);
  if (new Set(stepOrdinals).size !== 11 || stepOrdinals.some((value, index) => value !== index + 1)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['sop_steps'], message: 'SOP ordinal 必須完整且不重複' });
  }
});

export const StageCountsSchema = z.strictObject({
  intake_terms: z.number().int().nonnegative(),
  matching_willingness: z.number().int().nonnegative(),
  client_review: z.number().int().nonnegative(),
  contract_deposit: z.number().int().nonnegative(),
  date_confirmation: z.number().int().nonnegative(),
  active_service: z.number().int().nonnegative(),
  settlement_payout: z.number().int().nonnegative(),
});

export const OrderOperationalTimelinePageSchema = z.strictObject({
  items: z.array(OrderOperationalTimelineSchema),
  stage_counts: StageCountsSchema,
  next_cursor: z.string().min(1).nullable(),
  etag: Sha256Schema,
});

export type SourceLineage = z.infer<typeof SourceLineageSchema>;
export type StageProjection = z.infer<typeof StageProjectionSchema>;
export type SopStepProjection = z.infer<typeof SopStepProjectionSchema>;
export type OrderOperationalTimeline = z.infer<typeof OrderOperationalTimelineSchema>;
export type OrderOperationalTimelinePage = z.infer<typeof OrderOperationalTimelinePageSchema>;
