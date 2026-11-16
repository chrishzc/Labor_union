/**
 * File: line_message_flow_adapter.ts
 * Description: LINE 流程圖分類與狀態解析，引用正式目錄及規則，不保存文案或業務 gate。
 */
import type { PreviewDescriptor } from '../../api/line_notification_rules/line_message_preview_client';
import type { LineNotificationRuleModel } from './line_configuration_query_adapter';

export const FLOW_MANAGED_NOTIFICATION_EVENTS = new Set([
  'runtime.alert.review_required',
  'complaint.ingress.hold_high_ticket',
]);

export function notificationMessageHref(message?: string | null, category?: 'accounting'): string {
  const query = new URLSearchParams({ tab: 'push_queue' });
  if (message) query.set('message', message);
  if (category) query.set('category', category);
  return `#line-notifications?${query}`;
}

export type MessageFlowStatus = 'enabled' | 'disabled' | 'flow' | 'unavailable';
export function messageFlowStatus(descriptor: Pick<PreviewDescriptor, 'id' | 'builtin'>, rule?: LineNotificationRuleModel): MessageFlowStatus {
  if (rule) return FLOW_MANAGED_NOTIFICATION_EVENTS.has(rule.eventCode) ? 'flow' : rule.enabled ? 'enabled' : 'disabled';
  return descriptor.builtin ? 'flow' : 'unavailable';
}
export const MESSAGE_FLOW_STATUS_LABELS: Record<MessageFlowStatus, string> = {
  enabled: '已啟用', disabled: '已停用', flow: '由流程控制', unavailable: '狀態無法確認',
};

type MessageDeliveryMode = 'automatic' | 'manual' | 'reply';
export const MESSAGE_DELIVERY_LABELS: Record<MessageDeliveryMode, string> = {
  automatic: '自動推播',
  manual: '人工發送',
  reply: '只在聊天室回覆',
};

interface FlowNodeDefinition {
  id: string;
  title: string;
  ids?: readonly string[];
  templates?: readonly string[];
  internal?: boolean;
  previewOnly?: boolean;
  alternatives?: boolean;
  delivery?: readonly MessageDeliveryMode[];
  summary?: string;
}
interface FlowStageDefinition { title: string; nodes: readonly FlowNodeDefinition[] }
interface FlowJourneyDefinition { id: string; name: string; summary?: string; stages: readonly FlowStageDefinition[] }

