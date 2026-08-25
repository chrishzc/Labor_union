/**
 * File: line_runtime_target_client.ts
 * Description: 以 fresh Session 與 caller command identity 呼叫 LINE runtime alert target API。
 */

import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { LineRuntimeTargetError, mapLineRuntimeTargetError, type LineRuntimeTargetOperation } from './line_runtime_target_errors';
import {
  LineRuntimeAdminCandidatesResponseSchema,
  LineRuntimeAdminTargetRequestSchema,
  LineRuntimeAdminTargetApplyRequestSchema,
  LineRuntimeGroupResetRequestSchema,
  LineRuntimeGroupResetApplyRequestSchema,
  LineRuntimeTargetEnabledRequestSchema,
  LineRuntimeTargetEnabledApplyRequestSchema,
  LineRuntimeTargetPreviewResponseSchema,
  LineRuntimeTargetReceiptResponseSchema,
  LineRuntimeTargetsResponseSchema,
  type LineRuntimeAdminCandidate,
  type LineRuntimeAdminTargetRequest,
  type LineRuntimeAdminTargetApplyRequest,
  type LineRuntimeGroupResetRequest,
  type LineRuntimeGroupResetApplyRequest,
  type LineRuntimeTarget,
  type LineRuntimeTargetEnabledRequest,
  type LineRuntimeTargetEnabledApplyRequest,
  type LineRuntimeTargetPreview,
  type LineRuntimeTargetReceipt,
} from './line_runtime_target_schemas';

export interface LineRuntimeTargetOptions {
  correlationId: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface LineRuntimeTargetMutationOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

function requiredText(value: string, field: string): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > 191) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_VALIDATION', `${field} 必須是 1 至 191 字元的非空文字。`);
  return normalized;
}

function requestOptions(source: LineRuntimeTargetMutationOptions, correlationId: string, idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_UNAUTHENTICATED', '缺少有效的管理員 Session。', { status: 401 });
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(source.headers ?? {})) {
    if (['authorization', 'x-correlation-id', 'idempotency-key', 'content-type'].includes(name.toLowerCase())) continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = requiredText(correlationId, 'X-Correlation-ID');
  if (idempotencyKey !== undefined) headers['Idempotency-Key'] = requiredText(idempotencyKey, 'Idempotency-Key');
  return { token, headers, signal: source.signal, timeoutMs: source.timeoutMs, baseUrl: source.baseUrl };
}

function validate<T>(schema: z.ZodType<T>, value: T): T {
  const parsed = schema.safeParse(value);
  if (!parsed.success) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_VALIDATION', 'LINE runtime target request 不符合封閉契約。', { originalError: parsed.error });
  return parsed.data;
}

function decode<T>(schema: z.ZodType<{ data: T }>, raw: unknown): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_CONTRACT', 'LINE runtime target 回應不符合封閉契約。', { originalError: parsed.error });
  return parsed.data.data;
}

export async function listLineRuntimeTargets(source: LineRuntimeTargetOptions): Promise<LineRuntimeTarget[]> {
  try {
    const raw = await transport.get<unknown>('/api/v1/runtime/line-alert-targets', requestOptions(source, source.correlationId));
    return decode(LineRuntimeTargetsResponseSchema, raw);
  } catch (error) {
    throw mapLineRuntimeTargetError(error, 'list');
  }
}

export async function listLineRuntimeAdminCandidates(source: LineRuntimeTargetOptions): Promise<LineRuntimeAdminCandidate[]> {
  try {
    const raw = await transport.get<unknown>('/api/v1/runtime/line-alert-targets/admin-candidates', requestOptions(source, source.correlationId));
    return decode(LineRuntimeAdminCandidatesResponseSchema, raw);
  } catch (error) {
    throw mapLineRuntimeTargetError(error, 'candidates');
  }
}

async function mutation<T>(
  operation: LineRuntimeTargetOperation,
  expectedReceiptOperation: LineRuntimeTargetReceipt['operation'],
  expectedTargetId: number | null,
  method: 'POST' | 'PATCH',
  path: string,
  schema: z.ZodType<T>,
  request: T,
  source: LineRuntimeTargetMutationOptions,
): Promise<LineRuntimeTargetReceipt> {
  try {
    const body = validate(schema, request);
    const identity = body as { correlation_id: string; idempotency_key: string };
    const raw = await transport.request<unknown>(path, { ...requestOptions(source, identity.correlation_id, identity.idempotency_key), method, body });
    const receipt = decode(LineRuntimeTargetReceiptResponseSchema, raw);
    if (receipt.operation !== expectedReceiptOperation) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_CONTRACT', 'LINE runtime target receipt operation 與 request 不一致。');
    if (expectedTargetId !== null && receipt.target_id !== expectedTargetId) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_CONTRACT', 'LINE runtime target receipt identity 與 request 不一致。');
    if (receipt.correlation_id !== identity.correlation_id) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_CONTRACT', 'LINE runtime target receipt correlation 與 request 不一致。');
    return receipt;
  } catch (error) {
    throw mapLineRuntimeTargetError(error, operation);
  }
}

