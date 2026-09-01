/** Strict client for count-based historical service accounting. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const Fingerprint = z.string().regex(/^[0-9a-f]{64}$/);
const Assignment = z.strictObject({ assignment_identity: z.string().min(1), staff_id: z.number().int().positive(), staff_name: z.string().min(1), policy_version: z.string().min(1), policy_kind: z.enum(['citizen', 'subsidized_citizen', 'non_citizen']), hourly_rate_ntd: z.number().int().positive() });
const Query = z.strictObject({ case_no: z.string().min(1), lifecycle_status: z.string().min(1), lifecycle_version: z.number().int().nonnegative(), adoption_receipt_id: z.number().int().positive(), adoption_source_identity: z.string().min(1), historical_day_revision: z.number().int().nonnegative(), client_finance_version: z.number().int().nonnegative(), payroll_version: z.number().int().nonnegative(), contracted_service_days: z.number().int().positive(), service_hours_per_day: z.number().int().positive(), contractual_floor_fee_ntd: z.number().int().nonnegative(), client_identity_status: z.string().min(1), assignments: z.array(Assignment).min(1) });
const Allocation = z.strictObject({ assignment_identity: z.string(), staff_id: z.number().int().positive(), actual_service_days: z.number().int().positive(), actual_service_hours: z.string(), floor_fee_ntd: z.number().int().nonnegative() });
const Payroll = z.strictObject({ assignment_identity: z.string(), staff_id: z.number().int().positive(), actual_service_days: z.number().int().positive(), actual_hours: z.number().int().positive(), double_pay_hours: z.literal(0), hourly_rate_ntd: z.number().int().positive(), service_salary_ntd: z.number().int().nonnegative(), floor_fee_allocated_ntd: z.number().int().nonnegative(), effective_adjustments_ntd: z.number().int(), total_payable_ntd: z.number().int().positive() });
const Preview = z.strictObject({ facts: Query, total_actual_service_days: z.number().int().positive(), total_actual_service_hours: z.string(), historical_floor_fee_ntd: z.number().int().nonnegative(), historical_double_pay_days: z.literal(0), historical_double_pay_hours: z.literal('0'), allocations: z.array(Allocation).min(1), payroll_assignments: z.array(Payroll).min(1), staff_obligation_amount_ntd: z.number().int().positive(), client_obligation_amount_ntd: z.number().int().positive(), client_service_receivable_ntd: z.number().int().nonnegative(), client_subsidy_hours: z.number().int().nonnegative(), client_self_pay_service_hours: z.number().int().nonnegative(), preview_fingerprint: Fingerprint });
const Receipt = z.strictObject({ case_no: z.string(), resulting_historical_day_revision: z.number().int().positive(), resulting_client_finance_version: z.number().int().positive(), resulting_payroll_version: z.number().int().positive(), total_actual_service_days: z.number().int().positive(), client_obligation_amount_ntd: z.number().int().positive(), staff_obligation_amount_ntd: z.number().int().positive(), preview_fingerprint: Fingerprint, replayed: z.boolean() });
const envelope = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });

export type HistoricalServiceAccountingQuery = z.infer<typeof Query>;
export type HistoricalServiceAccountingPreview = z.infer<typeof Preview>;
export type HistoricalCaregiverDays = { assignment_identity: string; staff_id: number; actual_service_days: number };

const path = (caseNo: string) => `/api/v1/orders/${encodeURIComponent(caseNo)}/historical-service-accounting`;
const options = (headers?: Record<string, string>) => {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入再處理歷史服務天數。');
  return { token, timeoutMs: 30_000, headers };
};

export const historicalServiceAccountingClient = {
  async query(caseNo: string): Promise<HistoricalServiceAccountingQuery> {
    return decodePayload(envelope(Query), await transport.get(path(caseNo), options())).data;
  },
  async preview(caseNo: string, caregivers: HistoricalCaregiverDays[]): Promise<HistoricalServiceAccountingPreview> {
    return decodePayload(envelope(Preview), await transport.post(`${path(caseNo)}/preview`, { caregivers }, options({ 'X-Correlation-ID': `historical-days-preview-${crypto.randomUUID()}` }))).data;
  },
  async apply(preview: HistoricalServiceAccountingPreview, caregivers: HistoricalCaregiverDays[], reason: string) {
    const facts = preview.facts;
    return decodePayload(envelope(Receipt), await transport.post(`${path(facts.case_no)}/apply`, { caregivers, expected_lifecycle_version: facts.lifecycle_version, expected_historical_day_revision: facts.historical_day_revision, expected_client_finance_version: facts.client_finance_version, expected_payroll_version: facts.payroll_version, preview_fingerprint: preview.preview_fingerprint, reason }, options({ 'Idempotency-Key': `historical-days-${crypto.randomUUID()}`, 'X-Correlation-ID': `historical-days-apply-${crypto.randomUUID()}` }))).data;
  },
};
