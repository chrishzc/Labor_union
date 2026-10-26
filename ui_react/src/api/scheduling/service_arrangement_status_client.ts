import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const arrangementSchema = z.strictObject({
  case_no: z.string().min(1), plan_id: z.number().int().positive(),
  state: z.enum(['awaiting_service_start', 'awaiting_conditions', 'ready', 'queued', 'running', 'effective', 'failed']),
  blockers: z.array(z.string()), job_id: z.string().nullable(), assignment_count: z.number().int().nonnegative(),
});
const completionSchema = z.strictObject({
  case_no: z.string().min(1), current_status: z.string(),
  completion_instant: z.string().refine(value => !Number.isNaN(Date.parse(value))).nullable(),
  state: z.enum(['awaiting_schedule', 'awaiting_service', 'waiting', 'due', 'blocked', 'completed', 'cancelled']),
  blockers: z.array(z.string()),
});
export type AutomaticArrangementStatus = z.infer<typeof arrangementSchema>;
export type AutomaticCompletionStatus = z.infer<typeof completionSchema>;

async function query<T extends { case_no: string }>(path: string, caseNo: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const raw = await transport.get<unknown>(path, { token, signal });
  const result = z.strictObject({ success: z.boolean(), message: z.string(), data: schema.nullable(), error: z.string().nullable() }).safeParse(raw);
  if (!result.success) throw new ApiDecodeError('服務安排狀態回應結構異常。');
  if (!result.data.success || result.data.data === null) throw new ApiHttpError(422, 'SERVICE_ARRANGEMENT_STATUS_UNAVAILABLE', result.data.error ?? result.data.message);
  if ((result.data.data as T).case_no !== caseNo) throw new ApiDecodeError('服務安排狀態案件不一致。');
  return result.data.data as T;
}

export const serviceArrangementStatusClient = {
  async arrangement(caseNo: string, planId: number, signal?: AbortSignal) {
    const result = await query(`/api/v1/orders/${encodeURIComponent(caseNo)}/matching-plans/${planId}/automatic-arrangement`, caseNo, arrangementSchema, signal);
    if (result.plan_id !== planId) throw new ApiDecodeError('自動排班狀態方案不一致。');
    return result;
  },
  completion(caseNo: string, signal?: AbortSignal) {
    return query(`/api/v1/orders/${encodeURIComponent(caseNo)}/service-completion`, caseNo, completionSchema, signal);
  },
};

export function serviceArrangementBlockerLabel(code: string): string {
  const labels: Record<string, string> = {
    automatic_waiting_deposit_occupancy_conflict: '月嫂檔期衝突，無法自動保留，請更換月嫂或調整服務日期。',
    automatic_waiting_deposit_stale_plan: '推薦人選已變更，請重新讀取配對與服務日期。',
    matching_schedule_segment_dates_required: '月嫂分段沒有服務日期，請先核對各段日期，再重新確認日期表。',
    commitment_execution_mismatch: '目前排班的人選、服務天數或日期與簽約內容及雙方最新確認的日期表不符，請核對服務安排。',
    commitment_not_effective: '目前沒有有效的月嫂簽約服務資料，請先到「辦理契約與簽署」確認。',
    staff_occupancy_conflict: '月嫂目前有其他正式服務、有效預留或不可服務日期衝突，請調整日期或更換月嫂。',
    'assignment_plan_bootstrap.waiting_lock_required': '配對及服務日期確認後會自動保留檔期，請核對確認狀態。',
    'waiting_lock_conversion.contract_required': '客戶或月嫂契約尚未簽回。',
    'waiting_lock_conversion.service_time_required': '服務開始、結束時間或每日時數尚未完整。',
    'waiting_lock_conversion.deposit_required': '訂金尚未付清或人工放行。',
    matching_schedule_two_party_confirmation_required: '客戶與所有月嫂尚未確認目前日期表。',
    matching_schedule_confirmation_required: '請先儲存服務日期並記錄雙方確認。',
    confirmed_service_dates_required: '服務日期尚未儲存。',
    matching_schedule_confirmation_required_for_target_segments: '日期表與目前分段人選不同，請重新核對。',
    bootstrap_deposit_settlement_required: '訂金尚未付清或人工放行。',
    deposit_settlement_required: '訂金尚未付清或人工放行。',
    waiting_deposit_lock_required: '配對及服務日期確認後會自動保留檔期，請核對確認狀態。',
    bootstrap_contract_completion_required: '客戶或月嫂契約尚未簽回。',
    contract_completion_required: '客戶或月嫂契約尚未簽回。',
    automatic_arrangement_result_requires_readback: '自動排班尚未取得一致結果，請核對處理紀錄。',
  };
  return labels[code] ?? `尚未符合排班條件：${code}`;
}
