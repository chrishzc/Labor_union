/**
 * File: line_identity_runtime_config_client.ts
 * Description: 嚴格解碼公開 LIFF runtime config，供管理端產生 canonical 實機測試網址。
 */

import { z } from 'zod';
import { transport } from '../shared/transport';
import { extractErrorMessage } from '../shared/typed_errors';

const LineIdentityRuntimeConfigSchema = z.strictObject({
  liff_id: z.string().trim().min(1),
  public_base_url: z.string().url().nullable(),
});

const LineIdentityRuntimeConfigEnvelopeSchema = z.strictObject({
  success: z.literal(true),
  message: z.literal('Success'),
  data: LineIdentityRuntimeConfigSchema,
  error: z.null(),
});

export type LineIdentityRuntimeConfig = z.infer<typeof LineIdentityRuntimeConfigSchema>;

export interface LineIdentityRuntimeConfigClient {
  get(options?: { signal?: AbortSignal }): Promise<LineIdentityRuntimeConfig>;
}

export class LineIdentityRuntimeConfigError extends Error {
  public readonly name = 'LineIdentityRuntimeConfigError';
}

function requireSafePublicOrigin(value: string | null): string | null {
  if (value === null) return null;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
      || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) {
    throw new LineIdentityRuntimeConfigError('LIFF 公開網址格式不安全，未產生測試連結。');
  }
  return url.origin;
}

export async function getLineIdentityRuntimeConfig(
  options?: { signal?: AbortSignal },
): Promise<LineIdentityRuntimeConfig> {
  try {
    const raw = await transport.get<unknown>('/api/v1/line/identity/runtime-config', {
      signal: options?.signal,
      timeoutMs: 10_000,
    });
    const parsed = LineIdentityRuntimeConfigEnvelopeSchema.safeParse(raw);
    if (!parsed.success) {
      throw new LineIdentityRuntimeConfigError('LIFF runtime config 回應不符合封閉契約。');
    }
    return {
      ...parsed.data.data,
      public_base_url: requireSafePublicOrigin(parsed.data.data.public_base_url),
    };
  } catch (error) {
    if (error instanceof LineIdentityRuntimeConfigError) throw error;
    throw new LineIdentityRuntimeConfigError(extractErrorMessage(error));
  }
}

export const lineIdentityRuntimeConfigClient: LineIdentityRuntimeConfigClient = {
  get: getLineIdentityRuntimeConfig,
};
