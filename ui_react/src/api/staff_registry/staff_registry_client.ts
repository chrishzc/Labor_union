import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { response, StaffBankPreviewSchema, StaffBankReceiptSchema, StaffProfileMutationPreviewSchema, StaffProfileMutationReceiptSchema, type StaffBankCommand, type StaffBankPreview, type StaffProfileMutationPreview } from './staff_registry_schemas';

const auth = () => { const token = sessionClient.getToken(); if (!token) throw new Error('請先登入管理後台。'); return token; };
const unique = (scope: string) => `${scope}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
function decode<T>(schema: ReturnType<typeof response>, raw: unknown, message: string): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(message, parsed.error.issues.map((issue) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })), raw);
  if (parsed.data.data === null) throw new ApiDecodeError(`${message}：缺少資料本體。`, [], raw);
  return parsed.data.data as T;
}
const endpoint = (staffId: number, owner: 'profile' | 'bank-accounts', action: 'preview' | 'apply') => `/api/v1/staff/${encodeURIComponent(String(staffId))}/${owner}/${action}`;
export const staffRegistryClient = {
  async previewProfile(staffId: number, changes: Record<string, string | null>, expectedVersion: number): Promise<StaffProfileMutationPreview> { const raw = await transport.post(endpoint(staffId, 'profile', 'preview'), { changes, expected_version: expectedVersion }, { token: auth() }); return decode(response(StaffProfileMutationPreviewSchema), raw, '月嫂資料預覽回應異常'); },
  async applyProfile(staffId: number, changes: Record<string, string | null>, expectedVersion: number, fingerprint: string, reason: string, idempotencyKey = unique('staff-profile')) { const raw = await transport.post(endpoint(staffId, 'profile', 'apply'), { changes, expected_version: expectedVersion, preview_fingerprint: fingerprint, reason }, { token: auth(), headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': unique('staff-profile-correlation') } }); return decode(response(StaffProfileMutationReceiptSchema), raw, '月嫂資料儲存收據異常'); },
  async previewBank(staffId: number, command: StaffBankCommand, expectedVersion: number): Promise<StaffBankPreview> { const raw = await transport.post(endpoint(staffId, 'bank-accounts', 'preview'), { command, expected_version: expectedVersion }, { token: auth() }); return decode(response(StaffBankPreviewSchema), raw, '銀行帳戶預覽回應異常'); },
  async applyBank(staffId: number, command: StaffBankCommand, expectedVersion: number, fingerprint: string, reason: string, idempotencyKey = unique('staff-bank')) { const raw = await transport.post(endpoint(staffId, 'bank-accounts', 'apply'), { command, expected_version: expectedVersion, preview_fingerprint: fingerprint, reason }, { token: auth(), headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': unique('staff-bank-correlation') } }); return decode(response(StaffBankReceiptSchema), raw, '銀行帳戶儲存收據異常'); },
};
