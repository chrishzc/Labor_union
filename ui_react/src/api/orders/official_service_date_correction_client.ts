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
    code: z.enum(['special_pay', 'payroll_adjustments', 'subsidy_return', 'source_rate_snapshot_missing_or_ambiguous', 'double_pay', 'floor_fee']),
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
});

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
