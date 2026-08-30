/**
 * File: historical_operational_baseline_schemas.ts
 * Description: 嚴格解碼 Orders owned Historical Operational Baseline Query。
 */
import { z } from 'zod';

const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const CaseNoSchema = z.string().min(1).max(50).regex(/^[^\s]+$/);
const IdentitySchema = z.string().min(1).max(191);
const StepStateSchema = z.enum(['historical_baseline_completed', 'in_progress']);

export const HistoricalOperationalBaselineStepSchema = z.strictObject({
  step: z.number().int().min(1).max(11),
  state: StepStateSchema,
});

export const HistoricalOperationalBaselineProvenanceSchema = z.strictObject({
  source_event_identity: IdentitySchema,
  source_version: z.number().int().nonnegative(),
});

export const HistoricalOperationalBaselineLineageSchema = z.strictObject({
  baseline_event_identity: IdentitySchema,
  selected_step: z.number().int().min(1).max(11),
  resulting_orders_version: z.number().int().nonnegative(),
  resulting_owner_binding_fingerprint: FingerprintSchema,
  step_projection: z.array(HistoricalOperationalBaselineStepSchema).min(1).max(11),
});

export const HistoricalOperationalBaselineSchema = z.strictObject({
  order_identity: IdentitySchema,
  case_no: CaseNoSchema,
  historical_provenance: HistoricalOperationalBaselineProvenanceSchema,
  current_orders_version: z.number().int().nonnegative(),
  baseline_binding_fingerprint: FingerprintSchema,
  current_baseline: HistoricalOperationalBaselineLineageSchema.nullable(),
  allowed_steps: z.array(z.number().int().min(1).max(11)).length(11),
  evidence_modes: z.array(z.enum(['retained', 'historical_evidence_unavailable_accepted'])).length(2),
}).superRefine((value, context) => {
  if (value.allowed_steps.some((step, index) => step !== index + 1)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['allowed_steps'],
      message: 'Orders baseline allowed steps 必須為 1..11 的固定順序。',
    });
  }
  if (value.current_baseline !== null) {
    const projection = value.current_baseline.step_projection;
    if (projection.length !== value.current_baseline.selected_step) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['current_baseline', 'step_projection'],
        message: 'Orders baseline step projection 必須涵蓋至 selected step。',
      });
    }
    if (projection.some((item, index) => item.step !== index + 1)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['current_baseline', 'step_projection'],
        message: 'Orders baseline step projection 順序不正確。',
      });
    }
  }
});

export const HistoricalOperationalBaselineEnvelopeSchema = z.strictObject({
  success: z.literal(true),
  message: z.string(),
  data: HistoricalOperationalBaselineSchema,
  error: z.null(),
});

export type HistoricalOperationalBaseline = z.infer<typeof HistoricalOperationalBaselineSchema>;
