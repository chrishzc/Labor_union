/**
 * File: client_over_refund_recovery_client.ts
 * Description: Client Finance recovery 的 bounded Query／Preview／Apply typed client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  ClientOverRefundRecoveryAdjustmentPreviewSchema,
  ClientOverRefundRecoveryAdjustmentPreviewRequestSchema,
  ClientOverRefundRecoveryMatchedPreviewRequestSchema,
  ClientOverRefundRecoveryMatchingPreviewRequestSchema,
  ClientOverRefundRecoveryMatchingPreviewSchema,
  ClientOverRefundRecoveryMatchingReceiptSchema,
  ClientOverRefundRecoveryPreviewSchema,
  ClientOverRefundRecoveryQuerySchema,
  ClientOverRefundRecoveryReceiptSchema,
  ClientOverRefundRecoveryResponseSchema,
  type ClientOverRefundRecoveryAdjustmentPreview,
  type ClientOverRefundRecoveryAdjustmentPreviewRequest,
  type ClientOverRefundRecoveryMatchedPreviewRequest,
  type ClientOverRefundRecoveryMatchingPreview,
  type ClientOverRefundRecoveryMatchingPreviewRequest,
  type ClientOverRefundRecoveryMatchingReceipt,
  type ClientOverRefundRecoveryPreview,
  type ClientOverRefundRecoveryQuery,
  type ClientOverRefundRecoveryReceipt,
} from './client_over_refund_recovery_schemas';
import { ClientOverRefundRecoveryError, mapClientOverRefundRecoveryError } from './client_over_refund_recovery_errors';

export interface ClientOverRefundRecoveryClientOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface ClientOverRefundRecoveryCommandOptions extends ClientOverRefundRecoveryClientOptions { idempotencyKey: string; correlationId: string; }
export interface ClientOverRefundRecoveryClient {
  query(caseNo: string, recoveryIdentity: string, options?: ClientOverRefundRecoveryClientOptions): Promise<ClientOverRefundRecoveryQuery>;
  previewMatching(caseNo: string, request: ClientOverRefundRecoveryMatchingPreviewRequest, options?: ClientOverRefundRecoveryClientOptions): Promise<ClientOverRefundRecoveryMatchingPreview>;
  applyMatching(caseNo: string, request: ClientOverRefundRecoveryMatchingPreviewRequest & { expected_recovery_version: number; expected_account_version: number; preview_fingerprint: string; reason: string }, options: ClientOverRefundRecoveryCommandOptions): Promise<ClientOverRefundRecoveryMatchingReceipt>;
  previewCollection(caseNo: string, request: ClientOverRefundRecoveryMatchedPreviewRequest, options?: ClientOverRefundRecoveryClientOptions): Promise<ClientOverRefundRecoveryPreview>;
  applyCollection(caseNo: string, request: ClientOverRefundRecoveryMatchedPreviewRequest & { expected_recovery_version: number; expected_account_version: number; preview_fingerprint: string; reason: string }, options: ClientOverRefundRecoveryCommandOptions): Promise<ClientOverRefundRecoveryReceipt>;
  previewAdjustment(caseNo: string, request: ClientOverRefundRecoveryAdjustmentPreviewRequest, options?: ClientOverRefundRecoveryClientOptions): Promise<ClientOverRefundRecoveryAdjustmentPreview>;
  applyAdjustment(caseNo: string, request: ClientOverRefundRecoveryAdjustmentPreviewRequest & { expected_recovery_version: number; expected_account_version: number; preview_fingerprint: string; reason: string }, options: ClientOverRefundRecoveryCommandOptions): Promise<ClientOverRefundRecoveryReceipt>;
}

type CommandRequest = { expected_recovery_version: number; expected_account_version: number; preview_fingerprint: string; reason: string; evidence_reference: string };
const identityPattern = /^\S.{0,190}$/;

function text(value: string, label: string, max = 191): string {
  const normalized = value.trim();
  if (!identityPattern.test(normalized) || normalized.length > max) throw new ClientOverRefundRecoveryError('CLIENT_RECOVERY_VALIDATION', `${label} 必須是 1 至 ${max} 字元的非空字串。`);
  return normalized;
}
function casePath(caseNo: string, suffix: string): string {
  return `/api/v1/orders/${encodeURIComponent(text(caseNo, 'case_no'))}/client-finance/refund-overage-recovery${suffix}`;
}
function authenticated(options?: ClientOverRefundRecoveryClientOptions, command?: ClientOverRefundRecoveryCommandOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ClientOverRefundRecoveryError('CLIENT_RECOVERY_UNAUTHENTICATED', '缺少有效的管理員 Session。', false, 401);
  const headers: Record<string, string> = {};
  if (command) {
    headers['Idempotency-Key'] = text(command.idempotencyKey, 'Idempotency-Key');
    headers['X-Correlation-ID'] = text(command.correlationId, 'X-Correlation-ID');
  } else {
    headers['X-Correlation-ID'] = `client-over-refund-recovery-query-${Math.random().toString(36).slice(2, 10)}`;
  }
  return { token, signal: options?.signal, timeoutMs: options?.timeoutMs ?? 30_000, baseUrl: options?.baseUrl, headers };
}
function decode<T>(schema: z.ZodType<{ data: T }>, raw: unknown, label: string): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(`${label}回應結構異常。`, parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
  return parsed.data.data;
}
function validate<T>(schema: z.ZodType<T>, input: unknown, label: string): T {
  const parsed = schema.safeParse(input);
  if (!parsed.success) throw new ClientOverRefundRecoveryError('CLIENT_RECOVERY_INPUT_INVALID', `${label}輸入不符合 owner contract。`);
  return parsed.data;
}
function commandBody(request: CommandRequest): CommandRequest {
  const body = { ...request, reason: text(request.reason, 'reason', 500), evidence_reference: text(request.evidence_reference, 'evidence_reference', 500) };
  if (!Number.isInteger(body.expected_recovery_version) || body.expected_recovery_version < 0 || !Number.isInteger(body.expected_account_version) || body.expected_account_version < 0 || !/^[0-9a-f]{64}$/.test(body.preview_fingerprint)) throw new ClientOverRefundRecoveryError('CLIENT_RECOVERY_INPUT_INVALID', 'Apply 的 version、fingerprint 或 reason 不完整。');
  return body;
}

class DefaultClientOverRefundRecoveryClient implements ClientOverRefundRecoveryClient {
  async query(caseNo: string, recoveryIdentity: string, options?: ClientOverRefundRecoveryClientOptions) {
    const expectedCaseNo = text(caseNo, 'case_no');
    const expectedRecoveryIdentity = text(recoveryIdentity, 'recovery_identity');
    const endpoint = casePath(expectedCaseNo, `/${encodeURIComponent(expectedRecoveryIdentity)}`);
    try {
      const result = decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryQuerySchema), await transport.get(endpoint, authenticated(options)), 'Client recovery Query');
      if (result.case_no !== expectedCaseNo || result.recovery_identity !== expectedRecoveryIdentity) {
        throw new ClientOverRefundRecoveryError('CLIENT_RECOVERY_OWNER_MISMATCH', 'Client recovery Query 回傳不同 owner identity。');
      }
      return result;
    }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
  async previewMatching(caseNo: string, request: ClientOverRefundRecoveryMatchingPreviewRequest, options?: ClientOverRefundRecoveryClientOptions) {
    const body = validate(ClientOverRefundRecoveryMatchingPreviewRequestSchema, request, 'matching Preview');
    try { return decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryMatchingPreviewSchema), await transport.post(casePath(caseNo, '/matching/preview'), body, authenticated(options)), 'matching Preview'); }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
  async applyMatching(caseNo: string, request: ClientOverRefundRecoveryMatchingPreviewRequest & CommandRequest, options: ClientOverRefundRecoveryCommandOptions) {
    const { expected_recovery_version, expected_account_version, preview_fingerprint, reason, ...selection } = request;
    const body = { ...validate(ClientOverRefundRecoveryMatchingPreviewRequestSchema, selection, 'matching Apply'), ...commandBody({ expected_recovery_version, expected_account_version, preview_fingerprint, reason, evidence_reference: selection.evidence_reference }) };
    try { return decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryMatchingReceiptSchema), await transport.post(casePath(caseNo, '/matching/apply'), body, authenticated(options, options)), 'matching Apply'); }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
  async previewCollection(caseNo: string, request: ClientOverRefundRecoveryMatchedPreviewRequest, options?: ClientOverRefundRecoveryClientOptions) {
    const body = validate(ClientOverRefundRecoveryMatchedPreviewRequestSchema, request, 'collection Preview');
    try { return decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryPreviewSchema), await transport.post(casePath(caseNo, '/matched/preview'), body, authenticated(options)), 'collection Preview'); }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
  async applyCollection(caseNo: string, request: ClientOverRefundRecoveryMatchedPreviewRequest & CommandRequest, options: ClientOverRefundRecoveryCommandOptions) {
    const { expected_recovery_version, expected_account_version, preview_fingerprint, reason, ...selection } = request;
    const body = { ...validate(ClientOverRefundRecoveryMatchedPreviewRequestSchema, selection, 'collection Apply'), ...commandBody({ expected_recovery_version, expected_account_version, preview_fingerprint, reason, evidence_reference: selection.evidence_reference }) };
    try { return decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryReceiptSchema), await transport.post(casePath(caseNo, '/matched/apply'), body, authenticated(options, options)), 'collection Apply'); }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
  async previewAdjustment(caseNo: string, request: ClientOverRefundRecoveryAdjustmentPreviewRequest, options?: ClientOverRefundRecoveryClientOptions) {
    const body = validate(ClientOverRefundRecoveryAdjustmentPreviewRequestSchema, request, 'adjustment Preview');
    try { return decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryAdjustmentPreviewSchema), await transport.post(casePath(caseNo, '/adjustment/preview'), body, authenticated(options)), 'adjustment Preview'); }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
  async applyAdjustment(caseNo: string, request: ClientOverRefundRecoveryAdjustmentPreviewRequest & CommandRequest, options: ClientOverRefundRecoveryCommandOptions) {
    const { expected_recovery_version, expected_account_version, preview_fingerprint, reason, ...selection } = request;
    const body = { ...validate(ClientOverRefundRecoveryAdjustmentPreviewRequestSchema, selection, 'adjustment Apply'), ...commandBody({ expected_recovery_version, expected_account_version, preview_fingerprint, reason, evidence_reference: selection.evidence_reference }) };
    try { return decode(ClientOverRefundRecoveryResponseSchema(ClientOverRefundRecoveryReceiptSchema), await transport.post(casePath(caseNo, '/adjustment/apply'), body, authenticated(options, options)), 'adjustment Apply'); }
    catch (error) { throw mapClientOverRefundRecoveryError(error); }
  }
}

export const clientOverRefundRecoveryClient: ClientOverRefundRecoveryClient = new DefaultClientOverRefundRecoveryClient();
