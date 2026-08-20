/**
 * File: staff_payables_query_schemas.ts
 * Description: 定義Staff Payables obligations與events唯讀查詢的嚴格Zod契約。
 */
import { z } from 'zod';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const StaffPayablesQuerySchema = z.strictObject({
  staff_id: z.number().int().positive(),
  staff_payables_version: z.number().int().nonnegative(),
  obligations: z.array(z.strictObject({
    obligation_identity: z.string().min(1),
    case_no: z.string().min(1),
    amount_due_ntd: z.number().int().positive(),
    due_date: DateSchema.nullable(),
    net_paid_ntd: z.number().int().nonnegative(),
    balance_ntd: z.number().int(),
    payout_status: z.string(),
  })),
  events: z.array(z.strictObject({
    id: z.number().int().positive(),
    event_type: z.string(),
    amount_ntd: z.number().int().positive(),
    occurred_on: DateSchema,
    finance_import_row_id: z.number().int().positive().nullable(),
    reversal_of_event_id: z.number().int().positive().nullable(),
    reconciliation_reference: z.string(),
  })),
});
export const StaffPayablesResponseSchema = z.strictObject({ success: z.boolean(), message: z.string(), data: StaffPayablesQuerySchema, error: z.string().nullable().optional() });
export type StaffPayablesQuery = z.infer<typeof StaffPayablesQuerySchema>;
