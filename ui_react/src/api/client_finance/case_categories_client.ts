/** Case identity projection shared by finance lists; no case-number guessing. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiDecodeError } from '../shared/typed_errors';

export type FinanceCaseCategory = 'subsidy' | 'non_citizen';
export type FinanceCaseFilter = FinanceCaseCategory | 'all';
const response = z.strictObject({ success: z.literal(true), message: z.string(), error: z.string().nullable(),
  data: z.array(z.strictObject({ case_no: z.string().min(1), category: z.enum(['subsidy', 'non_citizen']) })) });
export const caseCategoriesClient = {
  async query(signal?: AbortSignal): Promise<Map<string, FinanceCaseCategory>> {
    const token = sessionClient.getToken();
    if (!token) throw new ApiDecodeError('請先登入。');
    const data = decodePayload(response, await transport.get('/api/v1/client-payments/case-categories', { token, signal })).data;
    if (new Set(data.map(row => row.case_no)).size !== data.length) throw new ApiDecodeError('案件類別資料重複。');
    return new Map(data.map(row => [row.case_no, row.category]));
  },
};
