/**
 * File: order_tracker_adapter.ts
 * Description: 將訂單摘要映射為未完成案件七階段卡片，並提供 SOP、LINE 與結清業務狀態。
 */
import type { OrderSummaryItem, OrderSummaryPage } from '../../api/orders/order_query_schemas';

export const TRACKER_STAGE_PROJECTION_UNAVAILABLE = '階段資料目前無法取得，請重新載入。';
export const TRACKER_ROOT_FACT_LINEAGE_UNAVAILABLE = '尚無此步驟的作業紀錄。';
export const TRACKER_NOTIFICATION_TIMELINE_UNAVAILABLE = '尚無 LINE 通知紀錄。';
export const TRACKER_TYPED_PROJECTION_UNAVAILABLE = '尚未登錄';

export type TrackerStageSlotId =
  | 'intake_terms'
  | 'matching_willingness'
  | 'client_review'
  | 'contract_deposit'
  | 'date_confirmation'
  | 'active_service'
  | 'settlement_payout';

export interface TrackerStageSlotViewModel {
  id: TrackerStageSlotId;
  title: string;
  description: string;
  badgeColor: string;
  textColor: string;
  availability: 'unavailable';
  count: null;
  unavailableMessage: string;
}

export const TRACKER_STAGE_SLOTS: readonly TrackerStageSlotViewModel[] = [
  ['intake_terms', '1. 📥 進件與補件', '資料驗證、時段與特殊條款確認', '#e0e7ff', '#3730a3'],
  ['matching_willingness', '2. 👩‍🍼 媒合與徵詢意願', '候選意願與媒合進度', '#ffedd5', '#9a3412'],
  ['client_review', '3. 👥 推薦客戶與確認', '正式推薦與客戶確認', '#fef3c7', '#854d0e'],
  ['contract_deposit', '4. 📝 雙邊簽約與定金', '契約與定金核銷', '#f3e8ff', '#6b21a8'],
  ['date_confirmation', '5. 📅 確認事前服務日期', '依精算結果確認正式服務日期', '#ccfbf1', '#0f766e'],
  ['active_service', '6. 🚀 正式服務履約', '出勤、請假與服務履約', '#dcfce7', '#166534'],
  ['settlement_payout', '7. 🏁 完工結案與請款', '完成、客戶款項與月嫂薪資', '#fee2e2', '#991b1b'],
].map(([id, title, description, badgeColor, textColor]) => ({
  id: id as TrackerStageSlotId,
  title,
  description,
  badgeColor,
  textColor,
  availability: 'unavailable' as const,
  count: null,
  unavailableMessage: TRACKER_STAGE_PROJECTION_UNAVAILABLE,
}));

const SOP_STEP_NAMES = [
  '進件報名與資料完整性驗證',
  '媒合月嫂候選人加入意願池',
  '發送訂單資訊詢問月嫂意願（LINE）',
  '月嫂回傳接案意願',
  '寄送月嫂履歷給客戶確認',
  '產生月嫂服務契約並留存簽回（寄送或人工確認）',
  '客戶定金核銷（訂單成立）',
  '產生客戶契約並留存簽回（寄送或人工確認）',
  '確認事前服務日期（精算）',
  '轉換正式排班與服務履約',
  '完工驗收、時數核對與尾款／薪資結清',
] as const;

export interface TrackerSopStepViewModel {
  stepNo: number;
  name: string;
  availability: 'unavailable';
  status: null;
  timestamp: null;
  notes: string;
}

export interface TrackerSettlementSlotViewModel {
  id: 'service-completion' | 'client-finance' | 'staff-payroll';
  label: string;
  owner: string;
  availability: 'unavailable';
  value: string;
}

export const TRACKER_SETTLEMENT_SLOTS: readonly TrackerSettlementSlotViewModel[] = [
  {
    id: 'service-completion',
    label: '服務完成',
    owner: 'Orders',
    availability: 'unavailable',
    value: '尚未完成服務驗收',
  },
  {
    id: 'client-finance',
    label: '客戶款項結清',
    owner: 'Client Finance',
    availability: 'unavailable',
    value: '尚未完成客戶款項結清',
  },
  {
    id: 'staff-payroll',
    label: '月嫂薪資核銷',
    owner: 'Staff Payables',
    availability: 'unavailable',
    value: '尚未完成月嫂薪資核銷',
  },
] as const;

