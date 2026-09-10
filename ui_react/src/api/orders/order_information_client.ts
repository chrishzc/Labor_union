import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

const schema = z.strictObject({
  template_id: z.enum(['tpl_info_01', 'tpl_info_02']),
  case_no: z.string(),
  assignment_id: z.number().int().positive(),
  fields: z.array(z.strictObject({
    field_id: z.string(), label: z.string(), owner: z.string(), source: z.string().nullable(),
    requiredness: z.string(), status: z.string(), value: z.union([z.string(), z.number(), z.null()]),
  })),
  owner_fingerprints: z.record(z.string(), z.string()),
  blockers: z.array(z.string()), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  can_render: z.boolean(),
});
export type OrderInformation = z.infer<typeof schema>;

/** Existing read-only Orders endpoint; no send, document creation or business calculation. */
export async function queryOrderInformation(caseNo: string, kind: 1 | 2, assignmentId: number, signal: AbortSignal): Promise<OrderInformation> {
  const template = kind === 1 ? 'tpl_info_01' : 'tpl_info_02';
  const response = decodePayload(z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.null() }),
    await transport.get(`/api/v1/orders/${encodeURIComponent(caseNo)}/order-information/${template}`, {
      token: sessionClient.getToken(), signal, params: { assignment_id: assignmentId },
    }));
  if (response.data.case_no !== caseNo || response.data.template_id !== template || response.data.assignment_id !== assignmentId) {
    throw new Error('資料與所選案件或月嫂不一致，請重新查詢。');
  }
  return response.data;
}
