/**
 * File: line_safe_review_link_client.ts
 * Description: M4 safe-review-link typed query/redeem/revoke client; token only lives in request memory.
 */

import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { mapSafeReviewLinkError } from './line_safe_review_link_errors';
import {
  SafeReviewLinkReceiptResponseSchema,
  SafeReviewLinkResponseSchema,
  SafeReviewLinkRedeemRequestSchema,
  SafeReviewLinkRevokeRequestSchema,
  type SafeReviewLink,
  type SafeReviewLinkReceipt,
  type SafeReviewLinkRedeemRequest,
  type SafeReviewLinkRevokeRequest,
} from './line_safe_review_link_schemas';

export interface SafeReviewLinkQueryOptions { correlationId: string; signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; headers?: Record<string, string>; }
export interface SafeReviewLinkMutationOptions extends Omit<SafeReviewLinkQueryOptions, 'correlationId'> {}

function requestOptions(source: SafeReviewLinkQueryOptions | SafeReviewLinkMutationOptions, correlationId: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new Error('缺少有效的管理員 Session。');
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(source.headers ?? {})) {
    if (['authorization', 'content-type', 'x-correlation-id'].includes(name.toLowerCase())) continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = correlationId.trim();
  return { token, headers, signal: source.signal, timeoutMs: source.timeoutMs, baseUrl: source.baseUrl };
}

function decode<T>(schema: z.ZodType<{ data: T }>, raw: unknown): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new Error('safe-review-link 回應不符合封閉契約。');
  return parsed.data.data;
}

function correlation(source: SafeReviewLinkQueryOptions | SafeReviewLinkMutationOptions): string {
  const value = 'correlationId' in source ? source.correlationId : '';
  if (!value.trim()) throw new Error('X-Correlation-ID 不可為空。');
  return value.trim();
}

export async function querySafeReviewLink(linkId: string, source: SafeReviewLinkQueryOptions): Promise<SafeReviewLink> {
  try {
    const raw = await transport.get<unknown>(`/api/v1/runtime/line-safe-review-links/${encodeURIComponent(linkId.trim())}`, requestOptions(source, correlation(source)));
    return decode(SafeReviewLinkResponseSchema, raw);
  } catch (error) { throw mapSafeReviewLinkError(error); }
}

export async function redeemSafeReviewLink(linkId: string, request: SafeReviewLinkRedeemRequest, source: SafeReviewLinkMutationOptions = {}): Promise<SafeReviewLinkReceipt> {
  try {
    const body = SafeReviewLinkRedeemRequestSchema.parse(request);
    const raw = await transport.request<unknown>(`/api/v1/runtime/line-safe-review-links/${encodeURIComponent(linkId.trim())}/redeem`, { ...requestOptions(source, body.correlation_id), method: 'POST', body });
    return decode(SafeReviewLinkReceiptResponseSchema, raw);
  } catch (error) { throw mapSafeReviewLinkError(error); }
}

export async function revokeSafeReviewLink(linkId: string, request: SafeReviewLinkRevokeRequest, source: SafeReviewLinkMutationOptions = {}): Promise<SafeReviewLinkReceipt> {
  try {
    const body = SafeReviewLinkRevokeRequestSchema.parse(request);
    const raw = await transport.request<unknown>(`/api/v1/runtime/line-safe-review-links/${encodeURIComponent(linkId.trim())}/revoke`, { ...requestOptions(source, body.correlation_id), method: 'POST', body });
    return decode(SafeReviewLinkReceiptResponseSchema, raw);
  } catch (error) { throw mapSafeReviewLinkError(error); }
}

export const safeReviewLinkClient = { query: querySafeReviewLink, redeem: redeemSafeReviewLink, revoke: revokeSafeReviewLink };
export type SafeReviewLinkClient = typeof safeReviewLinkClient;
