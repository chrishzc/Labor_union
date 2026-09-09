/** Strict client for operational-retention Query, Preview and Apply. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const SourceSchema = z.strictObject({
  source_id: z.string(),
  label: z.string(),
  storage_kind: z.enum(['database', 'files']),
  classification: z.enum(['eligible', 'blocked-unclassified']),
  current_logical_bytes: z.number().int().nonnegative(),
  eligible_count: z.number().int().nonnegative(),
  expired_count: z.number().int().nonnegative(),
  oldest_eligible_at_utc: z.string().datetime({ offset: true }).nullable(),
  estimated_reclaimable_bytes: z.number().int().nonnegative(),
  high_water_bytes: z.number().int().positive().nullable(),
  low_water_bytes: z.number().int().positive().nullable(),
  capacity_status: z.enum(['normal', 'high', 'unconfigured', 'unavailable']),
  blocked_reason: z.string().nullable(),
  last_run_at_utc: z.string().datetime({ offset: true }).nullable(),
  last_outcome: z.string().nullable(),
});

const DashboardSchema = z.strictObject({
  policy_revision: z.string(),
  retention_days: z.literal(30),
  sources: z.array(SourceSchema),
});

const PreviewSchema = z.strictObject({
  policy_revision: z.string(),
  source_id: z.string(),
  mode: z.enum(['expired', 'capacity']),
  reason: z.string(),
  previewed_at_utc: z.string().datetime({ offset: true }),
  cutoff_at_utc: z.string().datetime({ offset: true }),
  batch_size: z.number().int().positive(),
  candidate_count: z.number().int().nonnegative(),
  estimated_reclaimable_bytes: z.number().int().nonnegative(),
  current_logical_bytes: z.number().int().nonnegative(),
  target_low_water_bytes: z.number().int().positive().nullable(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

const ReceiptSchema = z.strictObject({
  idempotency_key: z.string(),
  source_id: z.string(),
  mode: z.enum(['expired', 'capacity']),
  policy_revision: z.string(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  outcome: z.enum(['completed', 'partial', 'capacity_unrelieved']),
  candidate_count: z.number().int().nonnegative(),
  deleted_count: z.number().int().nonnegative(),
  failed_count: z.number().int().nonnegative(),
  deleted_logical_bytes: z.number().int().nonnegative(),
  started_at_utc: z.string().datetime({ offset: true }),
  finished_at_utc: z.string().datetime({ offset: true }),
  correlation_id: z.string(),
  error_code: z.string().nullable(),
  replayed: z.boolean(),
});

export type RetentionDashboard = z.infer<typeof DashboardSchema>;
export type RetentionSource = z.infer<typeof SourceSchema>;
export type RetentionPreview = z.infer<typeof PreviewSchema>;
export type RetentionReceipt = z.infer<typeof ReceiptSchema>;
export type RetentionMode = 'expired' | 'capacity';

export interface PreviewInput {
  source_id: string;
  mode: RetentionMode;
  reason: string;
  batch_size: number;
}

function authenticatedOptions(
  options?: Omit<RequestOptions, 'method' | 'body' | 'token'>,
): Omit<RequestOptions, 'method' | 'body'> {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'RETENTION_UNAUTHENTICATED', '請先登入。');
  return { ...options, token };
}

export const operationalRetentionClient = {
  async dashboard(options?: Omit<RequestOptions, 'method' | 'body' | 'token'>): Promise<RetentionDashboard> {
    const raw = await transport.get('/api/v1/system/storage-retention', authenticatedOptions(options));
    return decodeEnvelope(DashboardSchema, raw);
  },

  async preview(
    input: PreviewInput,
    options?: Omit<RequestOptions, 'method' | 'body' | 'token'>,
  ): Promise<RetentionPreview> {
    const raw = await transport.post(
      '/api/v1/system/storage-retention/preview',
      input,
      authenticatedOptions(options),
    );
    return decodeEnvelope(PreviewSchema, raw);
  },

  async apply(
    preview: RetentionPreview,
    idempotencyKey: string,
    correlationId: string,
    options?: Omit<RequestOptions, 'method' | 'body' | 'token'>,
  ): Promise<RetentionReceipt> {
    const raw = await transport.post(
      '/api/v1/system/storage-retention/apply',
      {
        source_id: preview.source_id,
        mode: preview.mode,
        reason: preview.reason,
        batch_size: preview.batch_size,
        previewed_at_utc: preview.previewed_at_utc,
        preview_fingerprint: preview.preview_fingerprint,
        idempotency_key: idempotencyKey,
        correlation_id: correlationId,
      },
      authenticatedOptions(options),
    );
    return decodeEnvelope(ReceiptSchema, raw);
  },
};
