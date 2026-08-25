/**
 * File: assignment_plan_mutation_client.ts
 * Description: 嚴格處理正式排班 Preview、durable Apply 與 terminal outcome。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const SegmentInputSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  assigned_start_date: IsoDateSchema,
  assigned_end_date: IsoDateSchema,
  official_service_dates: z.array(IsoDateSchema).min(1),
});
const PreviewAssignmentSchema = SegmentInputSchema.extend({
  assignment_id: z.number().int().positive().nullable(),
  candidate_key: z.string().nullable(),
  sequence: z.number().int().positive(),
  actual_hours: z.number().int().nonnegative().nullable(),
  lineage_source_assignment_ids: z.array(z.number().int().positive()),
});
const PreviewSchema = z.object({
  case_no: z.string().min(1).max(50),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  cancelled_assignment_ids: z.array(z.number().int().positive()),
  assignments: z.array(PreviewAssignmentSchema).min(1).max(4),
  buffers: z.array(z.record(z.string(), z.unknown())),
  client_finance_impact: z.record(z.string(), z.unknown()),
  payroll_impact: z.record(z.string(), z.unknown()),
  orders_impact: z.record(z.string(), z.unknown()),
  preview_fingerprint: FingerprintSchema,
}).strict();
const AcceptedSchema = z.strictObject({ job_id: z.string().min(1).max(191), status_url: z.string().min(1) });
const FailureSchema = z.strictObject({
  kind: z.literal('failure'), schema_version: z.literal(1),
  error: z.strictObject({
    category: z.enum(['validation', 'conflict', 'domain_blocked', 'idempotency_mismatch', 'unavailable', 'internal']),
    code: z.string().min(1), message: z.string().min(1), retryable: z.boolean(),
    correlation_id: z.string().nullable(), domain_blockers: z.array(z.string()),
  }),
});
const SuccessSchema = z.strictObject({ kind: z.literal('success'), schema_version: z.literal(1), result_reference: z.string().min(1) });
const JobSchema = z.strictObject({
  job_id: z.string().min(1), status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']),
  command_type: z.literal('assignment_plan_apply'), attempt_count: z.number().int().nonnegative(),
  max_attempts: z.number().int().nonnegative(), outcome: z.union([SuccessSchema, FailureSchema]).nullable(),
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.object({ success: z.boolean(), message: z.string(), data: schema.nullable(), error: z.string().nullable().optional() }).passthrough();

export type AssignmentPlanSegmentInput = z.infer<typeof SegmentInputSchema>;
export type AssignmentPlanPreview = z.infer<typeof PreviewSchema>;
export type AssignmentPlanJob = z.infer<typeof JobSchema>;

function options(idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const headers: Record<string, string> = { 'X-Correlation-ID': `assignment-plan-${crypto.randomUUID()}` };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const parsed = envelope(schema).safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(`正式排班${operation}回應結構異常。`, parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
  if (!parsed.data.success || parsed.data.data === null) throw new ApiHttpError(422, 'ASSIGNMENT_PLAN_EMPTY_RESPONSE', parsed.data.error ?? parsed.data.message, false, raw);
  return parsed.data.data as T;
}

export const assignmentPlanMutationClient = {
  async preview(caseNo: string, segments: AssignmentPlanSegmentInput[]): Promise<AssignmentPlanPreview> {
    const raw = await transport.post<unknown>(`/api/v1/orders/${encodeURIComponent(caseNo)}/assignment-plan/preview`, { segments: SegmentInputSchema.array().min(1).max(4).parse(segments) }, options());
    const result = decode(PreviewSchema, raw, 'Preview');
    if (result.case_no !== caseNo) throw new ApiDecodeError('正式排班 Preview 案件 identity 不一致。');
    return result;
  },
  async apply(caseNo: string, segments: AssignmentPlanSegmentInput[], preview: AssignmentPlanPreview, reason: string): Promise<{ job_id: string; status_url: string }> {
    const raw = await transport.post<unknown>(`/api/v1/orders/${encodeURIComponent(caseNo)}/assignment-plan/apply`, {
      segments,
      expected_order_version: preview.order_version,
      expected_scheduling_version: preview.scheduling_version,
      expected_client_finance_version: preview.client_finance_version,
      expected_payroll_version: preview.payroll_version,
      preview_fingerprint: preview.preview_fingerprint,
      reason: reason.trim(),
    }, options(`assignment-plan-${caseNo}-${crypto.randomUUID()}`));
    return decode(AcceptedSchema, raw, 'Apply');
  },
  async queryJob(jobId: string): Promise<AssignmentPlanJob> {
    const raw = await transport.get<unknown>(`/api/v1/jobs/${encodeURIComponent(jobId)}`, options());
    const result = decode(JobSchema, raw, '工作結果');
    if (result.job_id !== jobId) throw new ApiDecodeError('正式排班 Job identity 不一致。');
    return result;
  },
};
