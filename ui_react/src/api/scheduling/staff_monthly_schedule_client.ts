import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const DaySchema = z.strictObject({
  work_date: DateSchema,
  status: z.enum(['available', 'working', 'resting', 'historical_assignment', 'waiting_deposit_lock', 'staff_unavailability']),
  assignment_id: z.number().int().positive().nullable().optional(),
  case_no: z.string().nullable().optional(),
  staff_id: z.number().int().positive(),
  client_name: z.string().nullable().optional(),
  order_status: z.string().nullable().optional(),
  staff_name: z.string().nullable().optional(),
  is_work_day: z.boolean(),
  is_double_pay: z.boolean(),
  notes: z.string().nullable().optional(),
  lock_id: z.number().int().positive().nullable().optional(),
  plan_id: z.number().int().positive().nullable().optional(),
  unavailability_block_id: z.number().int().positive().nullable().optional(),
  unavailability_kind: z.enum(['long_leave', 'paused_service']).nullable().optional(),
  unavailability_reason: z.string().nullable().optional(),
});
const SummarySchema = z.strictObject({
  status: z.enum(['white', 'yellow', 'red', 'green', 'historical', 'unavailable']),
  case_no: z.string().nullable().optional(),
  client_name: z.string().nullable().optional(),
  is_work_day: z.boolean(),
  is_double_pay: z.boolean(),
  assignment_id: z.number().int().positive().nullable().optional(),
  lock_id: z.number().int().positive().nullable().optional(),
  plan_id: z.number().int().positive().nullable().optional(),
  unavailability_block_id: z.number().int().positive().nullable().optional(),
  unavailability_kind: z.enum(['long_leave', 'paused_service']).nullable().optional(),
  unavailability_reason: z.string().nullable().optional(),
});
const ResponseSchema = z.strictObject({
  success: z.boolean(), message: z.string(),
  data: z.strictObject({
    staff_id: z.number().int().positive(),
    year: z.number().int().min(1900).max(2100),
    month: z.number().int().min(1).max(12),
    days: z.array(DaySchema).min(28),
    schedule_map: z.record(SummarySchema),
  }),
  error: z.string().nullable().optional(),
});
export type StaffMonthlySchedule = z.infer<typeof ResponseSchema>['data'];

export const staffMonthlyScheduleClient = {
  async query(staffId: number, year: number, month: number, options?: { signal?: AbortSignal }): Promise<StaffMonthlySchedule> {
    const token = sessionClient.getToken();
    if (!token) throw new Error('請先登入。');
    const raw = await transport.get<unknown>(`/api/v1/staff/${staffId}/monthly-schedule`, { token, signal: options?.signal, params: { year, month } });
    const decoded = ResponseSchema.safeParse(raw);
    if (!decoded.success) throw new ApiDecodeError('歷史指派月曆回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
    if (!decoded.data.success) throw new Error(decoded.data.error ?? decoded.data.message);
    const projection = decoded.data.data;
    if (projection.staff_id !== staffId || projection.year !== year || projection.month !== month) throw new Error('歷史指派月曆回應與 request 不一致。');
    const requestedMonth = `${year}-${String(month).padStart(2, '0')}-`;
    const invalidDay = projection.days.find((day) => (
      !day.work_date.startsWith(requestedMonth)
      || day.staff_id !== staffId
      || (day.status === 'historical_assignment' && (
        day.assignment_id == null
        || !day.case_no
        || !day.client_name
        || day.is_work_day
      ))
    ));
    if (invalidDay) throw new ApiDecodeError('歷史指派月曆回應結構異常。', [{ path: 'data.days', message: '日期、服務人員或歷史指派語意不符合 request contract。', code: 'custom' }], raw);
    return projection;
  },
};
