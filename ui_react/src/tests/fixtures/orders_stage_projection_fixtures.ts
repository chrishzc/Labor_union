/**
 * File: orders_stage_projection_fixtures.ts
 * Description: 提供 Orders 七階段 server projection 的嚴格測試資料。
 */
import type { OrderSummaryPage } from '../../api/orders/order_query_schemas';
import type {
  OrderOperationalTimelinePage,
  StageProjection,
} from '../../api/orders/order_stage_projection_schemas';

const STAGE_CODES = [
  'intake_terms',
  'matching_willingness',
  'client_review',
  'contract_deposit',
  'date_confirmation',
  'active_service',
  'settlement_payout',
] as const;

const CURRENT_STEP_BY_STAGE: Readonly<Record<typeof STAGE_CODES[number], number>> = {
  intake_terms: 1,
  matching_willingness: 2,
  client_review: 5,
  contract_deposit: 6,
  date_confirmation: 9,
  active_service: 10,
  settlement_payout: 11,
};

function lifecycleStatusForStage(stage: typeof STAGE_CODES[number]) {
  if (stage === 'active_service') return '服務中' as const;
  if (stage === 'settlement_payout') return '訂單完成' as const;
  if (stage === 'contract_deposit' || stage === 'date_confirmation') return '訂單成立' as const;
  return '洽談中' as const;
}

function stageProjection(code: typeof STAGE_CODES[number], ordinal: number, currentCode: typeof STAGE_CODES[number]): StageProjection {
  return {
    ordinal,
    code,
    label: code,
    owner: 'fixture-owner',
    status: code === currentCode ? 'in_progress' : 'not_started',
    source: {
      owner: 'fixture-owner',
      identity: `fixture:${code}`,
      version: 1,
    },
    occurred_at: code === currentCode ? '2026-08-21T00:00:00Z' : null,
    blockers: [],
    warnings: [],
    available_actions: [],
    availability_reason: null,
    settlement: [],
  };
}

export function buildOrdersStageProjectionFixture(summary: OrderSummaryPage): OrderOperationalTimelinePage {
  const counts = {
    intake_terms: 0,
    matching_willingness: 0,
    client_review: 0,
    contract_deposit: 0,
    date_confirmation: 0,
    active_service: 0,
    settlement_payout: 0,
  };
  const items = summary.items.map((item, index) => {
    const currentStage: typeof STAGE_CODES[number] = index === 0 ? 'intake_terms' : 'active_service';
    counts[currentStage] += 1;
    return {
      case_no: item.case_no,
      base_revision: index + 1,
      lifecycle_status: lifecycleStatusForStage(currentStage),
      current_stage_code: currentStage,
      current_step_ordinal: CURRENT_STEP_BY_STAGE[currentStage],
      stages: STAGE_CODES.map((code, stageIndex) => stageProjection(code, stageIndex + 1, currentStage)),
      sop_steps: Array.from({ length: 11 }, (_, stepIndex) => ({
        ordinal: stepIndex + 1,
        code: `step_${stepIndex + 1}`,
        label: `步驟 ${stepIndex + 1}`,
        owner: 'fixture-owner',
        status: 'not_started' as const,
        occurred_at: null,
        blockers: [],
        warnings: [],
        available_actions: [],
        availability_reason: null,
      })),
      projection_digest: 'a'.repeat(64),
    };
  });
  return {
    items,
    stage_counts: counts,
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}