export const LINE_MESSAGE_FLOWS: readonly FlowJourneyDefinition[] = [
  { id: 'matching', name: '媒合到服務', summary: '簽約與訂金付款可先後交錯；訂金正式核銷後即可建立案件群組，不必等簽約完成。正式日期與排班仍由既有前置條件檢查。', stages: [
    { title: '初步候選聯絡', nodes: [
      { id: 'candidate-info', title: '寄送案件資訊', delivery: ['manual'], ids: ['card-candidate-information-package'] },
      { id: 'candidate-response', title: '月嫂意願受理', delivery: ['reply'], ids: ['candidate-willing-received'], previewOnly: true },
    ] },
    { title: '正式媒合與客戶確認', nodes: [
      { id: 'recommendation', title: '寄送完整推薦確認包', delivery: ['manual'], ids: ['card-customer-confirmation'] },
      { id: 'matching-willingness', title: '正式媒合－月嫂意願受理', delivery: ['reply'], ids: ['matching-willing-received'] },
      { id: 'customer-response', title: '接受配對及其他回覆', delivery: ['reply'], ids: ['matching-customer-accepted', 'matching-customer-response'] },
    ] },
    { title: '簽約', nodes: [
      { id: 'external-signing', title: '契約送交與簽回', summary: '工會人員在瀏覽器預覽、列印或另存契約 PDF，送交第三方平台簽署並在工作台記錄送交。收回並確認客戶與所有現行月嫂的簽署文件後，才記錄簽約完成。' },
      { id: 'signing-reminders', title: '簽署提醒', summary: '工會人員在 LINE 官方帳號聊天後台手動選用範本，發給需要提醒的客戶或月嫂。' },
    ] },
    { title: '收款與建群', nodes: [
      { id: 'deposit-reminder', title: '訂金繳費提醒', delivery: ['automatic', 'manual'], ids: ['deposit-reminder'], summary: '雙方簽約完成且資料齊備後，依排程自動私訊客戶；工會人員也可從待辦手動發送。' },
      { id: 'deposit-settled', title: '訂金確認入帳', summary: '確認入帳後，由工會人員在 LINE 官方帳號聊天後台使用預設訊息手動發送，並於系統內標記已通知以消除待辦。' },
      { id: 'deposit-overdue', title: '訂金逾期－私訊補寄與人工提醒', delivery: ['automatic', 'manual'], ids: ['payment-overdue-deposit'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；任何私訊或按鈕回覆後改人工提醒，未核銷款項保留待辦。' },
      { id: 'group-invitation', title: '寄送案件群組邀請', delivery: ['manual'], ids: ['group-invitation-customer', 'group-invitation-staff'], summary: '訂金正式核銷後，人員在案件群組設定綁定與邀請網址，再輸入「發送邀請」；不以簽約完成作為建群門檻。' },
    ] },
    { title: '開始服務', nodes: [
      { id: 'group-helper-menu', title: '群組小幫手選單（月嫂專屬控制台）', delivery: ['reply'], ids: ['helper-menu-card', 'helper-menu-completed'], alternatives: true, summary: '月嫂在案件群組輸入「工會」或「小幫手」，系統以 Reply 回覆選單。正式完工後，本案月嫂重新叫出選單即可看到「滿意度調查問卷」。' },
      { id: 'confirm-start-date', title: '確認開工日', delivery: ['reply'], ids: ['helper-confirm-start-card', 'helper-confirm-start-completed'], summary: '月嫂或客戶由原生日期滾輪發起約定開工日提議，系統回覆開工確認單；防自提自審（提案方點同意靜默不反應），由對方確認後單一 UoW 自動完成排班並更新一期款期限；點擊重新選擇發送取消通知。正式開工後選單自動隱藏此項。' },
      { id: 'opening-day-greeting', title: '開工當天群組問候', delivery: ['automatic'], ids: ['payment-first-greeting', 'payment-first-reminder'], alternatives: true, summary: '開工當天向案件群組發送一則純文字問候。第一期款尚未結清時，在同一則文字附上繳款提醒。' },
      { id: 'service-schedule', title: '服務排程', delivery: ['reply'], ids: ['helper-schedule-unconfirmed', 'service-start-result'], summary: '以 7 欄排班日曆卡片呈現（圖例標註多月嫂區段與固定排休日，精簡直觀）；未開工時提示預期排程或先確認開工日，開工後供雙方查看已服務天數、剩餘天數與排休日（純 Reply 回覆，0 Push 額度）。' },
      { id: 'mutual-postponement', title: '雙方合意延期', delivery: ['reply'], ids: ['helper-postponement-card', 'helper-postponement-completed'], summary: '僅限本案月嫂由 Flex URI Action 免費開啟（客戶操作回覆阻擋提示）；LIFF 嚴格鎖定本案、阻擋客戶開啟，重用後台日曆樣式支援多天成對調整且天數守恆；無衝突送出並經客戶同意後單一 UoW 更新排班（防自提自審，客戶重新協調回覆取消通知）。' },
      { id: 'staff-assistance', title: '案件群組留言', internal: true, summary: '需要工會協助時，由月嫂或客戶在原案件群組留言。' },
      { id: 'group-guidelines', title: '客戶常見疑問', delivery: ['reply'], ids: ['helper-guidelines-card', 'helper-faq-ingredients', 'helper-faq-hours', 'helper-faq-subsidy'], summary: '宣導排程修改須事前合意、配合政府補助不提前解約、請假採合意延期補班；內建常見客戶疑問（食材採買、服務時段、補助撥款），月嫂可一鍵由系統 Reply 代發工會標準回答。支援於後台調整卡片文案、問題選項與標準回答。' },
    ] },
    { title: '持續服務與異動', nodes: [
      { id: 'first-overdue', title: '第一期款逾期－私訊補寄與人工提醒', delivery: ['automatic', 'manual'], ids: ['payment-overdue-first'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動私訊補寄一次；後續人工提醒也走客戶私訊。' },
      { id: 'first-payment-settled', title: '第一期款確認入帳', summary: '工會在 LINE 官方帳號私聊手動發送入帳通知，並在系統標記已通知。' },
      { id: 'second-payment', title: '第二期款到期提醒', delivery: ['automatic'], ids: ['payment-second-reminder'], summary: '到期當天仍有餘額時，依排程自動私訊客戶；不需第二期或已結清不催繳。' },
      { id: 'second-payment-settled', title: '第二期款入帳收據', summary: '確認入帳後，由工會人員在 LINE 官方帳號聊天後台使用預設訊息手動發送，並於系統內標記已通知以消除待辦。' },
      { id: 'second-overdue', title: '第二期款逾期－私訊補寄與人工提醒', delivery: ['automatic', 'manual'], ids: ['payment-overdue-second'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；回覆後改人工提醒，未核銷款項保留待辦。' },
    ] },
    { title: '完工與結案', nodes: [
      { id: 'service-completion', title: '滿意度調查問卷', delivery: ['reply'], ids: ['helper-satisfaction-survey'], summary: '正式完工後，本案月嫂可從群組小幫手點選問卷。系統在原群組回覆目前範本文字，問卷網址可在「通知與發送」補上。' },
      { id: 'settlement', title: '帳務結算與結案', internal: true, summary: '一般退款、補助核銷與月嫂付款由帳務流程處理。' },
    ] },
  ] },
  { id: 'identity', name: '登記與身分', stages: [
    { title: '加入好友', nodes: [{ id: 'welcome', title: '加入 LINE 好友（官方帳號設定）', internal: true, summary: '加入好友歡迎訊息改由 LINE 官方帳號後台設定，系統不額外發送歡迎訊息。' }] },
    { title: '登記需求', nodes: [
      { id: 'registration', title: '開啟服務登記', delivery: ['reply'], ids: ['service-registration', 'service-registration-unavailable'] },
      { id: 'registration-approved', title: '需求申請核准通知', delivery: ['automatic'], ids: ['registration-approved-citizen', 'registration-approved-non-citizen'], summary: '工會核准後私訊申請人。非市民核准通知包含正式案件編號，可於後台自訂核准文案。' },
    ] },
    { title: '身分確認', nodes: [
      { id: 'identity-links', title: '客戶、月嫂與工會身分入口', delivery: ['reply'], ids: ['identity-customer-link', 'identity-staff-link', 'identity-admin-link'] },
    ] },
    { title: '完成綁定', nodes: [{ id: 'identity-bound', title: '各身分綁定完成', delivery: ['automatic'], ids: ['identity-bound-customer', 'identity-bound-staff', 'identity-bound-admin'] }] },
  ] },
  { id: 'support', name: '自助服務與留言', summary: '一般詢問及客訴由工會人員在 LINE 官方帳號處理。服務導覽、FAQ 和異動表單仍可直接開啟。', stages: [
    { title: '開啟服務', nodes: [
      { id: 'service-menu', title: '查看服務導覽', delivery: ['reply'], ids: ['service-menu'] },
      { id: 'order-update-menu', title: '修改訂單資訊導覽', delivery: ['reply'], ids: ['order-update-menu'] },
      { id: 'service-explanations', title: '服務流程與收費說明', internal: true, summary: '統一在 AI 客服 LIFF 查看常見問答或提問；說明內容由 AI 客服工作室維護，不另設固定回覆。' },
      { id: 'service-progress', title: '查詢服務進度', delivery: ['reply'], ids: ['service-progress', 'service-progress-unbound'], summary: '查看已綁定案件的進度回覆，以及尚未綁定時的入口提示。' },
    ] },
    { title: '工會處理', nodes: [
      { id: 'official-account-chat', title: '官方帳號留言', internal: true, summary: '工會人員查看並回覆一般詢問與客訴。' },
      { id: 'order-change-follow-up', title: '訂單異動申請', internal: true, summary: '客戶送出表單取得申請編號。工會在訂單管理查看並記錄辦理結果。' },
      { id: 'admin-status', title: '查看系統狀態', internal: true, summary: '工會人員在手機待辦工作台查看系統狀態。' },
    ] },
  ] },
];

export const FLOW_PREVIEW_ONLY_IDS = new Set([
  'staff-leave-completed',
  'helper-menu-completed',
  ...LINE_MESSAGE_FLOWS.flatMap(journey =>
    journey.stages.flatMap(stage => stage.nodes.flatMap(node => node.previewOnly ? node.ids ?? [] : []))
  ),
]);

export interface FlowMessage { descriptor: PreviewDescriptor; rule?: LineNotificationRuleModel; status: MessageFlowStatus }
export function resolveFlowMessages(node: FlowNodeDefinition, descriptors: readonly PreviewDescriptor[], rules: readonly LineNotificationRuleModel[]): FlowMessage[] {
  return descriptors.filter(item => node.ids?.includes(item.id) || (item.template_id !== null && node.templates?.includes(item.template_id)))
    .map(descriptor => {
      const rule = rules.find(value => value.id === descriptor.id);
      return { descriptor, rule, status: messageFlowStatus(descriptor, rule) };
    });
}
