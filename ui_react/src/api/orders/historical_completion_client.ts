/**
 * File: historical_completion_client.ts
 * Description: 以 authenticated GET 讀取並 strict decode HOB-E completion projection。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import {
  HistoricalCompletionEnvelopeSchema,
  type HistoricalCompletion,
} from './historical_completion_schemas';

export const historicalCompletionPath = (caseNo: string): string =>
  `/api/v1/orders/${encodeURIComponent(caseNo)}/historical-completion`;

export interface HistoricalCompletionQueryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface HistoricalCompletionClient {
  query(caseNo: string, options?: HistoricalCompletionQueryOptions): Promise<HistoricalCompletion>;
}

export class HistoricalCompletionContractError extends Error {
  public readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
    this.name = 'HistoricalCompletionContractError';
  }
}

export async function queryHistoricalCompletion(
  caseNo: string,
  options?: HistoricalCompletionQueryOptions,
): Promise<HistoricalCompletion> {
  const identity = caseNo.trim();
  if (!identity) {
    throw new HistoricalCompletionContractError(
      'historical_completion_case_identity_missing',
      '案件編號不可為空。',
    );
  }
  const token = sessionClient.getToken();
  if (!token) {
    throw new HistoricalCompletionContractError(
      'historical_completion_unauthenticated',
      '請先登入再查詢歷史案件完成狀態。',
    );
  }
  const raw = await transport.get(historicalCompletionPath(identity), {
    token,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs ?? 30_000,
    headers: { 'X-Correlation-ID': `historical-completion-${crypto.randomUUID()}` },
  });
  const projection = decodePayload(HistoricalCompletionEnvelopeSchema, raw).data;
  if (projection.case_no !== identity) {
    throw new HistoricalCompletionContractError(
      'historical_completion_case_identity_mismatch',
      '伺服器回傳的案件與目前案件不一致。',
    );
  }
  return projection;
}

export const historicalCompletionClient: HistoricalCompletionClient = {
  query: queryHistoricalCompletion,
};
