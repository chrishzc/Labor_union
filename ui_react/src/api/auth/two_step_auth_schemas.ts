/**
 * @file two_step_auth_schemas.ts
 * @description 定義管理員兩步驟認證、權限主體與會話管理之 Zod 執行期驗證綱要。
 */
import { z } from 'zod';

// ============================================================================
// 1. Stage 1: Password Challenge (POST /api/v1/admin/auth/login/challenges)
// ============================================================================

export const AdminPasswordChallengeRequestSchema = z.object({
  username: z.string().min(1, '請輸入帳號').max(100),
  password: z.string().min(1, '請輸入密碼').max(256),
});
export type AdminPasswordChallengeRequest = z.infer<
  typeof AdminPasswordChallengeRequestSchema
>;

export const AdminPasswordChallengeResponseSchema = z.object({
  challenge_id: z.string().min(1),
  challenge_token: z.string().min(32).max(256),
  expires_at: z.string().datetime({ offset: true }),
});
export type AdminPasswordChallengeResponse = z.infer<
  typeof AdminPasswordChallengeResponseSchema
>;

// ============================================================================
// 2. Stage 2: Factor Verification (POST /api/v1/admin/auth/login/challenges/{id}/verify)
// ============================================================================

export const AdminFactorVerificationRequestSchema = z.object({
  challenge_token: z.string().min(32).max(256),
  factor_code: z.string().regex(/^[0-9]{6}$/, '驗證碼格式必須為 6 位數字'),
});
export type AdminFactorVerificationRequest = z.infer<
  typeof AdminFactorVerificationRequestSchema
>;

// ============================================================================
// 3. Admin Public Principal & Session
// ============================================================================

export const AdminPublicSchema = z.object({
  id: z.number().int().nullable(),
  username: z.string().min(1),
  display_name: z.string().min(1),
  role: z.string().min(1),
  linked_line_user_id: z.string().nullable().optional(),
  capabilities: z.array(z.string()).default([]),
  is_root: z.boolean().default(false),
  access_control_version: z.number().int().default(1),
});
export type AdminPublic = z.output<typeof AdminPublicSchema>;
export type AdminPublicInput = z.input<typeof AdminPublicSchema>;

export const AdminSessionResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.string().default('bearer'),
  expires_at: z.string().datetime({ offset: true }),
  admin: AdminPublicSchema,
});
export type AdminSessionResponse = z.output<typeof AdminSessionResponseSchema>;

// ============================================================================
// 4. Session Refresh & Logout
// ============================================================================

export const AdminRefreshResponseSchema = z.object({
  access_token: z.string().min(1).optional(),
  token_type: z.string().default('bearer').optional(),
  expires_at: z.string().datetime({ offset: true }),
  admin: AdminPublicSchema.optional(),
});
export type AdminRefreshResponse = z.output<typeof AdminRefreshResponseSchema>;

export const AdminLogoutResponseSchema = z.object({
  logged_out: z.boolean(),
});
export type AdminLogoutResponse = z.infer<typeof AdminLogoutResponseSchema>;

// ============================================================================
// 5. Envelope Helper
// ============================================================================

export function createEnvelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z.object({
    success: z.boolean().default(true),
    message: z.string().optional().default('Success'),
    data: dataSchema.nullable().optional(),
    error: z.string().nullable().optional(),
  });
}
