/**
 * File: line_identity_client.ts
 * Description: 呼叫 LINE 身分綁定 list/detail 與解除 Preview/Apply，逐次注入記憶體 Session 並嚴格解碼。
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
  LineIdentityRevocationApplyRequestSchema,
  LineIdentityRevocationPreviewViewSchema,
  LineIdentityRevocationRequestViewSchema,
  createLineIdentityEnvelopeSchema,
  type LineIdentityBindingListQuery,
  type LineIdentityBindingPageView,
  type LineIdentityBindingView,
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
  previewRevocation(
    lineUserId: string,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationPreviewView>;
  applyRevocation(
    lineUserId: string,
    payload: LineIdentityRevocationApplyRequest,
    options?: LineIdentityRequestOptions
  ): Promise<LineIdentityRevocationRequestView>;
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
}

export const lineIdentityClient: LineIdentityClient = new DefaultLineIdentityClient();
