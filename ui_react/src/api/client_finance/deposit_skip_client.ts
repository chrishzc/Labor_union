import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const fingerprint = z.string().regex(/^[0-9a-f]{64}$/);
const PreviewSchema = z.strictObject({
  case_no: z.string().min(1),
  expected_account_version: z.number().int().nonnegative(),
  resulting_account_version: z.number().int().nonnegative(),
  deposit_required_ntd: z.number().int().nonnegative(),
  deposit_net_received_ntd: z.number().int().nonnegative(),
  unpaid_progression_allowed: z.boolean(),
  mutates: z.boolean(),
  blockers: z.array(z.string()),
  preview_fingerprint: fingerprint,
});
const ReceiptSchema = z.strictObject({
  case_no: z.string().min(1),
  account_version: z.number().int().nonnegative(),
  unpaid_progression_allowed: z.boolean(),
  replayed: z.boolean(),
});
const envelope = <T extends z.ZodTypeAny>(data: T) => z.object({
  success: z.boolean(), message: z.string(), data: data.nullable(), error: z.string().nullable().optional(),
}).passthrough();

export type DepositSkipPreview = z.infer<typeof PreviewSchema>;

function options(idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const headers: Record<string, string> = { 'X-Correlation-ID': `deposit-skip-${crypto.randomUUID()}` };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const parsed = envelope(schema).safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(`手動跳過訂金 ${operation} 回應結構異常。`, parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
  if (!parsed.data.success || parsed.data.data === null) throw new ApiHttpError(422, 'DEPOSIT_SKIP_EMPTY_RESPONSE', parsed.data.error ?? parsed.data.message, false, raw);
  return parsed.data.data as T;
}

export const depositSkipClient = {
  async preview(caseNo: string): Promise<DepositSkipPreview> {
    const raw = await transport.post<unknown>(`/api/v1/orders/${encodeURIComponent(caseNo)}/client-finance/deposit-skip/preview`, undefined, options());
    return decode(PreviewSchema, raw, '預覽');
  },
  async apply(caseNo: string, preview: DepositSkipPreview, reason: string): Promise<z.infer<typeof ReceiptSchema>> {
    const raw = await transport.post<unknown>(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/client-finance/deposit-skip/apply`,
      { expected_account_version: preview.expected_account_version, preview_fingerprint: preview.preview_fingerprint, reason },
      options(`deposit-skip-${caseNo}-${crypto.randomUUID()}`),
    );
    return decode(ReceiptSchema, raw, '套用');
  },
};
