/**
 * File: accounts_payable_query_client.ts
 * Description: 以fresh Session查詢單月Accounts Payable canonical preview並驗證aggregate。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { AccountsPayableResponseSchema, CaseStaffPayableAuditResponseSchema, HistoricalPayableLookupResponseSchema, type AccountsPayablePreview, type CaseStaffPayableAudit, type HistoricalPayableAuditItem } from './accounts_payable_query_schemas';
import { AccountsPayableQueryError, mapAccountsPayableQueryError } from './accounts_payable_query_errors';
export interface AccountsPayableQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface AccountsPayableQueryClient {
  query(targetMonth: string, options?: AccountsPayableQueryOptions): Promise<AccountsPayablePreview>;
  queryCase(caseNo: string, targetMonth: string, options?: AccountsPayableQueryOptions): Promise<CaseStaffPayableAudit>;
  lookupHistorical(keyword: string, targetMonth: string, signal?: AbortSignal): Promise<HistoricalPayableAuditItem[]>;
  recordHistoricalUnpaid(caseNo: string, command: HistoricalUnpaidPayableCommand): Promise<void>;
  synchronizeHistorical(caseNo: string): Promise<string | undefined>;
}
export type HistoricalUnpaidPayableCommand = {
  staff_id: number; obligation_identity: string | null; expected_event_id: number | null;
  amount_ntd: number; due_date: string | null; evidence: string; confirmed_unpaid: true; key: string;
};

let correlationSequence = 0;

function nextCorrelationId(): string {
  correlationSequence += 1;
  return `accounts-payable-query-${correlationSequence.toString(36)}`;
}

class DefaultAccountsPayableQueryClient implements AccountsPayableQueryClient {
  async lookupHistorical(keyword: string, targetMonth: string, signal?: AbortSignal) {
    const raw = await transport.get<unknown>('/api/v1/finance-reports/accounts-payable/historical-lookup', {
      signal, token: sessionClient.getToken(), params: { keyword, target_month: targetMonth },
    });
    return HistoricalPayableLookupResponseSchema.parse(raw).data;
  }

  async recordHistoricalUnpaid(caseNo: string, command: HistoricalUnpaidPayableCommand) {
    await transport.post(`/api/v1/orders/${encodeURIComponent(caseNo)}/payroll/historical-unpaid-payable`, command, {
      token: sessionClient.getToken(),
    });
  }

  async synchronizeHistorical(caseNo: string) {
    const result = await transport.post<{ success: boolean; data?: { details: { action: string; reason?: string }[] } }>(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/payroll/sync-historical-baseline-obligations`,
      undefined, { token: sessionClient.getToken() },
    );
    if (!result.success) throw new Error('historical_payroll_sync_failed');
    const detail = result.data?.details[0];
    return detail?.action === 'skipped' ? detail.reason : detail?.action;
  }

  async query(targetMonth: string, options?: AccountsPayableQueryOptions): Promise<AccountsPayablePreview> {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth)) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_VALIDATION', 'targetMonth必須是YYYY-MM。');
    const token = sessionClient.getToken();
    if (!token) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>('/api/v1/finance-reports/accounts-payable', {
        signal: options?.signal,
        timeoutMs: options?.timeoutMs,
        baseUrl: options?.baseUrl,
        token,
        headers: { 'X-Correlation-ID': nextCorrelationId() },
        params: { target_month: targetMonth, view: 'summary' },
      });
      const decoded = AccountsPayableResponseSchema.safeParse(raw);
      if (!decoded.success) throw new ApiDecodeError('Accounts Payable回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
      if (!decoded.data.success) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_FAILURE', decoded.data.error ?? decoded.data.message);
      const result = decoded.data.data;
      if (result.row_count !== result.rows.length) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_COUNT_MISMATCH', 'row_count與rows不一致。');
      if (result.rows.reduce((sum, row) => sum + row.amount_ntd, 0) !== result.total_amount_ntd) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_TOTAL_MISMATCH', 'total_amount_ntd與rows不一致。');
      return result;
    } catch (error) { throw mapAccountsPayableQueryError(error); }
  }

  async queryCase(caseNo: string, targetMonth: string, options?: AccountsPayableQueryOptions): Promise<CaseStaffPayableAudit> {
    if (!caseNo.trim()) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_VALIDATION', 'caseNo不得為空白。');
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth)) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_VALIDATION', 'targetMonth必須是YYYY-MM。');
    const token = sessionClient.getToken();
    if (!token) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>(`/api/v1/finance-reports/accounts-payable/cases/${encodeURIComponent(caseNo)}`, {
        signal: options?.signal,
        timeoutMs: options?.timeoutMs,
        baseUrl: options?.baseUrl,
        token,
        headers: { 'X-Correlation-ID': nextCorrelationId() },
        params: { target_month: targetMonth },
      });
      const decoded = CaseStaffPayableAuditResponseSchema.safeParse(raw);
      if (!decoded.success) throw new ApiDecodeError('本案月嫂應付款查核回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
      if (!decoded.data.success) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_FAILURE', decoded.data.error ?? decoded.data.message);
      if (decoded.data.data.case_no !== caseNo) throw new AccountsPayableQueryError('ACCOUNTS_PAYABLE_IDENTITY_MISMATCH', '案件編號與查詢不一致。');
      return decoded.data.data;
    } catch (error) { throw mapAccountsPayableQueryError(error); }
  }
}
export const accountsPayableQueryClient: AccountsPayableQueryClient = new DefaultAccountsPayableQueryClient();
