import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const view = z.strictObject({
  registration_id: z.number().int().positive(), version: z.number().int().positive(),
  name: z.string().nullable(), phone: z.string().nullable(), approved: z.boolean(),
  status: z.enum(['pending', 'approving', 'approved', 'rejected', 'expired']),
  submitted_at_utc: z.string().datetime({offset:true}), expires_at_utc: z.string().datetime({offset:true}),
  fields: z.array(z.strictObject({ label: z.string(), value: z.string() })),
  registration_kind: z.enum(['subsidy', 'non_citizen']),
  case_no: z.string().nullable(), approved_at_utc: z.string().nullable(),
  passbook_image_url: z.string().nullable().optional(),
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.literal(true), message: z.string(), data: schema, error: z.null(),
});
export type RegistrationApplication = z.infer<typeof view>;

export interface ManualNonCitizenCaseInput {
  mode?: 'new';
  name: string;
  phone: string;
  gender?: string;
  identity_status?: string;
  service_start_date: string;
  service_end_date?: string | null;
  service_days: number;
  service_time: string;
  service_type?: string;
  delivery_type?: string;
  residence_type?: string;
  baby_info: string;
  city?: string;
  address?: string;
  due_month?: string;
  birth_date?: string;
  email: string;
  line_id?: string;
  notes?: string;
  admin_notes?: string;
  requires_cooking?: boolean;
  refund_bank_code: string;
  refund_account_no: string;
  holiday_double_pay?: '是' | '否';
}

const caseNumberView = z.strictObject({
  case_no: z.string(),
  virtual_account: z.string(),
});
export type NonCitizenCaseNumber = z.infer<typeof caseNumberView>;

const manualCaseReceiptView = caseNumberView.extend({
  client_id: z.number().int(),
  message: z.string(),
});
export type ManualNonCitizenCaseReceipt = z.infer<typeof manualCaseReceiptView>;

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
  async reject(application: RegistrationApplication): Promise<RegistrationApplication> {
    const result = decodePayload(envelope(view), await transport.post(`${path}/${application.registration_id}/reject`,
      { expected_version: application.version }, options())).data;
    if (result.registration_id !== application.registration_id || !['rejected', 'expired'].includes(result.status)) throw new Error('拒絕結果尚未確認，請重新查詢同一筆申請。');
    return result;
  },
  async approve(application: RegistrationApplication): Promise<RegistrationApplication> {
    const result = decodePayload(envelope(view), await transport.post(`${path}/${application.registration_id}/approve`,
      { expected_version: application.version }, options())).data;
    if (result.registration_id !== application.registration_id || !result.approved) throw new Error('核准結果尚未確認，請重新查詢同一筆申請。');
    if (result.registration_kind === 'non_citizen' && (!result.case_no || !result.approved_at_utc)) throw new Error('正式案件尚未確認，請重新查詢同一筆申請。');
    return result;
  },
  async nextNonCitizenNumber(): Promise<NonCitizenCaseNumber> {
    return decodePayload(envelope(caseNumberView), await transport.get(`${path}/manual-non-citizen/next-number`, options())).data;
  },
  async createManualNonCitizen(input: ManualNonCitizenCaseInput): Promise<ManualNonCitizenCaseReceipt> {
    return decodePayload(envelope(manualCaseReceiptView), await transport.post(`${path}/manual-non-citizen`,
      input, options())).data;
  },
};
