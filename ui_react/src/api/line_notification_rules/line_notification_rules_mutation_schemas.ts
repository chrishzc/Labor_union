/**
 * File: line_notification_rules_mutation_schemas.ts
 * Description: 定義 LINE 通知規則 Preview、Save 與 Delete 的嚴格請求及回應契約。
 */
import { z } from 'zod';
import { LineNotificationRuleSchema } from '../line_configuration/line_configuration_query_schemas';

const OperationIdentitySchema = z.string().trim().min(1).max(191);
const ReasonSchema = z.string().trim().min(1).max(1_000);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);

export const LineNotificationRulesMutationDefinitionSchema = z
  .object({ rules: z.array(LineNotificationRuleSchema) })
  .strict()
  .superRefine((definition, context) => {
    const ruleIds = new Set<string>();
    for (const rule of definition.rules) {
      if (ruleIds.has(rule.id)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['rules'],
          message: '通知規則 id 不可重複',
        });
      }
      ruleIds.add(rule.id);
    }
  });
export type LineNotificationRulesMutationDefinition = z.infer<
  typeof LineNotificationRulesMutationDefinitionSchema
>;

export const PreviewLineNotificationRulesRequestSchema = z
  .object({
    expected_revision: z.number().int().nonnegative(),
    definition: LineNotificationRulesMutationDefinitionSchema,
  })
  .strict();
export type PreviewLineNotificationRulesRequest = z.infer<
  typeof PreviewLineNotificationRulesRequestSchema
>;

const MutationFields = {
  expected_revision: z.number().int().nonnegative(),
  preview_fingerprint: FingerprintSchema,
  reason: ReasonSchema,
  idempotency_key: OperationIdentitySchema,
  correlation_id: OperationIdentitySchema,
};

export const SaveLineNotificationRulesRequestSchema = z
  .object({
    ...MutationFields,
    definition: LineNotificationRulesMutationDefinitionSchema,
  })
  .strict();
export type SaveLineNotificationRulesRequest = z.infer<
  typeof SaveLineNotificationRulesRequestSchema
>;

export const DeleteLineNotificationRuleRequestSchema = z
  .object(MutationFields)
  .strict();
export type DeleteLineNotificationRuleRequest = z.infer<
  typeof DeleteLineNotificationRuleRequestSchema
>;

export const PreviewLineNotificationRulesSchema = z
  .object({
    before_revision: z.number().int().nonnegative(),
    resulting_revision: z.number().int().nonnegative(),
    definition: LineNotificationRulesMutationDefinitionSchema,
    fingerprint: FingerprintSchema,
  })
  .strict();
export type PreviewLineNotificationRules = z.infer<
  typeof PreviewLineNotificationRulesSchema
>;

export const SaveLineNotificationRulesReceiptSchema = z
  .object({
    revision: z.number().int().nonnegative(),
    preview_fingerprint: FingerprintSchema,
    cancelled_intent_count: z.number().int().nonnegative(),
    cancelled_task_count: z.number().int().nonnegative(),
  })
  .strict();
export type SaveLineNotificationRulesReceipt = z.infer<
  typeof SaveLineNotificationRulesReceiptSchema
>;

export const DeleteLineNotificationRuleReceiptSchema = SaveLineNotificationRulesReceiptSchema
  .extend({ rule_id: z.string().regex(/^[a-z][a-z0-9_]{0,63}$/) })
  .strict();
export type DeleteLineNotificationRuleReceipt = z.infer<
  typeof DeleteLineNotificationRuleReceiptSchema
>;

function successEnvelope<TSchema extends z.ZodTypeAny>(dataSchema: TSchema) {
  return z
    .object({
      success: z.literal(true),
      message: z.string(),
      data: dataSchema,
      error: z.null(),
    })
    .strict();
}

export const PreviewLineNotificationRulesResponseSchema = successEnvelope(
  PreviewLineNotificationRulesSchema
);
export const SaveLineNotificationRulesResponseSchema = successEnvelope(
  SaveLineNotificationRulesReceiptSchema
);
export const DeleteLineNotificationRuleResponseSchema = successEnvelope(
  DeleteLineNotificationRuleReceiptSchema
);
