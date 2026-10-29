import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const money = z.number().int().positive();
const rates = z.strictObject({ covered: z.number().int().nonnegative(), excess: money });
export const PricingTermsSchema = z.strictObject({ identity_name: z.string().min(1).max(100),
  rule: z.enum(['citizen', 'social', 'non_citizen']), subsidy_hours: z.number().nonnegative().multipleOf(0.5), client: rates, payroll: rates });
export const PricingPolicySchema = z.strictObject({ effective_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  identities: z.array(PricingTermsSchema).min(1), twins_client: rates, twins_payroll: rates });
const version = z.strictObject({ revision: z.number().int().positive(), policy: PricingPolicySchema, actor: z.string(), reason: z.string() });
const catalog = z.strictObject({ revision: z.number().int().nonnegative(), versions: z.array(version) });
const amount = z.number().int().nonnegative();
const impact = z.strictObject({ covered_hours: z.number().nonnegative(), excess_hours: z.number().nonnegative(),
  client_amount: amount, staff_covered_amount: amount, staff_excess_amount: amount, staff_total_amount: amount,
  subsidy_amount: amount, subsidy_return_amount: amount });
const caseView = z.strictObject({ case_no: z.string(), revision: z.number().int().nonnegative(),
  source: z.enum(['legacy', 'policy', 'manual']), terms: PricingTermsSchema, impact });
const preview = z.strictObject({ current: caseView, candidate: PricingTermsSchema, before: impact, after: impact,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) });
const receipt = z.strictObject({ revision: z.number().int().positive() });
export type PricingTerms = z.infer<typeof PricingTermsSchema>;
export type PricingPolicy = z.infer<typeof PricingPolicySchema>;
export type PricingCatalog = z.infer<typeof catalog>;
export type CasePricing = z.infer<typeof caseView>;
export type PricingPreview = z.infer<typeof preview>;
export type PricingImpact = z.infer<typeof impact>;

export function pricingTermsError(terms: PricingTerms): string {
  if (terms.rule === 'non_citizen' && (terms.subsidy_hours !== 0 || terms.client.covered !== 0 || terms.payroll.covered !== 0)) return '非市民的補助時數與補助內時薪必須為 0。';
  if (terms.client.covered !== terms.payroll.covered) return '補助範圍內的客戶時薪與月嫂時薪必須相等，才能向政府報帳。';
  if (terms.subsidy_hours > 0 && terms.client.covered <= 0) return '有補助時數時，補助內時薪必須為正整數。';
  return '';
}

function options(key?: string) {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  const headers: Record<string, string> = key ? { 'Idempotency-Key': key } : {};
  return { token, headers };
}
function decode<T extends z.ZodTypeAny>(schema: T, value: unknown): z.output<T> {
  return decodePayload(z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.string().nullable().optional() }), value).data;
}
const root = '/api/v1/accounting-pricing';
export const accountingPricingClient = {
  async catalog() { return decode(catalog, await transport.get(root, options())); },
  async savePolicy(policy: PricingPolicy, expectedRevision: number, reason: string, key: string) {
    return decode(receipt, await transport.post(`${root}/policies`, { policy: PricingPolicySchema.parse(policy), expected_revision: expectedRevision, reason }, options(key)));
  },
  async queryCase(caseNo: string) { return decode(caseView, await transport.get(`${root}/cases/${encodeURIComponent(caseNo)}`, options())); },
  async previewCase(caseNo: string, terms: PricingTerms, expectedRevision: number) {
    return decode(preview, await transport.post(`${root}/cases/${encodeURIComponent(caseNo)}/preview`,
      { terms: PricingTermsSchema.parse(terms), expected_revision: expectedRevision }, options()));
  },
  async applyCase(caseNo: string, terms: PricingTerms, expectedRevision: number, reason: string, key: string) {
    return decode(receipt, await transport.post(`${root}/cases/${encodeURIComponent(caseNo)}/apply`,
      { terms: PricingTermsSchema.parse(terms), expected_revision: expectedRevision, reason }, options(key)));
  },
};
