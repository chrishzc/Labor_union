import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

const scalar = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const schema = z.strictObject({
  case_no: z.string(), scope: z.string(), assignment_id: z.number().int().positive().nullable(),
  template_key: z.string(), template_version: z.string().regex(/^[0-9a-f]{64}$/),
  owner_fingerprints: z.record(z.string(), z.string()),
  field_values: z.record(z.string(), z.union([scalar, z.array(scalar)])),
  blockers: z.array(z.string()), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/), ready_to_print: z.boolean(),
});
export type ContractFullPreview = z.infer<typeof schema>;

/** POST Preview is zero-write under the existing Contract Signing contract. */
export async function previewContractFields(caseNo: string, scope: 'client' | 'staff', segmentId: number | null, signal: AbortSignal): Promise<ContractFullPreview> {
  if (scope === 'staff' && (segmentId === null || !Number.isSafeInteger(segmentId) || segmentId <= 0)) throw new Error('請先選擇月嫂契約。');
  const target = scope === 'client' ? 'client' : `staff-segments/${segmentId}`;
  const response = decodePayload(z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.null() }),
    await transport.post(`/api/v1/orders/${encodeURIComponent(caseNo)}/contract-signing/${target}/preview`, {}, { token: sessionClient.getToken(), signal }));
  const expectedTemplate = scope === 'client' ? 'contract_client_copy' : 'contract_staff_service';
  if (response.data.case_no !== caseNo || response.data.scope !== scope || response.data.template_key !== expectedTemplate) throw new Error('契約預覽對象不一致。');
  return response.data;
}
