/** Read existing Client Finance roots and immutable history; never derive balances. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const amount = z.number().int().nonnegative();
const version = z.string().regex(/^(0|[1-9][0-9]*)$/);
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const summary = z.strictObject({
  case_no: z.string().min(1), account_version: version,
  open_receivable_amount_ntd: amount, open_payable_amount_ntd: amount,
  obligation_count: amount, ledger_entry_count: amount, receipt_entry_count: amount,
});
const detail = z.strictObject({
  case_no: z.string().min(1), account_version: version,
  obligations: z.array(z.strictObject({
    obligation_identity: z.string().min(1), obligation_type: z.enum(['deposit', 'first', 'second', 'refund', 'subsidy_return', 'adjustment']),
    direction: z.enum(['receivable_from_client', 'payable_to_client']), amount_due_ntd: amount,
    due_date: date.nullable(), status: z.enum(['open', 'settled', 'cancelled']), projection_version: version,
  })),
  ledger_entries: z.array(z.strictObject({
    entry_id: z.number().int().positive(), entry_type: z.enum(['receipt', 'refund', 'adjustment', 'reversal', 'subsidy_return', 'subsidy_advance']),
    amount_ntd: z.number().int().positive(), occurred_on: date, reconciliation_reference: z.string().min(1),
    reversal_of_entry_id: z.number().int().positive().nullable(), created_at: z.string(),
    allocations: z.array(z.strictObject({ obligation_identity: z.string().min(1), amount_ntd: z.number().int().positive() })),
  })),
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.string().nullable().optional() });
export type ClientFinanceHistory = z.infer<typeof detail>;
export type ClientFinanceSummary = z.infer<typeof summary>;

export const clientFinanceHistoryClient = {
  async queryAll(signal?: AbortSignal): Promise<ClientFinanceSummary[]> {
    const data = decodePayload(envelope(z.strictObject({ cases: z.array(summary) })), await transport.get('/api/v1/client-payments', { token: token(), signal })).data.cases;
    if (new Set(data.map(row => row.case_no)).size !== data.length) throw new ApiDecodeError('案件帳務清單重複。');
    return data;
  },
  async query(caseNo: string, signal?: AbortSignal): Promise<ClientFinanceHistory> {
    const data = decodePayload(envelope(detail), await transport.get(`/api/v1/client-payments/${encodeURIComponent(caseNo)}`, { token: token(), signal })).data;
    if (data.case_no !== caseNo || new Set(data.ledger_entries.map(row => row.entry_id)).size !== data.ledger_entries.length
      || new Set(data.obligations.map(row => row.obligation_identity)).size !== data.obligations.length) throw new ApiDecodeError('案件帳務明細不一致。');
    return data;
  },
};
function token() {
  const value = sessionClient.getToken();
  if (!value) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  return value;
}
