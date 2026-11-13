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
      { id: 'customer-response', title: '接受配對／專人協助／其他選擇受理', delivery: ['reply'], ids: ['matching-customer-accepted', 'matching-customer-assistance', 'matching-customer-response'] },
    ] },
    { title: '簽約', nodes: [
      { id: 'signing-reminders', title: '簽署提醒', summary: '工會人員在 LINE 官方帳號聊天後台手動選用範本，發給需要提醒的客戶或月嫂。簽約完成以確認簽回文件為準。' },
      { id: 'contract-documents', title: '寄送客戶及月嫂契約文件', delivery: ['manual'], ids: ['contract-document-client', 'contract-document-staff'], previewOnly: true, summary: '工會人員發起寄送後，系統分別私訊客戶或月嫂，提供對應契約的下載連結。' },
    ] },
    { title: '收款與建群', nodes: [
      { id: 'deposit-reminder', title: '訂金繳費提醒', delivery: ['automatic', 'manual'], ids: ['deposit-reminder'], summary: '雙方簽約完成且資料齊備後，依排程自動私訊客戶；工會人員也可從待辦手動發送。' },
      { id: 'deposit-help', title: '訂金專人協助受理', delivery: ['reply'], ids: ['deposit-assistance'] },
      { id: 'deposit-settled', title: '訂金確認入帳', delivery: ['manual'], ids: ['deposit-settled'] },
      { id: 'deposit-overdue', title: '訂金逾期－私訊補寄與人工提醒', delivery: ['automatic', 'manual'], ids: ['payment-overdue-deposit'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；任何私訊或按鈕回覆後改人工提醒，未核銷款項保留待辦。' },
      { id: 'group-invitation', title: '寄送案件群組邀請', delivery: ['manual'], ids: ['group-invitation-customer', 'group-invitation-staff'], summary: '訂金正式核銷後，人員在案件群組設定綁定與邀請網址，再輸入「發送邀請」；不以簽約完成作為建群門檻。' },
    ] },
    { title: '開始服務', nodes: [
      { id: 'coordinated-dates', title: '月嫂提交已協調的開始日', internal: true, summary: '客戶與月嫂在案件群組自行協調；月嫂由訂單查詢或排班資訊與請假提交日期。無衝突即更新正式日期、排班與第一期款到期日；需要代班或衝突才交工會。' },
      { id: 'start-date-record', title: '正式日期表記錄到案件群組', delivery: ['automatic'], ids: ['service-start-result'], summary: '正式保存成功後寄送群組日期表，僅記錄結果，沒有再次確認或拒絕按鈕。' },
      { id: 'service-start', title: '服務開始當天通知卡', delivery: ['automatic'], templates: ['LINE-ORDER-SERVICE-START-DAY-CARD-V1'] },
      { id: 'service-start-replies', title: '服務開始當天受理回覆', delivery: ['reply'], ids: ['service-start-normal-received', 'service-start-help-received'], summary: '點選「服務正常」或「需要協助」後，在原案件群組回覆。' },
      { id: 'first-payment', title: '第一期款－自動客戶私訊', delivery: ['automatic'], ids: ['payment-first-reminder','payment-first-greeting'], summary: '正式服務開始當天依排程私訊；已結清只保留服務問候。' },
      { id: 'first-payment-settled', title: '第一期款入帳收據', delivery: ['manual'], ids: ['payment-first-settled'], summary: '確認入帳後，由工會人員手動私訊客戶。' },
      { id: 'first-overdue', title: '第一期款逾期－私訊補寄與人工提醒', delivery: ['automatic', 'manual'], ids: ['payment-overdue-first'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；回覆後改人工提醒，未核銷款項保留待辦。' },
    ] },
    { title: '持續服務與異動', nodes: [
      { id: 'second-payment', title: '第二期款到期提醒', delivery: ['automatic'], ids: ['payment-second-reminder'], summary: '到期當天仍有餘額時，依排程自動私訊客戶；不需第二期或已結清不催繳。' },
      { id: 'second-payment-settled', title: '第二期款入帳收據', delivery: ['manual'], templates: ['LINE-SECOND-PAYMENT-SETTLED-TEXT-V1'], summary: '確認入帳後，由工會人員手動私訊客戶。' },
      { id: 'second-overdue', title: '第二期款逾期－私訊補寄與人工提醒', delivery: ['automatic', 'manual'], ids: ['payment-overdue-second'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；回覆後改人工提醒，未核銷款項保留待辦。' },
      { id: 'leave', title: '請假、順延、代班與換人（共用流程）', delivery: ['automatic', 'manual'], ids: ['service-start-inquiry', 'group-invitation-staff', 'service-start-result'], summary: '工會人員徵詢代班意願、邀請加入原群組。正式保存後，系統寄送群組日期表。' },
      { id: 'leave-completed', title: '月嫂請假完成正式排班處理', delivery: ['automatic'], ids: ['staff-leave-completed'], previewOnly: true, summary: '代班處理完成並結束關聯請假申請後，私訊原申請月嫂。' },
    ] },
    { title: '完工與結案', nodes: [
      { id: 'service-completion', title: '服務完工與滿意度問卷邀請', delivery: ['automatic'], templates: ['LINE-SERVICE-COMPLETION-TEXT-V1'], summary: '正常服務完工後，在原案件群組通知一次。問卷網址先留空，日後可於通知內容加入；不等待帳務結清。' },
      { id: 'settlement', title: '帳務結算與結案', internal: true, summary: '一般退款、補助核銷與月嫂付款由帳務流程處理。取消結算相關通知由工會人員另外發送。' },
      { id: 'cancellation-notices', title: '取消結算通知', delivery: ['manual'], ids: ['cancellation-notice-settlement', 'cancellation-notice-refund', 'cancellation-notice-collection'], summary: '工會人員可依案件狀態私訊客戶結算明細、退款完成或補收入帳。完成帳務操作不會自動寄送。' },
    ] },
  ] },
  { id: 'identity', name: '登記與身分', stages: [
    { title: '加入好友', nodes: [{ id: 'welcome', title: '加入 LINE 好友（官方帳號設定）', internal: true, summary: '加入好友歡迎訊息改由 LINE 官方帳號後台設定，系統不額外發送歡迎訊息。' }] },
    { title: '登記需求', nodes: [
      { id: 'registration', title: '開啟服務登記', delivery: ['reply'], ids: ['service-registration', 'service-registration-unavailable'] },
      { id: 'registration-approved', title: '需求申請核准通知', delivery: ['automatic'], ids: ['registration-approved-citizen', 'registration-approved-non-citizen'], previewOnly: true, summary: '工會核准後私訊申請人。非市民核准通知包含正式案件編號。' },
    ] },
    { title: '身分確認', nodes: [
      { id: 'identity-links', title: '客戶、月嫂與工會身分入口', delivery: ['reply'], ids: ['identity-customer-link', 'identity-staff-link', 'identity-admin-link'] },
      { id: 'identity-pending', title: '受理身分申請', delivery: ['automatic'], ids: ['identity-pending'], templates: ['staff_verification_rejected'] },
    ] },
    { title: '完成綁定', nodes: [{ id: 'identity-bound', title: '各身分綁定完成', delivery: ['automatic'], ids: ['identity-bound-customer', 'identity-bound-staff', 'identity-bound-admin'], templates: ['client_rebind_rejected'] }] },
  ] },
  { id: 'support', name: '客服與支援', summary: '一般留言不啟動聊天室 AI，也不自動開客服單。「問題／其他問題」回到自助導覽；明確呼叫專員後，留言才加入同一客服案件。舊 AI 回答錯誤按鈕只提示功能停用。', stages: [
    { title: '開啟服務', nodes: [
      { id: 'service-menu', title: '查看服務導覽', delivery: ['reply'], ids: ['service-menu'] },
      { id: 'order-update-menu', title: '修改訂單資訊導覽', delivery: ['reply'], ids: ['order-update-menu'] },
      { id: 'service-explanations', title: '服務流程與收費說明', internal: true, summary: '統一在 AI 客服 LIFF 查看常見問答或提問；說明內容由 AI 客服工作室維護，不另設固定回覆。' },
      { id: 'service-progress', title: '查詢服務進度', delivery: ['reply'], ids: ['service-progress', 'service-progress-unbound'], summary: '查看已綁定案件的進度回覆，以及尚未綁定時的入口提示。' },
    ] },
    { title: '聯絡專人', nodes: [
      { id: 'contact', title: '聯絡專人服務', delivery: ['reply'], ids: ['service-contact'], summary: '明確呼叫後建立或接續客服需求；聊天室受理回覆不會改走 Push。' },
      { id: 'complaint-received', title: '客訴已轉接真人客服', delivery: ['automatic'], ids: ['complaint-handoff-received'], previewOnly: true, summary: '符合客訴轉接條件時，私訊客戶已轉接真人客服。' },
      { id: 'change-request-received', title: '資料或訂單修改受理', delivery: ['automatic'], ids: ['service-profile-update', 'service-order-update'], summary: '客戶在聊天室提出資料或訂單修改需求後，系統私訊受理結果。' },
    ] },
    { title: '人工處理', nodes: [
      { id: 'admin-status', title: '查看系統狀態與客服待辦', internal: true, summary: '管理員於 LIFF 待辦工作台上方主動查看系統狀態；客服案件照常受理，不自動推播系統異常或重大客訴。' },
      { id: 'ticket-reply', title: '工會人員回覆客服工單', delivery: ['manual'], ids: ['customer-service-ticket-reply'], previewOnly: true, summary: '實際內容由工會人員逐案輸入。公版以一則範例回覆展示。' },
    ] },
    { title: '案件完成', nodes: [
      { id: 'ticket-close', title: '一般客服工單結案', internal: true, summary: '在客服工作台標記處理完成只更新工單狀態，客戶不會收到結案訊息。' },
      { id: 'resolved', title: '人工升級案件結案通知', delivery: ['automatic'], ids: ['service-resolved'], summary: '工會人員完成升級案件的結案操作後，系統自動私訊客戶處理結果。' },
    ] },
  ] },
];

export const FLOW_PREVIEW_ONLY_IDS = new Set(LINE_MESSAGE_FLOWS.flatMap(journey =>
  journey.stages.flatMap(stage => stage.nodes.flatMap(node => node.previewOnly ? node.ids ?? [] : []))
));

export interface FlowMessage { descriptor: PreviewDescriptor; rule?: LineNotificationRuleModel; status: MessageFlowStatus }
export function resolveFlowMessages(node: FlowNodeDefinition, descriptors: readonly PreviewDescriptor[], rules: readonly LineNotificationRuleModel[]): FlowMessage[] {
  return descriptors.filter(item => node.ids?.includes(item.id) || (item.template_id !== null && node.templates?.includes(item.template_id)))
    .map(descriptor => {
      const rule = rules.find(value => value.id === descriptor.id);
      return { descriptor, rule, status: messageFlowStatus(descriptor, rule) };
    });
}
