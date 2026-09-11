import { z } from 'zod';

const nullableText = z.string().nullable();
export const StaffProfileMutationPreviewSchema = z.strictObject({ staff_id: z.number().int().positive(), current_version: z.number().int().nonnegative(), before: z.record(nullableText), after: z.record(nullableText), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) });
export const StaffProfileMutationReceiptSchema = z.strictObject({ staff_id: z.number().int().positive(), resulting_version: z.number().int().positive(), changed_fields: z.array(z.string()), preview_fingerprint: z.string(), idempotency_key: z.string(), replayed: z.boolean(), readback: z.record(z.string(), nullableText) });
const safeAccount = z.strictObject({ account_id: z.number().int().positive().nullable(), bank_code: nullableText, branch_code: nullableText, account_last4: z.string().regex(/^\d{4}$/).nullable(), is_primary: z.boolean(), is_active: z.boolean() });
export const StaffBankPreviewSchema = z.strictObject({ staff_id: z.number().int().positive(), current_version: z.number().int().nonnegative(), operation: z.enum(['add', 'replace', 'deactivate', 'set_primary']), before: safeAccount.nullable(), after: safeAccount.nullable(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) });
export const StaffBankReceiptSchema = z.strictObject({ staff_id: z.number().int().positive(), account_id: z.number().int().positive(), operation: z.enum(['add', 'replace', 'deactivate', 'set_primary']), resulting_version: z.number().int().positive(), preview_fingerprint: z.string(), idempotency_key: z.string(), replayed: z.boolean(), readback: z.array(safeAccount) });
export const response = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.boolean(), message: z.string(), data: data.nullable(), error: z.string().nullable() });
export type StaffProfileMutationPreview = z.infer<typeof StaffProfileMutationPreviewSchema>;
export type StaffBankPreview = z.infer<typeof StaffBankPreviewSchema>;
export type StaffBankCommand = { operation: 'add' | 'replace' | 'deactivate' | 'set_primary'; account_id?: number; bank_code?: string; branch_code?: string; account_no?: string; is_primary?: boolean; successor_account_id?: number };
