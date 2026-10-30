/** LINE 流程圖僅分類正式目錄；內容、ID 與開關仍以 typed Query 為準。 */
import type { PreviewDescriptor } from '../../api/line_notification_rules/line_message_preview_client';
import type { LineNotificationRuleModel } from './line_configuration_query_adapter';

export const FLOW_MANAGED_NOTIFICATION_EVENTS = new Set([
  'runtime.alert.review_required',
  'complaint.ingress.hold_high_ticket',
]);

export type MessageFlowStatus = 'enabled' | 'disabled' | 'flow' | 'unavailable';
export function messageFlowStatus(descriptor: Pick<PreviewDescriptor, 'id' | 'builtin'>, rule?: LineNotificationRuleModel): MessageFlowStatus {
  if (rule) return FLOW_MANAGED_NOTIFICATION_EVENTS.has(rule.eventCode) ? 'flow' : rule.enabled ? 'enabled' : 'disabled';
  return descriptor.builtin || descriptor.id === 'welcome' ? 'flow' : 'unavailable';
}
export const MESSAGE_FLOW_STATUS_LABELS: Record<MessageFlowStatus, string> = {
  enabled: '已啟用', disabled: '已停用', flow: '由流程控制', unavailable: '狀態無法確認',
};

interface FlowNodeDefinition { id: string; title: string; ids?: readonly string[]; templates?: readonly string[]; internal?: boolean; summary?: string }
interface FlowStageDefinition { title: string; nodes: readonly FlowNodeDefinition[] }
interface FlowJourneyDefinition { id: string; name: string; summary?: string; stages: readonly FlowStageDefinition[] }

