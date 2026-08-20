/**
 * File: order_summary_adapter.ts
 * Description: 將 Orders 摘要轉為不推導階段、結清或推薦狀態的卡片模型。
 */
import type { OrderSummaryItem, OrderSummaryPage } from '../../api/orders/order_query_schemas';

export const ORDERS_TYPED_PROJECTION_UNAVAILABLE = '後端尚未提供 typed projection';

export type WorkflowStage =
  | 'intake_terms'
  | 'matching_willingness'
  | 'client_review'
  | 'contract_deposit'
  | 'date_confirmation'
  | 'active_service'
  | 'settlement_payout';

export interface FilterOption {
  label: string;
  stage: WorkflowStage | '全部';
}

export const ORDER_FILTER_OPTIONS: readonly FilterOption[] = [
  { label: '全部', stage: '全部' },
  { label: '1. 進件與補件', stage: 'intake_terms' },
  { label: '2. 媒合與徵詢意願', stage: 'matching_willingness' },
  { label: '3. 推薦客戶確認', stage: 'client_review' },
  { label: '4. 雙邊簽約定金', stage: 'contract_deposit' },
  { label: '5. 確認實際服務日期', stage: 'date_confirmation' },
  { label: '6. 正式服務中', stage: 'active_service' },
  { label: '7. 完工結案請款', stage: 'settlement_payout' },
];

export interface ServiceTimeTupleViewModel {
  startTime: string;
  endTime: string;
  dayOffset: 0 | 1;
  dailyHours: number;
  formattedText: string;
}

export interface OrderSummaryCardViewModel {
  id: string;
  clientName: string;
  clientPhone: string;
  serviceRange: string;
  serviceDays: number | null;
  serviceDaysLabel: string;
  serviceAddress: string;
  actualStartDate: string | null;
  actualEndDate: string | null;
  orderStatus: string;
  contractAmount: number | null;
  contractAmountFormatted: string;
  depositSettled: null;
  depositSettledText: string;
  assignedDoulaName: string | null;
  assignedDoulaDisplay: string;
  serviceTimeTuple: ServiceTimeTupleViewModel | null;
  requiresCooking: null;
  floorFee: null;
}

export interface OrderSummaryPageViewModel {
  items: OrderSummaryCardViewModel[];
  loadedCount: number;
  nextCursor: string | null;
  etag: string;
}

export function formatServiceRange(startDate: string | null, endDate: string | null): string {
  if (startDate && endDate) return `${startDate} ~ ${endDate}`;
  if (startDate) return `${startDate} 起（訖日未提供）`;
  if (endDate) return `起日未提供 ~ ${endDate}`;
  return '後端未提供約定服務起訖日';
}

export function adaptOrderSummaryItem(item: OrderSummaryItem): OrderSummaryCardViewModel {
  const serviceDays = item.service_days;
  const contractAmount = item.total_employer_self_pay_payable;
  const staffName = item.staff_name?.trim() || null;
  return {
    id: item.case_no,
    clientName: item.client_name,
    clientPhone: `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（聯絡電話）`,
    serviceRange: formatServiceRange(item.start_date, item.end_date),
    serviceDays,
    serviceDaysLabel: serviceDays === null ? ORDERS_TYPED_PROJECTION_UNAVAILABLE : `${serviceDays} 天`,
    serviceAddress: `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（服務地址）`,
    actualStartDate: item.actual_start_date,
    actualEndDate: item.actual_end_date,
    orderStatus: item.order_status,
    contractAmount,
    contractAmountFormatted:
      contractAmount === null ? ORDERS_TYPED_PROJECTION_UNAVAILABLE : `NT$ ${contractAmount.toLocaleString()}`,
    depositSettled: null,
    depositSettledText: `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶款項）`,
    assignedDoulaName: staffName,
    assignedDoulaDisplay:
      staffName ?? `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（正式指派月嫂）`,
    serviceTimeTuple: null,
    requiresCooking: null,
    floorFee: null,
  };
}

export function adaptOrderSummaryPage(page: OrderSummaryPage): OrderSummaryPageViewModel {
  const items = page.items.map(adaptOrderSummaryItem);
  return {
    items,
    loadedCount: items.length,
    nextCursor: page.next_cursor,
    etag: page.etag,
  };
}
