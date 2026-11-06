import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';

const preview = z.strictObject({
  kind: z.enum(['settlement', 'refund', 'collection']),
  text: z.string().nullable(),
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/).nullable(),
  unavailable_reason: z.string().nullable(),
  delivery_status: z.string().nullable(),
});
const result = z.strictObject({ task_id: z.number().int().positive(), status: z.string() });
export type CancellationNotice = z.infer<typeof preview>;
export type CancellationNoticeKind = CancellationNotice['kind'];

function endpoint(caseNo: string) {
  return `/api/v1/line/payment-overdue-reminders/cancellation-notices/${encodeURIComponent(caseNo)}`;
}

function options() {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  return { token };
}

export const cancellationNotificationClient = {
  async previews(caseNo: string, signal?: AbortSignal) {
    const response = await transport.get<{ data: unknown }>(endpoint(caseNo), { ...options(), signal, cache: 'no-store' });
    return z.array(preview).parse(response.data);
  },
  async send(caseNo: string, kind: CancellationNoticeKind, fingerprint: string) {
    const response = await transport.post<{ data: unknown }>(`${endpoint(caseNo)}/send`, { kind, fingerprint }, options());
    return result.parse(response.data);
  },
};
