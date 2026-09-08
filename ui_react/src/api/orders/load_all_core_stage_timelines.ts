import { orderCoreStageProjectionClient, type OrderCoreStageProjectionQueryParams, type OrderCoreStageProjectionQueryOptions } from './order_core_stage_projection_client';
import type { OrderCoreStageTimelinePage } from './order_core_stage_projection_schemas';

/** Publish only a complete, consistently ordered result. */
export async function loadAllCoreStageTimelines(
  query: OrderCoreStageProjectionQueryParams,
  options?: OrderCoreStageProjectionQueryOptions,
): Promise<OrderCoreStageTimelinePage> {
  let first: OrderCoreStageTimelinePage | undefined;
  let cursor = query.after_case_no;
  let previousKey = cursor?.toLowerCase();
  const items: OrderCoreStageTimelinePage['items'] = [];
  while (true) {
    options?.signal?.throwIfAborted();
    const page = await orderCoreStageProjectionClient.getCoreStageTimelines({ ...query, after_case_no: cursor }, options);
    if (!first) first = page;
    else if (JSON.stringify(page.stage_counts) !== JSON.stringify(first.stage_counts)
      || JSON.stringify(page.substatus_counts) !== JSON.stringify(first.substatus_counts)
      || JSON.stringify(page.historical_lifecycle_counts) !== JSON.stringify(first.historical_lifecycle_counts)) {
      throw new Error('查詢期間訂單統計已變動，請重新讀取清單。');
    }
    for (const item of page.items) {
      const key = item.case_no.toLowerCase();
      if (previousKey !== undefined && key <= previousKey) throw new Error('訂單分頁重複或順序不一致。');
      previousKey = key;
      items.push(item);
    }
    if (page.next_cursor === null) return { ...first, items, next_cursor: null };
    if (page.items.length === 0 || page.next_cursor !== page.items.at(-1)?.case_no) {
      throw new Error('訂單分頁游標無法繼續。');
    }
    cursor = page.next_cursor;
  }
}
