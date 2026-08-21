/**
 * File: holiday_schemas.ts
 * Description: 定義國定假日 Query、Preview、Apply 與 receipt 的 strict Zod 契約。
 */
import { z } from 'zod';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

function isCalendarDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export const HolidayDateSchema = z
  .string()
  .regex(ISO_DATE_PATTERN, '日期必須是 YYYY-MM-DD。')
  .refine(isCalendarDate, '日期不是有效日曆日期。');

export const HolidayFingerprintSchema = z
  .string()
  .regex(SHA256_PATTERN, 'fingerprint 必須是小寫 SHA-256。');

export const HolidayActionSchema = z.enum(['upsert', 'delete']);

export const HolidayHorizonSchema = z
  .strictObject({
    from_date: HolidayDateSchema,
    to_date: HolidayDateSchema,
  })
  .superRefine((horizon, context) => {
    if (horizon.from_date > horizon.to_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['to_date'],
        message: 'to_date 不得早於 from_date。',
      });
    }
  });

export const HolidayRowSchema = z.strictObject({
  holiday_date: HolidayDateSchema,
  holiday_name: z.string().min(1).max(100),
  is_double_pay_default: z.boolean(),
});

export const HolidayCalendarSchema = z.strictObject({
  planning_horizon: HolidayHorizonSchema,
  source_identity: z.string().min(1),
  calendar_version: HolidayFingerprintSchema,
  holidays: z.array(HolidayRowSchema).readonly(),
});

const HolidayQueryCamelSchema = z
  .strictObject({
    fromDate: HolidayDateSchema,
    toDate: HolidayDateSchema,
  })
  .superRefine((query, context) => {
    if (query.fromDate > query.toDate) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['toDate'],
        message: 'toDate 不得早於 fromDate。',
      });
    }
  });

const HolidayQuerySnakeSchema = z
  .strictObject({
    from_date: HolidayDateSchema,
    to_date: HolidayDateSchema,
  })
  .superRefine((query, context) => {
    if (query.from_date > query.to_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['to_date'],
        message: 'to_date 不得早於 from_date。',
      });
    }
  });

export const HolidayQuerySchema = z.union([
  HolidayQueryCamelSchema,
  HolidayQuerySnakeSchema,
]);

export const HolidayPreviewRequestSchema = z
  .strictObject({
    action: HolidayActionSchema,
    holiday_date: HolidayDateSchema,
    holiday_name: z.string().trim().min(1).max(100).nullable().optional(),
    is_double_pay_default: z.boolean().optional(),
    from_date: HolidayDateSchema.optional(),
    to_date: HolidayDateSchema.optional(),
  })
  .superRefine((request, context) => {
    if (request.action === 'upsert' && !request.holiday_name) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['holiday_name'],
        message: 'upsert 必須提供 holiday_name。',
      });
    }
    if ((request.from_date === undefined) !== (request.to_date === undefined)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['from_date'],
        message: 'from_date 與 to_date 必須同時提供。',
      });
    }
    if (
      request.from_date !== undefined &&
      request.to_date !== undefined &&
      request.from_date > request.to_date
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['to_date'],
        message: 'to_date 不得早於 from_date。',
      });
    }
    if (
      request.from_date !== undefined &&
      request.to_date !== undefined &&
      (request.holiday_date < request.from_date || request.holiday_date > request.to_date)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['holiday_date'],
        message: 'holiday_date 必須位於 planning horizon 內。',
      });
    }
  });

export const HolidayApplyRequestSchema = z
  .strictObject({
    action: HolidayActionSchema,
    holiday_date: HolidayDateSchema,
    holiday_name: z.string().trim().min(1).max(100).nullable().optional(),
    is_double_pay_default: z.boolean().optional(),
    from_date: HolidayDateSchema.optional(),
    to_date: HolidayDateSchema.optional(),
    expected_calendar_version: HolidayFingerprintSchema,
    preview_fingerprint: HolidayFingerprintSchema,
    reason: z.string().trim().min(1).max(500),
  })
  .superRefine((request, context) => {
    if (request.action === 'upsert' && !request.holiday_name) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['holiday_name'],
        message: 'upsert 必須提供 holiday_name。',
      });
    }
    if ((request.from_date === undefined) !== (request.to_date === undefined)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['from_date'],
        message: 'from_date 與 to_date 必須同時提供。',
      });
    }
    if (
      request.from_date !== undefined &&
      request.to_date !== undefined &&
      request.from_date > request.to_date
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['to_date'],
        message: 'to_date 不得早於 from_date。',
      });
    }
    if (
      request.from_date !== undefined &&
      request.to_date !== undefined &&
      (request.holiday_date < request.from_date || request.holiday_date > request.to_date)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['holiday_date'],
        message: 'holiday_date 必須位於 planning horizon 內。',
      });
    }
  });

