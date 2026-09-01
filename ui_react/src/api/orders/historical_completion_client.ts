/**
 * File: historical_completion_client.ts
 * Description: 以 authenticated GET 讀取並 strict decode HOB-E completion projection。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import {
  HistoricalCompletionEnvelopeSchema,
  HistoricalCompletionPreviewEnvelopeSchema,
  HistoricalCompletionReceiptEnvelopeSchema,
  type HistoricalCompletion,
  type HistoricalCompletionPreview,
  type HistoricalCompletionReceipt,
} from './historical_completion_schemas';

export const historicalCompletionPath = (caseNo: string): string =>
  `/api/v1/orders/${encodeURIComponent(caseNo)}/historical-completion`;

export interface HistoricalCompletionQueryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface HistoricalCompletionClient {
  query(caseNo: string, options?: HistoricalCompletionQueryOptions): Promise<HistoricalCompletion>;
  preview(caseNo: string): Promise<HistoricalCompletionPreview>;
  apply(
    preview: HistoricalCompletionPreview,
    reason: string,
  ): Promise<HistoricalCompletionReceipt>;
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

function mutationOptions(headers: Record<string, string>) {
  const token = sessionClient.getToken();
  if (!token) {
    throw new HistoricalCompletionContractError(
      'historical_completion_unauthenticated',
      '請先登入再處理歷史案件帳務完成。',
    );
  }
  return { token, timeoutMs: 30_000, headers };
}

export async function previewHistoricalCompletion(
  caseNo: string,
): Promise<HistoricalCompletionPreview> {
  const identity = caseNo.trim();
  if (!identity) {
    throw new HistoricalCompletionContractError(
      'historical_completion_case_identity_missing',
      '案件編號不可為空。',
    );
  }
  const raw = await transport.post(
    `${historicalCompletionPath(identity)}/preview`,
    {},
    mutationOptions({
      'X-Correlation-ID': `historical-completion-preview-${crypto.randomUUID()}`,
    }),
  );
  const preview = decodePayload(HistoricalCompletionPreviewEnvelopeSchema, raw).data;
  if (preview.case_no !== identity) {
    throw new HistoricalCompletionContractError(
      'historical_completion_case_identity_mismatch',
      '伺服器回傳的案件與目前案件不一致。',
    );
  }
  return preview;
}

export async function applyHistoricalCompletion(
  preview: HistoricalCompletionPreview,
  reason: string,
): Promise<HistoricalCompletionReceipt> {
  const normalizedReason = reason.trim();
  if (!normalizedReason) {
    throw new HistoricalCompletionContractError(
      'historical_completion_reason_missing',
      '請填寫確認原因。',
    );
  }
  const raw = await transport.post(
    `${historicalCompletionPath(preview.case_no)}/apply`,
    {
      expected_order_version: preview.expected_order_version,
      expected_client_finance_version: preview.expected_client_finance_version,
      expected_source_versions: preview.expected_source_versions,
      preview_fingerprint: preview.preview_fingerprint,
      reason: normalizedReason,
    },
    mutationOptions({
      'Idempotency-Key': `historical-completion-${crypto.randomUUID()}`,
      'X-Correlation-ID': `historical-completion-apply-${crypto.randomUUID()}`,
    }),
  );
  const receipt = decodePayload(HistoricalCompletionReceiptEnvelopeSchema, raw).data;
  if (receipt.case_no !== preview.case_no) {
    throw new HistoricalCompletionContractError(
      'historical_completion_case_identity_mismatch',
      '伺服器回傳的案件與目前案件不一致。',
    );
  }
  return receipt;
}

export const historicalCompletionClient: HistoricalCompletionClient = {
  query: queryHistoricalCompletion,
  preview: previewHistoricalCompletion,
  apply: applyHistoricalCompletion,
};
