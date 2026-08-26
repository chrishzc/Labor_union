/**
 * File: line_identity_client.ts
 * Description: 呼叫 LINE 身分查詢、審核、更正、解除與失敗維護端點，逐次注入記憶體 Session 並嚴格解碼。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { LineIdentityClientError, mapLineIdentityError } from './line_identity_errors';
import {
  LineIdentityBindingListQuerySchema,
  LineIdentityBindingPageViewSchema,
  LineIdentityBindingViewSchema,
  LineIdentityReplacementApplyRequestSchema,
  LineIdentityReplacementPreviewViewSchema,
  LineIdentityReviewApplyRequestSchema,
  LineIdentityReviewApplyViewSchema,
  LineIdentityReviewDecisionSchema,
  LineIdentityReviewListQuerySchema,
  LineIdentityReviewPageViewSchema,
  LineIdentityReviewPreviewRequestSchema,
  LineIdentityReviewPreviewViewSchema,
  LineIdentityReviewSummaryViewSchema,
  LineIdentityReviewViewSchema,
  LineIdentityRevocationActionRequestSchema,
  LineIdentityRevocationApplyRequestSchema,
  LineIdentityRevocationPreviewViewSchema,
  LineIdentityRevocationRequestViewSchema,
  createLineIdentityEnvelopeSchema,
  type LineIdentityBindingListQuery,
  type LineIdentityBindingPageView,
  type LineIdentityBindingView,
  type LineIdentityReplacementApplyRequest,
  type LineIdentityReplacementPreviewView,
  type LineIdentityReviewApplyRequest,
  type LineIdentityReviewApplyView,
  type LineIdentityReviewDecision,
  type LineIdentityReviewListQuery,
  type LineIdentityReviewPageView,
  type LineIdentityReviewPreviewRequest,
  type LineIdentityReviewPreviewView,
  type LineIdentityReviewSummaryView,
  type LineIdentityReviewView,
  type LineIdentityRevocationActionRequest,
  type LineIdentityRevocationApplyRequest,
  type LineIdentityRevocationPreviewView,
  type LineIdentityRevocationRequestView,
} from './line_identity_schemas';

export interface LineIdentityRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface LineIdentityClient {
  listBindings(
    query?: LineIdentityBindingListQuery,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityBindingPageView>;
  getBinding(
    lineUserId: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityBindingView>;
  previewReplacement(
    lineUserId: string,
    targetSubjectReference: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReplacementPreviewView>;
  applyReplacement(
    lineUserId: string,
    payload: LineIdentityReplacementApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityBindingView>;
  previewRevocation(
    lineUserId: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationPreviewView>;
  applyRevocation(
    lineUserId: string,
    payload: LineIdentityRevocationApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView>;
  retryRevocation(
    requestId: number,
    payload: LineIdentityRevocationActionRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView>;
  manualCompleteRevocation(
    requestId: number,
    payload: LineIdentityRevocationActionRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView>;
  listReviews(
    query?: LineIdentityReviewListQuery,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewPageView>;
  getReviewSummary(
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewSummaryView>;
  getReview(
    requestId: number,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewView>;
  previewReviewDecision(
    requestId: number,
    decision: LineIdentityReviewDecision,
    payload: LineIdentityReviewPreviewRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewPreviewView>;
  applyReviewDecision(
    requestId: number,
    decision: LineIdentityReviewDecision,
    payload: LineIdentityReviewApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewApplyView>;
}

function requestOptions(options?: LineIdentityRequestOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new LineIdentityClientError(
      'UNAUTHENTICATED',
      '管理員 Session 已失效或過期。'
    );
  }
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    token,
  };
}

function bindingPath(lineUserId: string): string {
  if (
    typeof lineUserId !== 'string' ||
    lineUserId.length === 0 ||
    lineUserId !== lineUserId.trim()
  ) {
    throw new LineIdentityClientError(
      'REQUEST_INVALID',
      'LINE 身分識別值不可為空白或含首尾空白。'
    );
  }
  return `/api/v1/line/identity-bindings/${encodeURIComponent(lineUserId)}`;
}

function revocationRequestPath(requestId: number): string {
  if (!Number.isInteger(requestId) || requestId <= 0) {
    throw new LineIdentityClientError(
      'REQUEST_INVALID',
      'LINE 身分解除申請識別值必須為正整數。'
    );
  }
  return `/api/v1/line/identity-bindings/revocations/${requestId}`;
}

function reviewPath(requestId: number): string {
  if (!Number.isInteger(requestId) || requestId <= 0) {
    throw new LineIdentityClientError(
      'REQUEST_INVALID',
      'LINE 身分審核識別值必須為正整數。'
    );
  }
  return `/api/v1/line/identity/reviews/${requestId}`;
}

function requiredText(value: string, label: string, maxLength: number): string {
  const normalized = typeof value === 'string' ? value.trim() : '';
  if (!normalized || normalized.length > maxLength) {
    throw new LineIdentityClientError(
      'REQUEST_INVALID',
      `${label}不可為空白且不得超過 ${maxLength} 字。`
    );
  }
  return normalized;
}

function decodeEnvelope<T extends z.ZodTypeAny>(
  dataSchema: T,
  raw: unknown
): z.output<T> {
  const envelope = decodePayload(createLineIdentityEnvelopeSchema(dataSchema), raw);
  if (!envelope.success) {
    throw new LineIdentityClientError(
      'BACKEND_REJECTED',
      'LINE 身分管理服務未接受此次請求。'
    );
  }
  if (envelope.data === null) {
    throw new LineIdentityClientError(
      'CONTRACT_MISMATCH',
      'LINE 身分管理成功回應缺少資料本體。'
    );
  }
  return envelope.data;
}

export async function listLineIdentityBindings(
  query: LineIdentityBindingListQuery = {},
  options?: LineIdentityRequestOptions
): Promise<LineIdentityBindingPageView> {
  try {
    const parsed = LineIdentityBindingListQuerySchema.parse(query);
    const raw = await transport.get('/api/v1/line/identity-bindings', {
      ...requestOptions(options),
      params: parsed,
    });
    return decodeEnvelope(LineIdentityBindingPageViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'query');
  }
}

export async function getLineIdentityBinding(
  lineUserId: string,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityBindingView> {
  try {
    const raw = await transport.get(bindingPath(lineUserId), requestOptions(options));
    return decodeEnvelope(LineIdentityBindingViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'query');
  }
}

export async function previewLineIdentityReplacement(
  lineUserId: string,
  targetSubjectReference: string,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityReplacementPreviewView> {
  try {
    const target = requiredText(targetSubjectReference, '更正對象識別值', 191);
    const raw = await transport.post(
      `${bindingPath(lineUserId)}/replacement/preview`,
      undefined,
      { ...requestOptions(options), params: { target_subject_reference: target } }
    );
    return decodeEnvelope(LineIdentityReplacementPreviewViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'preview');
  }
}

export async function applyLineIdentityReplacement(
  lineUserId: string,
  payload: LineIdentityReplacementApplyRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityBindingView> {
  try {
    const normalizedPayload = LineIdentityReplacementApplyRequestSchema.parse({
      ...payload,
      target_subject_reference: requiredText(
        payload.target_subject_reference,
        '更正對象識別值',
        191
      ),
      reason: requiredText(payload.reason, '更正原因', 1000),
    });
    const raw = await transport.post(
      `${bindingPath(lineUserId)}/replacement/apply`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityBindingViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'apply');
  }
}

export async function previewLineIdentityRevocation(
  lineUserId: string,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityRevocationPreviewView> {
  try {
    const raw = await transport.post(
      `${bindingPath(lineUserId)}/revocation/preview`,
      undefined,
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityRevocationPreviewViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'preview');
  }
}

export async function applyLineIdentityRevocation(
  lineUserId: string,
  payload: LineIdentityRevocationApplyRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityRevocationRequestView> {
  try {
    const normalizedPayload = LineIdentityRevocationApplyRequestSchema.parse({
      ...payload,
      reason: typeof payload.reason === 'string' ? payload.reason.trim() : payload.reason,
    });
    const raw = await transport.post(
      `${bindingPath(lineUserId)}/revocation/apply`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityRevocationRequestViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'apply');
  }
}

async function submitRevocationAction(
  requestId: number,
  action: 'retry' | 'manual-complete',
  payload: LineIdentityRevocationActionRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityRevocationRequestView> {
  try {
    const normalizedPayload = LineIdentityRevocationActionRequestSchema.parse({
      reason: requiredText(payload.reason, '維護原因', 1000),
    });
    const raw = await transport.post(
      `${revocationRequestPath(requestId)}/${action}`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityRevocationRequestViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'apply');
  }
}

export function retryLineIdentityRevocation(
  requestId: number,
  payload: LineIdentityRevocationActionRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityRevocationRequestView> {
  return submitRevocationAction(requestId, 'retry', payload, options);
}

export function manualCompleteLineIdentityRevocation(
  requestId: number,
  payload: LineIdentityRevocationActionRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityRevocationRequestView> {
  return submitRevocationAction(requestId, 'manual-complete', payload, options);
}

export async function listLineIdentityReviews(
  query: LineIdentityReviewListQuery = {},
  options?: LineIdentityRequestOptions
): Promise<LineIdentityReviewPageView> {
  try {
    const parsed = LineIdentityReviewListQuerySchema.parse(query);
    const raw = await transport.get('/api/v1/line/identity/reviews/numbered', {
      ...requestOptions(options),
      params: parsed,
    });
    return decodeEnvelope(LineIdentityReviewPageViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'query');
  }
}

export async function getLineIdentityReviewSummary(
  options?: LineIdentityRequestOptions
): Promise<LineIdentityReviewSummaryView> {
  try {
    const raw = await transport.get(
      '/api/v1/line/identity/reviews/summary',
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityReviewSummaryViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'query');
  }
}

export async function getLineIdentityReview(
  requestId: number,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityReviewView> {
  try {
    const raw = await transport.get(reviewPath(requestId), requestOptions(options));
    return decodeEnvelope(LineIdentityReviewViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'query');
  }
}

export async function previewLineIdentityReviewDecision(
  requestId: number,
  decision: LineIdentityReviewDecision,
  payload: LineIdentityReviewPreviewRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityReviewPreviewView> {
  try {
    const normalizedDecision = LineIdentityReviewDecisionSchema.parse(decision);
    const normalizedPayload = LineIdentityReviewPreviewRequestSchema.parse({
      ...payload,
      reason: requiredText(payload.reason, '審核原因', 1000),
    });
    const raw = await transport.post(
      `${reviewPath(requestId)}/${normalizedDecision}/preview`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityReviewPreviewViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'preview');
  }
}

export async function applyLineIdentityReviewDecision(
  requestId: number,
  decision: LineIdentityReviewDecision,
  payload: LineIdentityReviewApplyRequest,
  options?: LineIdentityRequestOptions
): Promise<LineIdentityReviewApplyView> {
  try {
    const normalizedDecision = LineIdentityReviewDecisionSchema.parse(decision);
    const normalizedPayload = LineIdentityReviewApplyRequestSchema.parse({
      ...payload,
      reason: requiredText(payload.reason, '審核原因', 1000),
    });
    const raw = await transport.post(
      `${reviewPath(requestId)}/${normalizedDecision}/apply`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodeEnvelope(LineIdentityReviewApplyViewSchema, raw);
  } catch (error) {
    throw mapLineIdentityError(error, 'apply');
  }
}

class DefaultLineIdentityClient implements LineIdentityClient {
  listBindings(
    query?: LineIdentityBindingListQuery,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityBindingPageView> {
    return listLineIdentityBindings(query, options);
  }

  getBinding(
    lineUserId: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityBindingView> {
    return getLineIdentityBinding(lineUserId, options);
  }

  previewReplacement(
    lineUserId: string,
    targetSubjectReference: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReplacementPreviewView> {
    return previewLineIdentityReplacement(lineUserId, targetSubjectReference, options);
  }

  applyReplacement(
    lineUserId: string,
    payload: LineIdentityReplacementApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityBindingView> {
    return applyLineIdentityReplacement(lineUserId, payload, options);
  }

  previewRevocation(
    lineUserId: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationPreviewView> {
    return previewLineIdentityRevocation(lineUserId, options);
  }

  applyRevocation(
    lineUserId: string,
    payload: LineIdentityRevocationApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView> {
    return applyLineIdentityRevocation(lineUserId, payload, options);
  }

  retryRevocation(
    requestId: number,
    payload: LineIdentityRevocationActionRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView> {
    return retryLineIdentityRevocation(requestId, payload, options);
  }

  manualCompleteRevocation(
    requestId: number,
    payload: LineIdentityRevocationActionRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView> {
    return manualCompleteLineIdentityRevocation(requestId, payload, options);
  }

  listReviews(
    query?: LineIdentityReviewListQuery,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewPageView> {
    return listLineIdentityReviews(query, options);
  }

  getReviewSummary(
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewSummaryView> {
    return getLineIdentityReviewSummary(options);
  }

  getReview(
    requestId: number,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewView> {
    return getLineIdentityReview(requestId, options);
  }

  previewReviewDecision(
    requestId: number,
    decision: LineIdentityReviewDecision,
    payload: LineIdentityReviewPreviewRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewPreviewView> {
    return previewLineIdentityReviewDecision(requestId, decision, payload, options);
  }

  applyReviewDecision(
    requestId: number,
    decision: LineIdentityReviewDecision,
    payload: LineIdentityReviewApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityReviewApplyView> {
    return applyLineIdentityReviewDecision(requestId, decision, payload, options);
  }
}

export const lineIdentityClient: LineIdentityClient = new DefaultLineIdentityClient();
