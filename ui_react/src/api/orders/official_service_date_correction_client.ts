import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value => {
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(`${value}T00:00:00Z`);
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}, '不是有效的日曆日期');

const AssignmentSchema = z.object({
  assignment_id: z.number().int().positive(),
  staff_id: z.number().int().positive(),
  staff_name: z.string(),
  service_dates: z.array(DateSchema),
});

const QuerySchema = z.object({
  case_no: z.string(),
  order_version: z.number().int(),
  scheduling_version: z.number().int(),
  generation_id: z.number().int(),
  order_status: z.string(),
  service_data_locked: z.boolean(),
  actual_end_date: DateSchema.nullable(),
  assignments: z.array(AssignmentSchema),
  history: z.array(z.object({
    event_id: z.number().int().positive(),
    event_type: z.enum(['original_completion', 'service_date_corrected']),
    recorded_at: z.string().datetime({ offset: true }),
    actor: z.string(),
    before_dates: z.array(DateSchema),
    after_dates: z.array(DateSchema),
    reason: z.string().nullable(),
    completion_instant: z.string().datetime({ offset: true }).nullable(),
  })),
  monetary_change_blocker: z.boolean(),
  monetary_blockers: z.array(z.object({
    code: z.enum(['payroll_adjustments', 'subsidy_return', 'source_rate_snapshot_missing_or_ambiguous', 'floor_fee']),
    message: z.string(),
    repair_target: z.enum(['payroll', 'subsidy', 'case_profile']),
  })),
});

