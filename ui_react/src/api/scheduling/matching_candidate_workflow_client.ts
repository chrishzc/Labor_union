/**
 * File: matching_candidate_workflow_client.ts
 * Description: 查詢單月嫂完整承接候選，並以既有正式 route 建立單段媒合方案。
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
  coverage_day_count: z.number().int().positive(),
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
  })).length(1),
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
  async searchSingleCaregiver(
    caseNo: string,
    startDate: string,
    endDate: string,
  ): Promise<MatchingAvailability> {
    const canonical = canonicalCaseNo(caseNo);
    const dates = DateRangeSchema.parse({ start_date: startDate, end_date: endDate });
    if (dates.start_date > dates.end_date) throw new Error('服務結束日不得早於開始日。');
    const data = result(
      AvailabilitySchema,
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonical)}/caregiver-segment-availability/search`,
        {
          segment_count: 1,
          segment_drafts: [dates],
          as_of: new Date().toISOString().slice(0, 10),
          filters: {},
        },
        authOptions(),
      ),
      'MATCHING_AVAILABILITY_SEARCH_FAILED',
    );
    if (data.case_no !== canonical) throw new Error('媒合候選查詢案件識別不一致。');
    return data;
  },

  async createSingleCaregiverPlan(
    caseNo: string,
    candidate: { staff_id: number; start_date: string; end_date: string },
  ): Promise<FormalMatchingPlan> {
    const canonical = canonicalCaseNo(caseNo);
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const segment = z.strictObject({
      staff_id: z.number().int().positive(),
      start_date: IsoDateSchema,
      end_date: IsoDateSchema,
    }).parse(candidate);
    if (segment.start_date > segment.end_date) throw new Error('服務結束日不得早於開始日。');
    const data = result(
      FormalPlanSchema,
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonical)}/matching-plans`,
        {
          segments: [segment],
          created_by: actor,
          as_of: new Date().toISOString().slice(0, 10),
        },
        authOptions(),
      ),
      'FORMAL_MATCHING_PLAN_CREATE_FAILED',
    );
    if (data.case_no !== canonical || data.segments[0]?.staff_id !== segment.staff_id) {
      throw new Error('正式媒合方案回讀 identity 不一致。');
    }
    return data;
  },
};
