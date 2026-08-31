/** Strict current-state contracts for GET /api/v1/anomalies. */
import { z } from 'zod';

export const CURRENT_ANOMALY_DEFINITION_CODES = ['LINE-006'] as const;
export type CurrentAnomalyDefinitionCode = (typeof CURRENT_ANOMALY_DEFINITION_CODES)[number];

export const CurrentAnomalySummarySchema = z.strictObject({
  issue_key: z.string().regex(/^ci_[0-9a-f]{64}$/),
  definition_code: z.literal('LINE-006'),
  owner_domain: z.string().trim().min(1).max(191),
  severity: z.enum(['warning', 'blocking']),
  blocking: z.boolean(),
  episode_started_at: z.string().datetime({ offset: true }),
  last_verified_at: z.string().datetime({ offset: true }),
});
export type CurrentAnomalySummary = z.infer<typeof CurrentAnomalySummarySchema>;

export const CurrentAnomalyPageSchema = z.strictObject({
  items: z.array(CurrentAnomalySummarySchema).max(100),
  next_cursor: z.string().min(1).max(2048).nullable(),
});
export type CurrentAnomalyPage = z.infer<typeof CurrentAnomalyPageSchema>;

export const CurrentAnomalyPageResponseSchema = z.strictObject({
  success: z.literal(true),
  message: z.string(),
  data: CurrentAnomalyPageSchema,
  error: z.string().nullable().optional(),
});
