/**
 * File: order_core_stage_projection_schemas.ts
 * Description: 嚴格解碼待辦看板 Beta 十三核心階段唯讀 contract。
 */
import { z } from 'zod';

export const CORE_STAGE_CODES = [
  'intake_validation',
  'matching_pool',
  'caregiver_line_delivery',
  'caregiver_willingness_reply',
  'formal_recommendation',
  'caregiver_contract',
  'deposit_settlement',
  'client_contract',
  'confirmed_service_dates',
  'formal_service',
  'service_completion',
  'client_settlement',
  'staff_payout',
] as const;

export const CORE_STAGE_STATUSES = [
  'not_started',
  'in_progress',
  'blocked',
  'completed',
  'unavailable',
] as const;

export const CORE_STAGE_BRANCH_TYPES = ['normal', 'historical', 'cancelled'] as const;
export const HISTORICAL_LIFECYCLE_FACETS = [
  'unserved',
  'in_service',
  'service_completed',
  'accounting_completed',
] as const;

export const CORE_STAGE_SUBSTATUS_CODES = [
  'intake_pending', 'intake_in_progress', 'intake_blocked', 'data_complete', 'intake_unavailable',
  'candidate_pool_pending', 'candidate_pool_building', 'candidate_pool_blocked', 'candidate_pool_ready', 'candidate_pool_unavailable',
  'contact_pending', 'contact_in_progress', 'contact_blocked', 'contact_completed', 'contact_unavailable',
  'reply_pending', 'reply_partial', 'reply_blocked', 'reply_complete', 'reply_unavailable',
  'recommendation_pending', 'recommendation_in_progress', 'recommendation_blocked', 'recommendation_completed', 'recommendation_unavailable',
  'caregiver_contract_pending', 'caregiver_contract_signing', 'caregiver_contract_blocked', 'caregiver_contract_completed', 'caregiver_contract_unavailable',
  'deposit_pending', 'deposit_in_progress', 'deposit_blocked', 'deposit_settled', 'deposit_unavailable',
  'client_contract_pending', 'client_contract_signing', 'client_contract_blocked', 'client_contract_completed', 'client_contract_unavailable',
  'date_confirmation_pending', 'date_confirmation_in_progress', 'date_confirmation_blocked', 'date_confirmed', 'date_confirmation_unavailable',
  'waiting_to_start', 'service_in_progress', 'service_blocked', 'service_period_completed', 'service_schedule_unavailable',
  'completion_pending', 'completion_in_progress', 'completion_blocked', 'completion_confirmed', 'completion_record_missing',
  'client_settlement_pending', 'client_settlement_in_progress', 'client_balance_open', 'client_settled', 'client_settlement_unavailable',
  'staff_settlement_pending', 'staff_settlement_in_progress', 'staff_payable_open', 'staff_settled', 'staff_settlement_unavailable',
] as const;

export type CoreStageCode = typeof CORE_STAGE_CODES[number];
export type CoreStageStatus = typeof CORE_STAGE_STATUSES[number];
export type CoreStageBranchType = typeof CORE_STAGE_BRANCH_TYPES[number];
export type HistoricalLifecycleFacet = typeof HISTORICAL_LIFECYCLE_FACETS[number];
export type CoreStageSubstatusCode = typeof CORE_STAGE_SUBSTATUS_CODES[number];

