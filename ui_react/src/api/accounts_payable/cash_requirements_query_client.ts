/** Typed, read-only cash requirements; amounts come from their accounting owners. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const RowSchema = z.strictObject({
  row_id: z.string().min(1), case_no: z.string().min(1).max(50), recipient_name: z.string().nullable(),
  payment_type: z.enum(['staff_payable', 'client_refund', 'client_subsidy_return']),
  certainty: z.enum(['estimated', 'confirmed']),
  source: z.enum(['staff_obligation', 'historical_payroll', 'missing_payroll', 'client_refund', 'subsidy_estimate']),
  source_amount_ntd: z.number().int().nonnegative().nullable(), unpaid_amount_ntd: z.number().int().nonnegative().nullable(),
  payment_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(), date_is_estimate: z.boolean(),
  pending_reasons: z.array(z.string().min(1)),
});
const PageSchema = z.strictObject({ rows: z.array(RowSchema), next_cursor: z.string().min(1).max(50).nullable() });
const ResponseSchema = z.strictObject({ success: z.boolean(), message: z.string(), data: PageSchema, error: z.string().nullable().optional() });
export type CashRequirementRow = z.infer<typeof RowSchema>;

export const cashRequirementsQueryClient = {
  async queryAll(signal?: AbortSignal): Promise<CashRequirementRow[]> {
    const token = sessionClient.getToken();
    if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const rows: CashRequirementRow[] = [];
    const identities = new Set<string>();
    let cursor: string | null = null;
    do {
      signal?.throwIfAborted();
      const params: Record<string, string | number> = { page_size: 100 };
      if (cursor) params.after_case_no = cursor;
      const raw = await transport.get('/api/v1/finance-reports/accounts-payable/cash-requirements', { token, signal, params });
      const response = decodePayload(ResponseSchema, raw);
      if (!response.success) throw new ApiHttpError(400, 'CASH_REQUIREMENTS_QUERY_FAILED', '預估資金需求查詢失敗。');
      for (const row of response.data.rows) {
        if (identities.has(row.row_id) || (cursor && row.case_no <= cursor)) throw new ApiDecodeError('預估資金需求查詢項目重複或案件順序異常。');
        identities.add(row.row_id); rows.push(row);
      }
      const next = response.data.next_cursor;
      if (next && ((cursor && next <= cursor) || response.data.rows.some(row => row.case_no > next))) throw new ApiDecodeError('預估資金需求查詢游標異常。');
      cursor = next;
    } while (cursor);
    signal?.throwIfAborted();
    return rows;
  },
};
