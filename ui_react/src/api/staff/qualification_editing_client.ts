/** Typed Q/P/A for existing manually registered Staff qualification facts. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';

const texts = (length: number) => z.array(z.string().min(1).max(length)).max(100);
const factsSchema = z.strictObject({
  special_skills: texts(191), has_massage_cert: z.boolean().nullable(),
  certifications: texts(191), care_babies: z.number().int().positive().max(2147483647).nullable(),
  transportation: texts(50),
});
const fingerprint = z.string().regex(/^[0-9a-f]{64}$/);
const snapshotSchema = z.strictObject({ staff_id: z.number().int().positive(), before: factsSchema, after: factsSchema, snapshot_fingerprint: fingerprint, preview_fingerprint: fingerprint.nullable() });
const receiptSchema = snapshotSchema.extend({ idempotency_key: z.string(), replayed: z.boolean(), correlation_id: z.string() });
export type QualificationFacts = z.infer<typeof factsSchema>;
export type QualificationSnapshot = z.infer<typeof snapshotSchema>;

function auth(signal?: AbortSignal, key?: string) {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理後台。');
  return { token, signal, headers: { 'X-Correlation-ID': `staff-qualification-${crypto.randomUUID()}`, ...(key ? { 'Idempotency-Key': key } : {}) } };
}
function decode<T>(schema: z.ZodType<T>, raw: unknown, staffId: number): T {
  const envelope = z.object({ success: z.literal(true), data: schema }).safeParse(raw);
  if (!envelope.success || (envelope.data.data as { staff_id: number }).staff_id !== staffId) throw new ApiDecodeError('資格資料回應異常，請重新查詢。', [], raw);
  return schema.parse(envelope.data.data);
}
const endpoint = (id: number) => {
  if (!Number.isInteger(id) || id <= 0) throw new Error('月嫂識別資料無效。');
  return `/api/v1/staff/${id}/qualification-editing`;
};
export const staffQualificationEditingClient = {
  async query(id: number, signal?: AbortSignal) { return decode(snapshotSchema, await transport.get(endpoint(id), auth(signal)), id); },
  async preview(id: number, facts: QualificationFacts, signal?: AbortSignal) { return decode(snapshotSchema, await transport.post(endpoint(id) + '/preview', factsSchema.parse(facts), auth(signal)), id); },
  async apply(id: number, facts: QualificationFacts, preview: QualificationSnapshot, reason: string, key: string, signal?: AbortSignal) {
    return decode(receiptSchema, await transport.post(endpoint(id) + '/apply', { ...factsSchema.parse(facts), expected_snapshot_fingerprint: preview.snapshot_fingerprint, preview_fingerprint: preview.preview_fingerprint, reason }, auth(signal, key)), id);
  },
};
