/**
 * File: matching_plan_communication_client.ts
 * Description: 以正式媒合方案契約建立履歷可靠發送任務或補登決策，嚴格驗證版本與回條 identity。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const CustomerDecisionReceiptSchema = z.strictObject({
  event_id: z.number().int().positive(),
  communication_version: z.number().int().nonnegative(),
  source: z.enum(['admin', 'manual', 'line']),
  willingness: z.null(),
  customer_decision: z.enum(['accepted', 'declined', 'contact_requested']),
});

const FormalPlanContactStateSchema = z.strictObject({
  plan: z.object({
    id: z.number().int().positive(),
    case_no: z.string().min(1).max(50),
    communication_version: z.number().int().nonnegative(),
    status: z.enum(['proposed', 'accepted']),
    is_active: z.number().int().nullable(),
  }).passthrough(),
  segments: z.array(z.object({
    segment_id: z.number().int().positive(),
    willingness: z.enum(['pending', 'willing', 'unwilling']),
  }).passthrough()).min(1),
  all_willing: z.boolean(),
  customer_decision: z.enum(['pending', 'accepted', 'declined', 'contact_requested']),
  customer_profiles_status: z.string().nullable(),
});

const CaregiverWillingnessReceiptSchema = z.strictObject({
  event_id: z.number().int().positive(),
  communication_version: z.number().int().nonnegative(),
  source: z.enum(['admin', 'manual', 'line']),
  willingness: z.literal('willing'),
  customer_decision: z.null(),
});

const CustomerProfilesNotificationReceiptSchema = z.strictObject({
  intent_id: z.number().int().positive(),
  line_delivery_task_id: z.number().int().positive().nullable(),
  delivery_status: z.enum(['pending', 'projected', 'failed', 'cancelled']),
  notification_kind: z.literal('customer_profiles'),
}).superRefine((receipt, context) => {
  if (receipt.delivery_status === 'projected' && receipt.line_delivery_task_id === null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['line_delivery_task_id'],
      message: '已投影的履歷發送任務必須有 LINE task identity。',
    });
  }
});

const EnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: CustomerDecisionReceiptSchema.nullable(),
  error: z.string().nullable(),
});

const ContactStateEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: FormalPlanContactStateSchema.nullable(),
  error: z.string().nullable(),
});

const WillingnessEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: CaregiverWillingnessReceiptSchema.nullable(),
  error: z.string().nullable(),
});

const CustomerProfilesNotificationEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: CustomerProfilesNotificationReceiptSchema.nullable(),
  error: z.string().nullable(),
});

export type CustomerDecisionReceipt = z.infer<typeof CustomerDecisionReceiptSchema>;
export type FormalPlanContactState = z.infer<typeof FormalPlanContactStateSchema>;
export type CustomerProfilesNotificationReceipt = z.infer<typeof CustomerProfilesNotificationReceiptSchema>;

function canonicalCaseNo(caseNo: string): string {
  const canonical = caseNo.trim();
  if (!canonical || canonical.length > 50) throw new Error('案件編號必須是 1 至 50 字元。');
  return canonical;
}

export const matchingPlanCommunicationClient = {
  async queryContactState(caseNo: string, planId: number): Promise<FormalPlanContactState> {
    const canonical = canonicalCaseNo(caseNo);
    const token = sessionClient.getToken();
    if (!Number.isInteger(planId) || planId <= 0) throw new Error('正式媒合方案識別必須是正整數。');
    if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const decoded = decodePayload(
      ContactStateEnvelopeSchema,
      await transport.get(
        `/api/v1/orders/${encodeURIComponent(canonical)}/matching-plans/${planId}/contact-state`,
        { token },
      ),
    );
    if (!decoded.success || decoded.data === null) {
      throw new ApiHttpError(422, 'MATCHING_CONTACT_STATE_QUERY_FAILED', decoded.error ?? decoded.message, false, decoded);
    }
    if (decoded.data.plan.id !== planId || decoded.data.plan.case_no !== canonical) {
      throw new Error('正式媒合方案聯繫狀態 identity 不一致。');
    }
    return decoded.data;
  },

  async sendCustomerProfiles(
    caseNo: string,
    planId: number,
    expectedVersion: number,
    note: string,
  ): Promise<CustomerProfilesNotificationReceipt> {
    const canonical = canonicalCaseNo(caseNo);
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    const token = sessionClient.getToken();
    const canonicalNote = note.trim();
    if (!Number.isInteger(planId) || planId <= 0) throw new Error('正式媒合方案識別必須是正整數。');
    if (!Number.isInteger(expectedVersion) || expectedVersion < 0) throw new Error('正式媒合方案版本無效，請重新載入。');
    if (!actor || !token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    if (!canonicalNote || canonicalNote.length > 1000) throw new Error('請填寫 1 至 1000 字的履歷傳送備註。');
    const decoded = decodePayload(
      CustomerProfilesNotificationEnvelopeSchema,
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonical)}/matching-plans/${planId}/resumes`,
        {
          actor,
          event_key: `orders-customer-profiles-${planId}-${crypto.randomUUID()}`,
          expected_version: expectedVersion,
          note: canonicalNote,
        },
        { token },
      ),
    );
    if (!decoded.success || decoded.data === null) {
      throw new ApiHttpError(422, 'CUSTOMER_PROFILES_SEND_FAILED', decoded.error ?? decoded.message, false, decoded);
    }
    return decoded.data;
  },

  async recordFormalPlanWillingness(
    caseNo: string,
    planId: number,
    segmentId: number,
    expectedVersion: number,
    reason: string,
  ): Promise<void> {
    const canonical = canonicalCaseNo(caseNo);
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    const token = sessionClient.getToken();
    const canonicalReason = reason.trim();
    if (!Number.isInteger(planId) || planId <= 0 || !Number.isInteger(segmentId) || segmentId <= 0) throw new Error('正式媒合方案或區段識別無效。');
    if (!Number.isInteger(expectedVersion) || expectedVersion < 0) throw new Error('正式媒合方案版本無效，請重新載入。');
    if (!actor || !token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    if (!canonicalReason || canonicalReason.length > 500) throw new Error('請填寫 1 至 500 字的月嫂確認依據。');
    const decoded = decodePayload(
      WillingnessEnvelopeSchema,
      await transport.put(
        `/api/v1/orders/${encodeURIComponent(canonical)}/matching-plans/${planId}/segments/${segmentId}/willingness`,
        {
          actor,
          event_key: `orders-formal-plan-willingness-${planId}-${segmentId}-${crypto.randomUUID()}`,
          willingness: 'willing',
          expected_version: expectedVersion,
          reason: canonicalReason,
        },
        { token },
      ),
    );
    if (!decoded.success || decoded.data === null) {
      throw new ApiHttpError(422, 'FORMAL_PLAN_WILLINGNESS_FAILED', decoded.error ?? decoded.message, false, decoded);
    }
    if (decoded.data.communication_version < expectedVersion) throw new Error('月嫂意願回條版本倒退，請重新載入。');
  },

  async recordCustomerDecision(
    caseNo: string,
    planId: number,
    expectedVersion: number,
    decision: 'accepted' | 'declined' | 'contact_requested',
    reason: string,
  ): Promise<CustomerDecisionReceipt> {
    const canonical = canonicalCaseNo(caseNo);
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    const token = sessionClient.getToken();
    const canonicalReason = reason.trim();
    if (!Number.isInteger(planId) || planId <= 0) throw new Error('正式媒合方案識別必須是正整數。');
    if (!Number.isInteger(expectedVersion) || expectedVersion < 0) throw new Error('正式媒合方案版本無效，請重新載入。');
    if (!actor || !token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    if (!canonicalReason || canonicalReason.length > 500) throw new Error('請填寫 1 至 500 字的客戶決策依據。');

    const decoded = decodePayload(
      EnvelopeSchema,
      await transport.put(
        `/api/v1/orders/${encodeURIComponent(canonical)}/matching-plans/${planId}/customer-decision`,
        {
          actor,
          event_key: `orders-customer-decision-${planId}-${crypto.randomUUID()}`,
          decision,
          expected_version: expectedVersion,
          reason: canonicalReason,
        },
        { token },
      ),
    );
    if (!decoded.success || decoded.data === null) {
      throw new ApiHttpError(422, 'MATCHING_CUSTOMER_DECISION_FAILED', decoded.error ?? decoded.message, false, decoded);
    }
    if (decoded.data.communication_version < expectedVersion) {
      throw new Error('客戶決策回條版本倒退，請重新載入。');
    }
    return decoded.data;
  },
};
