/**
 * Typed client for repairing incomplete Orders intake data and finalizing it back to normal flow.
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const VersionSchema = z.number().int().nonnegative();
const MissingFieldSchema = z.enum(['client_name', 'start_date', 'service_days']);
const ChangedTermSchema = z.enum(['start_date', 'service_days']);

const TermsPreviewSchema = z.strictObject({
  case_no: z.string().min(1),
  lifecycle_version: VersionSchema,
  before_start_date: DateSchema.nullable(),
  before_service_days: z.number().int().nonnegative().nullable(),
  after_start_date: DateSchema,
  after_service_days: z.number().int().positive(),
  changed_fields: z.array(ChangedTermSchema),
  blockers: z.array(z.string().min(1)),
  apply_allowed: z.boolean(),
  preview_fingerprint: FingerprintSchema,
});

const TermsReceiptSchema = z.strictObject({
  receipt_key: z.string().min(1),
  case_no: z.string().min(1),
  lifecycle_version: VersionSchema,
  start_date: DateSchema,
  service_days: z.number().int().positive(),
  changed_fields: z.array(ChangedTermSchema),
  preview_fingerprint: FingerprintSchema,
  replayed: z.boolean(),
});

const ClientNamePreviewSchema = z.strictObject({
  case_no: z.string().min(1),
  lifecycle_version: VersionSchema,
  before_client_name: z.string().nullable(),
  after_client_name: z.string().min(1),
  blockers: z.array(z.string().min(1)),
  apply_allowed: z.boolean(),
  preview_fingerprint: FingerprintSchema,
});

const ClientNameReceiptSchema = z.strictObject({
  receipt_key: z.string().min(1),
  case_no: z.string().min(1),
  lifecycle_version: VersionSchema,
  client_name: z.string().min(1),
  preview_fingerprint: FingerprintSchema,
  replayed: z.boolean(),
});

const CompletionPreviewSchema = z.strictObject({
  case_no: z.string().min(1),
  lifecycle_version: VersionSchema,
  current_status: z.string().min(1),
  target_status: z.string().min(1),
  missing_fields: z.array(MissingFieldSchema),
  blockers: z.array(z.string().min(1)),
  apply_allowed: z.boolean(),
  preview_fingerprint: FingerprintSchema,
});

const CompletionReceiptSchema = z.strictObject({
  receipt_key: z.string().min(1),
  case_no: z.string().min(1),
  lifecycle_version: VersionSchema,
  status: z.string().min(1),
  preview_fingerprint: FingerprintSchema,
  replayed: z.boolean(),
});

const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema,
  error: z.string().nullable(),
});

export type IntakeTermsPreview = z.infer<typeof TermsPreviewSchema>;
export type IntakeTermsReceipt = z.infer<typeof TermsReceiptSchema>;
export type IntakeClientNamePreview = z.infer<typeof ClientNamePreviewSchema>;
export type IntakeClientNameReceipt = z.infer<typeof ClientNameReceiptSchema>;
export type IntakeCompletionPreview = z.infer<typeof CompletionPreviewSchema>;
export type IntakeCompletionReceipt = z.infer<typeof CompletionReceiptSchema>;
export type IntakeMissingField = z.infer<typeof MissingFieldSchema>;

export interface IntakeRequestOptions {
  signal?: AbortSignal;
  correlationId?: string;
  timeoutMs?: number;
}

function canonicalCaseNo(caseNo: string): string {
  const value = caseNo.trim();
  if (!value || value.length > 50) throw new Error('案件編號必須為 1 至 50 字元。');
  return value;
}

function requestOptions(
  source?: IntakeRequestOptions,
  requiredHeaders?: Record<string, string>,
): RequestOptions {
  const token = sessionClient.getToken();
  return {
    signal: source?.signal,
    timeoutMs: source?.timeoutMs,
    ...(token ? { token } : {}),
    headers: { ...requiredHeaders },
  };
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  const result = decodePayload(envelope(schema), raw);
  if (!result.success) {
    throw new ApiHttpError(
      400,
      'ORDER_INTAKE_REPAIR_BUSINESS_ERROR',
      result.error ?? result.message,
      false,
      raw,
    );
  }
  return result.data;
}

function headers(
  caseNo: string,
  operation: string,
  source?: IntakeRequestOptions,
  idempotencyKey?: string,
): Record<string, string> {
  const correlation = source?.correlationId
    ?? `orders-intake-${operation}-${caseNo}-${Date.now()}`;
  return {
    'X-Correlation-ID': correlation,
    ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
  };
}

function commandKey(value: string): string {
  const key = value.trim();
  if (!key || key.length > 191) throw new Error('補件操作識別無效。');
  return key;
}

export const orderIntakeCompletionClient = {
  async previewTerms(
    caseNo: string,
    proposedStartDate: string,
    proposedServiceDays: number,
    source?: IntakeRequestOptions,
  ): Promise<IntakeTermsPreview> {
    const canonical = canonicalCaseNo(caseNo);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/intake-terms-bootstrap/preview`;
    return decode(
      TermsPreviewSchema,
      await transport.post(
        endpoint,
        {
          proposed_start_date: DateSchema.parse(proposedStartDate),
          proposed_service_days: z.number().int().positive().parse(proposedServiceDays),
        },
        requestOptions(source, headers(canonical, 'terms-preview', source)),
      ),
    );
  },

  async applyTerms(
    caseNo: string,
    preview: IntakeTermsPreview,
    reason: string,
    idempotencyKey: string,
    source?: IntakeRequestOptions,
  ): Promise<IntakeTermsReceipt> {
    const canonical = canonicalCaseNo(caseNo);
    const key = commandKey(idempotencyKey);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/intake-terms-bootstrap/apply`;
    return decode(
      TermsReceiptSchema,
      await transport.post(
        endpoint,
        {
          proposed_start_date: preview.after_start_date,
          proposed_service_days: preview.after_service_days,
          expected_lifecycle_version: preview.lifecycle_version,
          preview_fingerprint: preview.preview_fingerprint,
          reason: z.string().trim().min(1).max(500).parse(reason),
        },
        requestOptions(source, headers(canonical, 'terms-apply', source, key)),
      ),
    );
  },

  async previewClientName(
    caseNo: string,
    clientName: string,
    source?: IntakeRequestOptions,
  ): Promise<IntakeClientNamePreview> {
    const canonical = canonicalCaseNo(caseNo);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/intake-completion/client-name/preview`;
    return decode(
      ClientNamePreviewSchema,
      await transport.post(
        endpoint,
        { client_name: z.string().trim().min(1).max(100).parse(clientName) },
        requestOptions(source, headers(canonical, 'client-name-preview', source)),
      ),
    );
  },

  async applyClientName(
    caseNo: string,
    preview: IntakeClientNamePreview,
    reason: string,
    idempotencyKey: string,
    source?: IntakeRequestOptions,
  ): Promise<IntakeClientNameReceipt> {
    const canonical = canonicalCaseNo(caseNo);
    const key = commandKey(idempotencyKey);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/intake-completion/client-name/apply`;
    return decode(
      ClientNameReceiptSchema,
      await transport.post(
        endpoint,
        {
          client_name: preview.after_client_name,
          expected_lifecycle_version: preview.lifecycle_version,
          preview_fingerprint: preview.preview_fingerprint,
          reason: z.string().trim().min(1).max(500).parse(reason),
        },
        requestOptions(source, headers(canonical, 'client-name-apply', source, key)),
      ),
    );
  },

  async previewCompletion(
    caseNo: string,
    source?: IntakeRequestOptions,
  ): Promise<IntakeCompletionPreview> {
    const canonical = canonicalCaseNo(caseNo);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/intake-completion/preview`;
    return decode(
      CompletionPreviewSchema,
      await transport.post(
        endpoint,
        undefined,
        requestOptions(source, headers(canonical, 'completion-preview', source)),
      ),
    );
  },

  async applyCompletion(
    caseNo: string,
    preview: IntakeCompletionPreview,
    reason: string,
    idempotencyKey: string,
    source?: IntakeRequestOptions,
  ): Promise<IntakeCompletionReceipt> {
    const canonical = canonicalCaseNo(caseNo);
    const key = commandKey(idempotencyKey);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/intake-completion/apply`;
    return decode(
      CompletionReceiptSchema,
      await transport.post(
        endpoint,
        {
          expected_lifecycle_version: preview.lifecycle_version,
          preview_fingerprint: preview.preview_fingerprint,
          reason: z.string().trim().min(1).max(500).parse(reason),
        },
        requestOptions(source, headers(canonical, 'completion-apply', source, key)),
      ),
    );
  },
};

const blockerMessages: Record<string, string> = {
  order_intake_client_name_status_not_eligible: '案件已不在待補件狀態，不能使用姓名補件入口。',
  order_intake_client_name_already_set: '客戶姓名已存在；此入口只允許補齊缺失姓名。',
  order_intake_terms_bootstrap_service_data_locked: '服務資料已鎖定，不能再補改服務日期或天數。',
  order_intake_completion_service_data_locked: '服務資料已鎖定，目前不能完成進件補齊。',
  order_intake_terms_bootstrap_actual_start_exists: '案件已有實際開工日，不能使用進件補件流程。',
  order_intake_completion_actual_start_exists: '案件已有實際開工日，不能恢復為洽談中。',
  order_intake_terms_bootstrap_client_finance_exists: '客戶帳務資料已形成，不能使用進件補件流程。',
  order_intake_completion_client_finance_exists: '客戶帳務資料已形成，不能完成進件補齊。',
  order_intake_terms_bootstrap_payroll_exists: '薪資資料已形成，不能使用進件補件流程。',
  order_intake_completion_payroll_exists: '薪資資料已形成，不能完成進件補齊。',
  order_intake_terms_bootstrap_scheduling_not_pristine: '正式排班或指派資料已形成，不能使用進件補件流程。',
  order_intake_completion_scheduling_not_pristine: '正式排班或指派資料已形成，不能完成進件補齊。',
  order_intake_terms_bootstrap_status_not_eligible: '案件已不在待補件狀態，請重新載入。',
  order_intake_completion_status_not_eligible: '案件已不在待補件狀態，請重新載入。',
};

function domainBlockers(error: ApiHttpError): string[] {
  const raw = error.raw;
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return [];
  const detail = Reflect.get(raw, 'detail');
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) return [];
  const typed = Reflect.get(detail, 'error');
  if (typeof typed !== 'object' || typed === null || Array.isArray(typed)) return [];
  const blockers = Reflect.get(typed, 'domain_blockers');
  return Array.isArray(blockers)
    ? blockers.filter((value): value is string => typeof value === 'string')
    : [];
}

export function intakeRepairErrorMessage(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.code.includes('stale_preview')) {
      return '訂單資料版本已變更，請重新檢查缺件後再套用。';
    }
    if (error.status === 422) {
      return '補件資料不合法，請確認日期、服務天數、姓名與必填原因。';
    }
    const blockers = domainBlockers(error);
    if (blockers.length > 0) {
      return blockers.map((code) => blockerMessages[code] ?? code).join('；');
    }
  }
  return error instanceof Error ? error.message : '補件操作失敗，請重新載入後再試。';
}

export function intakeBlockerMessage(code: string): string {
  return blockerMessages[code] ?? code;
}
