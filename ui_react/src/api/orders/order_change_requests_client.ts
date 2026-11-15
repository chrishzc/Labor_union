import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const PATH = '/api/v1/orders/change-requests';
const Completion = z.strictObject({
  result: z.string(),
  actor_name: z.string(),
  completed_at: z.iso.datetime({ offset: true }),
});
const RequestFields = {
  request_id: z.number().int().positive(),
  case_no: z.string().min(1),
  kind: z.enum(['service_address', 'cooking_requirement', 'service_days', 'daily_service_window', 'other']),
  before: z.record(z.string(), z.string()),
  requested: z.record(z.string(), z.string()),
  submitted_at: z.iso.datetime({ offset: true }),
};
const OrderChangeRequest = z.discriminatedUnion('status', [
  z.strictObject({ ...RequestFields, status: z.literal('pending'), version: z.literal(0), completion: z.null() }),
  z.strictObject({ ...RequestFields, status: z.literal('completed'), version: z.literal(1), completion: Completion }),
]);
const OrderChangeRequestPage = z.strictObject({
  items: z.array(OrderChangeRequest),
  next_before_id: z.number().int().positive().nullable(),
});
const LegacyOrderChangePage = z.strictObject({
  items: z.array(z.strictObject({
    event_id: z.number().int().positive(),
    ticket_id: z.number().int().positive(),
    ticket_status: z.enum(['waiting', 'handling', 'resolved']),
    submitted_at: z.iso.datetime({ offset: true }),
  })),
  next_before_id: z.number().int().positive().nullable(),
});

export type OrderChangeRequestItem = z.infer<typeof OrderChangeRequest>;
export type OrderChangeRequestPage = z.infer<typeof OrderChangeRequestPage>;
export type LegacyOrderChangePage = z.infer<typeof LegacyOrderChangePage>;

export const orderChangeRequestsClient = {
  async list(caseNo: string | undefined, beforeId: number | null, signal: AbortSignal) {
    const query = new URLSearchParams();
    if (caseNo) query.set('case_no', caseNo);
    if (beforeId !== null) query.set('before_id', String(beforeId));
    const url = query.size ? `${PATH}?${query}` : PATH;
    const raw = await transport.get<unknown>(url, { token: sessionClient.getToken(), signal });
    return decodeEnvelope(OrderChangeRequestPage, raw);
  },
  async complete(requestId: number, expectedVersion: number, result: string) {
    const raw = await transport.post<unknown>(
      `${PATH}/${requestId}/complete`,
      { expected_version: expectedVersion, result },
      { token: sessionClient.getToken() },
    );
    return decodeEnvelope(OrderChangeRequest, raw);
  },
  async legacy(caseNo: string, beforeId: number | null, signal: AbortSignal) {
    const query = new URLSearchParams({ case_no: caseNo });
    if (beforeId !== null) query.set('before_id', String(beforeId));
    const raw = await transport.get<unknown>(
      `${PATH}/legacy?${query}`, { token: sessionClient.getToken(), signal },
    );
    return decodeEnvelope(LegacyOrderChangePage, raw);
  },
};
