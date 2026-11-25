import { z } from 'zod';
import { notifyCaseAccountingChanged } from '../shared/case_accounting_changes';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import type { ApiHttpError } from '../shared/typed_errors';

const money = z.number().int().positive();
const rates = z.strictObject({ covered: z.number().int().nonnegative(), excess: money });
export const PricingTermsSchema = z.strictObject({ identity_name: z.string().min(1).max(100),
  rule: z.enum(['citizen', 'social', 'non_citizen']), subsidy_hours: z.number().nonnegative().multipleOf(0.5), client: rates, payroll: rates });
const depositDays = z.number().int().min(0).max(2147483647).nullable().optional();
const policyIdentity = PricingTermsSchema.extend({ deposit_service_days: depositDays });
export const PricingPolicySchema = z.strictObject({ effective_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  identities: z.array(policyIdentity).min(1), twins_client: rates, twins_payroll: rates,
  indigenous_deposit_service_days: depositDays });
const version = z.strictObject({ revision: z.number().int().positive(), policy: PricingPolicySchema, actor: z.string(), reason: z.string() });
const catalog = z.strictObject({ revision: z.number().int().nonnegative(), versions: z.array(version) });
const amount = z.number().int().nonnegative();
const impact = z.strictObject({ covered_hours: z.number().nonnegative(), excess_hours: z.number().nonnegative(),
  case_total_amount: amount, union_income_amount: z.number().int().nullable(),
  client_amount: amount, staff_covered_amount: amount, staff_excess_amount: amount, staff_total_amount: amount,
  subsidy_amount: amount, subsidy_return_amount: amount });
const caseView = z.strictObject({ case_no: z.string(), revision: z.number().int().nonnegative(),
  source: z.enum(['legacy', 'policy', 'manual']), terms: PricingTermsSchema, impact });
const preview = z.strictObject({ current: caseView, candidate: PricingTermsSchema, before: impact, after: impact,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) });
const receipt = z.strictObject({ revision: z.number().int().positive() });
export type PricingTerms = z.infer<typeof PricingTermsSchema>;
export type PricingPolicyIdentity = z.infer<typeof policyIdentity>;
export type PricingPolicy = z.infer<typeof PricingPolicySchema>;
export type PricingCatalog = z.infer<typeof catalog>;
export type CasePricing = z.infer<typeof caseView>;
export type PricingPreview = z.infer<typeof preview>;
export type PricingImpact = z.infer<typeof impact>;

export function pricingIdentityLabel(terms: PricingTerms): string {
  if (['原民', '原住民市民'].includes(terms.identity_name)) return '原住民';
  if (!['一般市民', '補助市民', '社福', '低收入戶', '中低收入戶', '非市民'].includes(terms.identity_name)) return terms.identity_name;
  return { citizen: '一般市民', social: '補助市民', non_citizen: '非市民' }[terms.rule];
}

/** Copy a stored policy into a new draft; amounts and historical versions stay intact. */
export function pricingPolicyDraft(policy: PricingPolicy): PricingPolicy {
  const { indigenous_deposit_service_days, ...draft } = structuredClone(policy);
  const identities = draft.identities.map(item => ({
    ...item, identity_name: pricingIdentityLabel(item), deposit_service_days: policyDepositDays(policy, item),
  }));
  if (!identities.some(item => item.identity_name === '原住民')) {
    identities.push({
      identity_name: '原住民', rule: 'citizen', subsidy_hours: 80,
      client: { covered: 350, excess: 300 }, payroll: { covered: 350, excess: 300 },
      deposit_service_days: indigenous_deposit_service_days ?? null,
    });
  }
  return { ...draft, identities };
}

export function policyDepositDays(policy: PricingPolicy, item: PricingPolicyIdentity): number | null {
  return item.deposit_service_days ?? (pricingIdentityLabel(item) === '原住民' ? policy.indigenous_deposit_service_days : null) ?? null;
}

