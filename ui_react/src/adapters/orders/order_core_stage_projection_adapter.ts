/**
 * File: order_core_stage_projection_adapter.ts
 * Description: 將正式十三核心階段 response 映射為 Beta 唯讀工作台模型，並驗證 query/result 一致性。
 */
import type { OrderCoreStageProjectionQueryParams } from '../../api/orders/order_core_stage_projection_client';
import {
  substatusCodesForStage,
  type CoreStageBranchType,
  type CoreStageCode,
  type CoreStageCounts,
  type CoreStageProjection,
  type CoreStageSubstatusCode,
  type OrderCoreStageTimeline,
  type OrderCoreStageTimelinePage,
} from '../../api/orders/order_core_stage_projection_schemas';

export const ORDER_CORE_STAGE_PROJECTION_UNAVAILABLE =
  '正式十三階段查詢失敗；此頁不會改用舊投影或前端推導。';

export interface CoreStageDefinition {
  ordinal: number;
  code: CoreStageCode;
  shortLabel: string;
  label: string;
  ownerLabel: string;
}

export const CORE_STAGE_DEFINITIONS: readonly CoreStageDefinition[] = [
  { ordinal: 1, code: 'intake_validation', shortLabel: '進件', label: '進件與資料完整性驗證', ownerLabel: 'Case Import / Orders' },
  { ordinal: 2, code: 'matching_pool', shortLabel: '候選池', label: '建立候選月嫂池', ownerLabel: 'Assignments / Scheduling' },
  { ordinal: 3, code: 'caregiver_line_delivery', shortLabel: '詢問月嫂', label: '詢問月嫂接案意願', ownerLabel: 'Assignments / LINE Delivery' },
  { ordinal: 4, code: 'caregiver_willingness_reply', shortLabel: '等待回覆', label: '等待月嫂意願回覆', ownerLabel: 'Assignments / LINE' },
  { ordinal: 5, code: 'formal_recommendation', shortLabel: '客戶確認', label: '推薦月嫂給客戶確認', ownerLabel: 'Assignments / Customer Decision' },
  { ordinal: 6, code: 'caregiver_contract', shortLabel: '月嫂契約', label: '月嫂契約簽署', ownerLabel: 'Contract Signing' },
  { ordinal: 7, code: 'deposit_settlement', shortLabel: '定金', label: '客戶定金核銷', ownerLabel: 'Client Finance' },
  { ordinal: 8, code: 'client_contract', shortLabel: '客戶契約', label: '客戶契約簽署', ownerLabel: 'Contract Signing / Orders' },
  { ordinal: 9, code: 'confirmed_service_dates', shortLabel: '日期確認', label: '正式服務日期確認', ownerLabel: 'Orders / Scheduling' },
  { ordinal: 10, code: 'formal_service', shortLabel: '排班/服務', label: '正式排班與服務履約', ownerLabel: 'Scheduling / Orders' },
  { ordinal: 11, code: 'service_completion', shortLabel: '完工', label: '完工／服務完成確認', ownerLabel: 'Orders' },
  { ordinal: 12, code: 'client_settlement', shortLabel: '客戶結算', label: '客戶端結算', ownerLabel: 'Client Finance' },
  { ordinal: 13, code: 'staff_payout', shortLabel: '月嫂結算', label: '月嫂端結算', ownerLabel: 'Staff Payables' },
];

