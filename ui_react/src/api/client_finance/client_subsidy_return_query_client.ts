/** Typed, read-only case-based customer subsidy refund query. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const RowSchema = z.strictObject({
  case_no: z.string().min(1).max(50), client_name: z.string(), order_status: z.string(),
  amount_ntd: z.number().int().nonnegative().nullable(),
  due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(), is_estimate: z.boolean(),
});
const QuerySchema = z.strictObject({ rows: z.array(RowSchema), next_cursor: z.string().min(1).max(50).nullable() });
const ResponseSchema = z.strictObject({
  success: z.boolean(), message: z.string(), data: QuerySchema,
  error: z.string().nullable().optional(),
});
export type ClientSubsidyReturnQuery = z.infer<typeof QuerySchema>;
export type ClientSubsidyReturnQueryOptions = { search?: string; caseNo?: string; targetMonth?: string; afterCaseNo?: string; signal?: AbortSignal };

export const clientSubsidyReturnQueryClient = {
  async query(options: ClientSubsidyReturnQueryOptions = {}): Promise<ClientSubsidyReturnQuery> {
    const token = sessionClient.getToken();
    if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const params = new URLSearchParams({ page_size: '100' });
    const caseNo = options.caseNo?.trim();
    if (options.search?.trim()) params.set('search', options.search.trim());
    if (caseNo) params.set('case_no', caseNo);
    if (options.targetMonth) params.set('target_month', options.targetMonth);
    if (options.afterCaseNo) params.set('after_case_no', options.afterCaseNo);
    const raw = await transport.get(`/api/v1/finance-reports/client-subsidy-returns?${params}`, { signal: options.signal, token });
    const response = decodePayload(ResponseSchema, raw);
    if (!response.success) throw new ApiHttpError(400, 'CLIENT_SUBSIDY_RETURN_QUERY_FAILED', '補助退款查詢失敗。');
    const cases = response.data.rows.map(item => item.case_no);
    if (new Set(cases).size !== cases.length) throw new ApiDecodeError('補助退款查詢案件重複。');
    if (caseNo && response.data.rows.some(row => row.case_no !== caseNo)) throw new ApiDecodeError('補助退款查詢案件不一致。');
    if (options.afterCaseNo && response.data.next_cursor && response.data.next_cursor <= options.afterCaseNo) throw new ApiDecodeError('補助退款查詢游標未前進。');
    return response.data;
  },
};
