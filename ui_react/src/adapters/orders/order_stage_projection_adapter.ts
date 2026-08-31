/**
 * File: order_stage_projection_adapter.ts
 * Description: 將已驗證的 Orders stage projection 映射到 Summary 可見案件，拒絕缺漏與重複 identity。
 */
import type { OrderSummaryPage } from '../../api/orders/order_query_schemas';
import type {
  OrderOperationalTimeline,
  OrderOperationalTimelinePage,
  StageProjection,
} from '../../api/orders/order_stage_projection_schemas';

export const ORDER_STAGE_PROJECTION_UNAVAILABLE = '訂單階段資料載入失敗，請重新載入。';

export class OrderStageProjectionIdentityError extends Error {
  constructor(message = 'Orders stage projection 與摘要案件識別不一致。') {
    super(message);
    this.name = 'OrderStageProjectionIdentityError';
  }
}

export function indexOperationalTimelines(
  page: OrderOperationalTimelinePage,
  summary: OrderSummaryPage,
): ReadonlyMap<string, OrderOperationalTimeline> {
  const expected = summary.items.map((item) => item.case_no);
  if (new Set(expected).size !== expected.length) throw new OrderStageProjectionIdentityError('摘要案件識別重複。');
  const expectedSet = new Set(expected);
  const seen = new Set<string>();
  for (const item of page.items) {
    if (seen.has(item.case_no)) throw new OrderStageProjectionIdentityError('stage projection 案件識別重複。');
    seen.add(item.case_no);
  }
  if (expected.some((caseNo) => !seen.has(caseNo))) {
    throw new OrderStageProjectionIdentityError('stage projection 缺少摘要案件。');
  }
  if (page.next_cursor !== null && page.items.length === 0) {
    throw new OrderStageProjectionIdentityError('空頁不得帶有 next_cursor。');
  }
  return new Map(
    page.items
      .filter((item) => expectedSet.has(item.case_no))
      .map((item) => [item.case_no, item]),
  );
}

export function stageCount(page: OrderOperationalTimelinePage, code: string): number | null {
  if (!(code in page.stage_counts)) return null;
  return page.stage_counts[code as keyof typeof page.stage_counts];
}

export function stageByCode(timeline: OrderOperationalTimeline, code: string): StageProjection | null {
  return timeline.stages.find((stage) => stage.code === code) ?? null;
}

const STATUS_LABELS: Record<string, string> = {
  not_started: '尚未開始',
  in_progress: '進行中',
  blocked: '受阻',
  completed: '已完成',
  unavailable: '待補正式根事實',
};

const AVAILABILITY_REASON_LABELS: Record<string, string> = {
  case_import_and_terms_lineage_missing: '請先完成進件匯入與訂單條款',
  matching_plan_lineage_missing: '尚未形成媒合方案',
  formal_recommendation_projection_missing: '尚未形成正式推薦紀錄',
  contract_and_deposit_lineage_missing: '尚未形成雙邊簽約與定金紀錄',
  formal_assignment_lineage_missing: '尚未形成正式指派',
  confirmed_service_date_lineage_missing: '尚未形成確認服務日期版本',
  official_service_period_missing: '正式服務日或服務時段尚未完整',
  service_completion_projection_missing: '尚未完成服務結案',
  obligation_projection_missing: '尚未形成結清義務',
  contract_completion_lineage_missing: '尚未完成契約簽回',
  deposit_obligation_missing: '尚未形成定金義務',
  line_timeline_out_of_scope: '請至 LINE 專區查閱通知歷程',
  matching_contact_lineage_missing: '尚未形成月嫂聯繫紀錄',
  matching_willingness_lineage_missing: '尚未形成月嫂意願紀錄',
  staff_contract_signing_lineage_missing: '尚未形成月嫂簽回紀錄',
  client_contract_signing_lineage_missing: '尚未形成客戶簽回紀錄',
};

export function stageStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? `未知狀態：${status}`;
}

export function stageAvailabilityLabel(value: string | null): string | null {
  if (!value) return null;
  return AVAILABILITY_REASON_LABELS[value]
    ?? (value.endsWith('_missing') ? '尚未形成正式根事實' : '請依目前階段補齊正式根事實');
}

export function formatProjectionTimestamp(value: string | null): string {
  if (!value) return '尚無事件時間';
  return value;
}
