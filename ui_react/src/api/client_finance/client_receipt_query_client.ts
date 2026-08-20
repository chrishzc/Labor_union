/**
 * File: client_receipt_query_client.ts
 * Description: 以fresh Session執行單一案件Client Receipt唯讀GET並嚴格驗證identity。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { ClientReceiptQueryResponseSchema, type ClientReceiptQuery } from './client_receipt_query_schemas';
import { ClientReceiptQueryError, mapClientReceiptQueryError } from './client_receipt_query_errors';

export interface ClientReceiptQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface ClientReceiptQueryClient { query(caseNo: string, options?: ClientReceiptQueryOptions): Promise<ClientReceiptQuery>; }

class DefaultClientReceiptQueryClient implements ClientReceiptQueryClient {
  async query(caseNo: string, options?: ClientReceiptQueryOptions): Promise<ClientReceiptQuery> {
    const normalized = caseNo.trim();
    if (!normalized) throw new ClientReceiptQueryError('CLIENT_RECEIPT_VALIDATION', '案件編號不得為空。');
    const token = sessionClient.getToken();
    if (!token) throw new ClientReceiptQueryError('CLIENT_RECEIPT_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>(
        `/api/v1/orders/${encodeURIComponent(normalized)}/client-finance/receipt-reconciliation`,
        { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, token }
      );
      const decoded = ClientReceiptQueryResponseSchema.safeParse(raw);
      if (!decoded.success) throw new ApiDecodeError('Client Receipt回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
      if (!decoded.data.success) throw new ClientReceiptQueryError('CLIENT_RECEIPT_FAILURE', decoded.data.error ?? decoded.data.message);
      const result = decoded.data.data;
      if (result.case_no !== normalized) throw new ClientReceiptQueryError('CLIENT_RECEIPT_IDENTITY_MISMATCH', '案件identity與request不一致。');
      if (new Set(result.bank_facts.map((item) => item.finance_import_row_id)).size !== result.bank_facts.length) throw new ClientReceiptQueryError('CLIENT_RECEIPT_DUPLICATE_FACT', '銀行fact identity重複。');
      if (new Set(result.obligations.map((item) => item.obligation_identity)).size !== result.obligations.length) throw new ClientReceiptQueryError('CLIENT_RECEIPT_DUPLICATE_OBLIGATION', '義務identity重複。');
      return result;
    } catch (error) { throw mapClientReceiptQueryError(error); }
  }
}

export const clientReceiptQueryClient: ClientReceiptQueryClient = new DefaultClientReceiptQueryClient();