export function pricingTermsError(terms: PricingTerms): string {
  if (terms.rule === 'non_citizen' && (terms.subsidy_hours !== 0 || terms.client.covered !== 0 || terms.payroll.covered !== 0)) return '非市民的補助時數與補助內時薪必須為 0。';
  if (terms.client.covered !== terms.payroll.covered) return '補助範圍內的客戶時薪與月嫂時薪必須相等，才能向政府報帳。';
  if (terms.subsidy_hours > 0 && terms.client.covered <= 0) return '有補助時數時，補助內時薪必須為正整數。';
  return '';
}

export function pricingRequestError(error: ApiHttpError, fallback: string): string {
  switch (error.code) {
    case 'case_pricing_stale':
    case 'pricing_write_conflict': return '計價資料已變更，請重新查詢後再儲存。';
    case 'case_pricing_identity_not_confirmed': return '本案補助身分待確認，請至客戶資料核對。';
    case 'case_pricing_identity_rule_immutable': return '計價調整只能沿用本案補助身分。若須更正身分，請至客戶資料辦理。';
    case 'case_pricing_birth_source_ambiguous': return '本案胎數資料不一致，請至客戶資料核對正式胎數。';
    case 'case_pricing_service_facts_required': return '本案缺少可計價的服務資料，請先核對服務條件與已確認服務日期或歷史服務時數。';
    case 'case_pricing_payroll_snapshot_required': return '本案缺少月嫂給付資料，請先核對案件的月嫂與薪資資料。';
    case 'client_finance_bootstrap_required': return '本案尚未建立正式帳務資料，請先核對帳務初始化狀態。';
    case 'case_pricing_override_missing': return '找不到本案綁定的人工計價設定，請核對既有帳務資料。';
    case 'case_pricing_bound_policy_missing': return '找不到本案綁定的計價政策版本，請核對案件及政策版本。';
    case 'case_pricing_settled_subsidy_correction_required': return '本次調整涉及已核銷的補助，請先核對原補助紀錄與更正方式。';
    case 'full_subsidy_existing_financial_history_conflict': return '本案已有收付款或退款紀錄，無法自動改為免自備，請先核對原始帳務。';
    case 'client_refund_recipient_snapshot_missing': return '本案調整將產生退款，但缺少客戶退款銀行帳戶；請先至客戶資料補齊退款帳號後再儲存。';
    case 'historical_pricing_unique_assignment_required': return '本案的歷史月嫂無法唯一確認，請核對原始派案。';
    case 'historical_pricing_original_installments_required': return '本案缺少原始期款，請先核對歷史收款資料。';
    case 'historical_pricing_original_payable_required': return '本案缺少原始月嫂應付，請先核對歷史薪資資料。';
    case 'historical_pricing_original_subsidy_return_required': return '本案缺少原始補助退款，請先核對歷史退款資料。';
    case 'historical_pricing_amount_conflict': return '本次計價差額無法套用至原始金額，請核對歷史收付款與退款資料。';
    case 'pricing_covered_rates_must_match': return '補助範圍內的客戶時薪與月嫂時薪必須相等，才能向政府報帳。';
    case 'pricing_covered_rate_must_be_positive': return '有補助時數時，補助內時薪必須為正整數。';
    default: return error.status === 403 ? '目前帳號無權執行個案計價調整。' : fallback;
  }
}

function options(key?: string) {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  const headers: Record<string, string> = key ? { 'Idempotency-Key': key } : {};
  return { token, headers };
}
function decode<T>(schema: z.ZodType<T>, value: unknown): T {
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
    const result = decode(receipt, await transport.post(`${root}/cases/${encodeURIComponent(caseNo)}/apply`,
      { terms: PricingTermsSchema.parse(terms), expected_revision: expectedRevision, reason }, options(key)));
    notifyCaseAccountingChanged(caseNo);
    return result;
  },
};
