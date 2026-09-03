/** Strict read-only contract for immutable Historical Orders adoption evidence. */
import { z } from 'zod';

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const HistoricalAdoptionPairedStaffEvidenceSchema = z.strictObject({
  caregiver_ordinal: z.number().int().positive(),
  staff_name: z.string().min(1),
  staff_id: z.number().int().positive(),
  resolution: z.enum(['evidence_only', 'assignment_candidate', 'assignment_reused']),
  source_start_date: DateSchema.nullable(),
  source_end_date: DateSchema.nullable(),
  assignment_id: z.number().int().positive().nullable(),
});

export const HistoricalOrderAdoptionEvidenceSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  receipt_id: z.number().int().positive(),
  receipt_identity: z.string().min(1),
  evidence_owner: z.literal('Historical Orders Adoption'),
  source_identity: z.string().min(1),
  source_fingerprint: Sha256Schema,
  preview_fingerprint: Sha256Schema,
  historical_source_status: z.enum(['cancelled', 'deposit_paid', 'discussion']).nullable(),
  operational_baseline_step: z.number().int().min(1).max(11).nullable(),
  source_start_date: DateSchema.nullable(),
  source_end_date: DateSchema.nullable(),
  source_period_availability: z.enum(['available', 'unavailable']),
  paired_staff: z.array(HistoricalAdoptionPairedStaffEvidenceSchema),
  paired_staff_availability: z.enum(['available', 'unavailable']),
}).superRefine((value, context) => {
  if (
    value.source_start_date !== null
    && value.source_end_date !== null
    && value.source_start_date > value.source_end_date
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['source_end_date'],
      message: '歷史來源服務期間不得反轉',
    });
  }
  const periodAvailable = value.source_start_date !== null || value.source_end_date !== null;
  if ((value.source_period_availability === 'available') !== periodAvailable) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['source_period_availability'],
      message: '歷史來源期間 availability 與 evidence 不一致',
    });
  }
  if ((value.paired_staff_availability === 'available') !== (value.paired_staff.length > 0)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['paired_staff_availability'],
      message: '歷史配對 Staff availability 與 evidence 不一致',
    });
  }
});

export const HistoricalOrderAdoptionEvidenceEnvelopeSchema = z.strictObject({
  success: z.literal(true),
  message: z.string(),
  data: HistoricalOrderAdoptionEvidenceSchema,
  error: z.null(),
});

export type HistoricalOrderAdoptionEvidence = z.infer<typeof HistoricalOrderAdoptionEvidenceSchema>;
