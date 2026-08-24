/**
 * File: anomaly_query_adapter.ts
 * Description: 將 Anomalies 唯讀 DTO 轉為安全的頁面模型。
 */

import type {
  AnomalySummaryView,
  AnomalySeverity,
  AnomalyWorkflowStatus,
  StaffCalendarNavigationView,
  ImportWarningTaskView,
  ImportWarningTrackingStatus,
  ImportWarningNavigationAction,
  AnomalyDetailView,
  ImportWarningReferralView,
} from '../../api/anomalies/anomaly_query_schemas';

// ============================================================================
// 1. Domain Category Types & Constants
// ============================================================================

export type AnomalyDomainCategory =
  | '全部'
  | '匯入資料'
  | '媒合推播'
  | '排班調度'
  | '客戶帳務'
  | '月嫂薪資'
  | '政府補助'
  | '其他';

export type CategoryTabKey = AnomalyDomainCategory;

export const CATEGORY_TAB_KEYS: readonly CategoryTabKey[] = [
  '全部',
  '匯入資料',
  '媒合推播',
  '排班調度',
  '客戶帳務',
  '月嫂薪資',
  '政府補助',
  '其他',
] as const;

// ============================================================================
// 2. View Model Interfaces
// ============================================================================

export interface AnomalyMetadataViewModel {
  sourceDomain: string;
  sourceVersion: number;
  workflowVersion: number;
  predicateActive: boolean;
}

export interface AnomalySummaryViewModel {
  id: string; // fingerprint identity
  fingerprint: string;
  code: string; // definition_code
  title: string;
  severity: string; // "🔴 嚴重阻擋" | "🟡 警示待補"
  severityClass: 'critical' | 'warning';
  status: string; // "🟡 待處理" | "🔵 已認領" | "✅ 已排除"
  rawSeverity: AnomalySeverity;
  rawWorkflowStatus: AnomalyWorkflowStatus;
  rawDomain: string;
  category: AnomalyDomainCategory;
  relatedEntity: string;
  description: string;
  suggestedAction: string;
  rootEvidence: string;
  staffCalendarNavigation: StaffCalendarNavigationView | null;
  metadata: AnomalyMetadataViewModel;
}

export interface ImportWarningTaskViewModel {
  occurrenceIdentity: string;
  owningLane: string;
  laneLabel: string;
  logicalCode: string;
  fieldPath: string;
  maskedSubject: string;
  issueCodes: string[];
  status: ImportWarningTrackingStatus;
  statusLabel: string;
  version: number;
  evidenceReference: string | null;
  displayMessage: string;
  navigationAction: ImportWarningNavigationAction | null;
}

export interface AnomalyKPIViewModel {
  criticalCount: number;
  warningCount: number;
  openCount: number;
  claimedCount: number;
}

export interface AnomalyTimelineEventViewModel {
  action: string;
  expectedWorkflowVersion: number;
  resultingWorkflowVersion: number;
  createdAt: string;
}

export interface AnomalyDetailViewModel {
  summary: AnomalySummaryViewModel;
  timeline: AnomalyTimelineEventViewModel[];
  timelineAvailable: boolean;
  actionsAvailable: boolean;
}

export interface ImportWarningReferralViewModel {
  occurrenceIdentity: string;
  expectedVersion: number;
  owningLane: string;
  logicalCode: string;
  fieldPath: string;
  maskedSubject: string;
  displayMessage: string;
  navigationAction: 'hcm_import_center';
  actionKind: 'owner_preview_apply' | 'wait_for_counterpart';
  targetCommand: 'preview_hcm_resubmission' | null;
}

// ============================================================================
// 3. Mapping & Transformation Functions
// ============================================================================

/**
 * 將後端 source_domain 對應至前端介面之領域分類
 */
export function mapDomainToCategory(domain: string | null | undefined): AnomalyDomainCategory {
  if (!domain) return '其他';
  const normalized = domain.trim().toLowerCase();

  switch (normalized) {
    case 'case_import':
    case 'finance_import':
      return '匯入資料';

    case 'line':
    case 'line_integration':
    case 'matching':
      return '媒合推播';

    case 'scheduling':
    case 'assignments':
      return '排班調度';

    case 'client_finance':
      return '客戶帳務';

    case 'staff_payables':
    case 'payroll':
      return '月嫂薪資';

    case 'government_subsidy':
      return '政府補助';

    default:
      return '其他';
  }
}

/**
 * 將匯入警示通道 (owning_lane) 對應至中文標籤
 */
export function mapImportWarningLaneLabel(lane: string | null | undefined): string {
  if (!lane) return '其他匯入';
  const normalized = lane.trim().toLowerCase();

  switch (normalized) {
    case 'hcm':
      return 'HCM 匯入';
    case 'beclass':
    case 'client_beclass':
    case 'staff_beclass':
      return 'BeClass 匯入';
    case 'historical_orders':
    case 'historical_order':
    case 'historical':
      return '歷史訂單匯入';
    case 'finance':
    case 'finance_import':
      return '財務匯入';
    default:
      return lane.toUpperCase();
  }
}

/**
 * 將匯入警示追蹤狀態對應至中文標籤
 */
export function mapImportWarningStatusLabel(status: ImportWarningTrackingStatus | string): string {
  switch (status) {
    case 'open':
      return '待處理';
    case 'awaiting_external_confirmation':
      return '等待外部確認';
    case 'response_recorded':
      return '已記錄回應';
    case 'reimport_requested':
      return '要求重新匯入';
    case 'closed':
      return '已結案';
    case 'auto_resolved':
      return '自動排除';
    default:
      return String(status);
  }
}

