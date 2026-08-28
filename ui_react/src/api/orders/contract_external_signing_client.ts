/**
 * File: contract_external_signing_client.ts
 * Description: 嚴格解碼外部簽約 successor Query、PDF、完成回報、最終文件 Preview／Apply 與 readback。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { ADMIN_SESSION_UNAUTHORIZED_EVENT, transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const SessionIdSchema = z.string().regex(/^ces_[0-9a-f]{32}$/);
const ReceiptIdSchema = z.string().regex(/^cesr_[0-9a-f]{32}$/);
const StagingIdSchema = z.string().regex(/^cfs_[0-9a-f]{32}$/);
const PreviewTokenSchema = z.string().regex(/^cp_[A-Za-z0-9_-]{43}$/);
const FinalDocumentIdSchema = z.string().regex(/^cfd_[0-9a-f]{32}$/);
const ControlledFileIdSchema = z.string().regex(/^cf_[0-9a-f]{32}$/);
const PdfMimeSchema = z.literal('application/pdf');
const ZonedTimeSchema = z.string().datetime({ offset: true });
const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const ExternalSigningConfirmationMethodSchema = z.enum(['phone', 'paper', 'in_person', 'verified_other']);

export const ExternalSigningStateSchema = z.enum([
  'staff_reporting',
  'staff_reports_complete',
  'client_reported_final_pdf_pending',
  'completed',
  'superseded',
]);

const UnsignedDocumentSchema = z.strictObject({
  document_version_id: z.number().int().positive(),
  filename: z.string().min(1).max(255),
  mime_type: PdfMimeSchema,
  size_bytes: z.number().int().positive(),
});

const StaffTargetSchema = z.strictObject({
  matching_segment_id: z.number().int().positive(),
  staff_subject_reference: z.string().min(1).max(191),
  document_version_id: z.number().int().positive(),
  reported: z.boolean(),
});

const ClientTargetSchema = z.strictObject({
  client_subject_reference: z.string().min(1).max(191),
  document_version_id: z.number().int().positive(),
  reported: z.boolean(),
});

const LegacyRecoveryTargetSchema = z.strictObject({
  scope: z.enum(['staff', 'client']),
  matching_segment_id: z.number().int().positive().nullable(),
  target_subject_reference: z.string().min(1).max(191),
  current_document_version_id: z.number().int().positive(),
  reported: z.boolean(),
  legacy_document_version_id: z.number().int().positive().nullable(),
  signing_event_id: z.number().int().positive().nullable(),
  command_receipt_id: z.number().int().positive().nullable(),
  legacy_media_sha256: Sha256Schema.nullable(),
}).superRefine((value, context) => {
  if ((value.scope === 'staff') !== (value.matching_segment_id !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['matching_segment_id'], message: 'recovery target scope is invalid' });
  }
  const legacyValues = [
    value.legacy_document_version_id,
    value.signing_event_id,
    value.command_receipt_id,
    value.legacy_media_sha256,
  ];
  if (legacyValues.some((item) => item !== null) && !legacyValues.every((item) => item !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['legacy_document_version_id'], message: 'legacy recovery lineage must be complete' });
  }
});

export const LegacyRecoveryQuerySchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  session_id: SessionIdSchema,
  matching_plan_id: z.number().int().positive(),
  current_document_set_sha256: Sha256Schema,
  commitment_id: z.number().int().positive().nullable(),
  state: z.enum(['staff_reporting', 'staff_reports_complete', 'client_reported_final_pdf_pending', 'completed']),
  status_version: z.number().int().nonnegative(),
  targets: z.array(LegacyRecoveryTargetSchema).min(2),
}).superRefine((value, context) => {
  const staffTargets = value.targets.filter((target) => target.scope === 'staff');
  const clientTargets = value.targets.filter((target) => target.scope === 'client');
  if (staffTargets.length === 0 || clientTargets.length !== 1) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['targets'], message: 'recovery target cardinality is invalid' });
  }
  const segmentIds = staffTargets.map((target) => target.matching_segment_id);
  if (new Set(segmentIds).size !== segmentIds.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['targets'], message: 'staff recovery targets must be unique' });
  }
  const allStaffReported = staffTargets.every((target) => target.reported);
  const clientReported = clientTargets[0]?.reported ?? false;
  const validState = (
    (value.state === 'staff_reporting' && !allStaffReported && !clientReported)
    || (value.state === 'staff_reports_complete' && allStaffReported && !clientReported && value.commitment_id !== null)
    || (['client_reported_final_pdf_pending', 'completed'].includes(value.state)
      && allStaffReported && clientReported && value.commitment_id !== null)
  );
  if (!validState) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['state'], message: 'recovery target reports do not match state' });
  }
});

export const LegacyRecoveryPreviewSchema = z.strictObject({
  preview_fingerprint: Sha256Schema,
  session_id: SessionIdSchema,
  expected_status_version: z.number().int().nonnegative(),
  scope: z.enum(['staff', 'client']),
  matching_segment_id: z.number().int().positive().nullable(),
  current_document_version_id: z.number().int().positive(),
  current_document_set_sha256: Sha256Schema,
  current_commitment_id: z.number().int().positive().nullable(),
  legacy_media_sha256: Sha256Schema,
  blockers: z.array(z.string()),
  can_apply: z.boolean(),
}).superRefine((value, context) => {
  if ((value.scope === 'staff') !== (value.matching_segment_id !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['matching_segment_id'], message: 'recovery Preview scope is invalid' });
  }
  if (value.can_apply !== (value.blockers.length === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['can_apply'], message: 'recovery Preview readiness does not match blockers' });
  }
});

export const ContractExternalSigningQuerySchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  session_id: SessionIdSchema,
  state: ExternalSigningStateSchema,
  status_version: z.number().int().nonnegative(),
  matching_plan_id: z.number().int().positive(),
  commitment_id: z.number().int().positive().nullable(),
  unsigned_document: UnsignedDocumentSchema.nullable(),
  staff_targets: z.array(StaffTargetSchema).min(1),
  client_target: ClientTargetSchema,
}).superRefine((value, context) => {
  const segmentIds = value.staff_targets.map((target) => target.matching_segment_id);
  if (new Set(segmentIds).size !== segmentIds.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['staff_targets'], message: 'staff signing targets must be unique' });
  }
  const allStaffReported = value.staff_targets.every((target) => target.reported);
  if (value.state === 'staff_reporting' && allStaffReported) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['state'], message: 'staff_reporting cannot have every staff report' });
  }
  if (value.state !== 'staff_reporting' && !allStaffReported && value.state !== 'superseded') {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['staff_targets'], message: 'post-staff state requires every staff report' });
  }
  if (value.client_target.reported !== ['client_reported_final_pdf_pending', 'completed'].includes(value.state)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['client_target', 'reported'], message: 'client report does not match closed state' });
  }
});

const ReceiptSchema = z.strictObject({
  receipt_id: ReceiptIdSchema,
  command_type: z.enum(['record_staff_report', 'record_client_report', 'apply_final_signed_contract']),
  schema_version: z.literal('contract-external-signing-receipt.v1'),
  session_id: SessionIdSchema,
  outcome_state: z.enum(['recorded', 'completed']),
  resulting_status_version: z.number().int().positive(),
  resulting_state: ExternalSigningStateSchema,
  matching_segment_id: z.number().int().positive().nullable(),
  final_document_id: FinalDocumentIdSchema.nullable(),
  replayed: z.boolean(),
  applied_at: ZonedTimeSchema,
}).superRefine((value, context) => {
  const staffReport = value.command_type === 'record_staff_report'
    && value.outcome_state === 'recorded'
    && ['staff_reporting', 'staff_reports_complete'].includes(value.resulting_state)
    && value.matching_segment_id !== null
    && value.final_document_id === null;
  const clientReport = value.command_type === 'record_client_report'
    && value.outcome_state === 'recorded'
    && value.resulting_state === 'client_reported_final_pdf_pending'
    && value.matching_segment_id === null
    && value.final_document_id === null;
  const finalApply = value.command_type === 'apply_final_signed_contract'
    && value.outcome_state === 'completed'
    && value.resulting_state === 'completed'
    && value.matching_segment_id === null
    && value.final_document_id !== null;
  if (!staffReport && !clientReport && !finalApply) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['command_type'], message: 'receipt command result union is invalid' });
  }
});

const PreviewSchema = z.strictObject({
  preview_token: PreviewTokenSchema,
  staging_id: StagingIdSchema,
  expected_staging_version: z.number().int().positive(),
  filename: z.string().min(1).max(255),
  mime_type: PdfMimeSchema,
  size_bytes: z.number().int().positive(),
  blockers: z.array(z.string()),
  can_apply: z.boolean(),
}).superRefine((value, context) => {
  if (value.can_apply !== (value.blockers.length === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['can_apply'], message: 'Preview readiness does not match blockers' });
  }
});

const StagingEnvelopeDataSchema = z.strictObject({
  staging_id: StagingIdSchema,
  filename: z.string().min(1).max(255),
  mime_type: PdfMimeSchema,
  size_bytes: z.number().int().positive(),
  expires_at: ZonedTimeSchema,
});

const FinalReadbackSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  session_id: SessionIdSchema,
  final_document_id: FinalDocumentIdSchema,
  controlled_file_id: ControlledFileIdSchema,
  version_number: z.number().int().positive(),
  filename: z.string().min(1).max(255),
  mime_type: PdfMimeSchema,
  size_bytes: z.number().int().positive(),
  status: z.literal('completed'),
  integrity_verified: z.literal(true),
  applied_at: ZonedTimeSchema,
});

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({
    success: z.literal(true),
    message: z.string(),
    data,
    error: z.null(),
  });
}

export type ContractExternalSigningQuery = z.infer<typeof ContractExternalSigningQuerySchema>;
export type ExternalSigningReceipt = z.infer<typeof ReceiptSchema>;
export type FinalDocumentPreview = z.infer<typeof PreviewSchema>;
export type FinalDocumentReadback = z.infer<typeof FinalReadbackSchema>;
export type LegacyRecoveryQuery = z.infer<typeof LegacyRecoveryQuerySchema>;
export type LegacyRecoveryTarget = z.infer<typeof LegacyRecoveryTargetSchema>;
export type LegacyRecoveryPreview = z.infer<typeof LegacyRecoveryPreviewSchema>;
export type ExternalSigningConfirmationMethod = z.infer<typeof ExternalSigningConfirmationMethodSchema>;

export interface ExternalSigningCommandIdentity {
  idempotencyKey: string;
  correlationId: string;
  receiptId: string;
}

export interface CompletionReportInput {
  expected_status_version: number;
  expected_document_version_id: number;
  confirmation_method: ExternalSigningConfirmationMethod;
  reason: string;
}

export interface FinalDocumentApplyInput {
  staging_id: string;
  expected_staging_version: number;
  preview_token: string;
  expected_status_version: number;
}

const LegacyRecoveryPreviewInputSchema = z.strictObject({
  scope: z.enum(['staff', 'client']),
  matching_segment_id: z.number().int().positive().nullable(),
  legacy_document_version_id: z.number().int().positive(),
  signing_event_id: z.number().int().positive(),
  command_receipt_id: z.number().int().positive(),
  confirmation_method: ExternalSigningConfirmationMethodSchema,
  reason: z.string().min(1).max(1000),
}).superRefine((value, context) => {
  if ((value.scope === 'staff') !== (value.matching_segment_id !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['matching_segment_id'], message: 'recovery input scope is invalid' });
  }
});

export type LegacyRecoveryPreviewInput = z.infer<typeof LegacyRecoveryPreviewInputSchema>;

export interface LegacyRecoveryApplyInput extends LegacyRecoveryPreviewInput {
  preview_fingerprint: string;
  expected_status_version: number;
}

export interface PdfDownloadArtifact {
  blob: Blob;
  filename: string;
  mimeType: 'application/pdf';
}

function canonicalCaseNo(caseNo: string): string {
  const value = caseNo.trim();
  if (!value || value.length > 50) throw new Error('案件編號無效。');
  return value;
}

function authToken(): string {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  return token;
}

function uuidHex(): string {
  if (!globalThis.crypto?.randomUUID) throw new Error('瀏覽器無法建立安全命令識別。');
  return globalThis.crypto.randomUUID().replaceAll('-', '').toLowerCase();
}

export function createExternalSigningCommandIdentity(prefix: string): ExternalSigningCommandIdentity {
  if (!/^[a-z][a-z0-9-]{0,31}$/.test(prefix)) throw new Error('命令識別前綴無效。');
  const commandUuid = uuidHex();
  return {
    idempotencyKey: `contract-external.${prefix}:${commandUuid}`,
    correlationId: `contract-external-${prefix}-${uuidHex()}`,
    receiptId: `cesr_${commandUuid}`,
  };
}

function commandOptions(identity: ExternalSigningCommandIdentity, signal?: AbortSignal): RequestOptions {
  ReceiptIdSchema.parse(identity.receiptId);
  return {
    token: authToken(),
    signal,
    headers: {
      'Idempotency-Key': identity.idempotencyKey,
      'X-Correlation-ID': identity.correlationId,
      'X-Receipt-ID': identity.receiptId,
    },
  };
}

function stagingCommandOptions(identity: ExternalSigningCommandIdentity): RequestOptions {
  return {
    token: authToken(),
    headers: {
      'Idempotency-Key': identity.idempotencyKey,
      'X-Correlation-ID': identity.correlationId,
    },
  };
}

function normalizedReport<T extends { reason: string }>(input: T): T {
  const reason = input.reason.trim();
  if (!reason) throw new Error('請填寫外部簽署完成證據。');
  return { ...input, reason };
}

function filenameFromDisposition(value: string | null): string | null {
  if (!value?.toLowerCase().startsWith('attachment;')) return null;
  const encoded = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try { return decodeURIComponent(encoded); } catch { return null; }
  }
  return value.match(/filename="?([^";]+)"?/i)?.[1]?.trim() ?? null;
}

async function assertPdfBytes(blob: Blob): Promise<void> {
  if (blob.size < 11) throw new ApiHttpError(422, 'UNSIGNED_PDF_EMPTY', '未簽契約 PDF 內容無效。');
  const head = new TextDecoder().decode(await blob.slice(0, 5).arrayBuffer());
  const tail = new TextDecoder().decode(await blob.slice(Math.max(0, blob.size - 16)).arrayBuffer());
  if (head !== '%PDF-' || !tail.includes('%%EOF')) {
    throw new ApiHttpError(422, 'UNSIGNED_PDF_CONTENT_INVALID', '未簽契約 PDF 格式驗證失敗。');
  }
}

async function downloadError(response: Response): Promise<ApiHttpError> {
  const payload = await response.json().catch(() => null) as { detail?: { error?: { code?: unknown; message?: unknown; retryable?: unknown } } } | null;
  const error = payload?.detail?.error;
  return new ApiHttpError(
    response.status,
    typeof error?.code === 'string' ? error.code : `HTTP_${response.status}`,
    typeof error?.message === 'string' ? error.message : `未簽契約 PDF 下載失敗（HTTP ${response.status}）。`,
    typeof error?.retryable === 'boolean' ? error.retryable : response.status >= 500,
  );
}

function basePath(caseNo: string): string {
  return `/api/v1/orders/${encodeURIComponent(canonicalCaseNo(caseNo))}/contract-external-signing`;
}

export const contractExternalSigningClient = {
  async query(caseNo: string, options?: { signal?: AbortSignal }): Promise<ContractExternalSigningQuery> {
    const expectedCaseNo = canonicalCaseNo(caseNo);
    const value = decodePayload(
      envelope(ContractExternalSigningQuerySchema),
      await transport.get(basePath(expectedCaseNo), { token: authToken(), signal: options?.signal }),
    ).data;
    if (value.case_no !== expectedCaseNo) throw new ApiHttpError(409, 'CONTRACT_CASE_MISMATCH', '外部簽約查詢案件識別不一致。');
    return value;
  },

  async queryLegacyRecovery(caseNo: string, options?: { signal?: AbortSignal }): Promise<LegacyRecoveryQuery> {
    const expectedCaseNo = canonicalCaseNo(caseNo);
    const value = decodePayload(
      envelope(LegacyRecoveryQuerySchema),
      await transport.get(`${basePath(expectedCaseNo)}/legacy-recovery`, { token: authToken(), signal: options?.signal }),
    ).data;
    if (value.case_no !== expectedCaseNo) throw new ApiHttpError(409, 'CONTRACT_RECOVERY_CASE_MISMATCH', '歷史簽回修復案件識別不一致。');
    return value;
  },

  async previewLegacyRecovery(
    caseNo: string,
    input: LegacyRecoveryPreviewInput,
    signal?: AbortSignal,
  ): Promise<LegacyRecoveryPreview> {
    const normalized = LegacyRecoveryPreviewInputSchema.parse({ ...input, reason: input.reason.trim() });
    return decodePayload(
      envelope(LegacyRecoveryPreviewSchema),
      await transport.post(
        `${basePath(caseNo)}/legacy-recovery/preview`,
        normalized,
        { token: authToken(), signal },
      ),
    ).data;
  },

  async applyLegacyRecovery(
    caseNo: string,
    input: LegacyRecoveryApplyInput,
    identity: ExternalSigningCommandIdentity,
    signal?: AbortSignal,
  ): Promise<ExternalSigningReceipt> {
    const { preview_fingerprint: previewFingerprint, expected_status_version: expectedStatusVersion, ...previewInput } = input;
    Sha256Schema.parse(previewFingerprint);
    if (!Number.isInteger(expectedStatusVersion) || expectedStatusVersion < 0) throw new Error('歷史簽回修復狀態版本無效。');
    const normalized = LegacyRecoveryPreviewInputSchema.parse({ ...previewInput, reason: previewInput.reason.trim() });
    const value = decodePayload(
      envelope(ReceiptSchema),
      await transport.post(
        `${basePath(caseNo)}/legacy-recovery/apply`,
        {
          ...normalized,
          preview_fingerprint: previewFingerprint,
          expected_status_version: expectedStatusVersion,
        },
        commandOptions(identity, signal),
      ),
    ).data;
    if (value.receipt_id !== identity.receiptId) throw new ApiHttpError(409, 'CONTRACT_RECOVERY_RECEIPT_MISMATCH', '歷史簽回修復 receipt 識別不一致。');
    if (value.resulting_status_version !== expectedStatusVersion + 1) {
      throw new ApiHttpError(409, 'CONTRACT_RECOVERY_STATUS_VERSION_MISMATCH', '歷史簽回修復 receipt 狀態版本不符合預期。');
    }
    return value;
  },

  async downloadUnsignedPdf(caseNo: string, expectedDocumentVersionId: number, signal?: AbortSignal): Promise<PdfDownloadArtifact> {
    if (!Number.isInteger(expectedDocumentVersionId) || expectedDocumentVersionId <= 0) throw new Error('未簽文件版本無效。');
    const token = authToken();
    const correlationId = `contract-external-download-${uuidHex()}`;
    const response = await fetch(`${basePath(caseNo)}/unsigned-pdf`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Expected-Document-Version': String(expectedDocumentVersionId),
        'X-Correlation-ID': correlationId,
      },
      signal,
    });
    if (!response.ok) {
      if (response.status === 401) {
        window.dispatchEvent(new CustomEvent(ADMIN_SESSION_UNAUTHORIZED_EVENT, { detail: { rejectedToken: token } }));
      }
      throw await downloadError(response);
    }
    if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/pdf') {
      throw new ApiHttpError(422, 'UNSIGNED_PDF_MEDIA_TYPE_INVALID', '未簽契約下載不是 PDF。');
    }
    if (!response.headers.get('cache-control')?.toLowerCase().split(',').map((value) => value.trim()).includes('no-store')) {
      throw new ApiHttpError(422, 'UNSIGNED_PDF_CACHE_POLICY_INVALID', '未簽契約下載缺少 no-store。');
    }
    if (response.headers.get('x-contract-document-version') !== String(expectedDocumentVersionId)) {
      throw new ApiHttpError(409, 'UNSIGNED_PDF_VERSION_STALE', '未簽契約文件版本已變更。');
    }
    if (response.headers.get('x-correlation-id') !== correlationId) {
      throw new ApiHttpError(409, 'UNSIGNED_PDF_CORRELATION_MISMATCH', '未簽契約下載回應識別不一致。');
    }
    const filename = filenameFromDisposition(response.headers.get('content-disposition'));
    if (!filename || !filename.toLowerCase().endsWith('.pdf')) {
      throw new ApiHttpError(422, 'UNSIGNED_PDF_FILENAME_INVALID', '未簽契約下載檔名無效。');
    }
    const blob = await response.blob();
    await assertPdfBytes(blob);
    return { blob, filename, mimeType: 'application/pdf' };
  },

  async recordStaffCompletionReport(
    caseNo: string,
    segmentId: number,
    input: CompletionReportInput,
    identity: ExternalSigningCommandIdentity,
    signal?: AbortSignal,
  ): Promise<ExternalSigningReceipt> {
    if (!Number.isInteger(segmentId) || segmentId <= 0) throw new Error('月嫂分段識別無效。');
    return decodePayload(
      envelope(ReceiptSchema),
      await transport.post(
        `${basePath(caseNo)}/staff-segments/${segmentId}/completion-reports`,
        normalizedReport(input),
        commandOptions(identity, signal),
      ),
    ).data;
  },

  async recordClientCompletionReport(
    caseNo: string,
    input: CompletionReportInput & { expected_commitment_id: number },
    identity: ExternalSigningCommandIdentity,
    signal?: AbortSignal,
  ): Promise<ExternalSigningReceipt> {
    if (!Number.isInteger(input.expected_commitment_id) || input.expected_commitment_id <= 0) throw new Error('服務承諾識別無效。');
    return decodePayload(
      envelope(ReceiptSchema),
      await transport.post(
        `${basePath(caseNo)}/client/completion-reports`,
        normalizedReport(input),
        commandOptions(identity, signal),
      ),
    ).data;
  },

  async stageFinalDocument(caseNo: string, file: File, identity: ExternalSigningCommandIdentity) {
    if (file.type.toLowerCase() !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf') || file.size <= 0) {
      throw new Error('最終簽署文件必須是非空 PDF。');
    }
    const form = new FormData();
    form.set('document', file, file.name);
    return decodePayload(
      envelope(StagingEnvelopeDataSchema),
      await transport.post(`${basePath(caseNo)}/final-document/staging`, form, stagingCommandOptions(identity)),
    ).data;
  },

  async previewFinalDocument(caseNo: string, input: { staging_id: string; expected_status_version: number }, signal?: AbortSignal): Promise<FinalDocumentPreview> {
    StagingIdSchema.parse(input.staging_id);
    return decodePayload(
      envelope(PreviewSchema),
      await transport.post(`${basePath(caseNo)}/final-document/preview`, input, { token: authToken(), signal }),
    ).data;
  },

  async applyFinalDocument(
    caseNo: string,
    input: FinalDocumentApplyInput,
    identity: ExternalSigningCommandIdentity,
    signal?: AbortSignal,
  ): Promise<ExternalSigningReceipt> {
    StagingIdSchema.parse(input.staging_id);
    PreviewTokenSchema.parse(input.preview_token);
    return decodePayload(
      envelope(ReceiptSchema),
      await transport.post(`${basePath(caseNo)}/final-document/apply`, input, commandOptions(identity, signal)),
    ).data;
  },

  async getReceipt(caseNo: string, receiptId: string, signal?: AbortSignal): Promise<ExternalSigningReceipt> {
    ReceiptIdSchema.parse(receiptId);
    const value = decodePayload(
      envelope(ReceiptSchema),
      await transport.get(`${basePath(caseNo)}/receipts/${receiptId}`, { token: authToken(), signal }),
    ).data;
    if (value.receipt_id !== receiptId) throw new ApiHttpError(409, 'CONTRACT_RECEIPT_MISMATCH', '簽約 receipt 識別不一致。');
    return value;
  },

  async getFinalDocumentReadback(caseNo: string, signal?: AbortSignal): Promise<FinalDocumentReadback> {
    const expectedCaseNo = canonicalCaseNo(caseNo);
    const value = decodePayload(
      envelope(FinalReadbackSchema),
      await transport.get(`${basePath(expectedCaseNo)}/final-document/readback`, { token: authToken(), signal }),
    ).data;
    if (value.case_no !== expectedCaseNo) {
      throw new ApiHttpError(409, 'CONTRACT_FINAL_READBACK_CASE_MISMATCH', '最終 PDF readback 案件識別不一致。');
    }
    return value;
  },
};
