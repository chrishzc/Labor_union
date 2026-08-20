/**
 * File: client_receipt_query_schemas.ts
 * Description: 定義Client Receipt根事實查詢的嚴格Zod契約。
 */
import { z } from 'zod';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);

export const ClientReceiptBankFactSchema = z.strictObject({
  finance_import_row_id: z.number().int().positive(),
  amount_ntd: z.number().int().positive(),
  transaction_date: DateSchema,
  dedup_fingerprint: FingerprintSchema,
});

export const ClientReceiptObligationSchema = z.strictObject({
  obligation_identity: z.string().min(1),
  payment_stage: z.enum(['deposit', 'first', 'second', 'adjustment']),
  amount_due_ntd: z.number().int().positive(),
  due_date: DateSchema.nullable(),
});

export const ClientReceiptQuerySchema = z.strictObject({
  case_no: z.string().min(1),
  account_version: z.number().int().nonnegative(),
  bank_facts: z.array(ClientReceiptBankFactSchema),
  obligations: z.array(ClientReceiptObligationSchema),
});

export const ClientReceiptQueryResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: ClientReceiptQuerySchema,
  error: z.string().nullable().optional(),
});

export type ClientReceiptQuery = z.infer<typeof ClientReceiptQuerySchema>;
