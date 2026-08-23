/**
 * File: line_notification_rules_mutation_adapter.ts
 * Description: 將通知規則目錄、Preview 與 mutation receipt 映射為可編輯及去敏 UI 模型。
 */
import type { LineNotificationRulesCatalog } from '../../api/line_configuration/line_configuration_query_schemas';
import type {
  DeleteLineNotificationRuleReceipt,
  LineNotificationRulesMutationDefinition,
  PreviewLineNotificationRules,
  SaveLineNotificationRulesReceipt,
} from '../../api/line_notification_rules/line_notification_rules_mutation_schemas';

export interface LineNotificationRulesDraftModel {
  revision: number;
  definition: LineNotificationRulesMutationDefinition;
}

export interface LineNotificationRulesPreviewModel {
  beforeRevision: number;
  resultingRevision: number;
  definition: LineNotificationRulesMutationDefinition;
  ruleCount: number;
  fingerprint: string;
  fingerprintSummary: string;
}

export interface LineNotificationRulesMutationReceiptModel {
  operation: 'save' | 'delete';
  revision: number;
  ruleId: string | null;
  cancelledIntentCount: number;
  cancelledTaskCount: number;
  fingerprintSummary: string;
}

function summarizeFingerprint(fingerprint: string): string {
  return `${fingerprint.slice(0, 8)}…${fingerprint.slice(-4)}`;
}

export function adaptLineNotificationRulesDraft(
  catalog: LineNotificationRulesCatalog
): LineNotificationRulesDraftModel {
  const rules = 'rules' in catalog.definition ? catalog.definition.rules : [];
  return {
    revision: catalog.revision,
    definition: {
      rules: rules.map((rule) => ({
        ...rule,
        enabled: rule.enabled ?? false,
        schedule: { ...rule.schedule },
        frequency: rule.frequency ? { ...rule.frequency } : { kind: 'once' },
        predicates: [...(rule.predicates ?? [])],
      })),
    },
  };
}

export function adaptLineNotificationRulesPreview(
  preview: PreviewLineNotificationRules
): LineNotificationRulesPreviewModel {
  return {
    beforeRevision: preview.before_revision,
    resultingRevision: preview.resulting_revision,
    definition: preview.definition,
    ruleCount: preview.definition.rules.length,
    fingerprint: preview.fingerprint,
    fingerprintSummary: summarizeFingerprint(preview.fingerprint),
  };
}

export function adaptLineNotificationRulesSaveReceipt(
  receipt: SaveLineNotificationRulesReceipt
): LineNotificationRulesMutationReceiptModel {
  return {
    operation: 'save',
    revision: receipt.revision,
    ruleId: null,
    cancelledIntentCount: receipt.cancelled_intent_count,
    cancelledTaskCount: receipt.cancelled_task_count,
    fingerprintSummary: summarizeFingerprint(receipt.preview_fingerprint),
  };
}

export function adaptLineNotificationRuleDeleteReceipt(
  receipt: DeleteLineNotificationRuleReceipt
): LineNotificationRulesMutationReceiptModel {
  return {
    operation: 'delete',
    revision: receipt.revision,
    ruleId: receipt.rule_id,
    cancelledIntentCount: receipt.cancelled_intent_count,
    cancelledTaskCount: receipt.cancelled_task_count,
    fingerprintSummary: summarizeFingerprint(receipt.preview_fingerprint),
  };
}
