import { z } from 'zod';

import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';

const IntentSchema = z.strictObject({
  client_payment_policy_version: z.string().min(1),
  client_hourly_rate_ntd: z.number().int().positive(),
  deposit_service_days: z.number().int().nonnegative(),
  deposit_due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  first_payment_due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  payroll_policy_version: z.string().min(1),
});

const StatusSchema = z.strictObject({
  case_no: z.string().min(1),
  ready: z.boolean(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  service_time_complete: z.boolean(),
  recommendation: IntentSchema.nullable(),
  domain_blockers: z.array(z.string()),
});

const PreviewSchema = IntentSchema.extend({
  case_no: z.string().min(1),
  order_version: z.number().int().nonnegative(),
  source_identity_status: z.string().min(1),
  payroll_policy_kind: z.string().min(1),
  payroll_hourly_rate_ntd: z.number().int().positive(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  mutation: z.enum(['create', 'create_with_existing_scheduling', 'keep_existing']),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

const ReceiptSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  bootstrap_created: z.boolean(),
  bootstrap_event_id: z.number().int().positive(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

const response = <T extends z.ZodTypeAny>(data: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: data.nullable(),
  error: z.string().nullable(),
});

const StatusResponseSchema = response(StatusSchema);
const PreviewResponseSchema = response(PreviewSchema);
const ReceiptResponseSchema = response(ReceiptSchema);

export type CaseArchitectureBootstrapIntent = z.infer<typeof IntentSchema>;
export type CaseArchitectureBootstrapStatus = z.infer<typeof StatusSchema>;
export type CaseArchitectureBootstrapPreview = z.infer<typeof PreviewSchema>;
export type CaseArchitectureBootstrapReceipt = z.infer<typeof ReceiptSchema>;

const token = () => {
  const value = sessionClient.getToken();
  if (!value) throw new Error('請先登入管理後台。');
  return value;
};

const decode = <T>(
  schema: { safeParse(value: unknown): { success: true; data: { data: T | null } } | { success: false; error: { issues: readonly { path: PropertyKey[]; message: string; code: string }[] } } },
  raw: unknown,
  message: string,
): T => {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(message, parsed.error.issues.map((issue) => ({
      path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code,
    })), raw);
  }
  if (parsed.data.data === null) throw new ApiDecodeError(`${message}：缺少資料本體。`, [], raw);
  return parsed.data.data;
};

const identity = (scope: string) => `${scope}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
const path = (caseNo: string, operation: string) => `/api/v1/cases/${encodeURIComponent(caseNo)}/architecture-bootstrap/${operation}`;

export const caseArchitectureBootstrapClient = {
  async status(caseNo: string): Promise<CaseArchitectureBootstrapStatus> {
    const raw = await transport.get(path(caseNo, 'status'), { token: token() });
    return decode(StatusResponseSchema, raw, '案件初始資料狀態回應結構異常');
  },

  async preview(caseNo: string, intent: CaseArchitectureBootstrapIntent): Promise<CaseArchitectureBootstrapPreview> {
    const raw = await transport.post(path(caseNo, 'preview'), intent, {
      token: token(), headers: { 'X-Correlation-ID': identity('case-bootstrap-preview') },
    });
    return decode(PreviewResponseSchema, raw, '案件初始資料預覽回應結構異常');
  },

  async apply(
    caseNo: string,
    intent: CaseArchitectureBootstrapIntent,
    preview: CaseArchitectureBootstrapPreview,
    reason: string,
    idempotencyKey: string,
  ): Promise<CaseArchitectureBootstrapReceipt> {
    const raw = await transport.post(path(caseNo, 'apply'), {
      ...intent,
      expected_order_version: preview.order_version,
      preview_fingerprint: preview.preview_fingerprint,
      reason,
    }, {
      token: token(),
      headers: {
        'Idempotency-Key': idempotencyKey,
        'X-Correlation-ID': identity('case-bootstrap-apply'),
      },
    });
    return decode(ReceiptResponseSchema, raw, '案件初始資料收據回應結構異常');
  },
};
