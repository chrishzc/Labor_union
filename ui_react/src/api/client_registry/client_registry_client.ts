import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  ClientRegistryDetailResponseSchema, ClientRegistryPageResponseSchema,
  RegistryMutationPreviewResponseSchema, RegistryMutationReceiptResponseSchema,
  type BeClassChanges, type ClientProfileChanges, type ClientRegistryDetail,
  type ClientRegistryPage, type RegistryMutationPreview, type RegistryMutationReceipt,
} from './client_registry_schemas';

type Owner = 'profile' | 'beclass';
const token = () => {
  const value = sessionClient.getToken();
  if (!value) throw new Error('請先登入管理後台。');
  return value;
};
const decode = <T>(schema: { safeParse(value: unknown): { success: true; data: { data: T | null } } | { success: false; error: { issues: readonly { path: PropertyKey[]; message: string; code: string }[] } } }, raw: unknown, message: string): T => {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(message, parsed.error.issues.map((issue) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })), raw);
  if (parsed.data.data === null) throw new ApiDecodeError(`${message}：缺少資料本體。`, [], raw);
  return parsed.data.data;
};
const key = (scope: string) => `${scope}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;

export const clientRegistryClient = {
  async list(query?: string): Promise<ClientRegistryPage> {
    const raw = await transport.get('/api/v1/admin/registries/clients', { token: token(), params: { query: query?.trim() || undefined, limit: 100 } });
    return decode(ClientRegistryPageResponseSchema, raw, '客戶名冊回應結構異常');
  },
  async query(caseNo: string): Promise<ClientRegistryDetail> {
    const raw = await transport.get(`/api/v1/admin/registries/clients/${encodeURIComponent(caseNo)}`, { token: token() });
    return decode(ClientRegistryDetailResponseSchema, raw, '客戶名冊詳情回應結構異常');
  },
  async preview(caseNo: string, owner: Owner, changes: ClientProfileChanges | BeClassChanges, expectedVersion: number): Promise<RegistryMutationPreview> {
    const raw = await transport.post(`/api/v1/admin/registries/clients/${encodeURIComponent(caseNo)}/${owner}/preview`, { changes, expected_version: expectedVersion }, { token: token() });
    return decode(RegistryMutationPreviewResponseSchema, raw, '名冊變更預覽回應結構異常');
  },
  async apply(caseNo: string, owner: Owner, changes: ClientProfileChanges | BeClassChanges, expectedVersion: number, previewFingerprint: string, reason: string, idempotencyKey = key(`client-${owner}`)): Promise<RegistryMutationReceipt> {
    const raw = await transport.post(`/api/v1/admin/registries/clients/${encodeURIComponent(caseNo)}/${owner}/apply`, { changes, expected_version: expectedVersion, preview_fingerprint: previewFingerprint, reason }, { token: token(), headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': key('registry-correlation') } });
    return decode(RegistryMutationReceiptResponseSchema, raw, '名冊變更收據回應結構異常');
  },
};
