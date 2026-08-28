/**
 * File: matching_coordination_client.ts
 * Description: 以登入 Session 呼叫 M3 Query、Preview 與具冪等標頭的 Apply。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  MatchingCoordinationBusinessError,
  MatchingCoordinationRequestError,
  MatchingCoordinationUnauthenticatedError,
  mapMatchingCoordinationError,
} from './matching_coordination_errors';
import {
  ApplyCaregiverSelectionRequestSchema,
  ApplyCriteriaDiffRequestSchema,
  ApplyCustomerDecisionRequestSchema,
  ApplyInitialCriteriaRequestSchema,
  ApplyLeaveImpactRequestSchema,
  ApplyRematchRequestSchema,
  ApplyServiceDateRematchRequestSchema,
  ApplyZeroCandidateRequestSchema,
  ApplyZeroCandidateConfirmationRequestSchema,
  CriteriaDiffEnvelopeSchema,
  LeaveImpactPreviewEnvelopeSchema,
  MatchingApplyReceiptEnvelopeSchema,
  MatchingCoordinationQueryEnvelopeSchema,
  MatchingCoordinationQueryRequestSchema,
  MatchingCriteriaSnapshotEnvelopeSchema,
  MatchingPackageEnvelopeSchema,
  PreviewCriteriaDiffRequestSchema,
  PreviewInitialCriteriaRequestSchema,
  PreviewLeaveImpactRequestSchema,
  PreviewMatchingPackageRequestSchema,
  PreviewRematchRequestSchema,
  PreviewServiceDateRematchRequestSchema,
  PreviewZeroCandidateRequestSchema,
  PreviewZeroCandidateConfirmationRequestSchema,
  ServiceDateRematchPreviewEnvelopeSchema,
  ZeroCandidateAlternativeEnvelopeSchema,
  type ApplyCaregiverSelectionRequest,
  type ApplyCriteriaDiffRequest,
  type ApplyCustomerDecisionRequest,
  type ApplyInitialCriteriaRequest,
  type ApplyLeaveImpactRequest,
  type ApplyRematchRequest,
  type ApplyServiceDateRematchRequest,
  type ApplyZeroCandidateRequest,
  type ApplyZeroCandidateConfirmationRequest,
  type CriteriaDiff,
  type LeaveImpactPreviewResponse,
  type MatchingApplyReceiptResponse,
  type MatchingCoordinationQueryRequest,
  type MatchingCoordinationQueryResponse,
  type MatchingCriteriaSnapshot,
  type MatchingPackage,
  type PreviewCriteriaDiffRequest,
  type PreviewInitialCriteriaRequest,
  type PreviewLeaveImpactRequest,
  type PreviewMatchingPackageRequest,
  type PreviewRematchRequest,
  type PreviewServiceDateRematchRequest,
  type PreviewZeroCandidateRequest,
  type PreviewZeroCandidateConfirmationRequest,
  type ServiceDateRematchPreviewResponse,
  type ZeroCandidateAlternative,
} from './matching_coordination_schemas';

export interface MatchingCoordinationRequestOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
  correlationId?: string;
}

export interface MatchingCoordinationApplyOptions
  extends MatchingCoordinationRequestOptions {
  correlationId: string;
  idempotencyKey: string;
}

interface SuccessfulEnvelope<TData> {
  success: boolean;
  message: string;
  data: TData;
  error: string | null;
}

function validateCaseNo(caseNo: string): string {
  if (caseNo.trim().length < 1 || caseNo.length > 50) {
    throw new MatchingCoordinationRequestError(
      'case_no 必須為 1 至 50 字元的非空字串'
    );
  }
  return caseNo;
}

function validateHeader(name: string, value: string): string {
  if (value.trim().length < 1 || value.length > 191) {
    throw new MatchingCoordinationRequestError(
      `${name} 必須為 1 至 191 字元的非空字串`
    );
  }
  return value;
}

function parseRequest<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  value: unknown
): z.output<TSchema> {
  const parsed = schema.safeParse(value);
  if (!parsed.success) {
    throw new MatchingCoordinationRequestError(
      parsed.error.issues.map((issue) => issue.message).join('; ')
    );
  }
  return parsed.data;
}

function currentOptions(
  options?: MatchingCoordinationRequestOptions,
  apply = false
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new MatchingCoordinationUnauthenticatedError();

  const headers = { ...options?.headers };
  for (const name of Object.keys(headers)) {
    if (
      ['authorization', 'x-correlation-id', 'idempotency-key'].includes(
        name.toLowerCase()
      )
    ) {
      delete headers[name];
    }
  }
  if (options?.correlationId !== undefined) {
    headers['X-Correlation-ID'] = validateHeader(
      'X-Correlation-ID',
      options.correlationId
    );
  }
  if (apply) {
    const applyOptions = options as MatchingCoordinationApplyOptions;
    headers['Idempotency-Key'] = validateHeader(
      'Idempotency-Key',
      applyOptions.idempotencyKey
    );
  }

  return {
    signal: options?.signal,
    headers,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    token,
  };
}

function decodeEnvelope<TData>(
  schema: z.ZodType<SuccessfulEnvelope<TData>>,
  raw: unknown
): TData {
  const envelope = decodePayload(schema, raw);
  if (!envelope.success) {
    throw new MatchingCoordinationBusinessError(
      'matching_coordination_business_error',
      envelope.error ?? envelope.message
    );
  }
  return envelope.data;
}

async function invoke<TPayloadSchema extends z.ZodTypeAny, TData>(
  caseNo: string,
  suffix: string,
  payload: unknown,
  payloadSchema: TPayloadSchema,
  envelopeSchema: z.ZodType<SuccessfulEnvelope<TData>>,
  options?: MatchingCoordinationRequestOptions,
  apply = false
): Promise<TData> {
  try {
    const parsedCaseNo = validateCaseNo(caseNo);
    const parsedPayload = parseRequest(payloadSchema, payload);
    const raw = await transport.post(
      `/api/v1/matching-coordination/${encodeURIComponent(parsedCaseNo)}/${suffix}`,
      parsedPayload,
      currentOptions(options, apply)
    );
    return decodeEnvelope(envelopeSchema, raw);
  } catch (error) {
    throw mapMatchingCoordinationError(error);
  }
}

export function queryMatchingCoordination(
  caseNo: string,
  payload: MatchingCoordinationQueryRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<MatchingCoordinationQueryResponse> {
  return invoke(
    caseNo,
    'query',
    payload,
    MatchingCoordinationQueryRequestSchema,
    MatchingCoordinationQueryEnvelopeSchema,
    options
  );
}

export function previewInitialCriteria(
  caseNo: string,
  payload: PreviewInitialCriteriaRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<MatchingCriteriaSnapshot> {
  return invoke(
    caseNo,
    'preview/initial-criteria',
    payload,
    PreviewInitialCriteriaRequestSchema,
    MatchingCriteriaSnapshotEnvelopeSchema,
    options
  );
}

export function previewMatchingPackage(
  caseNo: string,
  payload: PreviewMatchingPackageRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<MatchingPackage> {
  return invoke(
    caseNo,
    'preview/package',
    payload,
    PreviewMatchingPackageRequestSchema,
    MatchingPackageEnvelopeSchema,
    options
  );
}

export function previewCriteriaDiff(
  caseNo: string,
  payload: PreviewCriteriaDiffRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<CriteriaDiff> {
  return invoke(
    caseNo,
    'preview/criteria-diff',
    payload,
    PreviewCriteriaDiffRequestSchema,
    CriteriaDiffEnvelopeSchema,
    options
  );
}

export function previewZeroCandidate(
  caseNo: string,
  payload: PreviewZeroCandidateRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<ZeroCandidateAlternative> {
  return invoke(
    caseNo,
    'preview/zero-candidate',
    payload,
    PreviewZeroCandidateRequestSchema,
    ZeroCandidateAlternativeEnvelopeSchema,
    options
  );
}

export function previewZeroCandidateConfirmation(
  caseNo: string,
  payload: PreviewZeroCandidateConfirmationRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<MatchingPackage> {
  return invoke(
    caseNo,
    'preview/confirm-zero-candidate',
    payload,
    PreviewZeroCandidateConfirmationRequestSchema,
    MatchingPackageEnvelopeSchema,
    options
  );
}

export function previewRematch(
  caseNo: string,
  payload: PreviewRematchRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<MatchingPackage> {
  return invoke(
    caseNo,
    'preview/rematch',
    payload,
    PreviewRematchRequestSchema,
    MatchingPackageEnvelopeSchema,
    options
  );
}

export function previewLeaveImpact(
  caseNo: string,
  payload: PreviewLeaveImpactRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<LeaveImpactPreviewResponse> {
  return invoke(
    caseNo,
    'preview/leave-impact',
    payload,
    PreviewLeaveImpactRequestSchema,
    LeaveImpactPreviewEnvelopeSchema,
    options
  );
}

export function previewServiceDateRematch(
  caseNo: string,
  payload: PreviewServiceDateRematchRequest,
  options?: MatchingCoordinationRequestOptions
): Promise<ServiceDateRematchPreviewResponse> {
  return invoke(
    caseNo,
    'preview/service-date-rematch',
    payload,
    PreviewServiceDateRematchRequestSchema,
    ServiceDateRematchPreviewEnvelopeSchema,
    options
  );
}

function invokeApply<TSchema extends z.ZodTypeAny>(
  caseNo: string,
  suffix: string,
  payload: unknown,
  schema: TSchema,
  options: MatchingCoordinationApplyOptions
): Promise<MatchingApplyReceiptResponse> {
  return invoke(
    caseNo,
    `apply/${suffix}`,
    payload,
    schema,
    MatchingApplyReceiptEnvelopeSchema,
    options,
    true
  );
}

export const applyLeaveImpact = (
  caseNo: string,
  payload: ApplyLeaveImpactRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'leave-impact', payload, ApplyLeaveImpactRequestSchema, options);

export const applyServiceDateRematch = (
  caseNo: string,
  payload: ApplyServiceDateRematchRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'service-date-rematch', payload, ApplyServiceDateRematchRequestSchema, options);

export const applyRematch = (
  caseNo: string,
  payload: ApplyRematchRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'rematch', payload, ApplyRematchRequestSchema, options);

export const applyInitialCriteria = (
  caseNo: string,
  payload: ApplyInitialCriteriaRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'initial-criteria', payload, ApplyInitialCriteriaRequestSchema, options);

export const applyCriteriaDiff = (
  caseNo: string,
  payload: ApplyCriteriaDiffRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'criteria-diff', payload, ApplyCriteriaDiffRequestSchema, options);

export const applyCaregiverSelection = (
  caseNo: string,
  payload: ApplyCaregiverSelectionRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'caregiver-selection', payload, ApplyCaregiverSelectionRequestSchema, options);

export const applyCustomerDecision = (
  caseNo: string,
  payload: ApplyCustomerDecisionRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'customer-decision', payload, ApplyCustomerDecisionRequestSchema, options);

export const applyZeroCandidate = (
  caseNo: string,
  payload: ApplyZeroCandidateRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(caseNo, 'zero-candidate', payload, ApplyZeroCandidateRequestSchema, options);

export const applyZeroCandidateConfirmation = (
  caseNo: string,
  payload: ApplyZeroCandidateConfirmationRequest,
  options: MatchingCoordinationApplyOptions
) => invokeApply(
  caseNo,
  'confirm-zero-candidate',
  payload,
  ApplyZeroCandidateConfirmationRequestSchema,
  options
);

export const matchingCoordinationClient = {
  query: queryMatchingCoordination,
  previewInitialCriteria,
  previewMatchingPackage,
  previewCriteriaDiff,
  previewZeroCandidate,
  previewZeroCandidateConfirmation,
  previewRematch,
  previewLeaveImpact,
  previewServiceDateRematch,
  applyLeaveImpact,
  applyServiceDateRematch,
  applyRematch,
  applyInitialCriteria,
  applyCriteriaDiff,
  applyCaregiverSelection,
  applyCustomerDecision,
  applyZeroCandidate,
  applyZeroCandidateConfirmation,
};

export type MatchingCoordinationClient = typeof matchingCoordinationClient;
