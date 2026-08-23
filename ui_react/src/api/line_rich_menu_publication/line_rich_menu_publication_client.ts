/**
 * File: line_rich_menu_publication_client.ts
 * Description: 以 fresh Session 呼叫 Rich Menu 發布 Preview、durable queue 與 retry 端點並嚴格解碼。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  LineRichMenuPublicationRequestError,
  LineRichMenuPublicationUnauthenticatedError,
  mapLineRichMenuPublicationError,
} from './line_rich_menu_publication_errors';
import {
  LineRichMenuPublicationQueueResponseSchema,
  LineRichMenuPublicationRetryResponseSchema,
  LineRichMenuPublishPreviewResponseSchema,
  LineRichMenuPublishRequestSchema,
  LineRichMenuRetryRequestSchema,
  type LineRichMenuPublicationMutation,
  type LineRichMenuPublishPreview,
  type LineRichMenuPublishRequest,
  type LineRichMenuRetryRequest,
} from './line_rich_menu_publication_schemas';

export interface LineRichMenuPublicationRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface LineRichMenuPublicationClient {
  preview(
    menuId: string,
    options?: LineRichMenuPublicationRequestOptions
  ): Promise<LineRichMenuPublishPreview>;
  publish(
    menuId: string,
    payload: LineRichMenuPublishRequest,
    options?: LineRichMenuPublicationRequestOptions
  ): Promise<LineRichMenuPublicationMutation>;
  retry(
    publicationId: number,
    payload: LineRichMenuRetryRequest,
    options?: LineRichMenuPublicationRequestOptions
  ): Promise<LineRichMenuPublicationMutation>;
}

function requestOptions(options?: LineRichMenuPublicationRequestOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LineRichMenuPublicationUnauthenticatedError();
  return {
    token,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
  };
}

function menuPath(menuId: string): string {
  const normalized = typeof menuId === 'string' ? menuId.trim() : '';
  if (!normalized || normalized.length > 191) {
    throw new LineRichMenuPublicationRequestError(
      'Rich Menu 識別值不可為空白且不得超過 191 字。'
    );
  }
  return `/api/v1/line/rich-menus/${encodeURIComponent(normalized)}`;
}

function publicationPath(publicationId: number): string {
  if (!Number.isInteger(publicationId) || publicationId <= 0) {
    throw new LineRichMenuPublicationRequestError('發布紀錄 ID 必須為正整數。');
  }
  return `/api/v1/line/rich-menus/publications/${publicationId}`;
}

function parseRequest<TData>(schema: z.ZodType<TData>, payload: unknown): TData {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new LineRichMenuPublicationRequestError(
      parsed.error.issues.map((issue) => issue.message).join('; ')
    );
  }
  return parsed.data;
}

async function call<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw mapLineRichMenuPublicationError(error);
  }
}

export function previewLineRichMenuPublication(
  menuId: string,
  options?: LineRichMenuPublicationRequestOptions
): Promise<LineRichMenuPublishPreview> {
  return call(async () => {
    const raw = await transport.post<object>(
      `${menuPath(menuId)}/publish-preview`,
      undefined,
      requestOptions(options)
    );
    return decodePayload(LineRichMenuPublishPreviewResponseSchema, raw).data;
  });
}

export function publishLineRichMenu(
  menuId: string,
  payload: LineRichMenuPublishRequest,
  options?: LineRichMenuPublicationRequestOptions
): Promise<LineRichMenuPublicationMutation> {
  return call(async () => {
    const normalizedPayload = parseRequest(LineRichMenuPublishRequestSchema, {
      ...payload,
      reason: typeof payload.reason === 'string' ? payload.reason.trim() : payload.reason,
    });
    const raw = await transport.post<object>(
      `${menuPath(menuId)}/publish`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodePayload(LineRichMenuPublicationQueueResponseSchema, raw).data;
  });
}

export function retryLineRichMenuPublication(
  publicationId: number,
  payload: LineRichMenuRetryRequest,
  options?: LineRichMenuPublicationRequestOptions
): Promise<LineRichMenuPublicationMutation> {
  return call(async () => {
    const normalizedPayload = parseRequest(LineRichMenuRetryRequestSchema, {
      ...payload,
      reason: typeof payload.reason === 'string' ? payload.reason.trim() : payload.reason,
    });
    const raw = await transport.post<object>(
      `${publicationPath(publicationId)}/retry`,
      normalizedPayload,
      requestOptions(options)
    );
    return decodePayload(LineRichMenuPublicationRetryResponseSchema, raw).data;
  });
}

export const lineRichMenuPublicationClient: LineRichMenuPublicationClient = {
  preview: previewLineRichMenuPublication,
  publish: publishLineRichMenu,
  retry: retryLineRichMenuPublication,
};