export const SUBSTATUS_BY_STAGE_STATUS = {
  intake_validation: {
    not_started: 'intake_pending', in_progress: 'intake_in_progress', blocked: 'intake_blocked', completed: 'data_complete', unavailable: 'intake_unavailable',
  },
  matching_pool: {
    not_started: 'candidate_pool_pending', in_progress: 'candidate_pool_building', blocked: 'candidate_pool_blocked', completed: 'candidate_pool_ready', unavailable: 'candidate_pool_unavailable',
  },
  caregiver_line_delivery: {
    not_started: 'contact_pending', in_progress: 'contact_in_progress', blocked: 'contact_blocked', completed: 'contact_completed', unavailable: 'contact_unavailable',
  },
  caregiver_willingness_reply: {
    not_started: 'reply_pending', in_progress: 'reply_partial', blocked: 'reply_blocked', completed: 'reply_complete', unavailable: 'reply_unavailable',
  },
  formal_recommendation: {
    not_started: 'recommendation_pending', in_progress: 'recommendation_in_progress', blocked: 'recommendation_blocked', completed: 'recommendation_completed', unavailable: 'recommendation_unavailable',
  },
  caregiver_contract: {
    not_started: 'caregiver_contract_pending', in_progress: 'caregiver_contract_signing', blocked: 'caregiver_contract_blocked', completed: 'caregiver_contract_completed', unavailable: 'caregiver_contract_unavailable',
  },
  deposit_settlement: {
    not_started: 'deposit_pending', in_progress: 'deposit_in_progress', blocked: 'deposit_blocked', completed: 'deposit_settled', unavailable: 'deposit_unavailable',
  },
  client_contract: {
    not_started: 'client_contract_pending', in_progress: 'client_contract_signing', blocked: 'client_contract_blocked', completed: 'client_contract_completed', unavailable: 'client_contract_unavailable',
  },
  confirmed_service_dates: {
    not_started: 'date_confirmation_pending', in_progress: 'date_confirmation_in_progress', blocked: 'date_confirmation_blocked', completed: 'date_confirmed', unavailable: 'date_confirmation_unavailable',
  },
  formal_service: {
    not_started: 'waiting_to_start', in_progress: 'service_in_progress', blocked: 'service_blocked', completed: 'service_period_completed', unavailable: 'service_schedule_unavailable',
  },
  service_completion: {
    not_started: 'completion_pending', in_progress: 'completion_in_progress', blocked: 'completion_blocked', completed: 'completion_confirmed', unavailable: 'completion_record_missing',
  },
  client_settlement: {
    not_started: 'client_settlement_pending', in_progress: 'client_settlement_in_progress', blocked: 'client_balance_open', completed: 'client_settled', unavailable: 'client_settlement_unavailable',
  },
  staff_payout: {
    not_started: 'staff_settlement_pending', in_progress: 'staff_settlement_in_progress', blocked: 'staff_payable_open', completed: 'staff_settled', unavailable: 'staff_settlement_unavailable',
  },
} as const satisfies Readonly<Record<CoreStageCode, Readonly<Record<CoreStageStatus, CoreStageSubstatusCode>>>>;

export function substatusCodesForStage(stage: CoreStageCode): readonly CoreStageSubstatusCode[] {
  const mapping = SUBSTATUS_BY_STAGE_STATUS[stage];
  return CORE_STAGE_STATUSES.map((status) => mapping[status]);
}

export function substatusBelongsToStage(
  stage: CoreStageCode,
  substatus: CoreStageSubstatusCode,
): boolean {
  return substatusCodesForStage(stage).includes(substatus);
}

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const NonnegativeIntSchema = z.number().int().nonnegative();
const DateTimeSchema = z.string().min(1);
const CoreStageCodeSchema = z.enum(CORE_STAGE_CODES);
const CoreStageStatusSchema = z.enum(CORE_STAGE_STATUSES);
const CoreStageBranchTypeSchema = z.enum(CORE_STAGE_BRANCH_TYPES);
const HistoricalLifecycleFacetSchema = z.enum(HISTORICAL_LIFECYCLE_FACETS);
const CoreStageSubstatusCodeSchema = z.enum(CORE_STAGE_SUBSTATUS_CODES);
const OrderLifecycleStatusSchema = z.enum([
  '待補件',
  '洽談中',
  '訂單成立',
  '服務中',
  '訂單完成',
  '訂單取消',
  '歷史訂單－未服務',
  '歷史訂單－服務中',
  '歷史訂單－服務完成',
  '歷史訂單－帳務完成',
]);

