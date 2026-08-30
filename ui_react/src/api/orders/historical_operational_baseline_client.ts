/**
 * File: historical_operational_baseline_client.ts
 * Description: 以 authenticated GET 讀取 Orders owned Historical Operational Baseline Query。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';
import {
  HistoricalOperationalBaselineEnvelopeSchema,
  type HistoricalOperationalBaseline,
} from './historical_operational_baseline_schemas';

export interface HistoricalOperationalBaselineQueryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface HistoricalOperationalBaselineClient {
  queryByCase(
    caseNo: string,
    options?: HistoricalOperationalBaselineQueryOptions,
  ): Promise<HistoricalOperationalBaseline>;
}

export class HistoricalOperationalBaselineUnavailableError extends Error {
  public readonly name = 'HistoricalOperationalBaselineUnavailableError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  public readonly causeValue?: unknown;

  constructor(
    code: string,
    message: string,
    retryable: boolean,
    status?: number,
    causeValue?: unknown,
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    this.causeValue = causeValue;
  }
}

export const historicalOperationalBaselinePath = (caseNo: string): string =>
  `/api/v1/orders/${encodeURIComponent(caseNo)}/historical-operational-baseline`;

export function mapHistoricalOperationalBaselineUnavailable(
  error: unknown,
): HistoricalOperationalBaselineUnavailableError {
  if (error instanceof HistoricalOperationalBaselineUnavailableError) return error;
  if (error instanceof ApiAbortError) {
    return new HistoricalOperationalBaselineUnavailableError(
      'historical_operational_baseline_aborted',
      error.message,
      false,
      undefined,
      error,
    );
  }
  if (error instanceof ApiHttpError) {
    return new HistoricalOperationalBaselineUnavailableError(
      error.code,
      error.message,
      error.retryable,
      error.status,
      error,
    );
  }
  if (error instanceof ApiDecodeError) {
    return new HistoricalOperationalBaselineUnavailableError(
      'historical_operational_baseline_contract_unavailable',
      '歷史案件作業基準 Query 契約無法驗證。',
      false,
      undefined,
      error,
    );
  }
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    return new HistoricalOperationalBaselineUnavailableError(
      'historical_operational_baseline_unavailable',
      '歷史案件作業基準 Query 目前無法使用。',
      true,
      undefined,
      error,
    );
  }
  return new HistoricalOperationalBaselineUnavailableError(
    'historical_operational_baseline_unavailable',
    '歷史案件作業基準 Query 目前無法使用。',
    false,
    undefined,
    error,
  );
}

export async function queryHistoricalOperationalBaselineByCase(
  caseNo: string,
  options?: HistoricalOperationalBaselineQueryOptions,
): Promise<HistoricalOperationalBaseline> {
  const identity = caseNo.trim();
  if (!identity || identity.length > 50 || /\s/.test(identity)) {
    throw new HistoricalOperationalBaselineUnavailableError(
      'historical_operational_baseline_case_invalid',
      '案件編號格式無效，無法讀取歷史案件作業基準。',
      false,
    );
  }
  const token = sessionClient.getToken();
  if (!token) {
    throw new HistoricalOperationalBaselineUnavailableError(
      'historical_operational_baseline_unauthenticated',
      '請先登入再讀取歷史案件作業基準。',
      false,
      401,
    );
  }

  try {
    const raw = await transport.get<unknown>(historicalOperationalBaselinePath(identity), {
      token,
      signal: options?.signal,
      timeoutMs: options?.timeoutMs ?? 30_000,
      baseUrl: options?.baseUrl,
    });
    const baseline = decodePayload(HistoricalOperationalBaselineEnvelopeSchema, raw).data;
    if (baseline.case_no !== identity) {
      throw new ApiDecodeError('伺服器回傳的 Orders baseline 不屬於目前案件。', [], raw);
    }
    return baseline;
  } catch (error) {
    throw mapHistoricalOperationalBaselineUnavailable(error);
  }
}

export const historicalOperationalBaselineClient: HistoricalOperationalBaselineClient = {
  queryByCase: queryHistoricalOperationalBaselineByCase,
};
