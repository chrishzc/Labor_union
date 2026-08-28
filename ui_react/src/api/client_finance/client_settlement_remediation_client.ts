/**
 * File: client_settlement_remediation_client.ts
 * Description: 封裝客戶應收／應付 owner Query、Preview 與 Apply，不推算解除狀態。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../shared/typed_errors';
import {
  ClientPayablePreviewResponseSchema, ClientPayableReceiptResponseSchema,
  ClientReceiptPreviewResponseSchema, ClientReceiptReceiptResponseSchema,
  ClientSettlementQueryResponseSchema,
  type ClientPayablePreview, type ClientPayableReceipt, type ClientPaymentStage,
  type ClientReceiptPreview, type ClientReceiptReceipt, type ClientSettlementQuery,
} from './client_settlement_remediation_schemas';

export type ClientSettlementPayableKind = 'refund' | 'subsidy_return';
export interface ClientSettlementOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface ClientSettlementApplyOptions extends ClientSettlementOptions { idempotencyKey: string; correlationId: string; }
export interface ReceiptSelection { payment_stage: ClientPaymentStage; finance_import_row_ids: number[]; obligation_identities: string[]; }
export interface PayableSelection { finance_import_row_ids: number[]; obligation_identities: string[]; allow_partial_refund_recovery: false; }

export class ClientSettlementRemediationError extends ApiError {
  public readonly name = 'ClientSettlementRemediationError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  constructor(code: string, message: string, retryable = false, status?: number) {
    super(message); this.code = code; this.retryable = retryable; this.status = status;
  }
}

function options(input: ClientSettlementOptions, correlationId: string, idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ClientSettlementRemediationError('CLIENT_SETTLEMENT_UNAUTHENTICATED', '請先登入。', false, 401);
  const headers: Record<string, string> = { 'X-Correlation-ID': correlationId };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers, signal: input.signal, timeoutMs: input.timeoutMs ?? 30_000, baseUrl: input.baseUrl };
}
function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  try { return decodePayload(schema, raw); }
  catch { throw new ClientSettlementRemediationError('CLIENT_SETTLEMENT_SCHEMA_MISMATCH', '回應不符合 Client Finance strict 契約。'); }
}
function mapped(error: unknown): ClientSettlementRemediationError {
  if (error instanceof ClientSettlementRemediationError) return error;
  if (error instanceof ApiTimeoutError) return new ClientSettlementRemediationError('CLIENT_SETTLEMENT_TIMEOUT', error.message, true);
  if (error instanceof ApiAbortError) return new ClientSettlementRemediationError('CLIENT_SETTLEMENT_ABORTED', error.message);
  if (error instanceof ApiNetworkError) return new ClientSettlementRemediationError('CLIENT_SETTLEMENT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new ClientSettlementRemediationError('CLIENT_SETTLEMENT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new ClientSettlementRemediationError(error.code, error.message, error.retryable, error.status);
  return new ClientSettlementRemediationError('CLIENT_SETTLEMENT_UNKNOWN', error instanceof Error ? error.message : '客戶帳務處理失敗。');
}
function base(caseNo: string): string {
  const value = caseNo.trim();
  if (!value) throw new ClientSettlementRemediationError('CLIENT_SETTLEMENT_CASE_INVALID', '案件編號不得為空。');
  return `/api/v1/orders/${encodeURIComponent(value)}/client-finance`;
}

export interface ClientSettlementRemediationClient {
  query(caseNo: string, request?: ClientSettlementOptions): Promise<ClientSettlementQuery>;
  previewReceipt(caseNo: string, selection: ReceiptSelection, request?: ClientSettlementOptions): Promise<ClientReceiptPreview>;
  applyReceipt(caseNo: string, selection: ReceiptSelection & { expected_account_version: number; preview_fingerprint: string; reason: string }, request: ClientSettlementApplyOptions): Promise<ClientReceiptReceipt>;
  previewPayable(caseNo: string, kind: ClientSettlementPayableKind, selection: PayableSelection, request?: ClientSettlementOptions): Promise<ClientPayablePreview>;
  applyPayable(caseNo: string, kind: ClientSettlementPayableKind, selection: PayableSelection & { expected_account_version: number; preview_fingerprint: string; reason: string }, request: ClientSettlementApplyOptions): Promise<ClientPayableReceipt>;
}

class DefaultClient implements ClientSettlementRemediationClient {
  async query(caseNo: string, request: ClientSettlementOptions = {}) {
    try {
      const raw = await transport.get<unknown>(`${base(caseNo)}/settlement-remediation`, options(request, `client-settlement-query-${crypto.randomUUID()}`));
      const data = decode(ClientSettlementQueryResponseSchema, raw).data;
      if (data.case_no !== caseNo.trim()) throw new ClientSettlementRemediationError('CLIENT_SETTLEMENT_IDENTITY_MISMATCH', 'Query 案件 identity 不一致。');
      return data;
    } catch (error) { throw mapped(error); }
  }
  async previewReceipt(caseNo: string, selection: ReceiptSelection, request: ClientSettlementOptions = {}) {
    try { return decode(ClientReceiptPreviewResponseSchema, await transport.post<unknown>(`${base(caseNo)}/receipt-reconciliation/preview`, selection, options(request, `client-receipt-preview-${crypto.randomUUID()}`))).data; }
    catch (error) { throw mapped(error); }
  }
  async applyReceipt(caseNo: string, selection: ReceiptSelection & { expected_account_version: number; preview_fingerprint: string; reason: string }, request: ClientSettlementApplyOptions) {
    try { return decode(ClientReceiptReceiptResponseSchema, await transport.post<unknown>(`${base(caseNo)}/receipt-reconciliation/apply`, selection, options(request, request.correlationId, request.idempotencyKey))).data; }
    catch (error) { throw mapped(error); }
  }
  async previewPayable(caseNo: string, kind: ClientSettlementPayableKind, selection: PayableSelection, request: ClientSettlementOptions = {}) {
    const endpoint = kind === 'refund' ? 'refund' : 'subsidy-return';
    try { return decode(ClientPayablePreviewResponseSchema, await transport.post<unknown>(`${base(caseNo)}/${endpoint}/preview`, selection, options(request, `client-${endpoint}-preview-${crypto.randomUUID()}`))).data; }
    catch (error) { throw mapped(error); }
  }
  async applyPayable(caseNo: string, kind: ClientSettlementPayableKind, selection: PayableSelection & { expected_account_version: number; preview_fingerprint: string; reason: string }, request: ClientSettlementApplyOptions) {
    const endpoint = kind === 'refund' ? 'refund' : 'subsidy-return';
    try { return decode(ClientPayableReceiptResponseSchema, await transport.post<unknown>(`${base(caseNo)}/${endpoint}/apply`, selection, options(request, request.correlationId, request.idempotencyKey))).data; }
    catch (error) { throw mapped(error); }
  }
}

export const clientSettlementRemediationClient: ClientSettlementRemediationClient = new DefaultClient();