const SourceLineageSchema = z.strictObject({
  owner: z.string().min(1),
  identity: z.string().min(1).nullable(),
  version: NonnegativeIntSchema.nullable(),
});

const ProjectionNoticeSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string(),
});

const AvailableReadActionSchema = z.strictObject({
  action_id: z.string().min(1),
  method: z.literal('GET'),
  path: z.string().min(1),
});

export const CoreStageProjectionSchema = z.strictObject({
  ordinal: z.number().int().min(1).max(13),
  code: CoreStageCodeSchema,
  label: z.string().min(1),
  owner: z.string().min(1),
  status: CoreStageStatusSchema,
  substatus_code: CoreStageSubstatusCodeSchema,
  source: SourceLineageSchema,
  occurred_at: DateTimeSchema.nullable(),
  blockers: z.array(ProjectionNoticeSchema),
  warnings: z.array(ProjectionNoticeSchema),
  available_read_actions: z.array(AvailableReadActionSchema),
  availability_reason: z.string().min(1).nullable(),
}).superRefine((stage, context) => {
  const expectedSubstatus = SUBSTATUS_BY_STAGE_STATUS[stage.code][stage.status];
  if (stage.substatus_code !== expectedSubstatus) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['substatus_code'],
      message: '子狀態必須由同一核心階段與狀態的正式 mapping 產生',
    });
  }
});

export const OrderCoreStageTimelineSchema = z.strictObject({
  case_no: z.string().min(1),
  base_revision: NonnegativeIntSchema,
  lifecycle_status: OrderLifecycleStatusSchema,
  branch_type: CoreStageBranchTypeSchema,
  current_core_stage_code: CoreStageCodeSchema.nullable(),
  current_core_stage_ordinal: z.number().int().min(1).max(13).nullable(),
  historical_current_owner_stage_code: CoreStageCodeSchema.nullable(),
  historical_current_owner_stage_ordinal: z.number().int().min(1).max(13).nullable(),
  core_stages: z.array(CoreStageProjectionSchema).length(13),
  source_projection_digest: Sha256Schema,
}).superRefine((timeline, context) => {
  timeline.core_stages.forEach((stage, index) => {
    if (stage.ordinal !== index + 1 || stage.code !== CORE_STAGE_CODES[index]) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['core_stages', index],
        message: '十三核心階段 ordinal 與 code 必須完整且依正式順序排列',
      });
    }
  });

  const hasCurrentCode = timeline.current_core_stage_code !== null;
  const hasCurrentOrdinal = timeline.current_core_stage_ordinal !== null;
  if (hasCurrentCode !== hasCurrentOrdinal) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['current_core_stage_code'],
      message: '目前核心階段 code 與 ordinal 必須同時存在或同時為空',
    });
  } else if (timeline.current_core_stage_code !== null && timeline.current_core_stage_ordinal !== null) {
    const current = timeline.core_stages[timeline.current_core_stage_ordinal - 1];
    if (current?.code !== timeline.current_core_stage_code) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['current_core_stage_code'],
        message: '目前核心階段必須指向同一份十三階段投影',
      });
    }
  }

  const hasHistoricalOwnerCode = timeline.historical_current_owner_stage_code !== null;
  const hasHistoricalOwnerOrdinal = timeline.historical_current_owner_stage_ordinal !== null;
  if (hasHistoricalOwnerCode !== hasHistoricalOwnerOrdinal) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['historical_current_owner_stage_code'],
      message: '歷史 current owner stage code 與 ordinal 必須同時存在或同時為空',
    });
  } else if (
    timeline.historical_current_owner_stage_code !== null
    && timeline.historical_current_owner_stage_ordinal !== null
  ) {
    const currentOwner = timeline.core_stages[timeline.historical_current_owner_stage_ordinal - 1];
    if (currentOwner?.code !== timeline.historical_current_owner_stage_code) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['historical_current_owner_stage_code'],
        message: '歷史 current owner stage 必須指向同一份十三階段投影',
      });
    }
    if (currentOwner?.source.owner === 'Historical Orders') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['historical_current_owner_stage_code'],
        message: 'immutable historical baseline 不得冒充目前正式 owner stage',
      });
    }
  }

  const expectedBranch: CoreStageBranchType = timeline.lifecycle_status === '訂單取消'
    ? 'cancelled'
    : timeline.lifecycle_status.startsWith('歷史訂單－')
      ? 'historical'
      : 'normal';
  if (timeline.branch_type !== expectedBranch) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['branch_type'],
      message: 'branch_type 必須對應正式 lifecycle status',
    });
  }
  if (timeline.branch_type !== 'normal' && hasCurrentCode) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['current_core_stage_code'],
      message: '歷史或取消支線不得保留 normal mainline current stage',
    });
  }
  if (timeline.branch_type !== 'historical' && hasHistoricalOwnerCode) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['historical_current_owner_stage_code'],
      message: '只有 historical 支線可回傳 historical current owner progression',
    });
  }
  if (timeline.branch_type === 'cancelled' && (hasCurrentCode || hasHistoricalOwnerCode)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['branch_type'],
      message: '取消訂單必須維持終止狀態',
    });
  }
});

