/**
 * File: finance_import_query_client.ts
 * Description: 以fresh Session執行Finance Import bounded GET並嚴格驗證identity與cursor。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { FinanceImportBatchListResponseSchema, FinanceImportManifestSchema, FinanceImportReviewPageSchema, FinanceImportRunPageSchema, financeEnvelope, type FinanceImportBatchSummary, type FinanceImportManifest, type FinanceImportReviewPage, type FinanceImportRunPage } from './finance_import_query_schemas';
import { FinanceImportQueryError, mapFinanceImportQueryError } from './finance_import_query_errors';
export interface FinanceImportQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
function options(source?: FinanceImportQueryOptions) { const token = sessionClient.getToken(); if (!token) throw new FinanceImportQueryError('FINANCE_IMPORT_UNAUTHENTICATED', '請先登入。', false, 401); return { signal: source?.signal, timeoutMs: source?.timeoutMs, baseUrl: source?.baseUrl, token }; }
function identity(value: string) { const normalized = value.trim(); if (!normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_VALIDATION', 'batch identity不得為空。'); return encodeURIComponent(normalized); }
async function decode<T>(promise: Promise<unknown>, schema: ReturnType<typeof financeEnvelope>, label: string): Promise<T> { try { const raw = await promise; const parsed = schema.safeParse(raw); if (!parsed.success) throw new ApiDecodeError(`${label}回應結構異常。`, parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw); if (!parsed.data.success) throw new FinanceImportQueryError('FINANCE_IMPORT_FAILURE', parsed.data.error ?? parsed.data.message); return parsed.data.data as T; } catch (error) { throw mapFinanceImportQueryError(error); } }
export const financeImportQueryClient = {
  async listBatches(query: { limit?: number; beforeBatchId?: number } = {}, source?: FinanceImportQueryOptions): Promise<FinanceImportBatchSummary[]> {
    const limit = query.limit ?? 50; if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new FinanceImportQueryError('FINANCE_IMPORT_VALIDATION', 'limit必須介於1至100。');
    try { const raw = await transport.get<unknown>('/api/v1/finance-import/batches', { ...options(source), params: { limit, before_batch_id: query.beforeBatchId } }); const parsed = FinanceImportBatchListResponseSchema.safeParse(raw); if (!parsed.success) throw new ApiDecodeError('Finance Import批次回應結構異常。', parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw); if (!parsed.data.success) throw new FinanceImportQueryError('FINANCE_IMPORT_FAILURE', parsed.data.error ?? parsed.data.message); const ids = parsed.data.data.map((item) => item.batch_id); if (new Set(ids).size !== ids.length) throw new FinanceImportQueryError('FINANCE_IMPORT_DUPLICATE_BATCH', 'batch identity重複。'); return parsed.data.data; } catch (error) { throw mapFinanceImportQueryError(error); }
  },
  getManifest(batchIdentity: string, source?: FinanceImportQueryOptions): Promise<FinanceImportManifest> { return decode(transport.get<unknown>(`/api/v1/finance-import/batches/${identity(batchIdentity)}/manifest`, options(source)), financeEnvelope(FinanceImportManifestSchema), 'Manifest'); },
  listReviewRows(batchIdentity: string, source?: FinanceImportQueryOptions): Promise<FinanceImportReviewPage> { return decode(transport.get<unknown>(`/api/v1/finance-import/batches/${identity(batchIdentity)}/review-rows`, { ...options(source), params: { limit: 50 } }), financeEnvelope(FinanceImportReviewPageSchema), 'Review rows'); },
  listReprocessRuns(batchIdentity: string, source?: FinanceImportQueryOptions): Promise<FinanceImportRunPage> { return decode(transport.get<unknown>(`/api/v1/finance-import/batches/${identity(batchIdentity)}/reprocess-runs`, { ...options(source), params: { limit: 25 } }), financeEnvelope(FinanceImportRunPageSchema), 'Reprocess runs'); },
};
