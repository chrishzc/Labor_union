/**
 * File: audit_query_client.ts
 * Description: 以最新記憶體 Bearer 查詢伺服器遮罩的管理員稽核分頁。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  AdminAuditMaskedPageResponseSchema,
  AdminAuditMaskedDetailResponseSchema,
  type AdminAuditMaskedDetail,
  type AdminAuditMaskedPage,
  type AuditQueryParams,
} from './audit_query_schemas';
import {
  AuditQueryError,
  mapAuditQueryError,
} from './audit_query_errors';

export type { AuditQueryParams } from './audit_query_schemas';

export type AuditQueryOptions = Omit<
  RequestOptions,
  'method' | 'body' | 'token' | 'params'
>;

export interface AuditQueryClient {
  query(params?: AuditQueryParams, options?: AuditQueryOptions): Promise<AdminAuditMaskedPage>;
  detail(auditId: number, options?: AuditQueryOptions): Promise<AdminAuditMaskedDetail>;
}

function requestOptions(options?: AuditQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new AuditQueryError('AUDIT_QUERY_UNAUTHENTICATED', '請先登入。', { status: 401 });
  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }
  return { ...options, headers, token };
}

function validateParams(params: AuditQueryParams): void {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 25;
  if (!Number.isInteger(page) || page < 1) throw new AuditQueryError('AUDIT_QUERY_INVALID', 'page 必須為正整數。');
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw new AuditQueryError('AUDIT_QUERY_INVALID', 'page_size 必須為 1 至 100 的整數。');
  }
  if (params.actionPrefix !== undefined && params.actionPrefix.length > 100) {
    throw new AuditQueryError('AUDIT_QUERY_INVALID', 'action_prefix 不得超過 100 字元。');
  }
  if (params.actorQuery !== undefined && params.actorQuery.length > 100) {
    throw new AuditQueryError('AUDIT_QUERY_INVALID', 'actor_query 不得超過 100 字元。');
  }
}

export async function queryAdminAudit(
  params: AuditQueryParams = {},
  options?: AuditQueryOptions,
): Promise<AdminAuditMaskedPage> {
  validateParams(params);
  try {
    const raw = await transport.get<unknown>('/api/v1/admin/audits', {
      ...requestOptions(options),
      params: {
        page: params.page ?? 1,
        page_size: params.pageSize ?? 25,
        action_prefix: params.actionPrefix?.trim() || undefined,
        actor_query: params.actorQuery?.trim() || undefined,
      },
    });
    const decoded = AdminAuditMaskedPageResponseSchema.safeParse(raw);
    if (!decoded.success) {
      throw new ApiDecodeError(
        '遮罩稽核回應結構不符 strict contract。',
        decoded.error.issues.map((issue) => ({
          path: issue.path.join('.') || '(root)',
          message: issue.message,
          code: issue.code,
        })),
        raw,
      );
    }
    if (!decoded.data.success) {
      throw new AuditQueryError('AUDIT_QUERY_INVALID', decoded.data.error ?? decoded.data.message);
    }
    return decoded.data.data;
  } catch (error) {
    throw mapAuditQueryError(error);
  }
}

export async function queryAdminAuditDetail(
  auditId: number,
  options?: AuditQueryOptions,
): Promise<AdminAuditMaskedDetail> {
  if (!Number.isInteger(auditId) || auditId < 1) {
    throw new AuditQueryError('AUDIT_QUERY_INVALID', 'audit_id 必須為正整數。');
  }
  try {
    const raw = await transport.get<unknown>(`/api/v1/admin/audits/${auditId}`, requestOptions(options));
    const decoded = AdminAuditMaskedDetailResponseSchema.safeParse(raw);
    if (!decoded.success) {
      throw new ApiDecodeError(
        '遮罩稽核明細回應結構不符 strict contract。',
        decoded.error.issues.map((issue) => ({
          path: issue.path.join('.') || '(root)',
          message: issue.message,
          code: issue.code,
        })),
        raw,
      );
    }
    if (!decoded.data.success) {
      throw new AuditQueryError('AUDIT_QUERY_INVALID', decoded.data.error ?? decoded.data.message);
    }
    return decoded.data.data;
  } catch (error) {
    throw mapAuditQueryError(error);
  }
}

export function createAuditQueryClient(): AuditQueryClient {
  return { query: queryAdminAudit, detail: queryAdminAuditDetail };
}

export const auditQueryClient = createAuditQueryClient();