export interface TrackerOrderCardViewModel {
  id: string;
  clientName: string;
  rawOrderStatus: string;
  identityStatus: string;
  assignedStaffName: string | null;
  assignedStaffDisplay: string;
  plannedServiceRange: string;
  actualServiceRange: string;
  serviceDaysLabel: string;
  contractAmountFormatted: string;
  clientPhoneText: string;
  serviceAddressText: string;
  waitingText: string;
  stepsChecklist: readonly TrackerSopStepViewModel[];
  notificationTimelineMessage: string;
  settlementSlots: readonly TrackerSettlementSlotViewModel[];
}

export interface OrderTrackerPageViewModel {
  stageSlots: readonly TrackerStageSlotViewModel[];
  unclassifiedOrders: TrackerOrderCardViewModel[];
  loadedCount: number;
  nextCursor: string | null;
  etag: string;
}

function displayText(value: string | null, label: string): string {
  return value?.trim() || `${TRACKER_TYPED_PROJECTION_UNAVAILABLE}（${label}）`;
}

function formatDateRange(start: string | null, end: string | null, label: string): string {
  if (start && end) return `${start} ～ ${end}`;
  if (start) return `${start} 起（結束日待填寫）`;
  if (end) return `開始日待填寫 ～ ${end}`;
  return `${TRACKER_TYPED_PROJECTION_UNAVAILABLE}（${label}）`;
}

export function createUnavailableSopSteps(): TrackerSopStepViewModel[] {
  return SOP_STEP_NAMES.map((name, index) => ({
    stepNo: index + 1,
    name,
    availability: 'unavailable' as const,
    status: null,
    timestamp: null,
    notes: TRACKER_ROOT_FACT_LINEAGE_UNAVAILABLE,
  }));
}

export function adaptTrackerOrderCard(item: OrderSummaryItem): TrackerOrderCardViewModel {
  const staffName = item.staff_name?.trim() || null;
  return {
    id: item.case_no,
    clientName: displayText(item.client_name, '客戶姓名'),
    rawOrderStatus: displayText(item.order_status, '原始訂單狀態'),
    identityStatus: displayText(item.identity_status, '身分狀態'),
    assignedStaffName: staffName,
    assignedStaffDisplay: staffName ?? '尚未正式指派',
    plannedServiceRange: formatDateRange(item.start_date, item.end_date, '約定服務日期'),
    actualServiceRange: formatDateRange(item.actual_start_date, item.actual_end_date, '實際服務日期'),
    serviceDaysLabel: item.service_days === null
      ? '待補服務天數'
      : `${item.service_days} 天`,
    contractAmountFormatted: item.total_employer_self_pay_payable === null
      ? '尚未登錄契約應付金額'
      : `NT$ ${item.total_employer_self_pay_payable.toLocaleString('en-US')}`,
    clientPhoneText: '開啟案件卡片後載入',
    serviceAddressText: '開啟案件卡片後載入',
    waitingText: '請依目前階段處理',
    stepsChecklist: createUnavailableSopSteps(),
    notificationTimelineMessage: TRACKER_NOTIFICATION_TIMELINE_UNAVAILABLE,
    settlementSlots: TRACKER_SETTLEMENT_SLOTS,
  };
}

export function adaptOrderTrackerPage(page: OrderSummaryPage): OrderTrackerPageViewModel {
  // server lifecycle_scope 是未完成集合的唯一 owner；adapter 不得重解中文狀態或靜默縮減結果。
  const unclassifiedOrders = page.items.map(adaptTrackerOrderCard);
  return {
    stageSlots: TRACKER_STAGE_SLOTS,
    unclassifiedOrders,
    loadedCount: unclassifiedOrders.length,
    nextCursor: page.next_cursor,
    etag: page.etag,
  };
}
