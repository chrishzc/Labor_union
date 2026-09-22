import { z } from 'zod';
import { OrderTermsSchema } from '../orders/order_query_schemas';

const nullableText = z.string().nullable();
const optionalNullableText = z.string().nullish().transform((value) => value ?? null);
const optionalNullablePositiveInt = z.number().int().positive().nullish().transform((value) => value ?? null);
const optionalNullableBoolean = z.boolean().nullish().transform((value) => value ?? null);
const profileValues = z.strictObject({
  name: nullableText, gender: nullableText, phone: nullableText, city: nullableText,
  address: nullableText, residence_type: nullableText, delivery_type: nullableText,
  baby_info: nullableText, notes: nullableText,
});
const beclassValues = z.strictObject({
  name: nullableText, email: nullableText, phone: nullableText, tel: nullableText,
  ext: nullableText, city: nullableText, zip_code: nullableText, address: nullableText,
  admin_notes: nullableText, multi_birth_count: nullableText,
});
const orderInformationValue = z.union([z.string(), z.boolean(), z.number()]).nullable();
const orderInformationValues = z.strictObject({
  dietary_habits: orderInformationValue,
  vegetarian_preference: orderInformationValue,
  alcohol_ratio: orderInformationValue,
  cooking_oil_type: orderInformationValue,
  maternal_allergy: orderInformationValue,
  special_care_notes: orderInformationValue,
  meal_preferences: orderInformationValue,
  cooking_tools: orderInformationValue,
  bath_water_prep: orderInformationValue,
  breastfeeding_method: orderInformationValue,
  holiday_pricing_terms: orderInformationValue,
  multi_birth_count: orderInformationValue,
  stair_floor_fee_mode: orderInformationValue,
  parking_space_provided: orderInformationValue,
  other_babies_present: orderInformationValue,
});
const financeValues = z.strictObject({
  virtual_account: z.string().min(1), service_unit_price_ntd: z.number().int().positive(),
  service_hours: z.number().nonnegative(), customer_payable_total_ntd: z.number().int().nonnegative(),
  deposit_amount_ntd: z.number().int().nonnegative(), first_payment_amount_ntd: z.number().int().nonnegative(),
  second_payment_amount_ntd: z.number().int().nonnegative(), received_total_ntd: z.number().int().nonnegative(),
  customer_balance_ntd: z.number().int(), subsidy_return_amount_ntd: z.number().int().nonnegative().nullable(),
  subsidy_return_due_date: nullableText, subsidy_return_status: nullableText,
});
const fieldCapabilities = z.record(z.string(), z.strictObject({
  owner: z.enum(['client_profile', 'client_beclass', 'order_terms']),
  editable: z.boolean(), reason: nullableText, options: z.array(z.string()).nullable(),
}));

const accountingDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable();
const clientObligationDate = z.strictObject({
  obligation_identity: z.string().min(1),
  obligation_type: z.enum(['deposit', 'first', 'second', 'subsidy_return']),
  due_date: accountingDate,
});
const staffObligationDate = z.strictObject({
  obligation_identity: z.string().min(1), obligation_kind: z.string().min(1),
  due_date: accountingDate, staff_id: z.number().int().positive(), staff_name: nullableText,
});

