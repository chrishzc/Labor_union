/**
 * File: order_card_projection_adapter.ts
 * Description: 將案件卡片投影映射為業務欄位、定金狀態與精簡來源資訊。
 */
import type {
  OrdersCardAssignmentSegment,
  OrdersCardProjection,
  OrdersCardProjectionField,
} from '../../api/orders/order_card_projection_schemas';

export const ORDERS_CARD_PROJECTION_UNAVAILABLE = '案件資料目前無法取得';

export interface OrdersCardProjectionRowViewModel {
  key: string;
  label: string;
  valueText: string;
  metadataText: string;
  availability: 'available' | 'unavailable' | 'blocked';
}

export interface OrdersCardAssignmentViewModel {
  key: string;
  rows: readonly OrdersCardProjectionRowViewModel[];
}

export interface OrdersCardProjectionViewModel {
  caseNo: string;
  rows: readonly OrdersCardProjectionRowViewModel[];
  depositSettlementState: 'settled' | 'unsettled' | null;
  assignmentSegments: readonly OrdersCardAssignmentViewModel[];
  assignmentSegmentsAvailability: 'available' | 'unavailable' | 'blocked';
  assignmentSegmentsMessage: string;
}

function fieldValueText<T>(field: OrdersCardProjectionField<T>, label: string, render: (value: T) => string): string {
  if (field.availability !== 'available') {
    return field.availability === 'blocked' ? `資料受阻（${label}）` : `資料待補正（${label}）`;
  }
  if (field.value === null) return `尚未登錄（${label}）`;
  return render(field.value);
}

function metadataText<T>(field: OrdersCardProjectionField<T>): string {
  const version = field.source_version ?? '未標記';
  const reason = field.availability_reason ? `；原因：${field.availability_reason}` : '';
  return `資料來源：${field.owner}；版本：${version}${reason}`;
}

function row<T>(key: string, label: string, field: OrdersCardProjectionField<T>, render: (value: T) => string): OrdersCardProjectionRowViewModel {
  return {
    key,
    label,
    valueText: fieldValueText(field, label, render),
    metadataText: metadataText(field),
    availability: field.availability,
  };
}

function optionalHistoricalRow<T>(
  key: string,
  label: string,
  field: OrdersCardProjectionField<T> | undefined,
  render: (value: T) => string,
): readonly OrdersCardProjectionRowViewModel[] {
  if (!field || field.source_version === null) return [];
  return [row(key, label, field, render)];
}

function dateText(value: string): string { return value; }

const ASSIGNMENT_STATUS_LABELS: Readonly<Record<string, string>> = {
  planned: '已排定',
  active: '正式服務中',
  completed: '已完成',
  replaced: '已由替代人員接手',
  cancelled: '已取消',
};

function assignmentStatusText(value: string): string {
  return ASSIGNMENT_STATUS_LABELS[value] ?? '狀態待確認';
}

function assignmentRows(segment: OrdersCardAssignmentSegment, key: string): OrdersCardAssignmentViewModel {
  return {
    key,
    rows: [
      row(`${key}.assignment_id`, 'assignment_id', segment.assignment_id, String),
      row(`${key}.staff_id`, 'staff_id', segment.staff_id, String),
      row(`${key}.staff_name`, 'staff_name', segment.staff_name, String),
      row(`${key}.sequence`, 'sequence', segment.sequence, String),
      row(`${key}.assigned_start_date`, 'assigned_start_date', segment.assigned_start_date, dateText),
      row(`${key}.assigned_end_date`, 'assigned_end_date', segment.assigned_end_date, dateText),
      row(`${key}.status`, 'status', segment.status, assignmentStatusText),
    ],
  };
}

export function adaptOrdersCardProjection(projection: OrdersCardProjection, expectedCaseNo?: string): OrdersCardProjectionViewModel {
  if (expectedCaseNo !== undefined && projection.case_no !== expectedCaseNo) {
    throw new Error('Orders card projection 案件識別不一致。');
  }
  return {
    caseNo: projection.case_no,
    depositSettlementState: projection.deposit_settlement_state.availability === 'available'
      ? projection.deposit_settlement_state.value
      : null,
    rows: [
      row('contact_phone', '聯絡電話', projection.contact_phone, String),
      row('contact_address', '服務地址', projection.contact_address, String),
      row('requires_cooking', '下廚料理', projection.requires_cooking, (value) => value ? '是' : '否'),
      row('floor_fee_ntd', '樓層加給', projection.floor_fee_ntd, (value) => `NT$ ${value.toLocaleString('en-US')}`),
      row('deposit_amount_ntd', '定金金額', projection.deposit_amount_ntd, (value) => `NT$ ${value.toLocaleString('en-US')}`),
      row('deposit_settlement_state', '定金結清狀態', projection.deposit_settlement_state, String),
      row('deposit_settled_on', '定金結清日期', projection.deposit_settled_on, dateText),
      ...optionalHistoricalRow(
        'historical_source_start_date',
        '歷史匯入開始日',
        projection.historical_source_start_date,
        dateText,
      ),
      ...optionalHistoricalRow(
        'historical_source_end_date',
        '歷史匯入結束日',
        projection.historical_source_end_date,
        dateText,
      ),
      ...optionalHistoricalRow(
        'historical_paired_staff_name',
        '歷史匯入配對月嫂',
        projection.historical_paired_staff_name,
        String,
      ),
      row('actual_start_date', '已發生實際開始日', projection.actual_start_date, dateText),
      row('actual_end_date', '已發生實際結束日', projection.actual_end_date, dateText),
    ],
    assignmentSegments: projection.assignment_segments.value?.map((segment, index) => assignmentRows(segment, `assignment.${index}`)) ?? [],
    assignmentSegmentsAvailability: projection.assignment_segments.availability,
    assignmentSegmentsMessage: fieldValueText(
      projection.assignment_segments,
      '正式指派分段',
      (segments) => segments.length === 0 ? '目前尚無正式指派分段。' : `已載入 ${segments.length} 段正式指派。`,
    ),
  };
}