export const LINE_MESSAGE_FLOWS: readonly FlowJourneyDefinition[] = [
  { id: 'matching', name: '媒合到服務', summary: '簽約與訂金付款可先後交錯；訂金正式核銷後即可建立案件群組，不必等簽約完成。正式日期與排班仍由既有前置條件檢查。', stages: [
    { title: '初步候選聯絡', nodes: [
      { id: 'candidate-info', title: '寄送案件資訊', ids: ['card-candidate-information-1', 'card-candidate-information-2', 'card-candidate-information-3'] },
      { id: 'coordination', title: '人工協調問題與回覆', ids: ['card-union-question', 'card-union-answer'] },
      { id: 'candidate-response', title: '月嫂意願受理', ids: ['candidate-willing-received'] },
    ] },
    { title: '正式媒合與客戶確認', nodes: [
      { id: 'recommendation', title: '寄送完整推薦確認包', ids: ['card-customer-confirmation'] },
      { id: 'customer-response', title: '接受配對／專人協助', ids: ['matching-customer-accepted', 'matching-customer-assistance'] },
    ] },
    { title: '簽約', nodes: [
      { id: 'signing-reminders', title: '人工發送簽署提醒', ids: ['contract-signing-client', 'contract-signing-staff'], summary: '人員點擊後建立客戶及月嫂私人提醒工作，無再次確認視窗；簽約完成仍以簽回文件為準。' },
    ] },
    { title: '收款與建群', nodes: [
      { id: 'deposit-reminder', title: '自動私訊訂金繳費提醒', ids: ['deposit-reminder', 'deposit-assistance'], summary: '雙方簽約完成且資料齊備後，依帳務提醒排程自動寄客戶私訊。' },
      { id: 'deposit-settled', title: '訂金確認入帳', ids: ['deposit-settled'] },
      { id: 'deposit-overdue', title: '訂金逾期－私訊補寄與人工提醒', ids: ['payment-overdue-deposit'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；任何私訊或按鈕回覆後改人工提醒，未核銷款項保留待辦。' },
      { id: 'group-invitation', title: '寄送案件群組邀請', ids: ['group-invitation-customer', 'group-invitation-staff'], summary: '訂金正式核銷後，人員在案件群組設定綁定與邀請網址，再輸入「發送邀請」；不以簽約完成作為建群門檻。' },
    ] },
    { title: '開始服務', nodes: [
      { id: 'coordinated-dates', title: '月嫂提交已協調的開始日', internal: true, summary: '客戶與月嫂在案件群組自行協調；月嫂由訂單查詢或排班資訊與請假提交日期。無衝突即更新正式日期、排班與第一期款到期日；需要代班或衝突才交工會。' },
      { id: 'start-date-record', title: '正式日期表記錄到案件群組', ids: ['service-start-result'], summary: '正式保存成功後寄送群組日期表，僅記錄結果，沒有再次確認或拒絕按鈕。' },
      { id: 'service-start', title: '服務開始當天', templates: ['LINE-ORDER-SERVICE-START-DAY-CARD-V1'], ids: ['service-start-normal-received', 'service-start-help-received'], summary: '查看當天卡片，以及「服務正常」「需要協助」後寄到原案件群組的受理回覆。' },
      { id: 'first-payment', title: '第一期款－自動客戶私訊', ids: ['payment-first-reminder','payment-first-greeting'], summary: '正式服務開始當天依排程私訊；已結清只保留服務問候。' },
      { id: 'first-overdue', title: '第一期款逾期－私訊補寄與人工提醒', ids: ['payment-overdue-first'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；回覆後改人工提醒，未核銷款項保留待辦。' },
    ] },
    { title: '持續服務與異動', nodes: [
      { id: 'baby-log', title: '日誌連續缺漏－工會決定提醒', ids: ['service-day-log-reminder'] },
      { id: 'second-payment', title: '第二期款到期與入帳', ids: ['payment-second-reminder'], templates: ['LINE-SECOND-PAYMENT-SETTLED-TEXT-V1'], summary: '到期當天仍有餘額時，依排程自動私訊客戶；不需第二期或已結清不催繳。' },
      { id: 'second-overdue', title: '第二期款逾期－私訊補寄與人工提醒', ids: ['payment-overdue-second'], summary: '逾期且距原提醒滿 24 小時、客戶未回覆時自動補寄一次；回覆後改人工提醒，未核銷款項保留待辦。' },
      { id: 'leave', title: '請假、順延、代班與換人（共用流程）', ids: ['service-start-inquiry', 'group-invitation-staff', 'service-start-result'], summary: '雙方自行協調。無衝突順延直接更新；代班或換人共用詢問意願、邀請加入原案件群組、工會記錄日期及帳務更新，最後寄無確認按鈕的日期表。' },
    ] },
    { title: '完工與結案', nodes: [
      { id: 'service-completion', title: '服務完工與滿意度問卷邀請', templates: ['LINE-SERVICE-COMPLETION-TEXT-V1'], summary: '正常服務完工後，在原案件群組通知一次。問卷網址先留空，日後可於通知內容加入；不等待帳務結清。' },
      { id: 'settlement', title: '帳務結算與結案', internal: true, summary: '客戶退款、補助整期核銷及月嫂付款由既有帳務流程處理；取消、退款與薪資成功不另發 LINE 通知。問卷網址目前依設定留空。' },
    ] },
  ] },
  { id: 'identity', name: '登記與身分', stages: [
    { title: '加入好友', nodes: [{ id: 'welcome', title: '加入 LINE 好友', ids: ['welcome'] }] },
    { title: '登記需求', nodes: [{ id: 'registration', title: '開啟服務登記', ids: ['service-registration'] }] },
    { title: '身分確認', nodes: [{ id: 'identity-pending', title: '受理身分申請', ids: ['identity-pending'], templates: ['staff_verification_rejected'] }] },
    { title: '完成綁定', nodes: [{ id: 'identity-bound', title: '各身分綁定完成', ids: ['identity-bound-customer', 'identity-bound-staff', 'identity-bound-admin'], templates: ['client_rebind_rejected'] }] },
  ] },
  { id: 'support', name: '客服與支援', summary: '一般留言不啟動聊天室 AI，也不自動開客服單。「問題／其他問題」回到自助導覽；明確呼叫專員後，留言才加入同一客服案件。舊 AI 回答錯誤按鈕只提示功能停用。', stages: [
    { title: '開啟服務', nodes: [
      { id: 'service-menu', title: '查看服務導覽', ids: ['service-menu'] },
      { id: 'service-explanations', title: '服務流程與收費說明', internal: true, summary: '統一在 AI 客服 LIFF 查看常見問答或提問；說明內容由 AI 客服工作室維護，不另設固定回覆。' },
      { id: 'service-progress', title: '查詢服務進度', ids: ['service-progress', 'service-progress-unbound'], summary: '查看已綁定案件的進度回覆，以及尚未綁定時的入口提示。' },
    ] },
    { title: '聯絡專人', nodes: [{ id: 'contact', title: '聯絡專人服務', ids: ['service-contact'], summary: '明確呼叫即建立或接續客服需求，不再要求轉真人確認。既有資料異動與訂單申請仍走原受理流程。' }] },
    { title: '人工處理', nodes: [{ id: 'admin-status', title: '查看系統狀態與客服待辦', internal: true, summary: '管理員於 LIFF 待辦工作台上方主動查看系統狀態；客服案件照常受理，不自動推播系統異常或重大客訴。' }] },
    { title: '案件完成', nodes: [{ id: 'resolved', title: '客服正式結案', ids: ['service-resolved'] }] },
  ] },
];

export interface FlowMessage { descriptor: PreviewDescriptor; rule?: LineNotificationRuleModel; status: MessageFlowStatus }
export function resolveFlowMessages(node: FlowNodeDefinition, descriptors: readonly PreviewDescriptor[], rules: readonly LineNotificationRuleModel[]): FlowMessage[] {
  return descriptors.filter(item => node.ids?.includes(item.id) || (item.template_id !== null && node.templates?.includes(item.template_id)))
    .map(descriptor => {
      const rule = rules.find(value => value.id === descriptor.id);
      return { descriptor, rule, status: messageFlowStatus(descriptor, rule) };
    });
}
