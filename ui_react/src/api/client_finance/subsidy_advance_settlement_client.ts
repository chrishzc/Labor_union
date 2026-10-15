/** Typed Client Finance recovery of an existing union subsidy advance. */
import { z } from 'zod';
import { transport } from '../shared/transport';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const positive = z.number().int().positive();
const money = z.number().int().nonnegative();
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const Row = z.strictObject({
  advance_id: positive, case_no: z.string().min(1), client_name: z.string(),
  advanced_on: date, advance_amount_ntd: positive, government_received_ntd: money,
  received_on: date.nullable(), recovered_amount_ntd: money,
  status: z.enum(['waiting_receipt', 'ready', 'recovered', 'review_required']),
  review_reason: z.string().nullable(),
});
const Page = z.strictObject({ rows: z.array(Row), next_cursor: positive.nullable() });
const Preview = z.strictObject({
  row: Row, account_version: money, batch_version: money,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const Receipt = z.strictObject({ advance_id: positive, case_no: z.string().min(1), recovered_amount_ntd: positive, account_version: money });
const response = <T extends z.ZodTypeAny>(data: T) => z.strictObject({
  success: z.literal(true), message: z.string(), data, error: z.string().nullable().optional(),
});
export type AdvanceSettlementRow = z.infer<typeof Row>;
export type AdvanceSettlementPreview = z.infer<typeof Preview>;
export type AdvanceSettlementApply = {
  expected_account_version: number; expected_batch_version: number;
  preview_fingerprint: string; reason: string;
};
const base = '/api/v1/client-finance/subsidy-advance-recoveries';
function options(signal?: AbortSignal, key?: string) {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  return { token, signal, headers: key ? { 'Idempotency-Key': key } : undefined };
}

export const subsidyAdvanceSettlementClient = {
  async queryAll(search = '', signal?: AbortSignal): Promise<AdvanceSettlementRow[]> {
    const rows: AdvanceSettlementRow[] = [];
    const ids = new Set<number>();
    let cursor = 0;
    do {
      signal?.throwIfAborted();
      const params = new URLSearchParams({ after_id: String(cursor), page_size: '100' });
      if (search.trim()) params.set('search', search.trim());
      const page = decodePayload(response(Page), await transport.get(`${base}?${params}`, options(signal))).data;
      signal?.throwIfAborted();
      for (const row of page.rows) {
        if (ids.has(row.advance_id) || row.advance_id <= cursor) throw new ApiDecodeError('墊款查詢項目重複或游標不一致。');
        ids.add(row.advance_id); rows.push(row);
      }
      if (page.next_cursor !== null && (page.next_cursor <= cursor || !ids.has(page.next_cursor))) throw new ApiDecodeError('墊款查詢游標未前進。');
      cursor = page.next_cursor ?? 0;
    } while (cursor);
    return rows;
  },
  async preview(advanceId: number, signal?: AbortSignal): Promise<AdvanceSettlementPreview> {
    const preview = decodePayload(response(Preview), await transport.post(`${base}/${advanceId}/preview`, {}, options(signal))).data;
    if (preview.row.advance_id !== advanceId || preview.row.status !== 'ready') throw new ApiDecodeError('銷帳預覽與所選墊款不一致。');
    return preview;
  },
  async apply(advanceId: number, body: AdvanceSettlementApply, key: string, signal?: AbortSignal) {
    const receipt = decodePayload(response(Receipt), await transport.post(`${base}/${advanceId}/apply`, body, options(signal, key))).data;
    if (receipt.advance_id !== advanceId) throw new ApiDecodeError('銷帳回執與所選墊款不一致。');
    return receipt;
  },
};
