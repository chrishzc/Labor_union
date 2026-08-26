/**
 * File: line_configuration_query_adapter.ts
 * Description: 將嚴格 LINE 設定 DTO 映射為顯示白名單模型，排除動作與 provider 敏感值。
 */
import type {
  LineNotificationFrequency,
  LineNotificationPredicate,
  LineNotificationRule,
  LineNotificationRulesCatalog,
  LineNotificationSchedule,
  LineRichMenuConfiguration,
  LineRichMenuPublication,
  LineRichMenuPublicationPage,
  LineRichMenuPublicationStatus,
  RichMenuAudienceRole,
} from '../../api/line_configuration/line_configuration_query_schemas';

export interface LineNotificationRuleModel {
  id: string;
  eventCode: string;
  eventLabel: string;
  recipientSelector: string;
  recipientLabel: string;
  templateId: string;
  enabled: boolean;
  scheduleLabel: string;
  frequencyLabel: string;
  predicateLabels: string[];
}

export interface LineNotificationRulesCatalogModel {
  revision: number;
  rules: LineNotificationRuleModel[];
  isEmpty: boolean;
}

export interface RichMenuButtonModel {
  id: string;
  label: string;
  bounds: { x: number; y: number; width: number; height: number };
  action?: RichMenuActionModel;
}

export type RichMenuActionModel =
  | { kind: 'message'; text: string }
  | { kind: 'uri'; uri: string; uriSource: 'literal' | 'liff' }
  | { kind: 'postback'; data: string }
  | { kind: 'richmenuswitch'; data: string; richMenuAliasId: string };

export interface RichMenuModel {
  id: string;
  name: string;
  audienceRole: RichMenuAudienceRole;
  audienceRoleLabel: string;
  enabled: boolean;
  selected: boolean;
  setAsDefault: boolean;
  chatBarText: string;
  width: number;
  height: number;
  buttons: RichMenuButtonModel[];
}

export interface LineRichMenuConfigurationModel {
  revision: number;
  version: number;
  menus: RichMenuModel[];
  isEmpty: boolean;
}

export interface LineRichMenuPublicationModel {
  id: number;
  menuDefinitionId: string;
  configurationRevision: number;
  status: LineRichMenuPublicationStatus;
  statusLabel: string;
}

export interface LineRichMenuPublicationPageModel {
  items: LineRichMenuPublicationModel[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  loadedCount: number;
  loadedScope: true;
}

function eventLabel(value: LineNotificationRule['event_code']): string {
  switch (value) {
    case 'order_lifecycle_transition': return '訂單生命週期變更';
    case 'service_time_checkpoint': return '服務時間節點';
    case 'beclass_completion_changed': return 'BeClass 完成狀態變更';
    case 'deposit_confirmed': return '訂金確認';
  }
}

function recipientLabel(value: LineNotificationRule['recipient_selector']): string {
  switch (value) {
    case 'client': return '客戶';
    case 'assigned_caregiver': return '已指派月嫂';
    case 'case_group': return '案件群組';
  }
}

function scheduleLabel(value: LineNotificationSchedule): string {
  switch (value.kind) {
    case 'immediate': return '立即通知';
    case 'service_end': return '服務結束時';
    case 'relative_service_time': return `服務時間後 ${value.offset_seconds} 秒`;
  }
}

function frequencyLabel(value: LineNotificationFrequency): string {
  switch (value.kind) {
    case 'once': return '一次';
    case 'recurring_bounded':
      return `最多 ${value.maximum_occurrences} 次，每 ${value.interval_days} 天`;
  }
}

function predicateLabel(value: LineNotificationPredicate): string {
  switch (value) {
    case 'requires_cooking_true': return '需要下廚';
    case 'baby_log_missing': return '嬰兒日誌缺失';
    case 'beclass_missing': return 'BeClass 資料缺失';
  }
}

function audienceRoleLabel(value: RichMenuAudienceRole): string {
  switch (value) {
    case 'customer': return '客戶';
    case 'staff': return '月嫂';
    case 'union_staff': return '工會人員';
    case 'union_staff_page': return '工會人員頁面';
  }
}

function publicationStatusLabel(value: LineRichMenuPublicationStatus): string {
  switch (value) {
    case 'draft': return '草稿';
    case 'queued': return '已排入';
    case 'publishing': return '發布中';
    case 'published': return '已發布';
    case 'publish_retryable_failed': return '發布可重試失敗';
    case 'failed': return '失敗';
    case 'rollback_queued': return '已排入回復';
    case 'delete_queued': return '已排入刪除';
    case 'rollback_retryable_failed': return '回復可重試失敗';
    case 'delete_retryable_failed': return '刪除可重試失敗';
    case 'rolled_back': return '已回復';
    case 'deleted': return '已刪除';
  }
}

export function adaptLineNotificationRulesCatalog(
  catalog: LineNotificationRulesCatalog
): LineNotificationRulesCatalogModel {
  const rules = 'rules' in catalog.definition ? catalog.definition.rules : [];
  return {
    revision: catalog.revision,
    rules: rules.map((rule) => ({
      id: rule.id,
      eventCode: rule.event_code,
      eventLabel: eventLabel(rule.event_code),
      recipientSelector: rule.recipient_selector,
      recipientLabel: recipientLabel(rule.recipient_selector),
      templateId: rule.template_id,
      enabled: rule.enabled ?? false,
      scheduleLabel: scheduleLabel(rule.schedule),
      frequencyLabel: frequencyLabel(rule.frequency ?? { kind: 'once' }),
      predicateLabels: (rule.predicates ?? []).map(predicateLabel),
    })),
    isEmpty: rules.length === 0,
  };
}

export function adaptLineRichMenuConfiguration(
  configuration: LineRichMenuConfiguration
): LineRichMenuConfigurationModel {
  if (!('menus' in configuration.definition)) {
    return { revision: configuration.revision, version: 1, menus: [], isEmpty: true };
  }
  return {
    revision: configuration.revision,
    version: configuration.definition.version ?? 1,
    menus: configuration.definition.menus.map((menu) => ({
      id: menu.id,
      name: menu.name,
      audienceRole: menu.audience_role,
      audienceRoleLabel: audienceRoleLabel(menu.audience_role),
      enabled: menu.enabled ?? true,
      selected: menu.selected ?? true,
      setAsDefault: menu.set_as_default ?? false,
      chatBarText: menu.chat_bar_text,
      width: menu.size?.width ?? 2500,
      height: menu.size?.height ?? 843,
      buttons: menu.buttons.map((button) => ({
        id: button.id,
        label: button.label,
        bounds: { ...button.bounds },
      })),
    })),
    isEmpty: false,
  };
}

export function adaptLineRichMenuPublication(
  publication: LineRichMenuPublication
): LineRichMenuPublicationModel {
  return {
    id: publication.id,
    menuDefinitionId: publication.menu_definition_id,
    configurationRevision: publication.configuration_revision,
    status: publication.status,
    statusLabel: publicationStatusLabel(publication.status),
  };
}

export function adaptLineRichMenuPublicationPage(
  page: LineRichMenuPublicationPage
): LineRichMenuPublicationPageModel {
  return {
    items: page.items.map(adaptLineRichMenuPublication),
    page: page.page,
    pageSize: page.page_size,
    total: page.total,
    totalPages: page.total_pages,
    loadedCount: page.items.length,
    loadedScope: true,
  };
}
