/**
 * File: leave_substitution_client.ts
 * Description: 以最新 memory token 呼叫請假代班三個 API 並嚴格解碼成功與錯誤契約。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  assertLeaveSubstitutionInput,
  LeaveSubstitutionUnauthenticatedError,
  LeaveSubstitutionValidationError,
  mapLeaveSubstitutionError,
  type LeaveSubstitutionError,
} from './leave_substitution_errors';
import {
  LeaveSubstitutionApplyRequestSchema,
  LeaveSubstitutionApplyResponseSchema,
  LeaveSubstitutionAssignmentsResponseSchema,
  LeaveSubstitutionPreviewRequestSchema,
  LeaveSubstitutionPreviewResponseSchema,
  type LeaveSubstitutionApplyRequest,
  type LeaveSubstitutionAssignment,
  type LeaveSubstitutionPreview,
  type LeaveSubstitutionPreviewRequest,
  type LeaveSubstitutionReceipt,
} from './leave_substitution_schemas';

export interface LeaveSubstitutionRequestOptions {
  correlationId?: string;
  idempotencyKey?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface LeaveSubstitutionClient {
  listAssignments(
    caseNo: string,
    options?: LeaveSubstitutionRequestOptions,
  ): Promise<LeaveSubstitutionAssignment[]>;
  preview(
    caseNo: string,
    request: LeaveSubstitutionPreviewRequest,
    options?: LeaveSubstitutionRequestOptions,
  ): Promise<LeaveSubstitutionPreview>;
  apply(
    caseNo: string,
    request: LeaveSubstitutionApplyRequest,
    options: LeaveSubstitutionRequestOptions,
  ): Promise<LeaveSubstitutionReceipt>;
}

const DEFAULT_TIMEOUT_MS = 10_000;
let correlationSequence = 0;

function nextCorrelationId(): string {
  correlationSequence += 1;
  return `scheduling-leave-${correlationSequence.toString(36)}`;
}

function validateCaseNo(caseNo: string): string {
  assertLeaveSubstitutionInput(
    typeof caseNo === 'string' && caseNo.trim().length > 0 && caseNo.length <= 50,
    'caseNo 必須是 1 至 50 字元的非空字串。',
  );
  assertLeaveSubstitutionInput(caseNo === caseNo.trim(), 'caseNo 不得包含前後空白。');
  return caseNo;
}

function formatSchemaIssues(error: { issues: readonly { path: (string | number)[]; message: string }[] }): string {
  return error.issues
    .map((issue) => `[${issue.path.join('.') || '(root)'}] ${issue.message}`)
    .join(', ');
}

function parseRequest<T>(
  schema: { safeParse(value: unknown): { success: true; data: T } | { success: false; error: { issues: readonly { path: (string | number)[]; message: string }[] } } },
  value: unknown,
): T {
  const result = schema.safeParse(value);
  if (!result.success) {
    throw new LeaveSubstitutionValidationError(
      `請假代班請求不符合 strict contract：${formatSchemaIssues(result.error)}`,
      result.error,
    );
  }
  return result.data;
}

function requestOptions(
  options: LeaveSubstitutionRequestOptions | undefined,
  operation: 'assignments' | 'preview' | 'apply',
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LeaveSubstitutionUnauthenticatedError();

  const headers: Record<string, string> = {};
  let headerCorrelation: string | undefined;
  let headerIdempotency: string | undefined;
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization') continue;
    if (normalized === 'x-correlation-id') {
      assertLeaveSubstitutionInput(
        headerCorrelation === undefined,
        'X-Correlation-ID 不得重複。',
      );
      headerCorrelation = value.trim();
      continue;
    }
    if (normalized === 'idempotency-key') {
      assertLeaveSubstitutionInput(
        headerIdempotency === undefined,
        'Idempotency-Key 不得重複。',
      );
      headerIdempotency = value.trim();
      continue;
    }
    headers[name] = value;
  }

  const explicitCorrelation = options?.correlationId?.trim();
  assertLeaveSubstitutionInput(
    !(explicitCorrelation && headerCorrelation),
    'X-Correlation-ID 不得同時由 options 與 headers 指定。',
  );
  const correlationId = explicitCorrelation || headerCorrelation || nextCorrelationId();
  assertLeaveSubstitutionInput(
    correlationId.length > 0 && correlationId.length <= 191,
    'X-Correlation-ID 長度必須介於 1 至 191。',
  );

  const explicitIdempotency = options?.idempotencyKey?.trim();
  assertLeaveSubstitutionInput(
    !(explicitIdempotency && headerIdempotency),
    'Idempotency-Key 不得同時由 options 與 headers 指定。',
  );
  const idempotencyKey = explicitIdempotency || headerIdempotency;
  if (operation === 'apply') {
    assertLeaveSubstitutionInput(
      Boolean(idempotencyKey) && (idempotencyKey?.length ?? 0) <= 191,
      'Apply 必須提供 1 至 191 字元的 stable Idempotency-Key。',
    );
  } else {
    assertLeaveSubstitutionInput(
      idempotencyKey === undefined,
      'Idempotency-Key 只允許用於 Apply。',
    );
  }

  headers['X-Correlation-ID'] = correlationId;
  if (operation === 'apply' && idempotencyKey !== undefined) {
    headers['Idempotency-Key'] = idempotencyKey;
  }

  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function decode<T>(
  schema: {
    safeParse(value: unknown):
      | {
          success: true;
          data: {
            success: boolean;
            message: string;
            data: T | null;
            error?: string | null;
          };
        }
      | {
          success: false;
          error: {
            issues: readonly { path: (string | number)[]; message: string }[];
          };
        };
  },
  raw: unknown,
  operation: string,
): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(
      `請假代班 ${operation} 回應結構異常。`,
      parsed.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
      })),
      raw,
    );
  }
  if (!parsed.data.success || parsed.data.data === null) {
    throw new ApiHttpError(
      422,
      `LEAVE_SUBSTITUTION_${operation.toUpperCase()}_EMPTY`,
      parsed.data.error ?? parsed.data.message,
      false,
      raw,
    );
  }
  return parsed.data.data;
}

function endpoint(caseNo: string, action: string): string {
  return `/api/v1/orders/${encodeURIComponent(caseNo)}/leave-substitution/${action}`;
}

export async function listLeaveSubstitutionAssignments(
  caseNo: string,
  options?: LeaveSubstitutionRequestOptions,
): Promise<LeaveSubstitutionAssignment[]> {
  try {
    const validatedCaseNo = validateCaseNo(caseNo);
    const raw = await transport.get<unknown>(
      endpoint(validatedCaseNo, 'assignments'),
      requestOptions(options, 'assignments'),
    );
    return decode(LeaveSubstitutionAssignmentsResponseSchema, raw, 'assignments');
  } catch (error) {
    throw mapLeaveSubstitutionError(error);
  }
}

export async function previewLeaveSubstitution(
  caseNo: string,
  request: LeaveSubstitutionPreviewRequest,
  options?: LeaveSubstitutionRequestOptions,
): Promise<LeaveSubstitutionPreview> {
  try {
    const validatedCaseNo = validateCaseNo(caseNo);
    const validatedRequest = parseRequest(LeaveSubstitutionPreviewRequestSchema, request);
    const raw = await transport.post<unknown>(
      endpoint(validatedCaseNo, 'preview'),
      validatedRequest,
      requestOptions(options, 'preview'),
    );
    return decode(LeaveSubstitutionPreviewResponseSchema, raw, 'preview');
  } catch (error) {
    throw mapLeaveSubstitutionError(error);
  }
}

export async function applyLeaveSubstitution(
  caseNo: string,
  request: LeaveSubstitutionApplyRequest,
  options: LeaveSubstitutionRequestOptions,
): Promise<LeaveSubstitutionReceipt> {
  try {
    const validatedCaseNo = validateCaseNo(caseNo);
    const validatedRequest = parseRequest(LeaveSubstitutionApplyRequestSchema, request);
    const raw = await transport.post<unknown>(
      endpoint(validatedCaseNo, 'apply'),
      validatedRequest,
      requestOptions(options, 'apply'),
    );
    return decode(LeaveSubstitutionApplyResponseSchema, raw, 'apply');
  } catch (error) {
    throw mapLeaveSubstitutionError(error);
  }
}

class DefaultLeaveSubstitutionClient implements LeaveSubstitutionClient {
  public listAssignments(
    caseNo: string,
    options?: LeaveSubstitutionRequestOptions,
  ): Promise<LeaveSubstitutionAssignment[]> {
    return listLeaveSubstitutionAssignments(caseNo, options);
  }

  public preview(
    caseNo: string,
    request: LeaveSubstitutionPreviewRequest,
    options?: LeaveSubstitutionRequestOptions,
  ): Promise<LeaveSubstitutionPreview> {
    return previewLeaveSubstitution(caseNo, request, options);
  }

  public apply(
    caseNo: string,
    request: LeaveSubstitutionApplyRequest,
    options: LeaveSubstitutionRequestOptions,
  ): Promise<LeaveSubstitutionReceipt> {
    return applyLeaveSubstitution(caseNo, request, options);
  }
}

export function createLeaveSubstitutionClient(): LeaveSubstitutionClient {
  return new DefaultLeaveSubstitutionClient();
}

export const leaveSubstitutionClient: LeaveSubstitutionClient =
  createLeaveSubstitutionClient();

export type { LeaveSubstitutionError };
