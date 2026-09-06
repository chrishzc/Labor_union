/** Query/Preview/Apply client for Staff's six canonical relation editor. */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  StaffCasePreferenceManualReceiptResponseSchema,
  StaffCasePreferenceManualSnapshotResponseSchema,
  StaffCasePreferenceRelationsSchema,
  type StaffCasePreferenceManualApplyPayload,
  type StaffCasePreferenceManualReceipt,
  type StaffCasePreferenceManualSnapshot,
  type StaffCasePreferenceRelations,
} from './staff_case_preferences_schemas';

const BASE = '/api/v1/staff/case-preference-manual';
export interface StaffCasePreferenceManualOptions { signal?: AbortSignal; headers?: Record<string, string>; timeoutMs?: number; baseUrl?: string; }
export interface StaffCasePreferenceManualApplyOptions extends StaffCasePreferenceManualOptions { idempotencyKey: string; }
function requireId(staffId: number) { if (!Number.isInteger(staffId) || staffId <= 0) throw new RangeError('staffId 必須是正整數。'); }
function requestOptions(options: StaffCasePreferenceManualOptions | undefined, key?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'staff_case_preference_manual_unauthenticated', '尚未登入。');
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    if (!['authorization', 'idempotency-key'].includes(name.toLowerCase())) headers[name] = value;
  }
  if (key !== undefined) headers['Idempotency-Key'] = key.trim();
  if (!Object.keys(headers).some((name) => name.toLowerCase() === 'x-correlation-id')) headers['X-Correlation-ID'] = 'staff-case-preference-' + Date.now().toString(36);
  return { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, headers, token };
}
function decodeSnapshot(raw: unknown, staffId: number): StaffCasePreferenceManualSnapshot {
  const parsed = StaffCasePreferenceManualSnapshotResponseSchema.safeParse(raw);
  if (!parsed.success || !parsed.data.success) throw new ApiDecodeError('六大接案能力回應結構異常。', [], raw);
  if (parsed.data.data.staff_id !== staffId) throw new ApiDecodeError('六大接案能力 identity 不一致。', [], raw);
  return parsed.data.data;
}
function decodeReceipt(raw: unknown, staffId: number): StaffCasePreferenceManualReceipt {
  const parsed = StaffCasePreferenceManualReceiptResponseSchema.safeParse(raw);
  if (!parsed.success || !parsed.data.success) throw new ApiDecodeError('六大接案能力 receipt 結構異常。', [], raw);
  if (parsed.data.data.staff_id !== staffId) throw new ApiDecodeError('六大接案能力 receipt identity 不一致。', [], raw);
  return parsed.data.data;
}
function validateRelations(relations: StaffCasePreferenceRelations) { return StaffCasePreferenceRelationsSchema.parse(relations); }
export const staffCasePreferenceManualClient = {
  async query(staffId: number, options?: StaffCasePreferenceManualOptions) {
    requireId(staffId);
    return decodeSnapshot(await transport.get<unknown>(BASE + '/' + staffId, requestOptions(options)), staffId);
  },
  async preview(staffId: number, relations: StaffCasePreferenceRelations, options?: StaffCasePreferenceManualOptions) {
    requireId(staffId);
    return decodeSnapshot(await transport.post<unknown>(BASE + '/' + staffId + '/preview', validateRelations(relations), requestOptions(options)), staffId);
  },
  async apply(staffId: number, payload: StaffCasePreferenceManualApplyPayload, options: StaffCasePreferenceManualApplyOptions) {
    requireId(staffId);
    return decodeReceipt(await transport.post<unknown>(BASE + '/' + staffId + '/apply', payload, requestOptions(options, options.idempotencyKey)), staffId);
  },
};
