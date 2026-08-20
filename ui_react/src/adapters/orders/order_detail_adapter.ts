/**
 * File: order_detail_adapter.ts
 * Description: 組合 Orders 四個 Drawer 的 typed facts，缺少 projection 時明確標示 unavailable。
 */
import type {
  ActualStart,
  AssignmentPlan,
  ContractCompletion,
  OrderCalendarDetail,
  OrderDetail,
  OrderTerms,
} from '../../api/orders/order_query_schemas';
import {
  ORDERS_TYPED_PROJECTION_UNAVAILABLE,
  formatServiceRange,
  type OrderSummaryCardViewModel,
} from './order_summary_adapter';

const unavailable = (scope: string) =>
  `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（${scope}）`;

export interface ServiceDateConfirmationDrawerViewModel {
  caseNo: string;
  actualStartDate: string;
  hasActualStartDate: boolean;
  restDaysSummary: string;
  serviceMode: string;
  serviceRangeText: string;
  contractedServiceDays: number | null;
  calculatedServiceDaysText: string;
  restDaysCountText: string;
  bufferDateRange: string;
  customerConfirmed: null;
  customerConfirmedText: string;
  staffConfirmed: null;
  staffConfirmedText: string;
  gatePassed: null;
}

export interface CandidatePoolItemViewModel {
  staffId: number;
  staffName: string;
  staffPhone: string;
  experienceYears: number;
  location: string;
  skills: string[];
  matchScore: number;
  goodConductValid: boolean;
  medicalExamValid: boolean;
  serviceRange: string;
  info1Sent: boolean;
  info1SentAt?: string;
  info2Sent: boolean;
  info2SentAt?: string;
  willingness: 'pending' | 'willing' | 'unwilling';
  willingnessLabel: string;
  selectedForResume: boolean;
}

export interface AssignmentSegmentViewModel {
  key: string;
  staffId: number;
  sequence: number;
  serviceRange: string;
  officialServiceDates: readonly string[];
  actualHoursText: string;
}

export interface MatchingWorkbenchDrawerViewModel {
  caseNo: string;
  planId: string;
  status: string;
  candidatePool: CandidatePoolItemViewModel[];
  assignmentSegments: AssignmentSegmentViewModel[];
  candidatePoolUnavailable: string;
  customerDecision: null;
  customerDecisionLabel: string;
  waitingLockAcquired: null;
  waitingLockText: string;
  resumeNote: string;
}

export interface OrderTermsContractDrawerViewModel {
  caseNo: string;
  clientName: string;
  serviceRange: string;
  serviceDays: number | null;
  serviceTimeText: string;
  requiresCookingText: string;
  floorFee: number | null;
  floorFeeText: string;
  contractAmount: number | null;
  contractAmountText: string;
  staffContractSigned: null;
  staffContractSignedText: string;
  depositSettled: boolean | null;
  depositSettledText: string;
  clientContractSigned: null;
  clientContractSignedText: string;
  domainBlockers: string[];
}

export interface OrderCancellationDrawerViewModel {
  caseNo: string;
  lifecycleStatus: string;
  cancellationType: string;
  statutoryExplanation: string;
  contractAmount: null;
  contractAmountText: string;
  depositAmount: null;
  depositAmountText: string;
  servedDays: null;
  serviceDays: null;
  servedDaysText: string;
  penaltyFee: null;
  penaltyFeeText: string;
  refundAmount: null;
  refundAmountText: string;
  isPurePreview: false;
}

export function localizeDomainBlocker(blockerKey: string): string {
  const labels: Record<string, string> = {
    MISSING_TIME_TERMS: '時段三欄尚未填寫完整',
    MISSING_COOKING_TERMS: '下廚料理需求條款尚未確認',
    DEPOSIT_UNSETTLED: '客戶定金尚未核銷入帳',
    STAFF_CONTRACT_UNSIGNED: '月嫂服務契約尚未簽回',
    CLIENT_CONTRACT_UNSIGNED: '客戶委任契約尚未簽回',
    SCHEDULE_UNCONFIRMED: '精算日程表尚未完成雙邊確認',
    MISSING_ACTUAL_START: '尚未通報確認實際服務開始日',
    MISSING_EMERGENCY_CONTACT: '未填寫緊急聯絡人（警示，非阻擋）',
  };
  return labels[blockerKey] ?? blockerKey;
}

export function adaptServiceDateConfirmationDrawer(params: {
  caseNo: string;
  actualStart?: ActualStart | null;
  calendarDetail?: OrderCalendarDetail | null;
  orderDetail?: OrderDetail | null;
}): ServiceDateConfirmationDrawerViewModel {
  const { caseNo, actualStart, calendarDetail, orderDetail } = params;
  const actualStartDate = actualStart?.current_actual_start_date ?? '—';
  return {
    caseNo,
    actualStartDate,
    hasActualStartDate: actualStart?.current_actual_start_date !== null && actualStart !== null && actualStart !== undefined,
    restDaysSummary: orderDetail?.custom_rest_dates ?? unavailable('排休摘要'),
    serviceMode: calendarDetail?.service_mode ?? unavailable('排班模式'),
    serviceRangeText: orderDetail
      ? formatServiceRange(orderDetail.start_date, orderDetail.end_date)
      : unavailable('約定服務起訖日'),
    contractedServiceDays: orderDetail?.service_days ?? null,
    calculatedServiceDaysText: unavailable('精算服務天數'),
    restDaysCountText: unavailable('順延天數'),
    bufferDateRange: unavailable('服務後緩衝期間'),
    customerConfirmed: null,
    customerConfirmedText: unavailable('客戶確認狀態'),
    staffConfirmed: null,
    staffConfirmedText: unavailable('月嫂確認狀態'),
    gatePassed: null,
  };
}