export const CoreStageCountsSchema = z.strictObject({
  intake_validation: NonnegativeIntSchema,
  matching_pool: NonnegativeIntSchema,
  caregiver_line_delivery: NonnegativeIntSchema,
  caregiver_willingness_reply: NonnegativeIntSchema,
  formal_recommendation: NonnegativeIntSchema,
  caregiver_contract: NonnegativeIntSchema,
  deposit_settlement: NonnegativeIntSchema,
  client_contract: NonnegativeIntSchema,
  confirmed_service_dates: NonnegativeIntSchema,
  formal_service: NonnegativeIntSchema,
  service_completion: NonnegativeIntSchema,
  client_settlement: NonnegativeIntSchema,
  staff_payout: NonnegativeIntSchema,
});

const CoreStageSubstatusCountsSchema = z.record(
  CoreStageSubstatusCodeSchema,
  NonnegativeIntSchema,
).superRefine((counts, context) => {
  const keys = Object.keys(counts).sort();
  if (keys.length === 0) return;
  const matchesOneStage = CORE_STAGE_CODES.some((stage) => {
    const expected = [...substatusCodesForStage(stage)].sort();
    return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
  });
  if (!matchesOneStage) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: '子狀態 counts 必須為空，或完整包含單一核心階段的五個正式子狀態',
    });
  }
});

export const HistoricalLifecycleCountsSchema = z.strictObject({
  unserved: NonnegativeIntSchema,
  in_service: NonnegativeIntSchema,
  service_completed: NonnegativeIntSchema,
  accounting_completed: NonnegativeIntSchema,
});

export const OrderCoreStageTimelinePageSchema = z.strictObject({
  items: z.array(OrderCoreStageTimelineSchema),
  stage_counts: CoreStageCountsSchema,
  substatus_counts: CoreStageSubstatusCountsSchema,
  historical_lifecycle_counts: HistoricalLifecycleCountsSchema,
  next_cursor: z.string().min(1).nullable(),
  etag: Sha256Schema,
});

export type CoreStageProjection = z.infer<typeof CoreStageProjectionSchema>;
export type OrderCoreStageTimeline = z.infer<typeof OrderCoreStageTimelineSchema>;
export type CoreStageCounts = z.infer<typeof CoreStageCountsSchema>;
export type HistoricalLifecycleCounts = z.infer<typeof HistoricalLifecycleCountsSchema>;
export type OrderCoreStageTimelinePage = z.infer<typeof OrderCoreStageTimelinePageSchema>;
export { HistoricalLifecycleFacetSchema };
