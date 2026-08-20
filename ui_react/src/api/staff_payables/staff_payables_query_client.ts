/**
 * File: staff_payables_query_client.ts
 * Description: 以fresh Session執行單一Staff Payables唯讀GET並驗證identity唯一性。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { StaffPayablesResponseSchema, type StaffPayablesQuery } from './staff_payables_query_schemas';
import { StaffPayablesQueryError, mapStaffPayablesQueryError } from './staff_payables_query_errors';
export interface StaffPayablesQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface StaffPayablesQueryClient { query(staffId: number, options?: StaffPayablesQueryOptions): Promise<StaffPayablesQuery>; }
class DefaultStaffPayablesQueryClient implements StaffPayablesQueryClient {
  async query(staffId: number, options?: StaffPayablesQueryOptions): Promise<StaffPayablesQuery> {
    if (!Number.isInteger(staffId) || staffId <= 0) throw new StaffPayablesQueryError('STAFF_PAYABLES_VALIDATION', 'staffId必須是正整數。');
    const token = sessionClient.getToken();
    if (!token) throw new StaffPayablesQueryError('STAFF_PAYABLES_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>(`/api/v1/staff-payables/${staffId}`, { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, token });
      const decoded = StaffPayablesResponseSchema.safeParse(raw);
      if (!decoded.success) throw new ApiDecodeError('Staff Payables回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
      if (!decoded.data.success) throw new StaffPayablesQueryError('STAFF_PAYABLES_FAILURE', decoded.data.error ?? decoded.data.message);
      const result = decoded.data.data;
      if (result.staff_id !== staffId) throw new StaffPayablesQueryError('STAFF_PAYABLES_IDENTITY_MISMATCH', 'staff identity與request不一致。');
      if (new Set(result.obligations.map((item) => item.obligation_identity)).size !== result.obligations.length) throw new StaffPayablesQueryError('STAFF_PAYABLES_DUPLICATE_OBLIGATION', '義務identity重複。');
      if (new Set(result.events.map((item) => item.id)).size !== result.events.length) throw new StaffPayablesQueryError('STAFF_PAYABLES_DUPLICATE_EVENT', '事件identity重複。');
      return result;
    } catch (error) { throw mapStaffPayablesQueryError(error); }
  }
}
export const staffPayablesQueryClient: StaffPayablesQueryClient = new DefaultStaffPayablesQueryClient();
