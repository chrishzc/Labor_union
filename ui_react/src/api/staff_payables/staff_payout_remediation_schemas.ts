/**
 * File: staff_payout_remediation_schemas.ts
 * Description: 定義 PAYOUT-001 核銷工作台的 Staff Payables 與 Job strict 契約。
 */
import { z } from 'zod';

const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const MoneySchema = z.strictObject({ amount: z.number().int().nonnegative() });
const AllocationSchema = z.strictObject({
  bank_fact_identity: z.string().min(1),
  obligation_identity: z.string().min(1),
  amount: MoneySchema,
});
const LedgerEventSchema = z.strictObject({
  identity: z.string().min(1),
  event_type: z.enum(['payout', 'return', 'reversal']),
  status: z.literal('succeeded'),
  staff_id: z.number().int().positive(),
  amount: MoneySchema,
  finance_import_fact_identity: z.string().min(1).nullable(),
  reversal_of_event_identity: z.string().min(1).nullable(),
});
const ObligationLinkSchema = z.strictObject({
  event_identity: z.string().min(1),
  obligation_identity: z.string().min(1),
  allocated_amount: MoneySchema,
});
const CandidateSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  bank_total: MoneySchema,
  obligation_total: MoneySchema,
  allocations: z.array(AllocationSchema),
  fingerprint: FingerprintSchema,
  events: z.array(LedgerEventSchema),
  obligation_links: z.array(ObligationLinkSchema),
  resulting_status: z.enum(['payable', 'partially_paid', 'completed', 'recovery_required', 'anomaly']),
  difference_mode: z.enum(['underpayment', 'overpayment']).nullable(),
  recovery: z.strictObject({
    identity: z.string().min(1),
    staff_id: z.number().int().positive(),
    original_amount: MoneySchema,
    source_bank_fact_identities: z.array(z.string().min(1)),
    source_obligation_identities: z.array(z.string().min(1)),
  }).nullable(),
});
const ReopenCandidateSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  event: LedgerEventSchema,
  obligation_links: z.array(ObligationLinkSchema),
  resulting_status: z.enum(['payable', 'partially_paid', 'completed', 'recovery_required', 'anomaly']),
  fingerprint: FingerprintSchema,
});

export const StaffPayoutPreviewSchema = z.strictObject({
  event_type: z.string().min(1),
  staff_payables_version: z.number().int().nonnegative(),
  bank_facts_version: z.number().int().nonnegative(),
  candidate: z.union([CandidateSchema, ReopenCandidateSchema]),
  preview_fingerprint: FingerprintSchema,
});

export const StaffPayoutJobAcceptedSchema = z.strictObject({
  job_id: z.string().min(1).max(191),
  status_url: z.string().min(1),
});

const JobSuccessSchema = z.strictObject({
  kind: z.literal('success'),
  schema_version: z.literal(1),
  result_reference: z.string().min(1).max(191),
});
const JobFailureSchema = z.strictObject({
  kind: z.literal('failure'),
  schema_version: z.literal(1),
  error: z.strictObject({
    category: z.enum(['validation', 'conflict', 'domain_blocked', 'idempotency_mismatch', 'unavailable', 'internal']),
    code: z.string().min(1).max(128),
    message: z.string().min(1).max(512),
    retryable: z.boolean(),
    correlation_id: z.string().min(1).max(255).nullable(),
    domain_blockers: z.array(z.string()),
  }),
});
export const StaffPayoutJobSchema = z.strictObject({
  job_id: z.string().min(1).max(191),
  status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']),
  command_type: z.literal('staff_payout_apply'),
  attempt_count: z.number().int().nonnegative(),
  max_attempts: z.number().int().nonnegative(),
  outcome: z.union([JobSuccessSchema, JobFailureSchema]).nullable(),
});

export const StaffPayoutResponseSchema = <T extends z.ZodTypeAny>(data: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data,
  error: z.string().nullable().optional(),
});

export type StaffPayoutPreview = z.infer<typeof StaffPayoutPreviewSchema>;
export type StaffPayoutJobAccepted = z.infer<typeof StaffPayoutJobAcceptedSchema>;
export type StaffPayoutJob = z.infer<typeof StaffPayoutJobSchema>;
