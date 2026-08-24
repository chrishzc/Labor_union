/**
 * File: schedule_precision_client.ts
 * Description: 以 strict contract 傳送固定週休、假日、請假及人工服務日覆核，回傳 server 精算結果。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const DateText = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const SchedulePrecisionRequestSchema = z.strictObject({
  actual_start_date: DateText,
  target_service_days: z.number().int().positive(),
  service_mode: z.enum(['週休1日', '週休2日', '連續服務']),
  custom_holiday_rest_dates: z.array(DateText).optional(),
  custom_leave_dates: z.array(DateText).optional(),
  custom_work_dates: z.array(DateText).optional(),
});
const SchedulePrecisionResultSchema = z.strictObject({
  actual_start_date: DateText,
  actual_end_date: DateText,
  target_service_days: z.number().int().positive(),
  total_calendar_days: z.number().int().positive(),
  actual_work_days_count: z.number().int().nonnegative(),
  rest_days_count: z.number().int().nonnegative(),
  national_holidays_found: z.array(z.strictObject({ date: DateText, name: z.string().nullable(), is_worked: z.boolean() })),
  total_estimated_salary: z.number().nonnegative().nullable(),
  weekly_stats: z.array(z.strictObject({ week_num: z.number().int().positive(), start_date: DateText, end_date: DateText, work_days: z.number().int().nonnegative(), rest_days: z.number().int().nonnegative(), holiday_days: z.number().int().nonnegative() })),
  day_by_day: z.array(z.strictObject({ date: DateText, day_num: z.number().int().positive(), is_work_day: z.boolean(), is_rest_day: z.boolean(), holiday_name: z.string().nullable() })),
});
const ResponseSchema = z.object({ success: z.boolean(), message: z.string(), data: SchedulePrecisionResultSchema.nullable(), error: z.string().nullable().optional() }).passthrough();

export type SchedulePrecisionRequest = z.infer<typeof SchedulePrecisionRequestSchema>;
export type SchedulePrecisionResult = z.infer<typeof SchedulePrecisionResultSchema>;

export const schedulePrecisionClient = {
  async calculate(request: SchedulePrecisionRequest): Promise<SchedulePrecisionResult> {
    const parsedRequest = SchedulePrecisionRequestSchema.safeParse(request);
    if (!parsedRequest.success) throw new ApiDecodeError('出勤精算輸入不符合契約。');
    const token = sessionClient.getToken();
    if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const raw = await transport.post<unknown>('/api/v1/orders/calculate-schedule', parsedRequest.data, {
      token, headers: { 'X-Correlation-ID': `schedule-precision-${crypto.randomUUID()}` },
    });
    const parsed = ResponseSchema.safeParse(raw);
    if (!parsed.success) throw new ApiDecodeError('出勤精算回應結構異常。', parsed.error.issues.map((i) => ({ path: i.path.join('.'), message: i.message, code: i.code })), raw);
    if (!parsed.data.success || parsed.data.data === null) throw new ApiHttpError(422, 'SCHEDULE_PRECISION_EMPTY', parsed.data.error ?? parsed.data.message, false, raw);
    return parsed.data.data;
  },
};
