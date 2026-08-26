/**
 * File: controlled_file_client.ts
 * Description: 提供受控檔案 list、staging、Preview、Apply 與 authenticated download typed client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { ADMIN_SESSION_UNAUTHORIZED_EVENT, transport } from '../shared/transport';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../shared/typed_errors';

const OwnerSchema = z.enum(['contract_signing', 'scheduling', 'orders', 'staff', 'line_integration']);
const PurposeSchema = z.enum([
  'final_signed_contract', 'service_date_confirmation', 'baby_log_photo', 'meal_photo',
  'order_notice', 'staff_resume', 'staff_certificate', 'staff_health_exam', 'rich_menu_background',
]);

const OWNER_PURPOSES: Record<z.infer<typeof OwnerSchema>, ReadonlySet<z.infer<typeof PurposeSchema>>> = {
  contract_signing: new Set(['final_signed_contract']),
  scheduling: new Set(['service_date_confirmation', 'baby_log_photo', 'meal_photo']),
  orders: new Set(['order_notice']),
  staff: new Set(['staff_resume', 'staff_certificate', 'staff_health_exam']),
  line_integration: new Set(['rich_menu_background']),
};
const ZonedDateTimeSchema = z.string().datetime({ offset: true });

function requireClosedPairing(
  value: { owner: z.infer<typeof OwnerSchema>; purpose: z.infer<typeof PurposeSchema> },
  context: z.RefinementCtx,
): void {
  if (!OWNER_PURPOSES[value.owner].has(value.purpose)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['purpose'],
      message: 'controlled-file owner/purpose pairing is invalid',
    });
  }
}

const fileShape = {
  file_id: z.string().regex(/^cf_[0-9a-f]{32}$/),
  owner: OwnerSchema,
  purpose: PurposeSchema,
  subject_reference: z.string(),
  filename: z.string(),
  logical_folder: z.string(),
  version: z.number().int().positive(),
  mime_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  status: z.string(),
  applied_at: ZonedDateTimeSchema,
};
const FileSchema = z.strictObject(fileShape).superRefine(requireClosedPairing);

const StagingSchema = z.strictObject({
  staging_id: z.string().regex(/^cfs_[0-9a-f]{32}$/),
  filename: z.string(),
  mime_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  sha256_digest: z.string().regex(/^[0-9a-f]{64}$/),
  expires_at: ZonedDateTimeSchema,
});

const CandidateSchema = z.strictObject({
  staging_id: z.string().regex(/^cfs_[0-9a-f]{32}$/),
  staging_version: z.number().int().positive(),
  owner: OwnerSchema,
  purpose: PurposeSchema,
  subject_reference: z.string(),
  object_key: z.string(),
  logical_folder: z.string(),
  filename: z.string(),
  mime_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  sha256_digest: z.string().regex(/^[0-9a-f]{64}$/),
  expires_at: ZonedDateTimeSchema,
}).superRefine(requireClosedPairing);

const PreviewSchema = z.strictObject({
  candidate: CandidateSchema,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  expected_staging_version: z.number().int().positive(),
  blockers: z.array(z.string()),
});

const ReceiptSchema = z.strictObject({
  ...fileShape,
  receipt_id: z.string().regex(/^cfr_[0-9a-f]{32}$/),
  outcome: z.enum(['created', 'replayed']),
  receipt_type: z.literal('controlled_file_apply'),
  schema_version: z.literal('controlled-file-apply-receipt.v1'),
  sha256_digest: z.string().regex(/^[0-9a-f]{64}$/),
}).superRefine(requireClosedPairing);

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({
    success: z.literal(true),
    message: z.string(),
    data,
    error: z.null(),
  });
}

const GlobalTypedErrorResponseSchema = z.strictObject({
  detail: z.strictObject({
    error: z.strictObject({
      category: z.enum([
        'validation', 'forbidden', 'not_found', 'domain_blocked', 'conflict',
        'idempotency_mismatch', 'unavailable', 'internal',
      ]),
      code: z.string(),
      message: z.string(),
      field_errors: z.array(z.strictObject({
        field: z.string(),
        code: z.string(),
        message: z.string(),
      })),
      domain_blockers: z.array(z.string()),
      retryable: z.boolean(),
      correlation_id: z.string(),
      current_version: z.number().int().nullable(),
    }),
  }),
});

export type ControlledFileOwner = z.infer<typeof OwnerSchema>;
export type ControlledFilePurpose = z.infer<typeof PurposeSchema>;
export type ControlledFileView = z.infer<typeof FileSchema>;
export type ControlledFileReceipt = z.infer<typeof ReceiptSchema>;

export interface ControlledFileIntent {
  staging_id: string;
  owner: ControlledFileOwner;
  purpose: ControlledFilePurpose;
  subject_reference: string;
  object_key: string;
  logical_folder: string;
}

function authToken(): string {
  const token = sessionClient.getToken();
  if (!token) throw new Error('缺少有效的管理員 Session');
  return token;
}

function commandId(prefix: string): string {
  const uuid = crypto.randomUUID().replaceAll('-', '').toLowerCase();
  return `${prefix}:${uuid}`;
}

export async function listControlledFiles(): Promise<ControlledFileView[]> {
  const raw = await transport.get<unknown>('/api/v1/storage/files', { token: authToken() });
  return envelope(z.strictObject({ items: z.array(FileSchema) })).parse(raw).data.items;
}

export async function stageControlledFile(
  file: File,
  metadata: Omit<ControlledFileIntent, 'staging_id'>,
): Promise<z.infer<typeof StagingSchema>> {
  const form = new FormData();
  form.set('document', file);
  form.set('owner', metadata.owner);
  form.set('purpose', metadata.purpose);
  form.set('subject_reference', metadata.subject_reference);
  form.set('object_key', metadata.object_key);
  form.set('logical_folder', metadata.logical_folder);
  const raw = await transport.post<unknown>('/api/v1/storage/staging', form, {
    token: authToken(),
    headers: {
      'Idempotency-Key': commandId('controlled-file.stage'),
      'X-Correlation-ID': commandId('controlled-file-stage'),
    },
  });
  return envelope(StagingSchema).parse(raw).data;
}

export async function previewControlledFile(intent: ControlledFileIntent) {
  const raw = await transport.post<unknown>('/api/v1/storage/files/preview', intent, {
    token: authToken(),
    headers: { 'X-Correlation-ID': commandId('controlled-file-preview') },
  });
  return envelope(PreviewSchema).parse(raw).data;
}

export async function applyControlledFile(intent: ControlledFileIntent, preview: z.infer<typeof PreviewSchema>) {
  const raw = await transport.post<unknown>('/api/v1/storage/files/apply', {
    ...intent,
    expected_staging_version: preview.expected_staging_version,
    preview_fingerprint: preview.preview_fingerprint,
  }, {
    token: authToken(),
    headers: {
      'Idempotency-Key': commandId('controlled-file.apply'),
      'X-Correlation-ID': commandId('controlled-file-apply'),
    },
  });
  return envelope(ReceiptSchema).parse(raw).data;
}

export async function downloadControlledFile(
  file: ControlledFileView,
  timeoutMs = 10000,
): Promise<void> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new RangeError('timeoutMs must be positive');
  const token = authToken();
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const response = await fetch(`/api/v1/storage/files/${encodeURIComponent(file.file_id)}/download`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as unknown;
      if (response.status === 401) {
        window.dispatchEvent(new CustomEvent(ADMIN_SESSION_UNAUTHORIZED_EVENT, {
          detail: { rejectedToken: token },
        }));
      }
      const decoded = GlobalTypedErrorResponseSchema.safeParse(payload);
      const error = decoded.success ? decoded.data.detail.error : null;
      throw new ApiHttpError(
        response.status,
        error?.code ?? `HTTP_${response.status}`,
        error?.message ?? `檔案下載失敗 (${response.status})`,
        error?.retryable ?? [502, 503, 504].includes(response.status),
        payload,
      );
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement('a');
      link.href = url;
      link.download = file.filename;
      link.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  } catch (error) {
    if (error instanceof ApiHttpError) throw error;
    if (timedOut) throw new ApiTimeoutError(timeoutMs);
    throw new ApiNetworkError(error instanceof Error ? error.message : '檔案下載失敗', error);
  } finally {
    window.clearTimeout(timer);
  }
}
