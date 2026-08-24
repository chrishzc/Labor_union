/**
 * File: matching_candidate_workflow_client.ts
 * Description: 查詢單月嫂或多月嫂候選，並以既有正式 route 建立一至四段媒合方案。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const DateRangeSchema = z.strictObject({
  start_date: IsoDateSchema,
  end_date: IsoDateSchema,
});
const SegmentDraftSchema = z.strictObject({
  staff_id: z.number().int().positive().optional(),
  start_date: IsoDateSchema.optional(),
  end_date: IsoDateSchema.optional(),
});
const PlanSegmentInputSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  start_date: IsoDateSchema,
  end_date: IsoDateSchema,
});
const SegmentCandidateSchema = z.strictObject({
  segment_index: z.number().int().nonnegative(),
  staff_id: z.number().int().positive(),
  start_date: IsoDateSchema,
  end_date: IsoDateSchema,
});
const CandidateOptionSchema = z.strictObject({
  segment_index: z.number().int().nonnegative(),
  staff_id: z.number().int().positive(),
  staff_name: z.string().min(1),
  // Partial availability can legitimately contain a candidate with zero
  // usable service days; the UI must render its conflicts rather than reject
  // the complete server response.
  coverage_day_count: z.number().int().nonnegative(),
  available_ranges: z.array(DateRangeSchema),
  case_period_start: IsoDateSchema,
  case_period_end: IsoDateSchema,
  required_service_dates: z.array(IsoDateSchema),
  supported_service_dates: z.array(IsoDateSchema),
  supported_ranges: z.array(DateRangeSchema.extend({ service_day_count: z.number().int().positive() })),
  supported_day_count: z.number().int().nonnegative(),
  required_day_count: z.number().int().positive(),
  full_case_coverage: z.boolean(),
  selected_segment_start: IsoDateSchema,
  selected_segment_end: IsoDateSchema,
  full_selected_segment_coverage: z.boolean(),
  uncovered_segment_dates: z.array(IsoDateSchema),
  source_scheduling_version: z.number().int().nonnegative(),
  filter_results: z.record(z.string(), z.boolean()),
});
const AvailabilitySchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  planned_start_date: IsoDateSchema,
  planned_end_date: IsoDateSchema,
  feasibility: z.enum(['complete', 'partial']),
  complete_combinations: z.array(z.array(SegmentCandidateSchema)),
  segment_candidates: z.array(SegmentCandidateSchema),
  candidate_options: z.array(CandidateOptionSchema),
  conflicts: z.array(z.strictObject({
    segment_index: z.number().int().nonnegative(),
    staff_id: z.number().int().positive().nullable(),
    work_date: IsoDateSchema,
    reason_code: z.string().min(1),
  })),
});
const FormalPlanSchema = z.strictObject({
  plan_id: z.number().int().positive(),
  case_no: z.string().min(1).max(50),
  version: z.number().int().positive(),
  status: z.literal('proposed'),
  result: z.enum(['created', 'existing']),
  segments: z.array(z.strictObject({
    segment_order: z.number().int().positive(),
    staff_id: z.number().int().positive(),
    assigned_start_date: IsoDateSchema,
    assigned_end_date: IsoDateSchema,
  })).min(1).max(4),
});
const envelope = <TSchema extends z.ZodTypeAny>(schema: TSchema) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema.nullable(),
  error: z.string().nullable(),
});

export type MatchingCandidateOption = z.infer<typeof CandidateOptionSchema>;
export type MatchingAvailability = z.infer<typeof AvailabilitySchema>;
export type FormalMatchingPlan = z.infer<typeof FormalPlanSchema>;
export type MatchingSegmentDraft = z.infer<typeof SegmentDraftSchema>;
export type MatchingPlanSegmentInput = z.infer<typeof PlanSegmentInputSchema>;
export type MatchingFilterPolicy = Readonly<{
  region: boolean;
  cooking: boolean;
  preferred_service_days: boolean;
  daily_service_hours: boolean;
}>;

export const defaultMatchingFilterPolicy: MatchingFilterPolicy = Object.freeze({
  region: true,
  cooking: true,
  preferred_service_days: true,
  daily_service_hours: true,
});

const MatchingFilterPolicySchema = z.strictObject({
  region: z.boolean(),
  cooking: z.boolean(),
  preferred_service_days: z.boolean(),
  daily_service_hours: z.boolean(),
});

function canonicalCaseNo(caseNo: string): string {
  const canonical = caseNo.trim();
  if (!canonical || canonical.length > 50) throw new Error('案件編號必須是 1 至 50 字元。');
  return canonical;
}

function authOptions(): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  return { token };
}

function result<T>(schema: z.ZodType<T>, raw: unknown, code: string): T {
  const decoded = decodePayload(envelope(schema), raw);
  if (!decoded.success || decoded.data === null) {
    throw new ApiHttpError(422, code, decoded.error ?? decoded.message, false, decoded);
  }
  return decoded.data as T;
}

export const matchingCandidateWorkflowClient = {
  async searchSegmentedCaregivers(
    caseNo: string,
    segmentCount: 1 | 2 | 3 | 4,
    segmentDrafts: MatchingSegmentDraft[] = [],
    filters: MatchingFilterPolicy = defaultMatchingFilterPolicy,
  ): Promise<MatchingAvailability> {
    const canonical = canonicalCaseNo(caseNo);
    const drafts = z.array(SegmentDraftSchema).max(segmentCount).parse(segmentDrafts);
    const parsedFilters = MatchingFilterPolicySchema.parse(filters);
    for (const draft of drafts) {
      if (draft.start_date && draft.end_date && draft.start_date > draft.end_date) {
        throw new Error('服務分段結束日不得早於開始日。');
      }
    }
    const data = result(
      AvailabilitySchema,
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonical)}/caregiver-segment-availability/search`,
        {
          segment_count: segmentCount,
          segment_drafts: drafts,
          as_of: new Date().toISOString().slice(0, 10),
          filters: parsedFilters,
        },
        authOptions(),
      ),
      'MATCHING_AVAILABILITY_SEARCH_FAILED',
    );
    if (data.case_no !== canonical) throw new Error('媒合候選查詢案件識別不一致。');
    return data;
  },

  async searchSingleCaregiver(
    caseNo: string,
    startDate: string,
    endDate: string,
    filters: MatchingFilterPolicy = defaultMatchingFilterPolicy,
  ): Promise<MatchingAvailability> {
    const dates = DateRangeSchema.parse({ start_date: startDate, end_date: endDate });
    if (dates.start_date > dates.end_date) throw new Error('服務結束日不得早於開始日。');
    return this.searchSegmentedCaregivers(caseNo, 1, [dates], filters);
  },

  async createMatchingPlan(
    caseNo: string,
    candidates: MatchingPlanSegmentInput[],
  ): Promise<FormalMatchingPlan> {
    const canonical = canonicalCaseNo(caseNo);
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const segments = z.array(PlanSegmentInputSchema).min(1).max(4).parse(candidates);
    for (const segment of segments) {
      if (segment.start_date > segment.end_date) throw new Error('服務分段結束日不得早於開始日。');
    }
    const data = result(
      FormalPlanSchema,
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonical)}/matching-plans`,
        {
          segments,
          created_by: actor,
          as_of: new Date().toISOString().slice(0, 10),
        },
        authOptions(),
      ),
      'FORMAL_MATCHING_PLAN_CREATE_FAILED',
    );
    if (data.case_no !== canonical || data.segments.length !== segments.length || data.segments.some((segment, index) => (
      segment.staff_id !== segments[index]?.staff_id
      || segment.assigned_start_date !== segments[index]?.start_date
      || segment.assigned_end_date !== segments[index]?.end_date
    ))) {
      throw new Error('正式媒合方案回讀 identity 不一致。');
    }
    return data;
  },

  async createSingleCaregiverPlan(
    caseNo: string,
    candidate: MatchingPlanSegmentInput,
  ): Promise<FormalMatchingPlan> {
    return this.createMatchingPlan(caseNo, [candidate]);
  },
};
