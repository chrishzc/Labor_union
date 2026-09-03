/**
 * File: subsidy_report_query_client.ts
 * Description: 以 fresh Session 查詢季度或年度補助報表並驗證期間、完整分區、aggregate 與 canonical data。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { SubsidyReportResponseSchema, type SubsidyReportPreview } from './subsidy_report_query_schemas';
import { SubsidyReportQueryError, mapSubsidyReportQueryError } from './subsidy_report_query_errors';
export type SubsidyReportQuery = { kind: 'quarterly'; applicationYear: number; quarter: number } | { kind: 'annual'; applicationYear: number };
export interface SubsidyReportQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
function validate(query: SubsidyReportQuery) { if (!Number.isInteger(query.applicationYear) || query.applicationYear < 1912) throw new SubsidyReportQueryError('SUBSIDY_REPORT_VALIDATION', 'applicationYear無效。'); if (query.kind === 'quarterly' && (!Number.isInteger(query.quarter) || query.quarter < 1 || query.quarter > 4)) throw new SubsidyReportQueryError('SUBSIDY_REPORT_VALIDATION', 'quarter無效。'); }
function assertView(view: SubsidyReportPreview, query: SubsidyReportQuery) {
  if (view.period_kind !== query.kind || view.application_year !== query.applicationYear || view.quarter !== (query.kind === 'quarterly' ? query.quarter : null)) throw new SubsidyReportQueryError('SUBSIDY_REPORT_PERIOD_MISMATCH', '報表period與request不一致。');
  const partitionKinds = new Set(view.partitions.map((item) => item.citizen_kind));
  if (partitionKinds.size !== view.partitions.length) throw new SubsidyReportQueryError('SUBSIDY_REPORT_DUPLICATE_PARTITION', 'partition重複。');
  if (!partitionKinds.has('general') || !partitionKinds.has('subsidized')) throw new SubsidyReportQueryError('SUBSIDY_REPORT_INCOMPLETE_PARTITIONS', '報表缺少必要partition。');
  const rows = view.partitions.flatMap((item) => item.rows);
  for (const partition of view.partitions) { if (partition.row_count !== partition.rows.length || partition.total_amount_ntd !== partition.rows.reduce((sum, row) => sum + row.subsidy_amount_ntd, 0)) throw new SubsidyReportQueryError('SUBSIDY_REPORT_AGGREGATE_MISMATCH', 'partition aggregate不一致。'); }
  if (view.total_row_count !== rows.length || view.total_amount_ntd !== rows.reduce((sum, row) => sum + row.subsidy_amount_ntd, 0)) throw new SubsidyReportQueryError('SUBSIDY_REPORT_AGGREGATE_MISMATCH', 'report aggregate不一致。');
  return view;
}
export const subsidyReportQueryClient = {
  async query(query: SubsidyReportQuery, options?: SubsidyReportQueryOptions): Promise<SubsidyReportPreview> {
    validate(query); const token = sessionClient.getToken(); if (!token) throw new SubsidyReportQueryError('SUBSIDY_REPORT_UNAUTHENTICATED', '請先登入。', false, 401);
    const path = `/api/v1/finance-reports/subsidy-reconciliation/${query.kind}`;
    const params = query.kind === 'quarterly' ? { application_year: query.applicationYear, quarter: query.quarter } : { application_year: query.applicationYear };
    try { const raw = await transport.get<unknown>(path, { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, token, params }); const decoded = SubsidyReportResponseSchema.safeParse(raw); if (!decoded.success) throw new ApiDecodeError('補助報表回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw); if (!decoded.data.success) throw new SubsidyReportQueryError('SUBSIDY_REPORT_FAILURE', decoded.data.error ?? decoded.data.message); return assertView(decoded.data.data, query); } catch (error) { throw mapSubsidyReportQueryError(error); }
  },
};
