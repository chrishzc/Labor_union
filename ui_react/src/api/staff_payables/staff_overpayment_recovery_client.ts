/**
 * File: staff_overpayment_recovery_client.ts
 * Description: Staff Payables recovery 的 bounded typed Query／Preview／Apply client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  mapStaffOverpaymentRecoveryError,
  StaffOverpaymentRecoveryError,
} from './staff_overpayment_recovery_errors';
import {
  StaffOverpaymentRecoveryAdjustmentPreviewSchema,
  StaffOverpaymentRecoveryCollectionPreviewSchema,
  StaffOverpaymentRecoveryMatchingPreviewSchema,
  StaffOverpaymentRecoveryMatchingReceiptSchema,
  StaffOverpaymentRecoveryQuerySchema,
  StaffOverpaymentRecoveryReceiptSchema,
  staffOverpaymentRecoveryEnvelope,
  type StaffOverpaymentRecoveryAdjustmentPreview,
  type StaffOverpaymentRecoveryCollectionPreview,
  type StaffOverpaymentRecoveryMatchingPreview,
  type StaffOverpaymentRecoveryMatchingReceipt,
  type StaffOverpaymentRecoveryQuery,
  type StaffOverpaymentRecoveryReceipt,
} from './staff_overpayment_recovery_schemas';

export interface StaffOverpaymentRecoveryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface StaffOverpaymentRecoveryCommand {
  idempotencyKey: string;
  correlationId: string;
  signal?: AbortSignal;
}

export interface StaffOverpaymentRecoveryMatchingInput {
  recovery_identity: string;
  finance_import_row_id: number;
  evidence_reference: string;
}

export interface StaffOverpaymentRecoveryCollectionInput {
  recovery_identity: string;
  finance_import_row_id: number;
  matching_identity: string;
  matching_version: number;
  evidence_reference: string;
}

export interface StaffOverpaymentRecoveryAdjustmentInput {
  recovery_identity: string;
  adjustment_amount_ntd: number;
  evidence_reference: string;
}

export interface StaffOverpaymentRecoveryApplyInput {
  reason: string;
  evidence_reference: string;
}

let correlationSequence = 0;

function nextCorrelation(operation: string): string {
  correlationSequence += 1;
  return `staff-overpayment-recovery-${operation}-${correlationSequence.toString(36)}`;
}

export function createStaffOverpaymentRecoveryCommandIdentity(operation: string): StaffOverpaymentRecoveryCommand {
  const normalized = operation.trim();
  if (!/^[a-z][a-z0-9-]{0,31}$/.test(normalized)) {
    throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_COMMAND_INVALID', '命令識別前綴無效。');
  }
  const uuid = globalThis.crypto?.randomUUID?.();
  if (!uuid) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_COMMAND_UNAVAILABLE', '瀏覽器無法建立安全命令識別。');
  const compact = uuid.replaceAll('-', '').toLowerCase();
  return {
    idempotencyKey: `staff-overpayment-recovery.${normalized}:${compact}`,
    correlationId: `staff-overpayment-recovery-${normalized}-${compact}`,
  };
}

function authToken(): string {
  const token = sessionClient.getToken();
  if (!token) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_UNAUTHENTICATED', '請先登入。', false, 401);
  return token;
}

function options(value?: StaffOverpaymentRecoveryOptions, headers: Record<string, string> = {}): RequestOptions {
  return {
    token: authToken(),
    signal: value?.signal,
    timeoutMs: value?.timeoutMs ?? 30_000,
    baseUrl: value?.baseUrl,
    headers,
  };
}

function commandOptions(command: StaffOverpaymentRecoveryCommand): RequestOptions {
  if (!command.idempotencyKey.trim() || !command.correlationId.trim()) {
    throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_COMMAND_INVALID', '命令識別不得為空白。');
  }
  return options(command, {
    'Idempotency-Key': command.idempotencyKey,
    'X-Correlation-ID': command.correlationId,
  });
}

function text(value: string, field: string, max = 191): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > max) {
    throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_INPUT_INVALID', `${field}格式不正確。`);
  }
  return normalized;
}

function rowId(value: number): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_BANK_ROW_INVALID', '銀行流水編號必須是正整數。');
  }
  return value;
}

function evidence(value: string): string {
  return text(value, 'evidence_reference');
}

function reason(value: string): string {
  return text(value, 'reason', 500);
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown, label: string): z.output<T> {
  try {
    return decodePayload(staffOverpaymentRecoveryEnvelope(schema), raw).data as z.output<T>;
  } catch (error) {
    throw mapStaffOverpaymentRecoveryError(error instanceof Error ? error : new Error(`${label}回應結構異常。`));
  }
}

function pathIdentity(value: string): string {
  return encodeURIComponent(text(value, 'recovery_identity'));
}

function requireStaffId(value: number): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_STAFF_ID_INVALID', 'staffId必須是正整數。');
  }
  return value;
}

function assertApplyIdentity(expected: string, actual: string): void {
  if (expected !== actual) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_IDENTITY_MISMATCH', 'Preview與Apply的recovery identity不一致。');
}

export interface StaffOverpaymentRecoveryClient {
  query(staffId: number, recoveryIdentity: string, options?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryQuery>;
  previewMatching(input: StaffOverpaymentRecoveryMatchingInput, options?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryMatchingPreview>;
  applyMatching(preview: StaffOverpaymentRecoveryMatchingPreview, input: StaffOverpaymentRecoveryMatchingInput & StaffOverpaymentRecoveryApplyInput, command: StaffOverpaymentRecoveryCommand): Promise<StaffOverpaymentRecoveryMatchingReceipt>;
  previewCollection(input: StaffOverpaymentRecoveryCollectionInput, options?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryCollectionPreview>;
  applyCollection(preview: StaffOverpaymentRecoveryCollectionPreview, input: StaffOverpaymentRecoveryCollectionInput & StaffOverpaymentRecoveryApplyInput, command: StaffOverpaymentRecoveryCommand): Promise<StaffOverpaymentRecoveryReceipt>;
  previewAdjustment(input: StaffOverpaymentRecoveryAdjustmentInput, options?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryAdjustmentPreview>;
  applyAdjustment(preview: StaffOverpaymentRecoveryAdjustmentPreview, input: StaffOverpaymentRecoveryAdjustmentInput & StaffOverpaymentRecoveryApplyInput, command: StaffOverpaymentRecoveryCommand): Promise<StaffOverpaymentRecoveryReceipt>;
}

class DefaultStaffOverpaymentRecoveryClient implements StaffOverpaymentRecoveryClient {
  async query(staffId: number, recoveryIdentity: string, requestOptions?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryQuery> {
    const normalizedStaffId = requireStaffId(staffId);
    const normalizedIdentity = text(recoveryIdentity, 'recovery_identity');
    try {
      const data = decode(StaffOverpaymentRecoveryQuerySchema, await transport.get(
        `/api/v1/staff-payables/overpayment-recoveries/${normalizedStaffId}/${pathIdentity(normalizedIdentity)}`,
        options(requestOptions, { 'X-Correlation-ID': nextCorrelation('query') }),
      ), 'Staff recovery Query');
      if (data.staff_id !== normalizedStaffId || data.recovery_identity !== normalizedIdentity) {
        throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_OWNER_MISMATCH', 'owner Query identity與請求不一致。');
      }
      return data;
    } catch (error) {
      throw mapStaffOverpaymentRecoveryError(error);
    }
  }

  async previewMatching(input: StaffOverpaymentRecoveryMatchingInput, requestOptions?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryMatchingPreview> {
    const body = { recovery_identity: text(input.recovery_identity, 'recovery_identity'), finance_import_row_id: rowId(input.finance_import_row_id), evidence_reference: evidence(input.evidence_reference) };
    try {
      return decode(StaffOverpaymentRecoveryMatchingPreviewSchema, await transport.post(
        '/api/v1/staff-payables/overpayment-recoveries/matching/preview', body,
        options(requestOptions, { 'X-Correlation-ID': nextCorrelation('matching-preview') }),
      ), 'Staff recovery matching Preview');
    } catch (error) { throw mapStaffOverpaymentRecoveryError(error); }
  }

  async applyMatching(preview: StaffOverpaymentRecoveryMatchingPreview, input: StaffOverpaymentRecoveryMatchingInput & StaffOverpaymentRecoveryApplyInput, command: StaffOverpaymentRecoveryCommand): Promise<StaffOverpaymentRecoveryMatchingReceipt> {
    const body = {
      recovery_identity: text(input.recovery_identity, 'recovery_identity'),
      finance_import_row_id: rowId(input.finance_import_row_id),
      expected_recovery_version: preview.recovery_version,
      expected_staff_payables_version: preview.staff_payables_version,
      preview_fingerprint: preview.preview_fingerprint,
      reason: reason(input.reason),
      evidence_reference: evidence(input.evidence_reference),
    };
    assertApplyIdentity(preview.recovery_identity, body.recovery_identity);
    try {
      return decode(StaffOverpaymentRecoveryMatchingReceiptSchema, await transport.post(
        '/api/v1/staff-payables/overpayment-recoveries/matching/apply', body,
        commandOptions(command),
      ), 'Staff recovery matching Apply');
    } catch (error) { throw mapStaffOverpaymentRecoveryError(error); }
  }

  async previewCollection(input: StaffOverpaymentRecoveryCollectionInput, requestOptions?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryCollectionPreview> {
    const body = {
      recovery_identity: text(input.recovery_identity, 'recovery_identity'),
      finance_import_row_id: rowId(input.finance_import_row_id),
      matching_identity: text(input.matching_identity, 'matching_identity'),
      matching_version: input.matching_version,
      evidence_reference: evidence(input.evidence_reference),
    };
    if (!Number.isInteger(body.matching_version) || body.matching_version <= 0) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_MATCHING_INVALID', 'matching version格式不正確。');
    try {
      return decode(StaffOverpaymentRecoveryCollectionPreviewSchema, await transport.post(
        '/api/v1/staff-payables/overpayment-recoveries/matched/preview', body,
        options(requestOptions, { 'X-Correlation-ID': nextCorrelation('collection-preview') }),
      ), 'Staff recovery collection Preview');
    } catch (error) { throw mapStaffOverpaymentRecoveryError(error); }
  }

  async applyCollection(preview: StaffOverpaymentRecoveryCollectionPreview, input: StaffOverpaymentRecoveryCollectionInput & StaffOverpaymentRecoveryApplyInput, command: StaffOverpaymentRecoveryCommand): Promise<StaffOverpaymentRecoveryReceipt> {
    const body = {
      recovery_identity: text(input.recovery_identity, 'recovery_identity'),
      finance_import_row_id: rowId(input.finance_import_row_id),
      matching_identity: text(input.matching_identity, 'matching_identity'),
      matching_version: input.matching_version,
      expected_recovery_version: preview.recovery_version,
      expected_staff_payables_version: preview.staff_payables_version,
      preview_fingerprint: preview.preview_fingerprint,
      reason: reason(input.reason),
      evidence_reference: evidence(input.evidence_reference),
    };
    assertApplyIdentity(preview.recovery_identity, body.recovery_identity);
    if (!Number.isInteger(body.matching_version) || body.matching_version <= 0) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_MATCHING_INVALID', 'matching version格式不正確。');
    try {
      return decode(StaffOverpaymentRecoveryReceiptSchema, await transport.post(
        '/api/v1/staff-payables/overpayment-recoveries/matched/apply', body,
        commandOptions(command),
      ), 'Staff recovery collection Apply');
    } catch (error) { throw mapStaffOverpaymentRecoveryError(error); }
  }

  async previewAdjustment(input: StaffOverpaymentRecoveryAdjustmentInput, requestOptions?: StaffOverpaymentRecoveryOptions): Promise<StaffOverpaymentRecoveryAdjustmentPreview> {
    const amount = input.adjustment_amount_ntd;
    if (!Number.isInteger(amount) || amount <= 0) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_AMOUNT_INVALID', 'Staff adjustment金額必須是正整數。');
    const body = { recovery_identity: text(input.recovery_identity, 'recovery_identity'), adjustment_amount_ntd: amount, evidence_reference: evidence(input.evidence_reference) };
    try {
      return decode(StaffOverpaymentRecoveryAdjustmentPreviewSchema, await transport.post(
        '/api/v1/staff-payables/overpayment-recoveries/adjustment/preview', body,
        options(requestOptions, { 'X-Correlation-ID': nextCorrelation('adjustment-preview') }),
      ), 'Staff recovery adjustment Preview');
    } catch (error) { throw mapStaffOverpaymentRecoveryError(error); }
  }

  async applyAdjustment(preview: StaffOverpaymentRecoveryAdjustmentPreview, input: StaffOverpaymentRecoveryAdjustmentInput & StaffOverpaymentRecoveryApplyInput, command: StaffOverpaymentRecoveryCommand): Promise<StaffOverpaymentRecoveryReceipt> {
    if (input.adjustment_amount_ntd !== preview.remaining_before_ntd) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_AMOUNT_STALE', 'Staff adjustment必須等於Preview的fresh remaining。');
    const body = {
      recovery_identity: text(input.recovery_identity, 'recovery_identity'),
      adjustment_amount_ntd: preview.remaining_before_ntd,
      expected_recovery_version: preview.recovery_version,
      expected_staff_payables_version: preview.staff_payables_version,
      preview_fingerprint: preview.preview_fingerprint,
      reason: reason(input.reason),
      evidence_reference: evidence(input.evidence_reference),
    };
    assertApplyIdentity(preview.recovery_identity, body.recovery_identity);
    try {
      return decode(StaffOverpaymentRecoveryReceiptSchema, await transport.post(
        '/api/v1/staff-payables/overpayment-recoveries/adjustment/apply', body,
        commandOptions(command),
      ), 'Staff recovery adjustment Apply');
    } catch (error) { throw mapStaffOverpaymentRecoveryError(error); }
  }
}

export const staffOverpaymentRecoveryClient: StaffOverpaymentRecoveryClient = new DefaultStaffOverpaymentRecoveryClient();