export function adaptMatchingWorkbenchDrawer(params: {
  caseNo: string;
  assignmentPlan?: AssignmentPlan | null;
}): MatchingWorkbenchDrawerViewModel {
  const { caseNo, assignmentPlan } = params;
  const assignmentSegments = (assignmentPlan?.assignments ?? []).map((segment) => ({
    key: segment.assignment_id === null
      ? segment.candidate_key ?? `${segment.staff_id}-${segment.sequence}`
      : String(segment.assignment_id),
    staffId: segment.staff_id,
    sequence: segment.sequence,
    serviceRange: `${segment.assigned_start_date} ~ ${segment.assigned_end_date}`,
    officialServiceDates: segment.official_service_dates,
    actualHoursText: segment.actual_hours === null
      ? unavailable('實際服務時數')
      : `${segment.actual_hours} 小時`,
  }));
  return {
    caseNo,
    planId: unavailable('媒合方案識別'),
    status: unavailable('媒合狀態'),
    candidatePool: [],
    assignmentSegments,
    candidatePoolUnavailable: unavailable('候選聯繫池與正式推薦'),
    customerDecision: null,
    customerDecisionLabel: unavailable('客戶決策'),
    waitingLockAcquired: null,
    waitingLockText: unavailable('等待訂金鎖'),
    resumeNote: unavailable('履歷說明備註'),
  };
}

function serviceTimeText(terms?: OrderTerms | null): string {
  const time = terms?.terms.service_time;
  if (!time || time.start_time === null || time.end_time === null || time.end_day_offset === null) {
    return unavailable('服務時段三欄');
  }
  return `${time.start_time} ~ ${time.end_time}（${time.end_day_offset === 0 ? '同日' : '跨日'}）`;
}

export function adaptOrderTermsContractDrawer(params: {
  caseNo: string;
  terms?: OrderTerms | null;
  completion?: ContractCompletion | null;
  summary?: OrderSummaryCardViewModel | null;
  orderDetail?: OrderDetail | null;
}): OrderTermsContractDrawerViewModel {
  const { caseNo, terms, completion, summary, orderDetail } = params;
  const requiresCooking = terms?.terms.requires_cooking;
  const floorFee = terms?.terms.floor_fee_ntd ?? orderDetail?.floor_fee ?? null;
  const contractAmount = summary?.contractAmount ?? null;
  const depositSettled = completion?.deposit_settled ?? null;
  return {
    caseNo,
    clientName: summary?.clientName ?? orderDetail?.client_name ?? unavailable('客戶姓名'),
    serviceRange: summary?.serviceRange ?? unavailable('約定服務起訖日'),
    serviceDays: terms?.terms.service_days ?? orderDetail?.service_days ?? summary?.serviceDays ?? null,
    serviceTimeText: serviceTimeText(terms),
    requiresCookingText:
      requiresCooking === true ? '是' : requiresCooking === false ? '否' : unavailable('下廚料理條款'),
    floorFee,
    floorFeeText: floorFee === null ? unavailable('樓層加給') : `NT$ ${floorFee.toLocaleString()}`,
    contractAmount,
    contractAmountText:
      contractAmount === null ? unavailable('合約總金額') : `NT$ ${contractAmount.toLocaleString()}`,
    staffContractSigned: null,
    staffContractSignedText: unavailable('月嫂契約簽回狀態'),
    depositSettled,
    depositSettledText:
      depositSettled === null ? unavailable('客戶定金核銷') : depositSettled ? '✅ 已核銷' : '⏳ 待核銷',
    clientContractSigned: null,
    clientContractSignedText: unavailable('客戶契約簽回狀態'),
    domainBlockers: (completion?.domain_blockers ?? []).map(localizeDomainBlocker),
  };
}

export function adaptOrderCancellationDrawer(params: {
  caseNo: string;
  summary?: OrderSummaryCardViewModel | null;
}): OrderCancellationDrawerViewModel {
  return {
    caseNo: params.caseNo,
    lifecycleStatus: params.summary?.orderStatus ?? unavailable('訂單狀態'),
    cancellationType: unavailable('取消類型'),
    statutoryExplanation: unavailable('取消與退款規則'),
    contractAmount: null,
    contractAmountText: unavailable('取消基準金額'),
    depositAmount: null,
    depositAmountText: unavailable('實收定金'),
    servedDays: null,
    serviceDays: null,
    servedDaysText: unavailable('已履約天數'),
    penaltyFee: null,
    penaltyFeeText: unavailable('扣除費用'),
    refundAmount: null,
    refundAmountText: unavailable('應退款金額'),
    isPurePreview: false,
  };
}
