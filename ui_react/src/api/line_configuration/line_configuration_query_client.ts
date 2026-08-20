/**
 * File: line_configuration_query_client.ts
 * Description: 只以 fresh memory Session 呼叫四個 LINE 設定 GET 白名單並嚴格解碼。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  LineConfigurationQueryRequestError,
  LineConfigurationQueryUnauthenticatedError,
  mapLineConfigurationQueryError,
} from './line_configuration_query_errors';
import {
  LineNotificationRulesCatalogSchema,
  LineRichMenuConfigurationSchema,
  LineRichMenuPublicationPageSchema,
  LineRichMenuPublicationSchema,
  createLineConfigurationQueryEnvelopeSchema,
  type LineNotificationRulesCatalog,
  type LineRichMenuConfiguration,
  type LineRichMenuPublication,
  type LineRichMenuPublicationPage,
} from './line_configuration_query_schemas';

export const LINE_CONFIGURATION_QUERY_TIMEOUT_MS = 10_000;
export const LINE_RICH_MENU_PUBLICATIONS_PAGE = 1;
export const LINE_RICH_MENU_PUBLICATIONS_PAGE_SIZE = 100;

export interface LineConfigurationQueryRequestOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  baseUrl?: string;
}

export interface LineConfigurationQueryClient {
  getNotificationRules(
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineNotificationRulesCatalog>;
  getRichMenuConfiguration(
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineRichMenuConfiguration>;
  listRichMenuPublications(
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineRichMenuPublicationPage>;
  getRichMenuPublication(
    publicationId: number,
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineRichMenuPublication>;
}

function readRequestOptions(
  options?: LineConfigurationQueryRequestOptions
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LineConfigurationQueryUnauthenticatedError();
  const headers = { ...options?.headers };
  for (const name of Object.keys(headers)) {
    if (
      ['authorization', 'content-type', 'idempotency-key', 'x-correlation-id'].includes(
        name.toLowerCase()
      )
    ) {
      delete headers[name];
    }
  }
  return {
    token,
    signal: options?.signal,
    headers,
    baseUrl: options?.baseUrl,
    timeoutMs: LINE_CONFIGURATION_QUERY_TIMEOUT_MS,
  };
}

function decodeEnvelope<T extends z.ZodTypeAny>(
  dataSchema: T,
  raw: object
): z.output<T> {
  return decodePayload(createLineConfigurationQueryEnvelopeSchema(dataSchema), raw)
    .data;
}

function requirePublicationId(publicationId: number): number {
  if (!Number.isInteger(publicationId) || publicationId < 1) {
    throw new LineConfigurationQueryRequestError(
      'Rich Menu 發布紀錄 ID 必須為正整數。'
    );
  }
  return publicationId;
}

async function read<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw mapLineConfigurationQueryError(error);
  }
}

export async function getLineNotificationRules(
  options?: LineConfigurationQueryRequestOptions
): Promise<LineNotificationRulesCatalog> {
  return read(async () => {
    const raw = await transport.get<object>(
      '/api/v1/line/notification-rules',
      readRequestOptions(options)
    );
    return decodeEnvelope(LineNotificationRulesCatalogSchema, raw);
  });
}

export async function getLineRichMenuConfiguration(
  options?: LineConfigurationQueryRequestOptions
): Promise<LineRichMenuConfiguration> {
  return read(async () => {
    const raw = await transport.get<object>(
      '/api/v1/line/configurations/rich_menus',
      readRequestOptions(options)
    );
    return decodeEnvelope(LineRichMenuConfigurationSchema, raw);
  });
}

export async function listLineRichMenuPublications(
  options?: LineConfigurationQueryRequestOptions
): Promise<LineRichMenuPublicationPage> {
  return read(async () => {
    const raw = await transport.get<object>('/api/v1/line/rich-menus/publications', {
      ...readRequestOptions(options),
      params: {
        page: LINE_RICH_MENU_PUBLICATIONS_PAGE,
        page_size: LINE_RICH_MENU_PUBLICATIONS_PAGE_SIZE,
      },
    });
    return decodeEnvelope(LineRichMenuPublicationPageSchema, raw);
  });
}

export async function getLineRichMenuPublication(
  publicationId: number,
  options?: LineConfigurationQueryRequestOptions
): Promise<LineRichMenuPublication> {
  return read(async () => {
    const validId = requirePublicationId(publicationId);
    const raw = await transport.get<object>(
      `/api/v1/line/rich-menus/publications/${encodeURIComponent(String(validId))}`,
      readRequestOptions(options)
    );
    return decodeEnvelope(LineRichMenuPublicationSchema, raw);
  });
}

class DefaultLineConfigurationQueryClient implements LineConfigurationQueryClient {
  getNotificationRules(
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineNotificationRulesCatalog> {
    return getLineNotificationRules(options);
  }

  getRichMenuConfiguration(
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineRichMenuConfiguration> {
    return getLineRichMenuConfiguration(options);
  }

  listRichMenuPublications(
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineRichMenuPublicationPage> {
    return listLineRichMenuPublications(options);
  }

  getRichMenuPublication(
    publicationId: number,
    options?: LineConfigurationQueryRequestOptions
  ): Promise<LineRichMenuPublication> {
    return getLineRichMenuPublication(publicationId, options);
  }
}

export function createLineConfigurationQueryClient(): LineConfigurationQueryClient {
  return new DefaultLineConfigurationQueryClient();
}

export const lineConfigurationQueryClient: LineConfigurationQueryClient =
  createLineConfigurationQueryClient();
