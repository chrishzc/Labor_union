import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  ClientRegistryDetailResponseSchema, ClientRegistryPageResponseSchema,
  RegistryMutationPreviewResponseSchema, RegistryMutationReceiptResponseSchema,
  type BeClassChanges, type ClientProfileChanges, type ClientRegistryDetail,
  type ClientRegistryPage, type ClientRegistrySortBy, type ClientRegistrySortOrder,
  type RegistryMutationPreview, type RegistryMutationReceipt,
} from './client_registry_schemas';

type Owner = 'profile' | 'beclass';
export interface ClientRegistryListQuery {
  query?: string;
  multiBirthCount?: '單胞胎' | '雙胞胎';
  orderStatus?: string;
  requiresCooking?: boolean;
  sortBy?: ClientRegistrySortBy;
  sortOrder?: ClientRegistrySortOrder;
  limit?: number;
  after?: string;
  offset?: number;
}
export interface ClientRegistryExportArtifact { blob: Blob; filename: string }
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
const exportParams = (request: ClientRegistryListQuery) => {
  const params = new URLSearchParams();
  if (request.query?.trim()) params.set('query', request.query.trim());
  if (request.multiBirthCount) params.set('multi_birth_count', request.multiBirthCount);
  if (request.orderStatus?.trim()) params.set('order_status', request.orderStatus.trim());
  if (request.requiresCooking !== undefined) params.set('requires_cooking', String(request.requiresCooking));
  if (request.sortBy) params.set('sort_by', request.sortBy);
  if (request.sortOrder) params.set('sort_order', request.sortOrder);
  return params;
};
const exportFilename = (value: string | null) => {
  const match = value?.match(/filename="?([^";]+)"?/i);
  const candidate = match?.[1]?.trim();
  return candidate?.toLowerCase().endsWith('.xlsx') ? candidate : 'client-order-accounting.xlsx';
};

export const clientRegistryClient = {
  async list(request: ClientRegistryListQuery = {}): Promise<ClientRegistryPage> {
    const raw = await transport.get('/api/v1/admin/registries/clients', {
      token: token(),
      params: {
        query: request.query?.trim() || undefined,
        multi_birth_count: request.multiBirthCount,
        order_status: request.orderStatus?.trim() || undefined,
        requires_cooking: request.requiresCooking,
        sort_by: request.sortBy,
        sort_order: request.sortOrder,
        limit: request.limit ?? 100,
        after: request.after?.trim() || undefined,
        offset: request.offset,
      },
    });
    return decode(ClientRegistryPageResponseSchema, raw, '客戶名冊回應結構異常');
  },
  async query(caseNo: string): Promise<ClientRegistryDetail> {
    const raw = await transport.get(`/api/v1/admin/registries/clients/${encodeURIComponent(caseNo)}`, { token: token() });
    return decode(ClientRegistryDetailResponseSchema, raw, '客戶名冊詳情回應結構異常');
  },
  async downloadOrderAccounting(request: ClientRegistryListQuery = {}): Promise<ClientRegistryExportArtifact> {
    const params = exportParams(request);
    const suffix = params.size ? `?${params.toString()}` : '';
    const response = await fetch(`/api/v1/admin/registries/clients/export/order-accounting${suffix}`, {
      method: 'GET', headers: { Authorization: `Bearer ${token()}` },
    });
    if (!response.ok) throw new Error(`訂單帳務匯出失敗（HTTP ${response.status}）。`);
    const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
    if (!contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
      throw new Error('訂單帳務匯出回應不是 Excel 檔案。');
    }
    const blob = await response.blob();
    if (blob.size === 0) throw new Error('訂單帳務匯出檔案為空。');
    return { blob, filename: exportFilename(response.headers.get('content-disposition')) };
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
