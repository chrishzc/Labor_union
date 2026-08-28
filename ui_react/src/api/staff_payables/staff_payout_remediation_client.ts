/**
 * File: staff_payout_remediation_client.ts
 * Description: PAYOUT-001 的 bounded typed Query、Preview、Apply 與 Job terminal client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { staffPayablesQueryClient } from './staff_payables_query_client';
import type { StaffPayablesQuery } from './staff_payables_query_schemas';
import {
  StaffPayoutJobAcceptedSchema,
  StaffPayoutJobSchema,
  StaffPayoutPreviewSchema,
  StaffPayoutResponseSchema,
  type StaffPayoutJob,
  type StaffPayoutJobAccepted,
  type StaffPayoutPreview,
} from './staff_payout_remediation_schemas';
import { mapStaffPayoutRemediationError, StaffPayoutRemediationError } from './staff_payout_remediation_errors';

export interface StaffPayoutRemediationOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface StaffPayoutRemediationCommand { idempotencyKey: string; correlationId: string; signal?: AbortSignal; }
export interface StaffPayoutSelection { financeImportRowIds: number[]; obligationIdentities: string[]; }
export interface StaffPayoutRemediationClient {
  query(staffId: number, options?: StaffPayoutRemediationOptions): Promise<StaffPayablesQuery>;
  preview(selection: StaffPayoutSelection, options?: StaffPayoutRemediationOptions): Promise<StaffPayoutPreview>;
  apply(preview: StaffPayoutPreview, selection: StaffPayoutSelection, reason: string, command: StaffPayoutRemediationCommand, options?: StaffPayoutRemediationOptions): Promise<StaffPayoutJobAccepted>;
  queryJob(jobId: string, options?: StaffPayoutRemediationOptions): Promise<StaffPayoutJob>;
}

function positiveId(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value <= 0) throw new StaffPayoutRemediationError('STAFF_PAYOUT_INPUT_INVALID', `${field}必須是正整數。`);
  return value;
}
function identity(value: string, field: string): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > 191) throw new StaffPayoutRemediationError('STAFF_PAYOUT_INPUT_INVALID', `${field}不可為空白。`);
  return normalized;
}
function ids(values: number[], field: string): number[] {
  if (!Array.isArray(values) || values.length < 1) throw new StaffPayoutRemediationError('STAFF_PAYOUT_INPUT_INVALID', `${field}不可為空。`);
  const normalized = values.map((value) => positiveId(value, field));
  if (new Set(normalized).size !== normalized.length) throw new StaffPayoutRemediationError('STAFF_PAYOUT_INPUT_INVALID', `${field}不可重複。`);
  return normalized;
}
function identities(values: string[], field: string): string[] {
  if (!Array.isArray(values) || values.length < 1) throw new StaffPayoutRemediationError('STAFF_PAYOUT_INPUT_INVALID', `${field}不可為空。`);
  const normalized = values.map((value) => identity(value, field));
  if (new Set(normalized).size !== normalized.length) throw new StaffPayoutRemediationError('STAFF_PAYOUT_INPUT_INVALID', `${field}不可重複。`);
  return normalized;
}
function authOptions(value: StaffPayoutRemediationOptions | StaffPayoutRemediationCommand, headers: Record<string, string> = {}): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffPayoutRemediationError('STAFF_PAYOUT_UNAUTHENTICATED', '請先登入。', false, 401);
  return { token, signal: value.signal, timeoutMs: 'timeoutMs' in value ? value.timeoutMs ?? 30_000 : 30_000, baseUrl: 'baseUrl' in value ? value.baseUrl : undefined, headers };
}
function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown, label: string): z.output<T> {
  try {
    const envelope = decodePayload(StaffPayoutResponseSchema(schema), raw);
    if (!envelope.success || envelope.data === null) throw new StaffPayoutRemediationError('STAFF_PAYOUT_EMPTY_RESPONSE', envelope.error ?? envelope.message);
    return envelope.data as z.output<T>;
  } catch (error) {
    throw mapStaffPayoutRemediationError(error instanceof Error ? error : new Error(`${label}回應結構異常。`));
  }
}
function normalizeSelection(selection: StaffPayoutSelection): StaffPayoutSelection {
  return { financeImportRowIds: ids(selection.financeImportRowIds, 'finance_import_row_ids'), obligationIdentities: identities(selection.obligationIdentities, 'obligation_identities') };
}
function commandHeaders(command: StaffPayoutRemediationCommand): Record<string, string> {
  if (!command.idempotencyKey.trim() || !command.correlationId.trim()) throw new StaffPayoutRemediationError('STAFF_PAYOUT_COMMAND_INVALID', '命令識別不得為空白。');
  return { 'Idempotency-Key': command.idempotencyKey, 'X-Correlation-ID': command.correlationId };
}
function requireStaffId(value: number): number { return positiveId(value, 'staffId'); }

class DefaultStaffPayoutRemediationClient implements StaffPayoutRemediationClient {
  async query(staffId: number, options?: StaffPayoutRemediationOptions): Promise<StaffPayablesQuery> {
    try { return await staffPayablesQueryClient.query(requireStaffId(staffId), options); }
    catch (error) { throw mapStaffPayoutRemediationError(error); }
  }
  async preview(selection: StaffPayoutSelection, options?: StaffPayoutRemediationOptions): Promise<StaffPayoutPreview> {
    const normalized = normalizeSelection(selection);
    try {
      return decode(StaffPayoutPreviewSchema, await transport.post('/api/v1/staff-payables/payout/preview', {
        finance_import_row_ids: normalized.financeImportRowIds,
        obligation_identities: normalized.obligationIdentities,
      }, authOptions(options ?? {}, { 'X-Correlation-ID': `staff-payout-preview-${crypto.randomUUID()}` })), 'PAYOUT Preview');
    } catch (error) { throw mapStaffPayoutRemediationError(error); }
  }
  async apply(preview: StaffPayoutPreview, selection: StaffPayoutSelection, reason: string, command: StaffPayoutRemediationCommand, options?: StaffPayoutRemediationOptions): Promise<StaffPayoutJobAccepted> {
    const normalized = normalizeSelection(selection);
    const normalizedReason = reason.trim();
    if (!normalizedReason || normalizedReason.length > 500) throw new StaffPayoutRemediationError('STAFF_PAYOUT_REASON_INVALID', '處理理由不可為空白且不得超過500字。');
    if (!preview.preview_fingerprint || !/^[0-9a-f]{64}$/.test(preview.preview_fingerprint)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_PREVIEW_INVALID', 'Preview fingerprint 無效。');
    try {
      return decode(StaffPayoutJobAcceptedSchema, await transport.post('/api/v1/staff-payables/payout/apply', {
        finance_import_row_ids: normalized.financeImportRowIds,
        obligation_identities: normalized.obligationIdentities,
        expected_staff_payables_version: preview.staff_payables_version,
        expected_bank_facts_version: preview.bank_facts_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: normalizedReason,
      }, authOptions({ ...command, ...options }, commandHeaders(command))), 'PAYOUT Apply');
    } catch (error) { throw mapStaffPayoutRemediationError(error); }
  }
  async queryJob(jobId: string, options?: StaffPayoutRemediationOptions): Promise<StaffPayoutJob> {
    const normalized = identity(jobId, 'job_id');
    try {
      const result = decode(StaffPayoutJobSchema, await transport.get(`/api/v1/jobs/${encodeURIComponent(normalized)}`, authOptions(options ?? {}, { 'X-Correlation-ID': `staff-payout-job-${crypto.randomUUID()}` })), 'PAYOUT Job');
      if (result.job_id !== normalized) throw new StaffPayoutRemediationError('STAFF_PAYOUT_JOB_IDENTITY_MISMATCH', 'Job identity 與查詢不一致。');
      return result;
    } catch (error) { throw mapStaffPayoutRemediationError(error); }
  }
}

export function createStaffPayoutRemediationCommand(operation = 'apply'): StaffPayoutRemediationCommand {
  const normalized = operation.trim();
  if (!/^[a-z][a-z0-9-]{0,31}$/.test(normalized)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_COMMAND_INVALID', '命令操作識別無效。');
  const uuid = globalThis.crypto?.randomUUID?.();
  if (!uuid) throw new StaffPayoutRemediationError('STAFF_PAYOUT_COMMAND_UNAVAILABLE', '瀏覽器無法建立安全命令識別。');
  const compact = uuid.replaceAll('-', '').toLowerCase();
  return { idempotencyKey: `staff-payout.${normalized}:${compact}`, correlationId: `staff-payout-${normalized}-${compact}` };
}

export const staffPayoutRemediationClient: StaffPayoutRemediationClient = new DefaultStaffPayoutRemediationClient();
