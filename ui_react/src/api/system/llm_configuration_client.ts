/**
 * File: llm_configuration_client.ts
 * Description: Gemini API Key write-only 管理端 client；只讀設定狀態與安全連線結果，不讀回 secret。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';


export const LlmApiKeyStatusSchema = z.strictObject({
  configured: z.boolean(),
  updated_at: z.string().nullable(),
});

export const LlmConnectionTestSchema = z.strictObject({
  connected: z.boolean(),
  provider: z.string(),
  model: z.string(),
  code: z.string().nullable(),
});

export type LlmApiKeyStatus = z.infer<typeof LlmApiKeyStatusSchema>;
export type LlmConnectionTest = z.infer<typeof LlmConnectionTestSchema>;

function requireToken(): string {
  const token = sessionClient.getToken();
  if (!token) throw new Error('未登入或 Session 已清除');
  return token;
}

export async function fetchLlmApiKeyStatus(): Promise<LlmApiKeyStatus> {
  const raw = await transport.get('/api/v1/system/llm/api-key/status', {
    token: requireToken(),
  });
  return decodeEnvelope(LlmApiKeyStatusSchema, raw);
}

export async function replaceLlmApiKey(apiKey: string): Promise<LlmApiKeyStatus> {
  const raw = await transport.post(
    '/api/v1/system/llm/api-key',
    { api_key: apiKey },
    { token: requireToken() },
  );
  return decodeEnvelope(LlmApiKeyStatusSchema, raw);
}

export async function testLlmConnection(): Promise<LlmConnectionTest> {
  const raw = await transport.post(
    '/api/v1/system/llm/connection-test',
    {},
    { token: requireToken() },
  );
  return decodeEnvelope(LlmConnectionTestSchema, raw);
}
