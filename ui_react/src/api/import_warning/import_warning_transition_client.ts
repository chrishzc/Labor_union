/**
 * File: import_warning_transition_client.ts
 * Description: 以 session Bearer 呼叫匯入警示 Preview、Apply receipt 與 authenticated receipt lookup。
 */

import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import {
  ImportWarningTransitionError,
  mapImportWarningTransitionError,
} from './import_warning_transition_errors';
import {
  WarningTransitionPreviewResponseSchema,
  WarningTransitionReceiptResponseSchema,
  WarningTransitionRequestSchema,
  type WarningTransitionPreview,
  type WarningTransitionReceipt,
  type WarningTransitionRequest,
} from './import_warning_transition_schemas';

export interface ImportWarningTransitionRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface ImportWarningTransitionPreviewOptions extends ImportWarningTransitionRequestOptions {
  idempotencyKey: string;
}

export interface ImportWarningTransitionApplyOptions extends ImportWarningTransitionRequestOptions {
  idempotencyKey: string;
}

export interface ImportWarningTransitionClient {
  preview(
    occurrenceIdentity: string,
    request: WarningTransitionRequest,
    options: ImportWarningTransitionPreviewOptions,
  ): Promise<WarningTransitionPreview>;
  apply(
    occurrenceIdentity: string,
    request: WarningTransitionRequest,
    options: ImportWarningTransitionApplyOptions,
  ): Promise<WarningTransitionReceipt>;
  queryReceipt(
    receiptIdentity: string,
    options?: ImportWarningTransitionRequestOptions,
  ): Promise<WarningTransitionReceipt>;
}

let correlationSequence = 0;

function nextCorrelationId(): string {
  correlationSequence += 1;
  return `import-warning-transition-${correlationSequence.toString(36)}`;
}

function requiredText(value: string | undefined, field: string): string {
  const normalized = value?.trim() ?? '';
  if (!normalized || normalized.length > 191) {
    throw new ImportWarningTransitionError('IMPORT_WARNING_VALIDATION', `${field} 必須是 1 至 191 字元的非空字串。`);
  }
  return normalized;
}

function occurrencePath(occurrenceIdentity: string): string {
  return `/api/v1/import-warning-tracking/tasks/${encodeURIComponent(requiredText(occurrenceIdentity, 'occurrence_identity'))}`;
}

function receiptPath(receiptIdentity: string): string {
  const normalized = requiredText(receiptIdentity, 'receipt_identity');
  if (!/^[0-9a-f]{64}$/.test(normalized)) {
    throw new ImportWarningTransitionError('IMPORT_WARNING_VALIDATION', 'receipt_identity 必須是 64 位小寫十六進位字串。');
  }
  return `/api/v1/import-warning-tracking/receipts/${encodeURIComponent(normalized)}`;
}

function requestOptions(
  options: ImportWarningTransitionRequestOptions | undefined,
  idempotencyKey?: string,
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new ImportWarningTransitionError('IMPORT_WARNING_UNAUTHENTICATED', '缺少有效的管理員 Session。', { status: 401 });
  }

  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization' || normalized === 'x-correlation-id' || normalized === 'idempotency-key') continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = requiredText(options?.correlationId ?? nextCorrelationId(), 'X-Correlation-ID');
  if (idempotencyKey !== undefined) {
    headers['Idempotency-Key'] = requiredText(idempotencyKey, 'Idempotency-Key');
  }
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function formatIssues(error: z.ZodError): string {
  return error.issues.map((issue) => `[${issue.path.join('.') || '(root)'}] ${issue.message}`).join(', ');
}

function decode<T>(schema: z.ZodType<{ data: T }>, raw: unknown, endpoint: string): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new ImportWarningTransitionError(
      'IMPORT_WARNING_CONTRACT',
      `[${endpoint}] 回應契約驗證失敗：${formatIssues(parsed.error)}`,
      { originalError: parsed.error },
    );
  }
  return parsed.data.data;
}

function validateRequest(request: WarningTransitionRequest): WarningTransitionRequest {
  const parsed = WarningTransitionRequestSchema.safeParse(request);
  if (!parsed.success) {
    throw new ImportWarningTransitionError('IMPORT_WARNING_VALIDATION', `transition request 不符合 strict contract：${formatIssues(parsed.error)}`, { originalError: parsed.error });
  }
  return parsed.data;
}

export async function previewImportWarningTransition(
  occurrenceIdentity: string,
  request: WarningTransitionRequest,
  options: ImportWarningTransitionPreviewOptions,
): Promise<WarningTransitionPreview> {
  const validated = validateRequest(request);
  const endpoint = `${occurrencePath(occurrenceIdentity)}/preview`;
  try {
    return decode(
      WarningTransitionPreviewResponseSchema,
      await transport.post<unknown>(endpoint, validated, requestOptions(options, options.idempotencyKey)),
      endpoint,
    );
  } catch (error) {
    throw mapImportWarningTransitionError(error, 'preview');
  }
}

export async function applyImportWarningTransition(
  occurrenceIdentity: string,
  request: WarningTransitionRequest,
  options: ImportWarningTransitionApplyOptions,
): Promise<WarningTransitionReceipt> {
  const validated = validateRequest(request);
  const key = requiredText(options.idempotencyKey, 'Idempotency-Key');
  const endpoint = `${occurrencePath(occurrenceIdentity)}/apply`;
  try {
    return decode(
      WarningTransitionReceiptResponseSchema,
      await transport.post<unknown>(endpoint, validated, requestOptions(options, key)),
      endpoint,
    );
  } catch (error) {
    throw mapImportWarningTransitionError(error, 'apply');
  }
}

export async function queryImportWarningTransitionReceipt(
  receiptIdentity: string,
  options?: ImportWarningTransitionRequestOptions,
): Promise<WarningTransitionReceipt> {
  const endpoint = receiptPath(receiptIdentity);
  try {
    return decode(
      WarningTransitionReceiptResponseSchema,
      await transport.get<unknown>(endpoint, requestOptions(options)),
      endpoint,
    );
  } catch (error) {
    throw mapImportWarningTransitionError(error, 'receipt');
  }
}

export const importWarningTransitionClient: ImportWarningTransitionClient = {
  preview: previewImportWarningTransition,
  apply: applyImportWarningTransition,
  queryReceipt: queryImportWarningTransitionReceipt,
};