async function preview<T>(
  operation: LineRuntimeTargetOperation,
  path: string,
  schema: z.ZodType<T>,
  request: T,
  source: LineRuntimeTargetMutationOptions,
): Promise<LineRuntimeTargetPreview> {
  try {
    const body = validate(schema, request);
    const identity = body as { correlation_id: string };
    const raw = await transport.post<unknown>(
      path,
      body,
      requestOptions(source, identity.correlation_id),
    );
    return decode(LineRuntimeTargetPreviewResponseSchema, raw);
  } catch (error) {
    throw mapLineRuntimeTargetError(error, operation);
  }
}

export async function previewAddLineRuntimeAdminTarget(request: LineRuntimeAdminTargetRequest, source: LineRuntimeTargetMutationOptions = {}): Promise<LineRuntimeTargetPreview> {
  return preview('add', '/api/v1/runtime/line-alert-targets/admin/preview', LineRuntimeAdminTargetRequestSchema, request, source);
}

export async function previewResetLineRuntimeGroup(request: LineRuntimeGroupResetRequest, source: LineRuntimeTargetMutationOptions = {}): Promise<LineRuntimeTargetPreview> {
  return preview('reset', '/api/v1/runtime/line-alert-targets/group/reset/preview', LineRuntimeGroupResetRequestSchema, request, source);
}

export async function previewSetLineRuntimeTargetEnabled(targetId: number, request: LineRuntimeTargetEnabledRequest, source: LineRuntimeTargetMutationOptions = {}): Promise<LineRuntimeTargetPreview> {
  if (!Number.isInteger(targetId) || targetId < 1) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_VALIDATION', 'target_id 必須是正整數。');
  return preview('toggle', `/api/v1/runtime/line-alert-targets/${targetId}/preview`, LineRuntimeTargetEnabledRequestSchema, request, source);
}

export async function addLineRuntimeAdminTarget(request: LineRuntimeAdminTargetApplyRequest, source: LineRuntimeTargetMutationOptions = {}): Promise<LineRuntimeTargetReceipt> {
  return mutation('add', 'admin_target_add', null, 'POST', '/api/v1/runtime/line-alert-targets/admin', LineRuntimeAdminTargetApplyRequestSchema, request, source);
}

export async function resetLineRuntimeGroup(request: LineRuntimeGroupResetApplyRequest, source: LineRuntimeTargetMutationOptions = {}): Promise<LineRuntimeTargetReceipt> {
  return mutation('reset', 'group_reset', null, 'POST', '/api/v1/runtime/line-alert-targets/group/reset', LineRuntimeGroupResetApplyRequestSchema, request, source);
}

export async function setLineRuntimeTargetEnabled(targetId: number, request: LineRuntimeTargetEnabledApplyRequest, source: LineRuntimeTargetMutationOptions = {}): Promise<LineRuntimeTargetReceipt> {
  if (!Number.isInteger(targetId) || targetId < 1) throw new LineRuntimeTargetError('LINE_RUNTIME_TARGET_VALIDATION', 'target_id 必須是正整數。');
  return mutation('toggle', request.enabled ? 'enable' : 'disable', targetId, 'PATCH', `/api/v1/runtime/line-alert-targets/${targetId}`, LineRuntimeTargetEnabledApplyRequestSchema, request, source);
}

export const lineRuntimeTargetClient = {
  listTargets: listLineRuntimeTargets,
  listAdminCandidates: listLineRuntimeAdminCandidates,
  previewAddAdminTarget: previewAddLineRuntimeAdminTarget,
  previewResetGroup: previewResetLineRuntimeGroup,
  previewSetEnabled: previewSetLineRuntimeTargetEnabled,
  addAdminTarget: addLineRuntimeAdminTarget,
  resetGroup: resetLineRuntimeGroup,
  setEnabled: setLineRuntimeTargetEnabled,
};
