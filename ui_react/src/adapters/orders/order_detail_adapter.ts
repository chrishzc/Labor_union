/**
 * File: order_detail_adapter.ts
 * Description: 組合 Orders 四個 Drawer 的 typed facts，並呈現既有精算與取消預覽結果。
 */
import type {
  ActualStart,
  AssignmentPlan,
  ContractCompletion,
  OrderCalendarDetail,
  OrderDetail,
  OrderTerms,
} from '../../api/orders/order_query_schemas';
import type { ContractSigningStatus } from '../../api/orders/contract_signing_client';
import type { CandidateContactPool } from '../../api/scheduling/candidate_contact_pool_client';
import type { SchedulePrecisionResult } from '../../api/scheduling/schedule_precision_client';
import type { ActiveWaitingDepositPlan } from '../../api/scheduling/waiting_deposit_lock_client';
import {
  ORDERS_TYPED_PROJECTION_UNAVAILABLE,
  formatServiceRange,
  type OrderSummaryCardViewModel,
} from './order_summary_adapter';

const unavailable = (scope: string) =>
  `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（${scope}）`;

const readableCandidateReason = (reason: string | null): string | null => {
  const canonical = reason?.trim() ?? '';
  if (canonical.length === 0) return null;
  return /^[?\uFFFD]+$/u.test(canonical) ? '原因文字無法辨識' : canonical;
};

const candidateInformationStatusLabel = (status: string | null | undefined): string => ({
  queued: '已排入，等待處理',
  pending: '已排入，等待處理',
  sent: 'LINE 已接受發送',
  manually_confirmed: '已人工確認送達',
  retryable_failed: '暫時失敗，等待重試',
  failed: '發送失敗',
  cancelled: '已取消',
}[status ?? ''] ?? (status ? '狀態待確認' : '尚未建立'));

const customerProfilesStatusLabel = (status: string | null | undefined): string | null => status === null || status === undefined
  ? null
  : ({
      pending: '等待排入',
      projected: '已排入發送',
      failed: '發送失敗',
      cancelled: '已取消',
      manually_confirmed: '已人工確認送達',
    }[status] ?? '狀態待確認');

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
  candidateId: number;
  staffId: number;
  staffName: string;
  serviceStartDate: string;
  serviceEndDate: string;
  serviceRange: string;
  contactStatus: 'active' | 'selected' | 'withdrawn';
  info1Status: string;
  info1StatusLabel: string;
  info2Status: string;
  info2StatusLabel: string;
  willingness: 'pending' | 'willing' | 'unwilling';
  willingnessLabel: string;
  reason: string | null;
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
  customerProfilesStatus: string | null;
  customerProfilesStatusLabel: string | null;
  candidatePool: CandidatePoolItemViewModel[];
  assignmentSegments: AssignmentSegmentViewModel[];
  serviceTimeText: string;
  requiresCookingText: string;
  waitingLockAcquired: boolean;
  waitingLockText: string;
  planSegments: NonNullable<ActiveWaitingDepositPlan['segments']>;
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
  staffContractSigned: boolean;
  staffContractSignedText: string;
  depositSettled: boolean | null;
  depositSettledText: string;
  clientContractSigned: boolean;
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
  precision?: SchedulePrecisionResult | null;
}): ServiceDateConfirmationDrawerViewModel {
  const { caseNo, actualStart, calendarDetail, orderDetail, precision } = params;
  const actualStartDate = actualStart?.current_actual_start_date ?? '—';
  return {
    caseNo,
    actualStartDate,
    hasActualStartDate: actualStart?.current_actual_start_date !== null && actualStart !== null && actualStart !== undefined,
    restDaysSummary: orderDetail?.custom_rest_dates ?? unavailable('排休摘要'),
    serviceMode: calendarDetail?.service_mode ?? unavailable('排班模式'),
    serviceRangeText: precision
      ? `${precision.actual_start_date} ~ ${precision.actual_end_date}`
      : orderDetail
      ? formatServiceRange(orderDetail.start_date, orderDetail.end_date)
      : unavailable('約定服務起訖日'),
    contractedServiceDays: orderDetail?.service_days ?? null,
    calculatedServiceDaysText: precision
      ? `${precision.actual_work_days_count} 天（目標 ${precision.target_service_days} 天）`
      : unavailable('精算服務天數'),
    restDaysCountText: precision ? `${precision.rest_days_count} 天` : unavailable('順延天數'),
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
  candidateContactPool?: CandidateContactPool | null;
  activePlan?: ActiveWaitingDepositPlan | null;
  customerDecision?: 'pending' | 'accepted' | 'declined' | 'contact_requested' | null;
  customerProfilesStatus?: string | null;
  terms?: OrderTerms | null;
}): MatchingWorkbenchDrawerViewModel {
  const { caseNo, assignmentPlan, candidateContactPool, activePlan, customerDecision, customerProfilesStatus, terms } = params;
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
    planId: activePlan ? String(activePlan.planId) : '尚無進行中的媒合方案',
    status: customerDecision === 'accepted' || activePlan?.status === 'accepted'
      ? '已接受'
      : activePlan?.status === 'proposed' ? '提案中' : '無進行中方案',
    customerProfilesStatus: customerProfilesStatus ?? null,
    customerProfilesStatusLabel: customerProfilesStatusLabel(customerProfilesStatus),
    candidatePool: (candidateContactPool?.candidates ?? []).map((candidate) => ({
      candidateId: candidate.id,
      staffId: candidate.staff_id,
      staffName: candidate.staff_name,
      serviceStartDate: candidate.service_start_date,
      serviceEndDate: candidate.service_end_date,
      serviceRange: `${candidate.service_start_date} ~ ${candidate.service_end_date}`,
      contactStatus: candidate.status,
      info1Status: candidate.information['1']?.status ?? '尚未建立',
      info1StatusLabel: candidateInformationStatusLabel(candidate.information['1']?.status),
      info2Status: candidate.information['2']?.status ?? '尚未建立',
      info2StatusLabel: candidateInformationStatusLabel(candidate.information['2']?.status),
      willingness: candidate.willingness,
      willingnessLabel: candidate.willingness === 'willing'
        ? '願意'
        : candidate.willingness === 'unwilling' ? '不願意' : '待回覆',
      reason: readableCandidateReason(candidate.reason),
    })),
    assignmentSegments,
    serviceTimeText: serviceTimeText(terms),
    requiresCookingText: terms?.terms.requires_cooking === true
      ? '需要下廚'
      : terms?.terms.requires_cooking === false ? '不需下廚' : '資料待補正（下廚料理條款）',
    waitingLockAcquired: activePlan?.activeLockId !== null && activePlan?.activeLockId !== undefined,
    waitingLockText: assignmentSegments.length > 0
      ? '等待訂金鎖已轉換為正式排班'
      : activePlan?.activeLockId
      ? `已取得等待訂金鎖 #${activePlan.activeLockId}`
      : activePlan ? '目前尚未取得等待訂金鎖' : '目前沒有可建立鎖定的進行中媒合方案',
    planSegments: activePlan?.segments ?? [],
  };
}

