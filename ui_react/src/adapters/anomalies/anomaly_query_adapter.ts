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

const ANOMALY_TITLES: Readonly<Record<string, string>> = {
  'SCHEDULE-001': '假日排班尚未確認',
  'SCHEDULE-002': '已替換排班待確認',
  'SCHEDULE-003': '月嫂排班時間重疊',
  'SCHEDULE-005': '假日服務意願與排班衝突',
  'SCHEDULE-006': '正式服務日期與排班不一致',
  'ORDER-001': '尚未聯繫候選月嫂',
  'ORDER-002': '願意接案的月嫂尚待後續聯繫',
  'ORDER-003': '候選月嫂尚未回覆意願',
  'ORDER-004': '媒合方案尚待定案',
  'BECLASS-001': '客戶尚未完成 BeClass 資料',
  'IMPORT-001': '匯入資料格式待修正',
  'IMPORT-003': 'BeClass 身分對應待確認',
  'IMPORT-004': 'HCM 匯入待人工確認',
  'HISTORICAL-ORDER-001': '歷史訂單匯入待人工確認',
  'finance_import_manual_review': '銀行流水待人工確認',
  'LINE-001': '客戶尚未完成 LINE 綁定',
  'LINE-005': '月嫂尚未完成 LINE 綁定',
  'LINE-006': 'LINE 通知發送待確認',
  'PAYOUT-003': '月嫂收款資料待補正',
  'GOVSUB-006': '政府補助溢撥待處理',
  'CLIENTREFUND-001': '客戶退款退匯待處理',
  'RECEIVABLE-001': '客戶應付款已逾期',
  'CLIENTPAYABLE-001': '客戶退款／調整應付已逾期',
  'RETURN-001': '政府補助退還款已逾期',
};

const ANOMALY_DESCRIPTIONS: Readonly<Record<string, string>> = {
  'RECEIVABLE-001': '列出本案每筆逾期應收與金額；所有同碼逾期應收餘額歸零後才解除。',
  'CLIENTPAYABLE-001': '列出本案每筆逾期退款／調整應付與金額；所有同碼逾期義務餘額歸零後才解除。',
  'RETURN-001': '列出本案每筆逾期補助退還義務與金額；不得與一般客戶退款互抵。',
};

function anomalyTitle(code: string, category: AnomalyDomainCategory): string {
  return ANOMALY_TITLES[code] ?? `${category}待處理事項`;
}

function anomalySubject(identity: string, category: AnomalyDomainCategory): string {
  const normalized = identity.trim();
  const staffMatch = /^staff:(\d+)$/i.exec(normalized);
  if (staffMatch) return `月嫂 #${staffMatch[1]}`;
  const caseMatch = /^case:(.+)$/i.exec(normalized);
  if (caseMatch) return `案件 ${caseMatch[1]}`;
  if (/^\d{9}$/.test(normalized)) return `案件 ${normalized}`;
  if (/^finance-import-row:/i.test(normalized)) return '銀行流水匯入資料';
  if (/^beclass-counterpart:/i.test(normalized)) return 'BeClass 對應資料';
  if (/^schedule:/i.test(normalized)) return '排班資料';
  return `${category}相關資料`;
}

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
  issueKey?: string;
  sourceIdentity: string;
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
    case 'client_receivable':
    case 'client_payable':
    case 'client_subsidy_return':
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
    case 'beclass_client':
    case 'beclass_staff':
      return 'BeClass 匯入';
    case 'historical_orders':
    case 'historical_order':
    case 'historical':
      return '歷史訂單匯入';
    case 'finance':
    case 'finance_import':
      return '財務匯入';
    default:
      return '其他匯入';
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
      return '狀態待確認';
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

  const category = dto.definition_code === 'HISTORICAL-ORDER-001'
    ? '匯入資料'
    : mapDomainToCategory(dto.source_domain);
  const title = anomalyTitle(dto.definition_code, category);
  const relatedEntity = ['RECEIVABLE-001', 'CLIENTPAYABLE-001', 'RETURN-001'].includes(dto.definition_code)
    ? `案件 ${dto.source_identity}`
    : anomalySubject(dto.source_identity, category);

  return {
    id: dto.fingerprint,
    fingerprint: dto.fingerprint,
    issueKey: dto.issue_key,
    sourceIdentity: dto.source_identity,
    code: dto.definition_code,
    title,
    severity: severityLabel,
    severityClass,
    status: statusLabel,
    rawSeverity: dto.severity,
    rawWorkflowStatus: dto.workflow_status,
    rawDomain: dto.source_domain,
    category,
    relatedEntity,
    description: ANOMALY_DESCRIPTIONS[dto.definition_code]
      ?? `請核對${relatedEntity}的目前資料與可採取的處理方式。`,
    suggestedAction: dto.definition_code === 'HISTORICAL-ORDER-001'
      ? '開啟處理方式，上傳只含此 review 對應列的更正工作簿。'
      : '開啟詳情查看可執行的處置。',
    rootEvidence: `影響對象：${relatedEntity}`,
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
  const maskedSubject = (() => {
    const value = dto.masked_subject.trim();
    if (!value || value.toLowerCase() === 'masked') return '資料內容已遮罩';
    if (/^finance-row-/i.test(value)) return '銀行流水資料';
    if (/^client-/i.test(value)) return '客戶資料';
    if (/^staff-/i.test(value)) return '月嫂資料';
    if (/^hcm-/i.test(value)) return '匯入資料';
    return value;
  })();
  return {
    occurrenceIdentity: dto.occurrence_identity,
    owningLane: dto.owning_lane,
    laneLabel: mapImportWarningLaneLabel(dto.owning_lane),
    logicalCode: dto.logical_code,
    fieldPath: dto.field_path,
    maskedSubject,
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