export const HolidayPreviewCommandSchema = z.strictObject({
  action: HolidayActionSchema,
  holiday_date: HolidayDateSchema,
  holiday_name: z.string().min(1).max(100).nullable(),
  is_double_pay_default: z.boolean(),
  from_date: HolidayDateSchema,
  to_date: HolidayDateSchema,
  expected_calendar_version: HolidayFingerprintSchema,
});

export const HolidayPreviewSchema = z.strictObject({
  command: HolidayPreviewCommandSchema,
  before: HolidayRowSchema.nullable(),
  planning_horizon: HolidayHorizonSchema,
  source_identity: z.string().min(1),
  calendar_version: HolidayFingerprintSchema,
  schedule_impact: z.literal('none'),
  payroll_impact: z.literal('none'),
  preview_fingerprint: HolidayFingerprintSchema,
});

export const HolidayReceiptSchema = z.strictObject({
  receipt_key: z.string().min(1).max(191),
  action: HolidayActionSchema,
  holiday_date: HolidayDateSchema,
  changed: z.boolean(),
  planning_horizon: HolidayHorizonSchema,
  source_identity: z.string().min(1),
  previous_calendar_version: HolidayFingerprintSchema,
  resulting_calendar_version: HolidayFingerprintSchema,
  preview_fingerprint: HolidayFingerprintSchema,
});

const baseResponseFields = {
  success: z.boolean(),
  message: z.string(),
  error: z.string().nullable().optional(),
};

export const HolidayQueryResponseSchema = z.strictObject({
  ...baseResponseFields,
  data: z.union([HolidayCalendarSchema, z.array(HolidayRowSchema)]).nullable(),
});

export const HolidayPreviewResponseSchema = z.strictObject({
  ...baseResponseFields,
  data: HolidayPreviewSchema.nullable(),
});

export const HolidayReceiptResponseSchema = z.strictObject({
  ...baseResponseFields,
  data: HolidayReceiptSchema.nullable(),
});

export type HolidayDate = z.infer<typeof HolidayDateSchema>;
export type HolidayAction = z.infer<typeof HolidayActionSchema>;
export type HolidayHorizon = z.infer<typeof HolidayHorizonSchema>;
export type HolidayRow = z.infer<typeof HolidayRowSchema>;
export type HolidayCalendar = z.infer<typeof HolidayCalendarSchema>;
export type HolidayQuery = z.infer<typeof HolidayQuerySchema>;
export type HolidayPreviewRequest = z.infer<typeof HolidayPreviewRequestSchema>;
export type HolidayApplyRequest = z.infer<typeof HolidayApplyRequestSchema>;
export type HolidayPreviewCommand = z.infer<typeof HolidayPreviewCommandSchema>;
export type HolidayPreview = z.infer<typeof HolidayPreviewSchema>;
export type HolidayReceipt = z.infer<typeof HolidayReceiptSchema>;
export type HolidayQueryResponse = z.infer<typeof HolidayQueryResponseSchema>;
export type HolidayPreviewResponse = z.infer<typeof HolidayPreviewResponseSchema>;
export type HolidayReceiptResponse = z.infer<typeof HolidayReceiptResponseSchema>;

// 以 verb-oriented alias 保留 client/adapter 易讀的公開命名。
export const HolidayCalendarViewSchema = HolidayCalendarSchema;
export const HolidayRowViewSchema = HolidayRowSchema;
export const HolidayPreviewViewSchema = HolidayPreviewSchema;
export const HolidayReceiptViewSchema = HolidayReceiptSchema;
