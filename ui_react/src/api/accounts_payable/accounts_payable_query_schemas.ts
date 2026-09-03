/**
 * File: accounts_payable_query_schemas.ts
 * Description: 定義Accounts Payable server-canonical preview的嚴格Zod契約。
 */
import { z } from 'zod';
const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const AccountsPayablePreviewSchema = z.strictObject({
  target_payment_date: DateSchema,
  row_count: z.number().int().nonnegative(),
  total_amount_ntd: z.number().int().nonnegative(),
  rows: z.array(z.strictObject({
    payment_date: DateSchema,
    payment_type: z.string(),
    recipient_name: z.string(),
    bank_code: z.string(),
    bank_account: z.string(),
    amount_ntd: z.number().int().positive(),
    obligation_identities: z.array(z.string()),
    case_numbers: z.array(z.string()),
    recipient_identity_card: z.string(),
  })),
});
export const AccountsPayableResponseSchema = z.strictObject({ success: z.boolean(), message: z.string(), data: AccountsPayablePreviewSchema, error: z.string().nullable().optional() });
export type AccountsPayablePreview = z.infer<typeof AccountsPayablePreviewSchema>;
