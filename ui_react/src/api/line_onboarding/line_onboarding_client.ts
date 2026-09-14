/**
 * File: line_onboarding_client.ts
 * Description: 提供 LINE 新好友 Onboarding 歡迎訊息查詢、預覽與手動更新的 API Client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';

export interface LineOnboardingData {
  template_id: string;
  content: string;
  revision: number;
  sample_preview: string;
  variables: string[];
}

export interface UpdateLineOnboardingPayload {
  content: string;
  expected_revision: number;
  reason?: string;
}

export interface PreviewLineOnboardingResult {
  sample_preview: string;
  variables: string[];
}

const LineOnboardingDataSchema = z.object({
  template_id: z.string(),
  content: z.string(),
  revision: z.number().int().nonnegative(),
  sample_preview: z.string(),
  variables: z.array(z.string()),
});

const LineOnboardingEnvelopeSchema = z.object({
  success: z.literal(true),
  message: z.string().optional(),
  data: LineOnboardingDataSchema,
  error: z.null().optional(),
});

const PreviewLineOnboardingResultSchema = z.object({
  sample_preview: z.string(),
  variables: z.array(z.string()),
});

const PreviewLineOnboardingEnvelopeSchema = z.object({
  success: z.literal(true),
  message: z.string().optional(),
  data: PreviewLineOnboardingResultSchema,
  error: z.null().optional(),
});

export interface LineOnboardingClientOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface LineOnboardingClient {
  get(options?: LineOnboardingClientOptions): Promise<LineOnboardingData>;
  preview(
    content: string,
    options?: LineOnboardingClientOptions
  ): Promise<PreviewLineOnboardingResult>;
  update(
    payload: UpdateLineOnboardingPayload,
    options?: LineOnboardingClientOptions
  ): Promise<LineOnboardingData>;
}

function requestOptions(options?: LineOnboardingClientOptions): RequestOptions {
  const token = sessionClient.getToken();
  return {
    token: token ?? undefined,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs ?? 10000,
    baseUrl: options?.baseUrl,
  };
}

export class DefaultLineOnboardingClient implements LineOnboardingClient {
  async get(options?: LineOnboardingClientOptions): Promise<LineOnboardingData> {
    const raw = await transport.get<object>(
      '/api/v1/line/onboarding',
      requestOptions(options)
    );
    const decoded = decodePayload(LineOnboardingEnvelopeSchema, raw);
    return decoded.data;
  }

  async preview(
    content: string,
    options?: LineOnboardingClientOptions
  ): Promise<PreviewLineOnboardingResult> {
    const raw = await transport.post<object>(
      '/api/v1/line/onboarding/preview',
      { content },
      requestOptions(options)
    );
    const decoded = decodePayload(PreviewLineOnboardingEnvelopeSchema, raw);
    return decoded.data;
  }

  async update(
    payload: UpdateLineOnboardingPayload,
    options?: LineOnboardingClientOptions
  ): Promise<LineOnboardingData> {
    const raw = await transport.put<object>(
      '/api/v1/line/onboarding',
      {
        content: payload.content,
        expected_revision: payload.expected_revision,
        reason: payload.reason ?? '更新新好友歡迎訊息',
      },
      requestOptions(options)
    );
    const decoded = decodePayload(LineOnboardingEnvelopeSchema, raw);
    return decoded.data;
  }
}

export const lineOnboardingClient: LineOnboardingClient =
  new DefaultLineOnboardingClient();
