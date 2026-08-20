/**
 * File: accounts_payable_query_client.ts
 * Description: 以fresh Session查詢單月Accounts Payable masked preview並驗證aggregate。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { AccountsPayableResponseSchema, type AccountsPayablePreview } from './accounts_payable_query_schemas';
import { AccountsPayableQueryError, mapAccountsPayableQueryError } from './accounts_payable_query_errors';
export interface AccountsPayableQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface AccountsPayableQueryClient { query(targetMonth: string, options?: AccountsPayableQueryOptions): Promise<AccountsPayablePreview>; }
class DefaultAccountsPayableQueryClient implements AccountsPayableQueryClient {
  async query(targetMonth: string, options?: AccountsPayableQueryOptions): Promise<AccountsPayablePreview> {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth)) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_VALIDATION', 'targetMonth必須是YYYY-MM。');
    const token = sessionClient.getToken();
    if (!token) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>('/api/v1/finance-reports/accounts-payable', { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, token, params: { target_month: targetMonth, view: 'summary' } });
      const decoded = AccountsPayableResponseSchema.safeParse(raw);
      if (!decoded.success) throw new ApiDecodeError('Accounts Payable回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
      if (!decoded.data.success) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_FAILURE', decoded.data.error ?? decoded.data.message);
      const result = decoded.data.data;
      if (result.row_count !== result.rows.length) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_COUNT_MISMATCH', 'row_count與rows不一致。');
      if (result.rows.reduce((sum, row) => sum + row.amount_ntd, 0) !== result.total_amount_ntd) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_TOTAL_MISMATCH', 'total_amount_ntd與rows不一致。');
      return result;
    } catch (error) { throw mapAccountsPayableQueryError(error); }
  }
}
export const accountsPayableQueryClient: AccountsPayableQueryClient = new DefaultAccountsPayableQueryClient();
