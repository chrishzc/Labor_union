import { describe, expect, it } from 'vitest';
import {
  CORE_STAGE_CODES, OrderCoreStageTimelinePageSchema, substatusCodesForStage,
} from '../../../../../../../api/orders/order_core_stage_projection_schemas';

function page(counts: Record<string, number>) {
  return {
    items: [],
    stage_counts: Object.fromEntries(CORE_STAGE_CODES.map(code => [code, 0])),
    substatus_counts: counts,
    historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 },
    next_cursor: null,
    etag: 'a'.repeat(64),
  };
}

describe('核心階段子狀態計數解碼', () => {
  it('模組可載入，接受空計數及任一完整階段，不要求所有階段同時存在', () => {
    expect(OrderCoreStageTimelinePageSchema.safeParse(page({})).success).toBe(true);
    for (const stage of CORE_STAGE_CODES) {
      const counts = Object.fromEntries(substatusCodesForStage(stage).map(code => [code, 1]));
      expect(OrderCoreStageTimelinePageSchema.safeParse(page(counts)).success).toBe(true);
    }
  });

  it('拒絕未知鍵、缺少子狀態、跨階段混算及負數，保留原閉合契約', () => {
    expect(OrderCoreStageTimelinePageSchema.safeParse(page({ unknown: 0 })).success).toBe(false);
    const stage = CORE_STAGE_CODES.find(code => substatusCodesForStage(code).length > 1)!;
    const keys = substatusCodesForStage(stage);
    expect(OrderCoreStageTimelinePageSchema.safeParse(page({ [keys[0]]: 0 })).success).toBe(false);
    const other = CORE_STAGE_CODES.find(code => code !== stage)!;
    const mixed = Object.fromEntries([...keys, ...substatusCodesForStage(other)].map(code => [code, 0]));
    expect(OrderCoreStageTimelinePageSchema.safeParse(page(mixed)).success).toBe(false);
    const negative = Object.fromEntries(keys.map(code => [code, -1]));
    expect(OrderCoreStageTimelinePageSchema.safeParse(page(negative)).success).toBe(false);
  });
});
