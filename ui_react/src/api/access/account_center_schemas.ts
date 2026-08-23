/**
 * File: account_center_schemas.ts
 * Description: Root Account Center mutation 的 strict request/receipt 契約。
 */
import { z } from 'zod';
import { AccountDirectoryItemSchema } from './account_directory_schemas';

const commandBase = {
  reason: z.string().min(1).max(500),
  idempotency_key: z.string().min(1).max(191),
};

export const AccountCreateCommandSchema = z.object({
  username: z.string().min(1).max(100),
  password: z.string().min(12).max(256),
  display_name: z.string().min(1).max(100),
  linked_line_user_id: z.string().max(100).nullable().optional(),
  ...commandBase,
}).strict();

export const AccountEnabledCommandSchema = z.object({
  enabled: z.boolean(),
  expected_version: z.number().int().min(1),
  ...commandBase,
}).strict();

export const AccountPasswordResetCommandSchema = z.object({
  password: z.string().min(12).max(256),
  expected_version: z.number().int().min(1),
  ...commandBase,
}).strict();

export const AccountSecurityCommandSchema = z.object({
  expected_version: z.number().int().min(1),
  ...commandBase,
}).strict();

export const AccountMutationReceiptSchema = z.object({
  operation: z.enum([
    'account-create', 'account-enabled', 'account-password-reset',
    'account-mfa-reset', 'account-sessions-revoke',
  ]),
  target_account_id: z.number().int().positive(),
  resulting_access_control_version: z.number().int().min(1),
  receipt_identity: z.string().regex(/^[0-9a-f]{64}$/),
  replayed: z.boolean(),
  account: AccountDirectoryItemSchema.nullable().optional(),
}).strict();

export const AccountMutationResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
  data: AccountMutationReceiptSchema,
  error: z.string().nullable().optional(),
}).strict();

export type AccountCreateCommand = z.infer<typeof AccountCreateCommandSchema>;
export type AccountEnabledCommand = z.infer<typeof AccountEnabledCommandSchema>;
export type AccountPasswordResetCommand = z.infer<typeof AccountPasswordResetCommandSchema>;
export type AccountSecurityCommand = z.infer<typeof AccountSecurityCommandSchema>;
export type AccountMutationReceipt = z.infer<typeof AccountMutationReceiptSchema>;