export const ClientRegistrySummarySchema = z.strictObject({
  client_id: z.number().int().positive(), case_no: z.string().min(1),
  imported_virtual_accounts: z.array(z.string().min(1)), built_in_virtual_account: z.string().nullable(), name: nullableText,
  phone: nullableText, city: nullableText, district: z.string().nullable().optional(), multi_birth_count: optionalNullableText, service_days: optionalNullablePositiveInt,
  requires_cooking: optionalNullableBoolean, planned_start_date: nullableText, order_status: nullableText,
  staff_payment_due_date: accountingDate.optional(),
  client_obligation_dates: z.array(clientObligationDate).optional(),
  staff_obligation_dates: z.array(staffObligationDate).optional(),
  claim_application_year: z.number().int().min(1).max(9999).nullable().optional(),
  claim_application_month: z.number().int().min(1).max(12).nullable().optional(),
});
export const ClientRegistryPageSchema = z.strictObject({
  items: z.array(ClientRegistrySummarySchema), next_cursor: z.string().nullable(),
  next_offset: z.number().int().positive().nullable().optional(),
});
export const ClientRegistryChangeHistoryItemSchema = z.strictObject({
  sequence: z.number().int().positive(),
  event_type: z.string().min(1),
  label: z.string().min(1),
  reason: z.string().min(1),
  actor: z.string().min(1),
  occurred_at: z.string().datetime({ offset: true }),
});
export const ClientRegistryChangeHistorySchema = z.array(ClientRegistryChangeHistoryItemSchema);
export const ClientRegistryDetailSchema = z.strictObject({
  case_no: z.string().min(1),
  client: z.strictObject({ client_id: z.number().int().positive(), version: z.number().int().nonnegative(), values: profileValues, field_capabilities: fieldCapabilities }),
  beclass: z.strictObject({
    status: z.enum(['ready', 'unbound', 'duplicate_binding']), record_id: z.number().int().positive().nullable(),
    source_kind: z.enum(['imported', 'admin_manual']).nullable(),
    version: z.number().int().nonnegative().nullable(), values: beclassValues.nullable(), field_capabilities: fieldCapabilities,
  }),
  order_information: z.strictObject({
    status: z.enum(['ready', 'unbound', 'duplicate_binding']),
    values: orderInformationValues.nullable(),
    field_issues: z.record(z.string(), z.string()),
  }),
  finance: z.strictObject({ status: z.enum(['ready', 'not_ready']), code: nullableText, values: financeValues.nullable() }),
  order_terms: z.strictObject({ status: z.enum(['ready', 'not_found', 'not_ready']), code: nullableText, data: OrderTermsSchema.nullable(), field_capabilities: fieldCapabilities }),
});
export const RegistryMutationPreviewSchema = z.strictObject({
  owner: z.enum(['client_profile', 'client_beclass']), aggregate_identity: z.string(),
  current_version: z.number().int().nonnegative(), before: z.record(nullableText), after: z.record(nullableText),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
export const RegistryMutationReceiptSchema = z.strictObject({
  owner: z.enum(['client_profile', 'client_beclass']), aggregate_identity: z.string(),
  resulting_version: z.number().int().positive(), changed_fields: z.array(z.string()),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/), idempotency_key: z.string(), replayed: z.boolean(),
  readback: z.record(z.string(), nullableText),
});
const response = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.boolean(), message: z.string(), data: data.nullable(), error: z.string().nullable() });
export const ClientRegistryPageResponseSchema = response(ClientRegistryPageSchema);
export const ClientRegistryDetailResponseSchema = response(ClientRegistryDetailSchema);
export const ClientRegistryChangeHistoryResponseSchema = response(ClientRegistryChangeHistorySchema);
export const RegistryMutationPreviewResponseSchema = response(RegistryMutationPreviewSchema);
export const RegistryMutationReceiptResponseSchema = response(RegistryMutationReceiptSchema);

export type ClientRegistryPage = z.infer<typeof ClientRegistryPageSchema>;
export type ClientRegistrySortBy = 'case_no' | 'customer_name' | 'service_days' | 'expected_start_date';
export type ClientRegistrySortOrder = 'asc' | 'desc';
export type ClientRegistryDetail = z.infer<typeof ClientRegistryDetailSchema>;
export type ClientRegistryChangeHistoryItem = z.infer<typeof ClientRegistryChangeHistoryItemSchema>;
export type RegistryMutationPreview = z.infer<typeof RegistryMutationPreviewSchema>;
export type RegistryMutationReceipt = z.infer<typeof RegistryMutationReceiptSchema>;
export type ClientProfileChanges = Partial<z.infer<typeof profileValues>>;
export type BeClassChanges = Partial<z.infer<typeof beclassValues>>;
