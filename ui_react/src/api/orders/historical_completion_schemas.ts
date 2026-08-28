/**
 * File: historical_completion_schemas.ts
 * Description: 嚴格解碼 HOB-E Step 11 owner-terminal completion projection。
 */
import { z } from 'zod';

const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const CompletionStateSchema = z.enum(['completed', 'blocked', 'unavailable']);
const CompletionOwnerSchema = z.enum(['orders', 'scheduling', 'client_finance', 'staff_payables']);
const LosslessVersionSchema = z.string().regex(/^(0|[1-9][0-9]*)$/);

export const HistoricalCompletionAlertSchema = z.strictObject({
  code: z.string().trim().min(1).max(191),
  owner: CompletionOwnerSchema,
  field_path: z.string().trim().min(1).max(191),
  referral: z.enum([
    'orders.completion',
    'orders.actual_start',
    'scheduling.official_service_facts',
    'client_finance.settlement',
    'staff_payables.payout',
  ]),
  message: z.string().trim().min(1).max(191),
});

const OwnerVersionSchema = z.strictObject({
  owner: z.enum(['orders', 'client_finance']),
  version: LosslessVersionSchema,
});

const SourceVersionSchema = z.strictObject({
  kind: z.enum([
    'payroll_case_account',
    'staff_obligation',
    'staff_obligation_event',
    'staff_payable_account',
    'staff_payable_projection',
    'staff_payout_event',
    'staff_payout_return_event',
    'staff_payout_reversal_event',
    'staff_payout_allocation',
    'staff_bank_fact',
    'staff_overpayment_recovery',
    'staff_overpayment_recovery_event',
  ]),
  identity: z.string().trim().min(1).max(191),
  version: LosslessVersionSchema,
});

export const HistoricalCompletionSchema = z.strictObject({
  case_no: z.string().trim().min(1).max(50),
  state: CompletionStateSchema,
  step_11_status: CompletionStateSchema,
  step_11_completed: z.boolean(),
  historical_alerts_completed: z.boolean(),
  active_alerts: z.array(HistoricalCompletionAlertSchema),
  owner_versions: z.array(OwnerVersionSchema),
  owner_source_versions: z.array(SourceVersionSchema),
  source_fingerprint: FingerprintSchema,
  projection_fingerprint: FingerprintSchema,
}).superRefine((value, context) => {
  const completed = value.state === 'completed';
  if (value.step_11_status !== value.state) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['step_11_status'], message: 'Step 11 狀態與 aggregate 不一致' });
  }
  if (value.step_11_completed !== completed || value.historical_alerts_completed !== completed) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['step_11_completed'], message: 'terminal flags 與 aggregate 不一致' });
  }
  if ((completed && value.active_alerts.length !== 0) || (!completed && value.active_alerts.length === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['active_alerts'], message: 'active alerts 與 terminal 狀態不一致' });
  }
  const sourceKeys = value.owner_source_versions.map((item) => `${item.kind}:${item.identity}`);
  if (new Set(sourceKeys).size !== sourceKeys.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['owner_source_versions'], message: 'source vector identity 重複' });
  }
});

export const HistoricalCompletionEnvelopeSchema = z.strictObject({
  success: z.literal(true),
  message: z.string(),
  data: HistoricalCompletionSchema,
  error: z.null(),
});

export type HistoricalCompletion = z.infer<typeof HistoricalCompletionSchema>;
