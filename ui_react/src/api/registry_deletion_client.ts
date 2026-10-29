import { z } from 'zod';
import { sessionClient } from './auth/session_client';
import { transport } from './shared/transport';
import { ApiDecodeError } from './shared/typed_errors';

export type RegistryDeletionKind = 'case';
const previewSchema = z.object({
  kind: z.literal('case'), identity: z.string(), version: z.number().int().nonnegative(),
  client_version: z.number().int().nonnegative().nullable(), blockers: z.array(z.string()),
});
const receiptSchema = z.object({ kind: z.literal('case'), identity: z.string(), deleted: z.literal(true), replayed: z.boolean() });
export type RegistryDeletionPreview = z.infer<typeof previewSchema>;

function path(identity: string) {
  return `/api/v1/admin/registries/clients/${encodeURIComponent(identity)}/deletion`;
}
function decode<T>(schema: z.ZodType<T>, raw: unknown): T {
  const envelope = z.object({ success: z.literal(true), data: z.unknown() }).safeParse(raw);
  if (!envelope.success) throw new ApiDecodeError('無法確認刪除回應，請重新確認。');
  const parsed = schema.safeParse(envelope.data.data);
  if (!parsed.success) throw new ApiDecodeError('無法確認刪除回應，請重新確認。');
  return parsed.data;
}

export const registryDeletionClient = {
  async preview(kind: RegistryDeletionKind, identity: string) {
    const value = decode(previewSchema, await transport.get(path(identity), { token: sessionClient.getToken() }));
    if (value.kind !== kind || value.identity !== identity) throw new ApiDecodeError('刪除資格與選取資料不符。');
    return value;
  },
  async apply(preview: RegistryDeletionPreview, key: string) {
    const value = decode(receiptSchema, await transport.post(`${path(preview.identity)}/apply`, {
      expected_version: preview.version, expected_client_version: preview.client_version,
    }, {
      token: sessionClient.getToken(), headers: { 'Idempotency-Key': key, 'X-Correlation-ID': key },
    }));
    if (value.kind !== preview.kind || value.identity !== preview.identity) throw new ApiDecodeError('刪除結果與選取資料不符。');
    return value;
  },
};