function serviceTimeText(terms?: OrderTerms | null): string {
  const time = terms?.terms.service_time;
  if (!time || time.start_time === null || time.end_time === null || time.end_day_offset === null) {
    return '資料待補正（服務時段三欄）';
  }
  return `${time.start_time} ~ ${time.end_time}（${time.end_day_offset === 0 ? '同日' : '跨日'}）`;
}

export function adaptOrderTermsContractDrawer(params: {
  caseNo: string;
  terms?: OrderTerms | null;
  completion?: ContractCompletion | null;
  signing?: ContractSigningStatus | null;
  summary?: OrderSummaryCardViewModel | null;
  orderDetail?: OrderDetail | null;
}): OrderTermsContractDrawerViewModel {
  const { caseNo, terms, completion, signing, summary, orderDetail } = params;
  const requiresCooking = terms?.terms.requires_cooking;
  const floorFee = terms?.terms.floor_fee_ntd ?? orderDetail?.floor_fee ?? null;
  const contractAmount = summary?.contractAmount ?? null;
  const depositSettled = completion?.deposit_settled ?? null;
  const signedStaffSegments = signing?.staff_segments.filter((segment) => segment.signed_received).length ?? 0;
  const staffSegmentCount = signing?.staff_segments.length ?? 0;
  const staffContractSigned = staffSegmentCount > 0 && signedStaffSegments === staffSegmentCount;
  const clientContractSigned = signing?.client_signed_received ?? false;
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
    staffContractSigned,
    staffContractSignedText: staffSegmentCount === 0
      ? '尚無月嫂契約分段'
      : staffContractSigned ? '✅ 全部分段已簽回' : `⏳ 已簽回 ${signedStaffSegments}/${staffSegmentCount} 段`,
    depositSettled,
    depositSettledText:
      depositSettled === null ? unavailable('客戶定金核銷') : depositSettled ? '✅ 已核銷' : '⏳ 待核銷',
    clientContractSigned,
    clientContractSignedText: clientContractSigned
      ? '✅ 客戶契約已簽回'
      : signing?.client_document_sent ? '⏳ 已寄送，待客戶簽回' : '尚未寄送客戶契約',
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
