/**
 * File: historical_baseline_projector_client.ts
 * Description: 以 authenticated GET 依同一 case strict readback Historical Baseline Projector。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';
import {
  HistoricalBaselineProjectorEnvelopeSchema,
  type HistoricalBaselineProjectorReadModel,
} from './historical_baseline_projector_schemas';

export interface HistoricalBaselineProjectorQueryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface HistoricalBaselineProjectorClient {
  queryByCase(
    caseNo: string,
    options?: HistoricalBaselineProjectorQueryOptions,
  ): Promise<HistoricalBaselineProjectorReadModel>;
}

export class HistoricalBaselineProjectorUnavailableError extends Error {
  public readonly name = 'HistoricalBaselineProjectorUnavailableError';
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

export const historicalBaselineProjectorPath = (caseNo: string): string =>
  `/api/v1/orders/${encodeURIComponent(caseNo)}/historical-baseline-projector`;

export function mapHistoricalBaselineProjectorUnavailable(
  error: unknown,
): HistoricalBaselineProjectorUnavailableError {
  if (error instanceof HistoricalBaselineProjectorUnavailableError) return error;
  if (error instanceof ApiAbortError) {
    return new HistoricalBaselineProjectorUnavailableError(
      'historical_baseline_projection_aborted',
      error.message,
      false,
      undefined,
      error,
    );
  }
  if (error instanceof ApiHttpError) {
    return new HistoricalBaselineProjectorUnavailableError(
      error.code,
      error.message,
      error.retryable,
      error.status,
      error,
    );
  }
  if (error instanceof ApiDecodeError) {
    return new HistoricalBaselineProjectorUnavailableError(
      'historical_baseline_projection_contract_unavailable',
      '歷史基線投影回讀契約無法驗證。',
      false,
      undefined,
      error,
    );
  }
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    return new HistoricalBaselineProjectorUnavailableError(
      'historical_baseline_projection_unavailable',
      '歷史基線投影回讀目前無法使用。',
      true,
      undefined,
      error,
    );
  }
  return new HistoricalBaselineProjectorUnavailableError(
    'historical_baseline_projection_unavailable',
    '歷史基線投影回讀目前無法使用。',
    false,
    undefined,
    error,
  );
}

export async function queryHistoricalBaselineProjectorByCase(
  caseNo: string,
  options?: HistoricalBaselineProjectorQueryOptions,
): Promise<HistoricalBaselineProjectorReadModel> {
  const identity = caseNo.trim();
  if (!identity || identity.length > 50 || /\s/.test(identity)) {
    throw new HistoricalBaselineProjectorUnavailableError(
      'historical_baseline_projection_case_invalid',
      '案件編號格式無效，無法讀取歷史基線投影。',
      false,
    );
  }
  const token = sessionClient.getToken();
  if (!token) {
    throw new HistoricalBaselineProjectorUnavailableError(
      'historical_baseline_projection_unauthenticated',
      '請先登入再讀取歷史基線投影。',
      false,
      401,
    );
  }

  const endpoint = historicalBaselineProjectorPath(identity);
  try {
    const raw = await transport.get<unknown>(endpoint, {
      token,
      signal: options?.signal,
      timeoutMs: options?.timeoutMs ?? 30_000,
      baseUrl: options?.baseUrl,
    });
    const decoded = HistoricalBaselineProjectorEnvelopeSchema.safeParse(raw);
    if (!decoded.success) {
      throw new ApiDecodeError(
        `歷史基線投影回應契約驗證失敗: ${decoded.error.issues.map((issue) => issue.path.join('.') || '(root)').join(', ')}`,
        decoded.error.issues.map((issue) => ({
          path: issue.path.join('.') || '(root)',
          message: issue.message,
          code: issue.code,
        })),
        raw,
      );
    }
    const projection = decoded.data.data;
    if (projection.receipt !== null && projection.receipt.case_no !== identity) {
      throw new ApiDecodeError('伺服器回傳的 projector receipt 不屬於目前案件。', [], raw);
    }
    if (projection.current_alert !== null && projection.current_alert.display.case_no !== identity) {
      throw new ApiDecodeError('伺服器回傳的 current alert 不屬於目前案件。', [], raw);
    }
    return projection;
  } catch (error) {
    throw mapHistoricalBaselineProjectorUnavailable(error);
  }
}

export const historicalBaselineProjectorClient: HistoricalBaselineProjectorClient = {
  queryByCase: queryHistoricalBaselineProjectorByCase,
};
