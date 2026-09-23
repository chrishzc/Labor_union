import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

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
  monetary_change_blocker: z.boolean(),
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
  async query(caseNo: string) {
    return decodeEnvelope(QuerySchema, await transport.get(path(caseNo), options()));
  },
  async preview(caseNo: string, assignments: OfficialDateSelection[]) {
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
