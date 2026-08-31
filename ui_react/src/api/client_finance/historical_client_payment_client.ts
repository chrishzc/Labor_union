/** Strict Client Finance client for pre-system historical payment evidence. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const ObligationSchema = z.strictObject({
  obligation_identity: z.string().min(1), case_no: z.string().min(1), obligation_type: z.string().min(1),
  direction: z.enum(['receivable_from_client', 'payable_to_client']), amount_due_ntd: z.number().int().positive(),
  projection_version: z.number().int().nonnegative(), status: z.enum(['open', 'settled', 'cancelled']),
});
const QuerySchema = z.strictObject({
  case_no: z.string().min(1), account_version: z.number().int().nonnegative(), adoption_receipt_id: z.number().int().positive().nullable(),
  adopted: z.boolean(), normal_bank_candidate_identities: z.array(z.string().min(1)), obligations: z.array(ObligationSchema),
});
const PreviewSchema = z.strictObject({
  case_no: z.string().min(1), account_version: z.number().int().nonnegative(), adoption_receipt_id: z.number().int().positive().nullable(),
  obligations: z.array(ObligationSchema), amount_snapshot_ntd: z.number().int().nonnegative(), blockers: z.array(z.string()),
  can_apply: z.boolean(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const ReceiptSchema = z.strictObject({
  event_identity: z.string().min(1), case_no: z.string().min(1), obligation_identities: z.array(z.string().min(1)),
  amount_snapshot_ntd: z.number().int().positive(), resulting_account_version: z.number().int().positive(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const ProjectionSchema = z.strictObject({
  obligation_identity: z.string().min(1), amount_snapshot_ntd: z.number().int().positive(), obligation_projection_version: z.number().int().nonnegative(),
});
const ReadbackSchema = z.strictObject({
  case_no: z.string().min(1), account_version: z.number().int().nonnegative(), obligations: z.array(ObligationSchema),
  projections: z.array(ProjectionSchema), owner_terminal: z.boolean(),
});
const response = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.string().nullable().optional() });

export type HistoricalClientPaymentQuery = z.infer<typeof QuerySchema>;
export type HistoricalClientPaymentPreview = z.infer<typeof PreviewSchema>;
export type HistoricalClientPaymentReadback = z.infer<typeof ReadbackSchema>;
export type HistoricalClientPaymentIntent = {
  case_no: string; direction: 'receivable_from_client' | 'payable_to_client'; confirmation_kind: 'paid' | 'settled';
  obligation_identities: string[]; payment_date: string | null; payment_date_unknown_reason: string | null;
  source_availability: 'missing' | 'ambiguous' | 'unrecoverable'; evidence_reference: string | null;
};
export type HistoricalClientPaymentOptions = { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string };

export class HistoricalClientPaymentClientError extends Error {
  public readonly code: string;
  public readonly status?: number;
  public readonly retryable: boolean;
  constructor(code: string, message: string, status?: number, retryable = false) {
    super(message); this.code = code; this.status = status; this.retryable = retryable;
  }
}

function requestOptions(input: HistoricalClientPaymentOptions = {}, headers: Record<string, string> = {}): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new HistoricalClientPaymentClientError('HISTORICAL_CLIENT_UNAUTHENTICATED', '請先登入。', 401);
  return { ...input, token, headers, timeoutMs: input.timeoutMs ?? 30_000 };
}
function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  try { return decodePayload(response(schema), raw).data; }
  catch { throw new HistoricalClientPaymentClientError('HISTORICAL_CLIENT_SCHEMA_MISMATCH', '回應不符合 Client Finance strict 契約。'); }
}
function mapped(error: unknown): never {
  if (error instanceof HistoricalClientPaymentClientError) throw error;
  if (error instanceof ApiHttpError) throw new HistoricalClientPaymentClientError(error.code, error.message, error.status, error.retryable);
  throw new HistoricalClientPaymentClientError('HISTORICAL_CLIENT_OUTCOME_UNKNOWN', error instanceof Error ? error.message : '結果目前無法確認。', undefined, true);
}

export const historicalClientPaymentClient = {
  async query(caseNo: string, options: HistoricalClientPaymentOptions = {}): Promise<HistoricalClientPaymentQuery> {
    try { return decode(QuerySchema, await transport.get<unknown>(`/api/v1/client-payments/historical-payments/${encodeURIComponent(caseNo)}`, requestOptions(options))); }
    catch (error) { return mapped(error); }
  },
  async preview(intent: HistoricalClientPaymentIntent, options: HistoricalClientPaymentOptions = {}): Promise<HistoricalClientPaymentPreview> {
    try { return decode(PreviewSchema, await transport.post<unknown>('/api/v1/client-payments/historical-payments/preview', intent, requestOptions(options))); }
    catch (error) { return mapped(error); }
  },
  async apply(intent: HistoricalClientPaymentIntent, preview: HistoricalClientPaymentPreview, reason: string, idempotencyKey: string, options: HistoricalClientPaymentOptions = {}) {
    try {
      return decode(ReceiptSchema, await transport.post<unknown>('/api/v1/client-payments/historical-payments/apply', {
        ...intent, expected_account_version: preview.account_version, expected_adoption_receipt_id: preview.adoption_receipt_id,
        preview_fingerprint: preview.preview_fingerprint, reason,
      }, requestOptions(options, { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': `historical-client-${crypto.randomUUID()}` })));
    } catch (error) { return mapped(error); }
  },
  async readback(caseNo: string, options: HistoricalClientPaymentOptions = {}): Promise<HistoricalClientPaymentReadback> {
    try { return decode(ReadbackSchema, await transport.get<unknown>(`/api/v1/client-payments/historical-payments/${encodeURIComponent(caseNo)}/readback`, requestOptions(options))); }
    catch (error) { return mapped(error); }
  },
};