const PreviewSchema = QuerySchema.extend({
  proposed_assignments: z.array(z.object({
    assignment_id: z.number().int().positive(),
    service_dates: z.array(DateSchema),
  })),
  finance_impact: z.literal('no_op'),
  payroll_impact: z.literal('no_op'),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

const ReceiptSchema = z.object({
  case_no: z.string(),
  order_version: z.number().int(),
  scheduling_version: z.number().int(),
  generation_id: z.number().int(),
  effective_assignments: z.array(z.object({
    assignment_id: z.number().int().positive(),
    service_dates: z.array(DateSchema),
  })),
  preview_fingerprint: z.string(),
  funding_review_pending: z.boolean().default(false),
});

const AttributionPreviewSchema = z.object({
  case_no: z.string(),
  order_version: z.number().int(),
  scheduling_version: z.number().int(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  funding_review_pending: z.boolean().default(false),
  proposed_assignments: z.array(AssignmentSchema.pick({ staff_id: true, service_dates: true })),
  staff_entitlements: z.array(z.object({ staff_id: z.number().int(), amount_ntd: z.number().int() })),
  manual_amounts: z.array(z.object({ staff_id: z.number().int(), previous_calculated_ntd: z.number().int(), manual_ntd: z.number().int() })).default([]),
  funding: z.array(z.object({ staff_id: z.number().int(), kind: z.enum(['client', 'subsidy', 'unsplit']),
    before_ntd: z.number().int(), settled_ntd: z.number().int().nullable(), after_ntd: z.number().int().nullable() })).default([]),
  paid_obligations: z.array(z.object({
    staff_id: z.number().int(), before_ntd: z.number().int(), after_ntd: z.number().int(),
    paid_ntd: z.number().int(), recovery_increase_ntd: z.number().int(),
  })),
});
export type AttributionPreview = z.infer<typeof AttributionPreviewSchema>;
const FundingSourceSchema = z.object({
  staff_id: z.number().int(), kind: z.enum(['client', 'subsidy', 'unsplit']),
  amount_ntd: z.number().int(), settled_ntd: z.number().int().nullable(),
});
const FundingReviewSchema = z.discriminatedUnion('pending', [
  z.object({ pending: z.literal(false) }),
  z.object({
    pending: z.literal(true), preview_fingerprint: z.string(), subsidy_ntd: z.number().int(),
    payment_evidence_missing: z.boolean(),
    assignments: z.array(z.object({ assignment_id: z.number().int(), staff_id: z.number().int(),
      amount_ntd: z.number().int(), service_dates: z.array(DateSchema) })),
    sources: z.array(FundingSourceSchema),
    installments: z.array(FundingSourceSchema.extend({ payable_ntd: z.number().int(), recovery_ntd: z.number().int() })),
  }),
]);
export type AttributionFundingReview = Extract<z.infer<typeof FundingReviewSchema>, { pending: true }>;
export type AttributionFundingInput = { selections: { assignment_id: number; subsidy_ntd: number }[]; evidence: string };
export type AttributionMove = {
  source_assignment_id: number;
  source_date: string;
  staff_id: number;
  replacement_date: string;
  target_assignment_id: number | null;
};
export type AttributionChange = {
  source_assignment_id: number;
  staff_id: number;
  service_dates: string[];
  evidence: string;
  replacement_dates?: string[];
  scope?: 'served' | 'upcoming';
} | { moves: AttributionMove[]; evidence: string; scope: 'served' | 'upcoming' };

export type OfficialDateQuery = z.infer<typeof QuerySchema>;
export type OfficialDatePreview = z.infer<typeof PreviewSchema>;
export type OfficialDateSelection = { assignment_id: number; service_dates: string[] };

function options(headers: Record<string, string> = {}) {
  return { token: sessionClient.getToken(), headers };
}

function path(caseNo: string) {
  return `/api/v1/orders/${encodeURIComponent(caseNo)}/official-service-dates`;
}

export const officialServiceDateCorrectionClient = {
  async queryFundingReview(caseNo: string, signal: AbortSignal) {
    return decodeEnvelope(FundingReviewSchema, await transport.get(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-attribution/funding-review`, { ...options(), signal },
    ));
  },
  async previewFundingReview(caseNo: string, input: AttributionFundingInput) {
    return decodeEnvelope(FundingReviewSchema, await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-attribution/funding-review/preview`, input, options(),
    ));
  },
  async applyFundingReview(caseNo: string, input: AttributionFundingInput, fingerprint: string, key: string) {
    return decodeEnvelope(FundingReviewSchema, await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-attribution/funding-review/apply`,
      { ...input, preview_fingerprint: fingerprint }, options({ 'Idempotency-Key': key, 'X-Correlation-ID': key }),
    ));
  },
  async previewAttribution(caseNo: string, change: AttributionChange) {
    return decodeEnvelope(AttributionPreviewSchema, await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-attribution/preview`, change, options(),
    ));
  },
  async applyAttribution(caseNo: string, change: AttributionChange, preview: AttributionPreview, reason: string, key: string, adoptCalculatedAmounts = false) {
    return decodeEnvelope(ReceiptSchema, await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-attribution/apply`,
      { ...change, expected_order_version: preview.order_version, expected_scheduling_version: preview.scheduling_version,
        preview_fingerprint: preview.preview_fingerprint, reason, adopt_calculated_amounts: adoptCalculatedAmounts },
      options({ 'Idempotency-Key': key, 'X-Correlation-ID': key }),
    ));
  },
  async query(caseNo: string, request?: { signal?: AbortSignal }) {
    return decodeEnvelope(QuerySchema, await transport.get(path(caseNo), { ...options(), signal: request?.signal }));
  },
  async preview(caseNo: string, assignments: OfficialDateSelection[]) {
    for (const assignment of assignments) {
      for (const day of assignment.service_dates) {
        if (!DateSchema.safeParse(day).success) {
          throw new Error(`服務日期「${day}」不是有效日期；請返回「設定服務日期」月曆重新選取後預覽。`);
        }
      }
    }
    return decodeEnvelope(PreviewSchema, await transport.post(
      `${path(caseNo)}/preview`, { assignments }, options(),
    ));
  },
  async apply(caseNo: string, preview: OfficialDatePreview, reason: string, idempotencyKey: string) {
    return decodeEnvelope(ReceiptSchema, await transport.post(
      `${path(caseNo)}/apply`, {
        assignments: preview.proposed_assignments,
        expected_order_version: preview.order_version,
        expected_scheduling_version: preview.scheduling_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason,
      }, options({
        'Idempotency-Key': idempotencyKey,
        'X-Correlation-ID': `official-date-correction:${caseNo}:${idempotencyKey}`,
      }),
    ));
  },
};
