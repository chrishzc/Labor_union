/**
 * File: line_safe_review_link_schemas.ts
 * Description: M4 safe-review-link 的 strict query、redeem、revoke 與 readback DTO。
 */

import { z } from 'zod';

export const SafeReviewLinkStatusSchema = z.enum(['issued', 'redeemed', 'expired', 'revoked']);

export const SafeReviewLinkSchema = z.strictObject({
  link_id: z.string().min(1),
  status: SafeReviewLinkStatusSchema,
  canonical_internal_target: z.string().min(1),
  target_version: z.number().int().nonnegative(),
  source_alert_identity: z.string().min(1),
  expires_at_utc: z.string().datetime({ offset: true }),
  redeemed_at_utc: z.string().datetime({ offset: true }).nullable(),
  revoked_at_utc: z.string().datetime({ offset: true }).nullable(),
  root_version: z.number().int().nonnegative(),
});

export const SafeReviewLinkReceiptSchema = z.strictObject({
  receipt_id: z.string().min(1),
  outcome: SafeReviewLinkStatusSchema,
  replayed: z.boolean(),
  root_version: z.number().int().nonnegative(),
  readback: SafeReviewLinkSchema,
});

export const SafeReviewLinkRedeemRequestSchema = z.strictObject({
  raw_token: z.string().trim().min(1).max(512),
  capability: z.string().trim().min(1).max(100),
  current_target: z.string().trim().min(1).max(191),
  current_target_version: z.number().int().nonnegative(),
  idempotency_key: z.string().trim().min(1).max(191),
  correlation_id: z.string().trim().min(1).max(191),
});

export const SafeReviewLinkRevokeRequestSchema = z.strictObject({
  reason: z.string().trim().min(1).max(500),
  idempotency_key: z.string().trim().min(1).max(191),
  correlation_id: z.string().trim().min(1).max(191),
});

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });
}

export const SafeReviewLinkResponseSchema = envelope(SafeReviewLinkSchema);
export const SafeReviewLinkReceiptResponseSchema = envelope(SafeReviewLinkReceiptSchema);

export type SafeReviewLink = z.infer<typeof SafeReviewLinkSchema>;
export type SafeReviewLinkReceipt = z.infer<typeof SafeReviewLinkReceiptSchema>;
export type SafeReviewLinkRedeemRequest = z.infer<typeof SafeReviewLinkRedeemRequestSchema>;
export type SafeReviewLinkRevokeRequest = z.infer<typeof SafeReviewLinkRevokeRequestSchema>;