const SUBSTATUS_LABELS: Readonly<Record<CoreStageSubstatusCode, string>> = {
  intake_pending: '待進件', intake_in_progress: '進件處理中', intake_blocked: '進件阻塞', data_complete: '資料完整', intake_unavailable: '進件資料不可用',
  candidate_pool_pending: '待建候選池', candidate_pool_building: '候選池建立中', candidate_pool_blocked: '候選池阻塞', candidate_pool_ready: '候選池完成', candidate_pool_unavailable: '候選池不可用',
  contact_pending: '待詢問', contact_in_progress: '詢問送出中', contact_blocked: '詢問阻塞', contact_completed: '已完成詢問', contact_unavailable: '詢問資料不可用',
  reply_pending: '待回覆', reply_partial: '部分回覆', reply_blocked: '回覆阻塞', reply_complete: '回覆完成', reply_unavailable: '回覆資料不可用',
  recommendation_pending: '待推薦', recommendation_in_progress: '推薦處理中', recommendation_blocked: '推薦阻塞', recommendation_completed: '已完成推薦', recommendation_unavailable: '推薦資料不可用',
  caregiver_contract_pending: '待月嫂簽約', caregiver_contract_signing: '月嫂簽約中', caregiver_contract_blocked: '月嫂簽約阻塞', caregiver_contract_completed: '月嫂已簽約', caregiver_contract_unavailable: '月嫂契約不可用',
  deposit_pending: '待定金', deposit_in_progress: '定金核銷中', deposit_blocked: '定金阻塞', deposit_settled: '定金已核銷', deposit_unavailable: '定金資料不可用',
  client_contract_pending: '待客戶簽約', client_contract_signing: '客戶簽約中', client_contract_blocked: '客戶簽約阻塞', client_contract_completed: '客戶已簽約', client_contract_unavailable: '客戶契約不可用',
  date_confirmation_pending: '待日期確認', date_confirmation_in_progress: '日期確認中', date_confirmation_blocked: '日期確認阻塞', date_confirmed: '日期已確認', date_confirmation_unavailable: '日期資料不可用',
  waiting_to_start: '待開工', service_in_progress: '服務進行中', service_blocked: '服務阻塞', service_period_completed: '服務期間已完成', service_schedule_unavailable: '排班資料不可用',
  completion_pending: '待完工確認', completion_in_progress: '完工確認中', completion_blocked: '完工確認阻塞', completion_confirmed: '已確認完工', completion_record_missing: '完工紀錄缺漏',
  client_settlement_pending: '待客戶結算', client_settlement_in_progress: '客戶結算中', client_balance_open: '客戶款項未結', client_settled: '客戶已結清', client_settlement_unavailable: '客戶結算不可用',
  staff_settlement_pending: '待月嫂結算', staff_settlement_in_progress: '月嫂結算中', staff_payable_open: '月嫂應付款未結', staff_settled: '月嫂已結清', staff_settlement_unavailable: '月嫂結算不可用',
};

const BRANCH_LABELS: Readonly<Record<CoreStageBranchType, string>> = {
  normal: '正常訂單',
  historical: '歷史訂單',
  cancelled: '取消訂單',
};

export class OrderCoreStageProjectionAdapterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OrderCoreStageProjectionAdapterError';
  }
}

export interface CoreStageNoticeViewModel {
  id: string;
  stageLabel: string;
  message: string;
}

export interface CoreStageCaseViewModel {
  id: string;
  lifecycleStatus: string;
  branchType: CoreStageBranchType;
  branchLabel: string;
  baseRevision: number;
  currentStage: CoreStageProjection | null;
  statusLabel: string;
  blockers: readonly CoreStageNoticeViewModel[];
  warnings: readonly CoreStageNoticeViewModel[];
  sourceProjectionDigest: string;
}

export interface CoreStageSubstatusOptionViewModel {
  code: CoreStageSubstatusCode;
  label: string;
  count: number;
}

export interface OrderCoreStageWorkbenchViewModel {
  items: readonly CoreStageCaseViewModel[];
  stageCounts: CoreStageCounts;
  substatusOptions: readonly CoreStageSubstatusOptionViewModel[];
  nextCursor: string | null;
  etag: string;
}

export function coreStageDefinition(code: CoreStageCode): CoreStageDefinition {
  const definition = CORE_STAGE_DEFINITIONS.find((item) => item.code === code);
  if (!definition) throw new OrderCoreStageProjectionAdapterError(`未知核心階段：${code}`);
  return definition;
}

export function coreStageSubstatusLabel(code: CoreStageSubstatusCode): string {
  return SUBSTATUS_LABELS[code];
}

export function coreStageBranchLabel(branch: CoreStageBranchType): string {
  return BRANCH_LABELS[branch];
}

