import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const view = z.strictObject({
  registration_id: z.number().int().positive(), version: z.number().int().positive(),
  name: z.string(), phone: z.string(), approved: z.boolean(),
  fields: z.array(z.strictObject({ label: z.string(), value: z.string() })),
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.literal(true), message: z.string(), data: schema, error: z.null(),
});
export type RegistrationApplication = z.infer<typeof view>;
const path = '/api/v1/admin/registration-applications';
const options = () => {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理後台。');
  return { token };
};
export const registrationApplicationsClient = {
  async pending(afterId = 0): Promise<RegistrationApplication[]> {
    return decodePayload(envelope(z.array(view)), await transport.get(`${path}?after_id=${afterId}`, options())).data;
  },
  async detail(id: number): Promise<RegistrationApplication> {
    const result = decodePayload(envelope(view), await transport.get(`${path}/${id}`, options())).data;
    if (result.registration_id !== id) throw new Error('申請回應編號不一致。');
    return result;
  },
  async approve(application: RegistrationApplication): Promise<RegistrationApplication> {
    const result = decodePayload(envelope(view), await transport.post(`${path}/${application.registration_id}/approve`,
      { expected_version: application.version }, options())).data;
    if (result.registration_id !== application.registration_id || !result.approved) throw new Error('核准結果尚未確認，請重新查詢同一筆申請。');
    return result;
  },
};