/**
 * 將後端 AnomalySummaryView 轉換為前端 AnomalySummaryViewModel
 */
export function adaptAnomalySummary(dto: AnomalySummaryView): AnomalySummaryViewModel {
  const isBlocking = dto.severity === 'blocking';
  const severityLabel = isBlocking ? '🔴 嚴重阻擋' : '🟡 警示待補';
  const severityClass: 'critical' | 'warning' = isBlocking ? 'critical' : 'warning';

  let statusLabel = '🟡 待處理';
  if (dto.workflow_status === 'claimed') {
    statusLabel = '🔵 已認領';
  } else if (dto.workflow_status === 'resolved') {
    statusLabel = '✅ 已排除';
  }

  return {
    id: dto.fingerprint,
    fingerprint: dto.fingerprint,
    code: dto.definition_code,
    title: '異常偵測項目',
    severity: severityLabel,
    severityClass,
    status: statusLabel,
    rawSeverity: dto.severity,
    rawWorkflowStatus: dto.workflow_status,
    rawDomain: dto.source_domain,
    category: mapDomainToCategory(dto.source_domain),
    relatedEntity: dto.source_identity,
    description: `來源領域：${dto.source_domain}；來源版本：v${dto.source_version}`,
    suggestedAction: '開啟詳情查看可執行的處置。',
    rootEvidence: `來源識別：${dto.source_identity}`,
    staffCalendarNavigation: dto.staff_calendar_navigation ?? null,
    metadata: {
      sourceDomain: dto.source_domain,
      sourceVersion: dto.source_version,
      workflowVersion: dto.workflow_version,
      predicateActive: dto.predicate_active,
    },
  };
}

/**
 * 將後端 ImportWarningTaskView 轉換為前端 ImportWarningTaskViewModel
 */
export function adaptImportWarningTask(dto: ImportWarningTaskView): ImportWarningTaskViewModel {
  return {
    occurrenceIdentity: dto.occurrence_identity,
    owningLane: dto.owning_lane,
    laneLabel: mapImportWarningLaneLabel(dto.owning_lane),
    logicalCode: dto.logical_code,
    fieldPath: dto.field_path,
    maskedSubject: dto.masked_subject,
    issueCodes: Array.isArray(dto.issue_codes) ? [...dto.issue_codes] : [],
    status: dto.tracking_status,
    statusLabel: mapImportWarningStatusLabel(dto.tracking_status),
    version: dto.tracking_version,
    evidenceReference: dto.evidence_reference ?? null,
    displayMessage: dto.display_message,
    navigationAction: dto.navigation_action ?? null,
  };
}

/** 只映射 detail 的 server facts；不把 actor/reason/correlation/raw actions 放進文案。 */
export function adaptAnomalyDetail(dto: AnomalyDetailView): AnomalyDetailViewModel {
  return {
    summary: adaptAnomalySummary(dto.summary),
    timeline: dto.timeline.map((event) => ({
      action: event.action,
      expectedWorkflowVersion: event.expected_workflow_version,
      resultingWorkflowVersion: event.resulting_workflow_version,
      createdAt: event.created_at,
    })),
    timelineAvailable: dto.timeline.length > 0,
    actionsAvailable: dto.available_actions.length > 0,
  };
}

/** 將已封閉的 owning referral 轉成 neutral 導向資料；不啟用 transition。 */
export function adaptImportWarningReferral(
  dto: ImportWarningReferralView
): ImportWarningReferralViewModel {
  return {
    occurrenceIdentity: dto.occurrence_identity,
    expectedVersion: dto.expected_version,
    owningLane: dto.owning_lane,
    logicalCode: dto.logical_code,
    fieldPath: dto.field_path,
    maskedSubject: dto.masked_subject,
    displayMessage: dto.display_message,
    navigationAction: dto.navigation_action,
    actionKind: dto.action_kind,
    targetCommand: dto.target_command,
  };
}

/**
 * 計算異常清單之 KPI 統計摘要
 */
export function calculateAnomalyKPIs(
  anomalies: readonly AnomalySummaryViewModel[] | AnomalySummaryViewModel[]
): AnomalyKPIViewModel {
  let criticalCount = 0;
  let warningCount = 0;
  let openCount = 0;
  let claimedCount = 0;

  for (const anm of anomalies) {
    if (anm.rawSeverity === 'blocking' && anm.rawWorkflowStatus !== 'resolved') {
      criticalCount += 1;
    }
    if (anm.rawSeverity === 'warning' && anm.rawWorkflowStatus !== 'resolved') {
      warningCount += 1;
    }
    if (anm.rawWorkflowStatus === 'open') {
      openCount += 1;
    }
    if (anm.rawWorkflowStatus === 'claimed') {
      claimedCount += 1;
    }
  }

  return {
    criticalCount,
    warningCount,
    openCount,
    claimedCount,
  };
}

/**
 * 依分類標籤與狀態篩選條件過濾異常清單
 */
export function filterAnomalies(
  anomalies: readonly AnomalySummaryViewModel[] | AnomalySummaryViewModel[],
  category: string,
  statusFilter: string
): AnomalySummaryViewModel[] {
  return anomalies.filter((anm) => {
    const matchCategory =
      !category ||
      category === '全部' ||
      category.toLowerCase() === 'all' ||
      anm.category === category;

    const matchStatus =
      !statusFilter ||
      statusFilter === 'all' ||
      statusFilter === '全部' ||
      anm.rawWorkflowStatus === statusFilter;

    return matchCategory && matchStatus;
  });
}
