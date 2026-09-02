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

const RULE_NAMES: Record<string, string> = {
  'LU96-M1-GATEWAY-RETRY-FAIL-RULE-V1': 'M1：Gateway 核對失敗協處工單通知',
  'LU96-M1-LEAVE-EXTENSION-RULE-V1': 'M1：月嫂請假順延客戶確認通知',
  'LU96-M1-STAFF-RETIRE-RULE-V1': 'M1：月嫂退役權限回收通知',
  'LU96-M2-ROUTER-REPLY-RULE-V1': 'M2：AI 路由器確定性答覆推播',
  'LU96-M2-FEEDBACK-UNRESOLVED-RULE-V1': 'M2：AI 評分未解決工單通報',
  'LU96-M3-ZERO-POOL-RULE-V1': 'M3：零意願降維協商建議通知',
  'LU96-M3-MATCH-SUCCESS-CLIENT-RULE-V1': 'M3：派案成功通知（產婦端）',
  'LU96-M3-MATCH-SUCCESS-STAFF-RULE-V1': 'M3：派案成功通知（月嫂端）',
  'LU96-M3-LEAVE-AGREE-RULE-V1': 'M3：客戶同意請假順延確認',
  'LU96-M3-LEAVE-DISAGREE-RULE-V1': 'M3：客戶拒絕順延代班工單',
  'LU96-M4-SAFE-ALERT-RULE-V1': 'M4：幹部異常通報與安全審核',
  'LU96-M4-COMPLAINT-HIGH-RULE-V1': 'M4：重大客訴 HIGH 急件告警',
  'LU96-M4-SALARY-PAYABLE-RULE-V1': 'M4：代班薪資自動拆帳通報',
};

const EVENT_LABELS: Record<string, string> = {
  'gateway.identity_mismatch.second_attempt': '身分核對連續兩次失敗',
  'scheduling.leave.extension_requested': '月嫂申請請假調休',
  'staff.retirement.committed': '月嫂辦理退休生效',
  'router.deterministic.reply_committed': 'AI 確定性指令回覆',
  'feedback.unresolved.recorded': '客服回答評為未解決',
  'matching.zero_pool.preview_applied': '媒合意願池人數為零',
  'matching.decision.committed.client': '媒合派案成交（產婦）',
  'matching.decision.committed.staff': '媒合派案成交（月嫂）',
  'client.leave.extension_agreed': '產婦同意服務順延',
  'client.leave.extension_rejected': '產婦不同意順延需代班',
  'runtime.alert.review_required': '系統重大告警待審核',
  'complaint.ingress.hold_high_ticket': '重大客訴觸發急件工單',
  'payroll.substitute.obligation_projected': '代班出勤薪資拆帳結算',
  'order_lifecycle_transition': '訂單生命週期變更',
  'service_time_checkpoint': '服務時間節點',
  'beclass_completion_changed': 'BeClass 完成狀態變更',
  'deposit_confirmed': '訂金確認',
};

const RECIPIENT_LABELS: Record<string, string> = {
  'customer_service.ticket_owner': '客服工單專員',
  'client.bound_case': '案件產婦',
  'staff.binding_owner': '綁定月嫂',
  'conversation.bound_actor': '對話使用者',
  'matching.request.participants': '媒合相關對象',
  'assignment.client_snapshot': '指派產婦',
  'assignment.staff_snapshot': '指派月嫂',
  'scheduling.owner': '排班調度負責人',
  'admin.review_actor': '工會幹部審核群',
  'customer_service.claim_owner': '客訴專責處理人',
  'staff_payables.anomaly_owner': '財務核銷專員',
  'client': '客戶',
  'assigned_caregiver': '已指派月嫂',
  'case_group': '案件群組',
};

export function ruleName(id: string): string {
  return RULE_NAMES[id] ?? id;
}

function eventLabel(value: string): string {
  return EVENT_LABELS[value] ?? value;
}

function recipientLabel(value: string): string {
  return RECIPIENT_LABELS[value] ?? value;
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
    default: return String(value);
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