function currentStageForTimeline(timeline: OrderCoreStageTimeline): CoreStageProjection | null {
  if (timeline.current_core_stage_code === null) return null;
  const current = timeline.core_stages.find(
    (stage) => stage.code === timeline.current_core_stage_code,
  );
  if (!current) {
    throw new OrderCoreStageProjectionAdapterError(
      `案件 ${timeline.case_no} 的目前核心階段不存在於正式投影。`,
    );
  }
  return current;
}

function noticesForTimeline(
  timeline: OrderCoreStageTimeline,
  kind: 'blockers' | 'warnings',
): readonly CoreStageNoticeViewModel[] {
  return timeline.core_stages.flatMap((stage) => stage[kind].map((notice) => ({
    id: `${stage.code}:${notice.code}`,
    stageLabel: stage.label,
    message: notice.message,
  })));
}

function adaptTimeline(timeline: OrderCoreStageTimeline): CoreStageCaseViewModel {
  const currentStage = currentStageForTimeline(timeline);
  return {
    id: timeline.case_no,
    lifecycleStatus: timeline.lifecycle_status,
    branchType: timeline.branch_type,
    branchLabel: coreStageBranchLabel(timeline.branch_type),
    baseRevision: timeline.base_revision,
    currentStage,
    statusLabel: currentStage
      ? coreStageSubstatusLabel(currentStage.substatus_code)
      : coreStageBranchLabel(timeline.branch_type),
    blockers: noticesForTimeline(timeline, 'blockers'),
    warnings: noticesForTimeline(timeline, 'warnings'),
    sourceProjectionDigest: timeline.source_projection_digest,
  };
}

function sameKeys(left: readonly string[], right: readonly string[]): boolean {
  const normalizedLeft = [...left].sort();
  const normalizedRight = [...right].sort();
  return normalizedLeft.length === normalizedRight.length
    && normalizedLeft.every((value, index) => value === normalizedRight[index]);
}

function validateQueryResult(
  page: OrderCoreStageTimelinePage,
  query: OrderCoreStageProjectionQueryParams,
): void {
  if (query.branch_type !== undefined) {
    const mismatch = page.items.find((item) => item.branch_type !== query.branch_type);
    if (mismatch) {
      throw new OrderCoreStageProjectionAdapterError(
        `案件 ${mismatch.case_no} 不符合要求的 ${query.branch_type} 支線。`,
      );
    }
  }

  if (query.stage === undefined) {
    if (Object.keys(page.substatus_counts).length !== 0) {
      throw new OrderCoreStageProjectionAdapterError('未指定核心階段時不得回傳子狀態 counts。');
    }
    return;
  }

  const expectedSubstatuses = substatusCodesForStage(query.stage);
  if (!sameKeys(Object.keys(page.substatus_counts), expectedSubstatuses)) {
    throw new OrderCoreStageProjectionAdapterError('子狀態 counts 未完整對應要求的核心階段。');
  }

  for (const item of page.items) {
    const current = currentStageForTimeline(item);
    if (current?.code !== query.stage) {
      throw new OrderCoreStageProjectionAdapterError(
        `案件 ${item.case_no} 不符合要求的核心階段。`,
      );
    }
    if (query.substatus_code !== undefined && current.substatus_code !== query.substatus_code) {
      throw new OrderCoreStageProjectionAdapterError(
        `案件 ${item.case_no} 不符合要求的核心階段子狀態。`,
      );
    }
  }
}

export function adaptOrderCoreStageTimelinePage(
  page: OrderCoreStageTimelinePage,
  query: OrderCoreStageProjectionQueryParams,
): OrderCoreStageWorkbenchViewModel {
  validateQueryResult(page, query);
  const substatusOptions = query.stage === undefined
    ? []
    : substatusCodesForStage(query.stage).map((code) => ({
      code,
      label: coreStageSubstatusLabel(code),
      count: page.substatus_counts[code] ?? 0,
    }));

  return {
    items: page.items.map(adaptTimeline),
    stageCounts: page.stage_counts,
    substatusOptions,
    nextCursor: page.next_cursor,
    etag: page.etag,
  };
}
